"""
Authentication views — OTP-based login.
After successful login, publishes a `user.logged_in` event to RabbitMQ
so notification-service can send a welcome/session notification.
"""

import random
import logging

from django.utils import timezone
from django.core.cache import cache
from rest_framework import status
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated, AllowAny
from rest_framework_simplejwt.tokens import RefreshToken

from apps.users.models import User
from apps.users.serializers import UserSerializer
from apps.audit.models import AuditLog, AuditAction
from utils.publisher import publish_event
from utils.throttling import OTPRequestThrottle, OTPVerifyThrottle, record_otp_failure, clear_otp_failure
from utils.error import ErrorHandler

logger = logging.getLogger(__name__)


def _generate_otp() -> str:
    return str(random.randint(100000, 999999))


class RequestOTPView(APIView):
    """
    POST /auth/request-otp
    Stores a 6-digit OTP in Redis (5 min TTL) and publishes an
    `otp.requested` event so the email-service sends the OTP email.
    """
    permission_classes = [AllowAny]
    throttle_classes = [OTPRequestThrottle]  # 5/min per IP, sliding window

    def post(self, request):
        email = request.data.get("email", "").strip().lower()
        try:
            if not email:
                return Response({"message": "Email is required"}, status=status.HTTP_400_BAD_REQUEST)

            user = User.objects.filter(email__iexact=email).first()
            if not user:
                return Response({"message": "Email not registered"}, status=status.HTTP_404_NOT_FOUND)

            if not user.is_active:
                return Response({"message": "Account is inactive"}, status=status.HTTP_403_FORBIDDEN)

            otp = _generate_otp()
            cache.set(f"otp:{email}", otp, timeout=300)

            # Publish to email-service via RabbitMQ
            publish_event(
                exchange="pharmtrack.auth",
                routing_key="otp.requested",
                payload={
                    "event": "otp.requested",
                    "email": email,
                    "name": user.name,
                    "otp": otp,
                },
            )

            return Response({
                "message": "OTP sent successfully",
                "userType": user.role,
            })
        except Exception as exc:
            return ErrorHandler.handle(exc, "Failed to send OTP")


class VerifyOTPView(APIView):
    """
    POST /auth/verify-otp
    Validates OTP, issues JWT, publishes `user.logged_in` event.
    Wrong OTP increments brute-force counter (lockout after 5 failures / 15 min).
    """
    permission_classes = [AllowAny]
    throttle_classes = [OTPVerifyThrottle]  # 5/min per IP + lockout check

    def post(self, request):
        email = request.data.get("email", "").strip().lower()
        otp = request.data.get("otp", "").strip()

        try:
            if not email or not otp:
                return Response({"message": "Email and OTP are required"}, status=status.HTTP_400_BAD_REQUEST)

            # Resolve client IP for lockout tracking
            x_forwarded = request.META.get("HTTP_X_FORWARDED_FOR", "")
            client_ip = x_forwarded.split(",")[0].strip() if x_forwarded else request.META.get("REMOTE_ADDR", "unknown")

            stored_otp = cache.get(f"otp:{email}")
            if not stored_otp or stored_otp != otp:
                record_otp_failure(client_ip)  # increment brute-force counter
                return Response({"message": "Invalid or expired OTP"}, status=status.HTTP_400_BAD_REQUEST)

            user = User.objects.filter(email__iexact=email).first()
            if not user:
                return Response({"message": "User not found"}, status=status.HTTP_404_NOT_FOUND)

            if user.role not in ("admin", "superadmin"):
                return Response({"message": "Role not authorised"}, status=status.HTTP_403_FORBIDDEN)

            # Issue JWT
            refresh = RefreshToken.for_user(user)
            refresh["role"] = user.role
            refresh["email"] = user.email
            if user.role == "admin":
                refresh["department"] = user.department
            else:
                refresh["hasGlobalAccess"] = user.has_global_access

            user.last_login = timezone.now()
            user.save(update_fields=["last_login"])
            cache.delete(f"otp:{email}")
            clear_otp_failure(client_ip)  # successful login — reset failure counter

            AuditLog.log_action(user.id, AuditAction.LOGIN, request)

            # Notify downstream services
            publish_event(
                exchange="pharmtrack.auth",
                routing_key="user.logged_in",
                payload={
                    "event": "user.logged_in",
                    "user_id": str(user.id),
                    "email": user.email,
                    "name": user.name,
                    "role": user.role,
                },
            )

            return Response({
                "token": str(refresh.access_token),
                "refresh": str(refresh),
                "user": UserSerializer(user).data,
            })
        except Exception as exc:
            return ErrorHandler.handle(exc, "Invalid OTP")


class LogoutView(APIView):
    """POST /auth/logout — Blacklist refresh token."""
    permission_classes = [IsAuthenticated]

    def post(self, request):
        try:
            refresh_token = request.data.get("refresh")
            if refresh_token:
                RefreshToken(refresh_token).blacklist()
            AuditLog.log_action(request.user.id, AuditAction.LOGOUT, request)
            return Response({"message": "Logout successful"})
        except Exception as exc:
            logger.error("Logout error: %s", exc)
            return Response({"message": "Logout failed"}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)
