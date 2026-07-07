"""
Delivery Service — Django Settings
Owns delivery lifecycle: create, track, scan, complete, cancel.
Publishes events: delivery.assigned, delivery.status_changed, delivery.completed.
Consumes events: (none currently — listens to its own queue for external triggers).
JWT auth is validated against the shared secret from gateway.
"""
from pathlib import Path
from datetime import timedelta
from decouple import config

BASE_DIR = Path(__file__).resolve().parent.parent

SECRET_KEY = config("SECRET_KEY")
DEBUG = config("DEBUG", default=False, cast=bool)
ALLOWED_HOSTS = config("ALLOWED_HOSTS", default="*").split(",")

INSTALLED_APPS = [
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
    # Third-party
    "rest_framework",
    "rest_framework_simplejwt",
    "corsheaders",
    "django_filters",
    "drf_spectacular",
    "cloudinary",
    "cloudinary_storage",
    # Local
    "apps.deliveries",
    "apps.vehicles",
    "apps.medicines",
]

MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    "corsheaders.middleware.CorsMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
]

ROOT_URLCONF = "pharmtrack_delivery.urls"

TEMPLATES = [{
    "BACKEND": "django.template.backends.django.DjangoTemplates",
    "DIRS": [],
    "APP_DIRS": True,
    "OPTIONS": {"context_processors": [
        "django.template.context_processors.request",
        "django.contrib.auth.context_processors.auth",
        "django.contrib.messages.context_processors.messages",
    ]},
}]

WSGI_APPLICATION = "pharmtrack_delivery.wsgi.application"

DATABASES = {
    "default": {
        "ENGINE": "django.db.backends.postgresql",
        "NAME": config("DB_NAME", default="delivery_db"),
        "USER": config("DB_USER", default="postgres"),
        "PASSWORD": config("DB_PASSWORD"),
        "HOST": config("DB_HOST", default="postgres_delivery"),
        "PORT": config("DB_PORT", default="5432"),
        "CONN_MAX_AGE": 60,
    }
}

# JWT — validate tokens issued by gateway (shared HS256 secret)
SIMPLE_JWT = {
    "ACCESS_TOKEN_LIFETIME": timedelta(hours=24),
    "ALGORITHM": "HS256",
    "SIGNING_KEY": config("JWT_SECRET_KEY"),
    "AUTH_HEADER_TYPES": ("Bearer",),
}

REST_FRAMEWORK = {
    "DEFAULT_AUTHENTICATION_CLASSES": (
        "utils.auth.MicroserviceJWTAuthentication",
    ),
    "DEFAULT_PERMISSION_CLASSES": ("rest_framework.permissions.IsAuthenticated",),
    "DEFAULT_FILTER_BACKENDS": [
        "django_filters.rest_framework.DjangoFilterBackend",
        "rest_framework.filters.SearchFilter",
        "rest_framework.filters.OrderingFilter",
    ],
    "DEFAULT_PAGINATION_CLASS": "rest_framework.pagination.PageNumberPagination",
    "PAGE_SIZE": 10,
    "DEFAULT_SCHEMA_CLASS": "drf_spectacular.openapi.AutoSchema",
}

CORS_ALLOW_ALL_ORIGINS = True

CLOUDINARY_STORAGE = {
    "CLOUD_NAME": config("CLOUD_NAME", default=""),
    "API_KEY": config("CLOUD_API_KEY", default=""),
    "API_SECRET": config("CLOUD_API_SECRET", default=""),
}

CLOUDINARY = {
    "cloud_name": config("CLOUD_NAME", default=""),
    "api_key": config("CLOUD_API_KEY", default=""),
    "api_secret": config("CLOUD_API_SECRET", default=""),
}

DEFAULT_FILE_STORAGE = "cloudinary_storage.storage.MediaCloudinaryStorage"

QR_SECRET_KEY = config("QR_SECRET_KEY", default="default-qr-secret")
RABBITMQ_URL = config("RABBITMQ_URL")
GATEWAY_INTERNAL_URL = config("GATEWAY_INTERNAL_URL", default="http://gateway:8000")

SPECTACULAR_SETTINGS = {
    "TITLE": "PharmTrack Delivery Service API",
    "VERSION": "1.0.0",
}

STATIC_URL = "/static/"
STATIC_ROOT = BASE_DIR / "staticfiles"
DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"
LANGUAGE_CODE = "en-us"
TIME_ZONE = "UTC"
USE_I18N = True
USE_TZ = True
