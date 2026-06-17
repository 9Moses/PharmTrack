from pathlib import Path
from datetime import timedelta
from decouple import config

BASE_DIR = Path(__file__).resolve().parent.parent

SECRET_KEY = config("SECRET_KEY")
DEBUG = config("DEBUG", default=False, cast=bool)
ALLOWED_HOSTS = config("ALLOWED_HOSTS", default="*").split(",")

DJANGO_APPS = [
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
]

THIRD_PARTY_APPS = [
    "rest_framework",
    "rest_framework_simplejwt",
    "rest_framework_simplejwt.token_blacklist",
    "corsheaders",
    "django_filters",
    "drf_spectacular",
    "cloudinary",
    "cloudinary_storage",
]

LOCAL_APPS = [
    "apps.users",
    "apps.authentication",
    "apps.medicines",
    "apps.vehicles",
    "apps.audit",
]

INSTALLED_APPS = DJANGO_APPS + THIRD_PARTY_APPS + LOCAL_APPS

MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    # Rate-limit headers (X-RateLimit-*) — must be early so it wraps all responses
    "utils.middleware.RateLimitHeadersMiddleware",
    "corsheaders.middleware.CorsMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
]

ROOT_URLCONF = "pharmtrack_gateway.urls"

TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "DIRS": [],
        "APP_DIRS": True,
        "OPTIONS": {
            "context_processors": [
                "django.template.context_processors.debug",
                "django.template.context_processors.request",
                "django.contrib.auth.context_processors.auth",
                "django.contrib.messages.context_processors.messages",
            ],
        },
    },
]

WSGI_APPLICATION = "pharmtrack_gateway.wsgi.application"

DATABASES = {
    "default": {
        "ENGINE": "django.db.backends.postgresql",
        "NAME": config("DB_NAME", default="gateway_db"),
        "USER": config("DB_USER", default="postgres"),
        "PASSWORD": config("DB_PASSWORD"),
        "HOST": config("DB_HOST", default="postgres_gateway"),
        "PORT": config("DB_PORT", default="5432"),
        "CONN_MAX_AGE": 60,
    }
}

AUTH_USER_MODEL = "users.User"

# Redis cache — OTP storage
CACHES = {
    "default": {
        "BACKEND": "django_redis.cache.RedisCache",
        "LOCATION": config("REDIS_URL", default="redis://redis:6379/0"),
        "OPTIONS": {
            "CLIENT_CLASS": "django_redis.client.DefaultClient",
            "SOCKET_CONNECT_TIMEOUT": 5,
            "SOCKET_TIMEOUT": 5,
        },
    }
}

# JWT
SIMPLE_JWT = {
    "ACCESS_TOKEN_LIFETIME": timedelta(hours=config("JWT_ACCESS_LIFETIME_HOURS", default=24, cast=int)),
    "REFRESH_TOKEN_LIFETIME": timedelta(days=config("JWT_REFRESH_LIFETIME_DAYS", default=7, cast=int)),
    "ROTATE_REFRESH_TOKENS": True,
    "BLACKLIST_AFTER_ROTATION": True,
    "AUTH_HEADER_TYPES": ("Bearer",),
}

