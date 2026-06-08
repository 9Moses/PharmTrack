"""
utils/throttling.py — PharmTrack Gateway
=========================================
Distributed rate limiting via Redis sorted-set sliding window.

Algorithm
---------
For every request an atomic Lua script:
  1. ZREMRANGEBYSCORE — evicts timestamps older than (now - window)
  2. ZCARD            — counts requests still inside the window
  3. If count < limit : ZADD + EXPIRE → allowed
     Else             : return blocked (no write)

Why Lua?  A single server-side script is executed atomically by Redis,
so concurrent Gunicorn workers never race on the same key.

All throttle classes populate ``request._rate_limit_info`` so that
``RateLimitHeadersMiddleware`` can attach X-RateLimit-* headers without
any extra Redis round-trips.

Fail-open policy
----------------
If Redis is unreachable the throttle logs an ERROR and *allows* the
request — preserving service availability over strict enforcement.
"""

import time
import uuid
import logging

from django_redis import get_redis_connection
from rest_framework.throttling import BaseThrottle
from django.conf import settings

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Atomic Lua sliding-window script
# KEYS[1]  — Redis key (sorted set)
# ARGV[1]  — current time in milliseconds (integer)
# ARGV[2]  — window size in milliseconds (integer)
# ARGV[3]  — request limit (integer)
# ARGV[4]  — unique member id for this request (string)
#
# Returns: {allowed, current_count, window_ms}
#   allowed       → 1 = permit, 0 = reject
#   current_count → number of requests in window *after* this one (or at limit)
#   window_ms     → echoed back for convenience
# ---------------------------------------------------------------------------
_SLIDING_WINDOW_LUA = """
local key         = KEYS[1]
local now         = tonumber(ARGV[1])
local window      = tonumber(ARGV[2])
local limit       = tonumber(ARGV[3])
local unique_id   = ARGV[4]
local window_start = now - window

-- Evict entries that have fallen outside the sliding window
redis.call('ZREMRANGEBYSCORE', key, '-inf', window_start)

-- Count what remains
local count = redis.call('ZCARD', key)

if count < limit then
    -- Admit: record this request with its timestamp as score
    redis.call('ZADD', key, now, unique_id)
    -- TTL slightly > window so Redis can GC the key automatically
    redis.call('PEXPIRE', key, window + 1000)
    return {1, count + 1, window}
else
    -- Reject without writing (prevents inflating the counter)
    return {0, count, window}
end
"""

# Map human-readable period suffixes → seconds
_PERIOD_SECONDS: dict[str, int] = {
    "s": 1, "sec": 1, "second": 1, "seconds": 1,
    "m": 60, "min": 60, "minute": 60, "minutes": 60,
    "h": 3600, "hr": 3600, "hour": 3600, "hours": 3600,
    "d": 86400, "day": 86400, "days": 86400,
}


# ---------------------------------------------------------------------------
# Base throttle
# ---------------------------------------------------------------------------

