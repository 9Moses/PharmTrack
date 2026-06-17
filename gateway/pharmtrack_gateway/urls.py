from django.contrib import admin
from django.urls import path, include
from drf_spectacular.views import SpectacularAPIView, SpectacularSwaggerView, SpectacularRedocView
from . import healthz

urlpatterns = [
    path("admin/", admin.site.urls),

    path("healthz/", healthz, name="healthz"),

    # Auth & user management
    path("auth/", include("apps.authentication.urls")),
    path("users/", include("apps.users.urls")),
    path("medicines/", include("apps.medicines.urls")),
    path("vehicles/", include("apps.vehicles.urls")),

    # API Docs
    path("api/schema/", SpectacularAPIView.as_view(), name="schema"),
    path("api/docs/", SpectacularSwaggerView.as_view(url_name="schema"), name="swagger-ui"),
    path("api/redoc/", SpectacularRedocView.as_view(url_name="schema"), name="redoc"),
]