REST_FRAMEWORK = {
    "DEFAULT_AUTHENTICATION_CLASSES": (
        "rest_framework_simplejwt.authentication.JWTAuthentication",
    ),
    "DEFAULT_PERMISSION_CLASSES": (
        "rest_framework.permissions.IsAuthenticated",
    ),
    "DEFAULT_FILTER_BACKENDS": [
        "django_filters.rest_framework.DjangoFilterBackend",
        "rest_framework.filters.SearchFilter",
        "rest_framework.filters.OrderingFilter",
    ],
    "DEFAULT_PAGINATION_CLASS": "rest_framework.pagination.PageNumberPagination",
    "PAGE_SIZE": 10,
    "DEFAULT_SCHEMA_CLASS": "drf_spectacular.openapi.AutoSchema",
    "EXCEPTION_HANDLER": "utils.error.custom_exception_handler",
    # ── Distributed rate limiting (Redis sliding window) ──────────────────
    # Global defaults applied to every view.  Sensitive endpoints (OTP,
    # write mutations) override throttle_classes on the view itself.
    "DEFAULT_THROTTLE_CLASSES": [
        "utils.throttling.GlobalAnonThrottle",   # 100/hr — unauthenticated IPs
        "utils.throttling.GlobalUserThrottle",   # 1000–2000/hr — per role
        "utils.throttling.BurstThrottle",        # 30/min  — spike protection
    ],
    # Legacy DRF scoped-throttle rates kept for backward compatibility.
    # Custom rates are driven by RATE_LIMIT_RATES below.
    "DEFAULT_THROTTLE_RATES": {
        "anon": "100/hour",
        "user": "1000/hour",
        "otp": "5/minute",       # legacy — superseded by otp_request/otp_verify
        "otp_request": "5/minute",
        "otp_verify": "5/minute",
        "write": "200/hour",
        "burst": "30/minute",
    },
}

# CORS
CORS_ALLOW_ALL_ORIGINS = config("CORS_ALLOW_ALL", default=False, cast=bool)
_origins = config("CORS_ALLOWED_ORIGINS", default="")
CORS_ALLOWED_ORIGINS = [o.strip() for o in _origins.split(",") if o.strip()]

# Cloudinary
CLOUDINARY_STORAGE = {
    "CLOUD_NAME": config("CLOUD_NAME", default=""),
    "API_KEY": config("CLOUD_API_KEY", default=""),
    "API_SECRET": config("CLOUD_API_SECRET", default=""),
}
DEFAULT_FILE_STORAGE = "cloudinary_storage.storage.MediaCloudinaryStorage"

# QR Encryption
QR_SECRET_KEY = config("QR_SECRET_KEY", default="default-qr-secret")

# ── Distributed Rate Limiting ────────────────────────────────────────────────
# Single source of truth consumed by utils/throttling.py.
# All values follow the "<count>/<period>" format.
RATE_LIMIT_RATES: dict = {
    # Global scopes
    "anon":        config("RATE_LIMIT_ANON",        default="100/hour"),
    "user":        config("RATE_LIMIT_USER",        default="1000/hour"),
    "burst":       config("RATE_LIMIT_BURST",       default="30/minute"),
    # Auth endpoint scopes
    "otp_request": config("RATE_LIMIT_OTP_REQUEST", default="5/minute"),
    "otp_verify":  config("RATE_LIMIT_OTP_VERIFY",  default="5/minute"),
    # Write-mutation scope
    "write":       config("RATE_LIMIT_WRITE",       default="200/hour"),
}

# OTP brute-force lockout policy
# After THRESHOLD bad codes from the same IP within LOCKOUT_SECONDS the IP
# is blocked from /auth/verify-otp/ for LOCKOUT_SECONDS.
RATE_LIMIT_OTP_LOCKOUT_THRESHOLD: int = config(
    "RATE_LIMIT_OTP_LOCKOUT_THRESHOLD", default=5, cast=int
)
RATE_LIMIT_OTP_LOCKOUT_SECONDS: int = config(
    "RATE_LIMIT_OTP_LOCKOUT_SECONDS", default=900, cast=int  # 15 minutes
)

# RabbitMQ
RABBITMQ_URL = config("RABBITMQ_URL")

# API Docs
SPECTACULAR_SETTINGS = {
    "TITLE": "PharmTrack Gateway API",
    "DESCRIPTION": "Auth, Users, Medicines & Vehicles — Gateway Service",
    "VERSION": "1.0.0",
}

STATIC_URL = "/static/"
STATIC_ROOT = BASE_DIR / "staticfiles"
DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"

AUTH_PASSWORD_VALIDATORS = [
    {"NAME": "django.contrib.auth.password_validation.UserAttributeSimilarityValidator"},
    {"NAME": "django.contrib.auth.password_validation.MinimumLengthValidator"},
]

LANGUAGE_CODE = "en-us"
TIME_ZONE = "UTC"
USE_I18N = True
USE_TZ = True
