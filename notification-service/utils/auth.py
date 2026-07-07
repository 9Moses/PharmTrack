from rest_framework_simplejwt.authentication import JWTAuthentication
from rest_framework_simplejwt.exceptions import InvalidToken
from django.utils.translation import gettext_lazy as _


class GatewayUser:
    """
    A stateless representation of the REAL user authenticated via the Gateway's JWT.
    This is NOT dummy data. It extracts the cryptographically verified user_id
    from the token payload. We use this because 'notification-service' has its own
    isolated database and does not contain the 'users' table (which lives in Gateway).
    """
    def __init__(self, id):
        self.id = id
        self.is_authenticated = True
        self.is_active = True

    def __str__(self):
        return str(self.id)


class MicroserviceJWTAuthentication(JWTAuthentication):
    """
    Extracts the user_id from the verified token and attaches it to request.user.
    Does NOT query the database for a User object.
    """
    def get_user(self, validated_token):
        try:
            user_id = validated_token["user_id"]
        except KeyError:
            raise InvalidToken(_("Token contained no recognizable user identification"))

        return GatewayUser(id=user_id)


# Extension for drf-spectacular so the "Authorize" button still appears in Swagger UI
try:
    from drf_spectacular.extensions import OpenApiAuthenticationExtension

    class MicroserviceJWTScheme(OpenApiAuthenticationExtension):
        target_class = "utils.auth.MicroserviceJWTAuthentication"
        name = "jwtAuth"

        def get_security_definition(self, auto_schema):
            return {
                "type": "http",
                "scheme": "bearer",
                "bearerFormat": "JWT",
            }
except ImportError:
    pass