class RedisSlidingWindowThrottle(BaseThrottle):
    """
    Abstract base for all PharmTrack rate limiters.

    Subclasses must set:
      scope (str)  — logical name, used for Redis key prefix & settings lookup
      rate  (str)  — "count/period" e.g. "100/hour" (can be omitted to read
                     from ``settings.RATE_LIMIT_RATES[scope]``)
    """

    scope: str = "default"
    rate: str | None = None

    def __init__(self) -> None:
        self._redis = None          # lazily resolved
        self.num_requests, self.duration = self._parse_rate(
            self.rate or self._get_rate_from_settings()
        )

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def _get_rate_from_settings(self) -> str:
        rates: dict = getattr(settings, "RATE_LIMIT_RATES", {})
        return rates.get(self.scope, "100/hour")

    @staticmethod
    def _parse_rate(rate: str) -> tuple[int, int]:
        """Parse "count/period" → (count: int, seconds: int)."""
        try:
            count_str, period_str = rate.split("/", 1)
            period_str = period_str.strip().lower()
            return int(count_str), _PERIOD_SECONDS[period_str]
        except (ValueError, KeyError) as exc:
            raise ValueError(
                f"Invalid rate string '{rate}'. "
                f"Expected format: '<count>/<period>' e.g. '100/hour'."
            ) from exc

    def _get_redis(self):
        """Return a raw redis.Redis client (not the Django cache wrapper)."""
        if self._redis is None:
            self._redis = get_redis_connection("default")
        return self._redis

    # ------------------------------------------------------------------
    # Key strategy — override in subclasses for custom keying
    # ------------------------------------------------------------------

    def get_cache_key(self, request, view) -> str | None:
        """
        Return the Redis key for this request, or ``None`` to skip throttling.
        By default keys by user-id (authenticated) or IP (anonymous).
        """
        if request.user and request.user.is_authenticated:
            ident = str(request.user.id)
        else:
            ident = self.get_ident(request)
        return f"rl:{self.scope}:{ident}"

    # ------------------------------------------------------------------
    # Core allow/deny logic
    # ------------------------------------------------------------------

    def allow_request(self, request, view) -> bool:
        key = self.get_cache_key(request, view)
        if key is None:
            # This throttle intentionally skips this request
            return True

        now_ms = int(time.time() * 1000)
        window_ms = self.duration * 1000
        unique_id = str(uuid.uuid4())

        try:
            r = self._get_redis()
            result = r.eval(
                _SLIDING_WINDOW_LUA,
                1,          # number of KEYS
                key,        # KEYS[1]
                now_ms,     # ARGV[1]
                window_ms,  # ARGV[2]
                self.num_requests,  # ARGV[3]
                unique_id,  # ARGV[4]
            )
            allowed, current_count, _ = result

            remaining = max(0, self.num_requests - int(current_count))
            # Reset = start of next window (aligned to clock boundary)
            now_s = int(time.time())
            reset_at = now_s + (self.duration - (now_s % self.duration))

            self._store_rate_limit_info(request, remaining, reset_at)

            if not allowed:
                logger.warning(
                    "RATE_LIMIT_EXCEEDED scope=%s key=%s count=%d limit=%d",
                    self.scope, key, current_count, self.num_requests,
                )
            return bool(allowed)

        except Exception as exc:  # noqa: BLE001
            # Fail-open: Redis errors should not take down the API
            logger.error(
                "Rate limiter error (fail-open) scope=%s: %s", self.scope, exc
            )
            return True

    def _store_rate_limit_info(
        self, request, remaining: int, reset_at: int
    ) -> None:
        """
        Attach rate-limit metadata to the request so middleware can set headers.
        Multiple throttles may run; we keep info from all active scopes.
        """
        if not hasattr(request, "_rate_limit_info"):
            request._rate_limit_info = {}
        request._rate_limit_info[self.scope] = {
            "limit": self.num_requests,
            "remaining": remaining,
            "reset": reset_at,
            "scope": self.scope,
        }

    def wait(self) -> float:
        """
        Seconds the client should wait before retrying (used by DRF to set
        the ``Retry-After`` header on 429 responses).

        Uses the average inter-request interval as a conservative estimate.
        """
        return float(self.duration) / float(self.num_requests)


# ---------------------------------------------------------------------------
# Concrete throttle classes
# ---------------------------------------------------------------------------

class GlobalAnonThrottle(RedisSlidingWindowThrottle):
    """
    100 requests / hour for every unauthenticated IP address.
    Authenticated requests are intentionally skipped here and handled
    by ``GlobalUserThrottle``.
    """

    scope = "anon"
    rate = "100/hour"

    def get_cache_key(self, request, view) -> str | None:
        if request.user and request.user.is_authenticated:
            return None  # Delegate to GlobalUserThrottle
        return f"rl:anon:{self.get_ident(request)}"


class GlobalUserThrottle(RedisSlidingWindowThrottle):
    """
    Role-aware per-user hourly throttle:
      superadmin → 2 000 req / hour
      admin      → 1 000 req / hour

    Anonymous requests are skipped here — handled by ``GlobalAnonThrottle``.
    """

    scope = "user"

    # Defaults; overridden per-request based on role
    _ROLE_RATES: dict[str, tuple[int, int]] = {
        "superadmin": (2000, 3600),
        "admin": (1000, 3600),
    }
    _DEFAULT_RATE: tuple[int, int] = (1000, 3600)

    def __init__(self) -> None:
        self._redis = None
        self.num_requests, self.duration = self._DEFAULT_RATE

    def get_cache_key(self, request, view) -> str | None:
        if not (request.user and request.user.is_authenticated):
            return None  # Delegate to GlobalAnonThrottle
        return f"rl:user:{request.user.id}"

    def allow_request(self, request, view) -> bool:
        if request.user and request.user.is_authenticated:
            role = getattr(request.user, "role", "admin")
            self.num_requests, self.duration = self._ROLE_RATES.get(
                role, self._DEFAULT_RATE
            )
        return super().allow_request(request, view)


class BurstThrottle(RedisSlidingWindowThrottle):
    """
    30 requests / minute hard cap — protects against sudden traffic spikes
    regardless of hourly quota.  Applied to all requests (authenticated
    and anonymous).
    """

    scope = "burst"
    rate = "30/minute"

    def get_cache_key(self, request, view) -> str | None:
        if request.user and request.user.is_authenticated:
            return f"rl:burst:{request.user.id}"
        return f"rl:burst_anon:{self.get_ident(request)}"


