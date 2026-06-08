"""
utils/middleware.py — PharmTrack Gateway
=========================================
``RateLimitHeadersMiddleware``

Reads rate-limit metadata stored on ``request._rate_limit_info`` by the
custom throttle classes and injects standardised ``X-RateLimit-*`` headers
into **every** API response — including successful ones so clients can
track their remaining quota and implement proactive back-off.

Header contract
---------------
X-RateLimit-Limit      — total requests allowed in the current window
X-RateLimit-Remaining  — requests remaining (based on most-restrictive scope)
X-RateLimit-Reset      — Unix timestamp (UTC) when the window resets
X-RateLimit-Scope      — name of the throttle scope that is most restrictive

When multiple throttle scopes are active the values reported are from the
scope with the *fewest remaining requests* (worst case for the client).

Logging
-------
Every HTTP 429 response is logged at WARNING level with:
  path, method, user_id (or "anon"), client IP.
This feeds into any structured log aggregator (CloudWatch, Datadog, etc.)
without requiring a separate alerting hook.
"""

import logging

logger = logging.getLogger(__name__)


class RateLimitHeadersMiddleware:
    """
    WSGI-compatible middleware that enriches responses with rate-limit headers.

    Position in MIDDLEWARE
    ----------------------
    Insert *after* ``SecurityMiddleware`` (so security headers are set first)
    and *before* ``CorsMiddleware`` (so CORS headers are not overwritten):

        MIDDLEWARE = [
            "django.middleware.security.SecurityMiddleware",
            "utils.middleware.RateLimitHeadersMiddleware",   # ← here
            "corsheaders.middleware.CorsMiddleware",
            ...
        ]
    """

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        response = self.get_response(request)
        self._inject_rate_limit_headers(request, response)
        self._log_if_throttled(request, response)
        return response

    # ------------------------------------------------------------------
    # Header injection
    # ------------------------------------------------------------------

    def _inject_rate_limit_headers(self, request, response) -> None:
        """
        Attach X-RateLimit-* headers derived from ``request._rate_limit_info``.
        Does nothing if no throttle populated the dict (e.g. admin/ or docs/).
        """
        info: dict = getattr(request, "_rate_limit_info", {})
        if not info:
            return

        # Pick the scope the client is closest to exhausting
        most_restrictive = min(info.values(), key=lambda x: x["remaining"])

        response["X-RateLimit-Limit"] = str(most_restrictive["limit"])
        response["X-RateLimit-Remaining"] = str(most_restrictive["remaining"])
        response["X-RateLimit-Reset"] = str(most_restrictive["reset"])
        response["X-RateLimit-Scope"] = most_restrictive["scope"]

    # ------------------------------------------------------------------
    # Violation logging
    # ------------------------------------------------------------------

    def _log_if_throttled(self, request, response) -> None:
        """Log a structured WARNING for every HTTP 429 response."""
        if response.status_code != 429:
            return

        user = getattr(request, "user", None)
        if user and user.is_authenticated:
            user_id = str(getattr(user, "id", "unknown"))
            role = getattr(user, "role", "unknown")
        else:
            user_id = "anon"
            role = "anon"

        # Respect X-Forwarded-For from a reverse-proxy / load-balancer
        forwarded_for = request.META.get("HTTP_X_FORWARDED_FOR", "")
        ip = (
            forwarded_for.split(",")[0].strip()
            if forwarded_for
            else request.META.get("REMOTE_ADDR", "unknown")
        )

        logger.warning(
            "RATE_LIMIT_EXCEEDED | path=%s method=%s user_id=%s role=%s ip=%s",
            request.path,
            request.method,
            user_id,
            role,
            ip,
        )