class OTPRequestThrottle(RedisSlidingWindowThrottle):
    """
    5 OTP request emails / minute, keyed by client IP.

    Applied exclusively on ``POST /auth/request-otp/``.
    Replaces the legacy ``ScopedRateThrottle(scope='otp')``.
    """

    scope = "otp_request"
    rate = "5/minute"

    def get_cache_key(self, request, view) -> str:
        return f"rl:otp_req:{self.get_ident(request)}"


class OTPVerifyThrottle(RedisSlidingWindowThrottle):
    """
    5 OTP verification attempts / minute per IP.

    Additionally enforces a **lockout** when too many wrong codes have been
    submitted recently.  The lockout key is written by ``record_otp_failure()``
    (called from the view on every wrong OTP) and checked here *before* the
    sliding-window test so that locked-out IPs are rejected immediately even
    if they are within the per-minute rate.
    """

    scope = "otp_verify"
    rate = "5/minute"

    def get_cache_key(self, request, view) -> str:
        return f"rl:otp_ver:{self.get_ident(request)}"

    def allow_request(self, request, view) -> bool:
        ip = self.get_ident(request)
        lockout_key = f"rl:otp_lockout:{ip}"
        try:
            r = self._get_redis()
            if r.exists(lockout_key):
                ttl = r.pttl(lockout_key)  # ms remaining
                reset_at = int(time.time()) + max(1, ttl // 1000)
                self._store_rate_limit_info(request, 0, reset_at)
                logger.warning(
                    "OTP_LOCKOUT_ACTIVE ip=%s ttl_ms=%d", ip, ttl
                )
                return False
        except Exception as exc:  # noqa: BLE001
            logger.error("OTP lockout check failed (fail-open): %s", exc)

        return super().allow_request(request, view)


class WriteThrottle(RedisSlidingWindowThrottle):
    """
    200 write operations (POST / PATCH / PUT / DELETE) / hour per user.

    GET, HEAD and OPTIONS requests are transparently skipped (key = None)
    so read-heavy clients are not penalised by this throttle.
    """

    scope = "write"
    rate = "200/hour"

    def get_cache_key(self, request, view) -> str | None:
        if request.method in {"GET", "HEAD", "OPTIONS"}:
            return None  # read-only — skip
        if request.user and request.user.is_authenticated:
            return f"rl:write:{request.user.id}"
        return f"rl:write_anon:{self.get_ident(request)}"


# ---------------------------------------------------------------------------
# OTP failure / lockout helpers (called from authentication views)
# ---------------------------------------------------------------------------

_OTP_FAIL_KEY = "rl:otp_fail:{ip}"
_OTP_LOCKOUT_KEY = "rl:otp_lockout:{ip}"


def record_otp_failure(ip: str) -> int:
    """
    Increment the OTP failure counter for *ip*.

    When the counter reaches ``settings.RATE_LIMIT_OTP_LOCKOUT_THRESHOLD``
    (default 5) a lockout key is set with a TTL of
    ``settings.RATE_LIMIT_OTP_LOCKOUT_SECONDS`` (default 900 = 15 min).

    Returns the updated failure count, or 0 if Redis is unavailable.
    """
    threshold: int = getattr(settings, "RATE_LIMIT_OTP_LOCKOUT_THRESHOLD", 5)
    lockout_s: int = getattr(settings, "RATE_LIMIT_OTP_LOCKOUT_SECONDS", 900)

    try:
        r = get_redis_connection("default")
        fail_key = _OTP_FAIL_KEY.format(ip=ip)
        count = r.incr(fail_key)
        # Keep the failure counter alive for at least the lockout window
        r.expire(fail_key, lockout_s)

        if count >= threshold:
            lockout_key = _OTP_LOCKOUT_KEY.format(ip=ip)
            r.set(lockout_key, 1, ex=lockout_s)
            logger.warning(
                "OTP_LOCKOUT_SET ip=%s failures=%d lockout_seconds=%d",
                ip, count, lockout_s,
            )
        return count
    except Exception as exc:  # noqa: BLE001
        logger.error("record_otp_failure failed: %s", exc)
        return 0


def clear_otp_failure(ip: str) -> None:
    """
    Clear the OTP failure counter and any active lockout for *ip*.

    Should be called after a *successful* OTP verification so that a
    legitimate user who mistyped their code once is not permanently
    penalised.
    """
    try:
        r = get_redis_connection("default")
        r.delete(
            _OTP_FAIL_KEY.format(ip=ip),
            _OTP_LOCKOUT_KEY.format(ip=ip),
        )
    except Exception as exc:  # noqa: BLE001
        logger.error("clear_otp_failure failed: %s", exc)
