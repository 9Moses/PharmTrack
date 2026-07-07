"""
Delivery Service Views
Handles the full delivery lifecycle and publishes RabbitMQ events:
  delivery.assigned          → notification-service, email-service
  delivery.status_changed    → notification-service
  delivery.completed         → notification-service, email-service
  delivery.cancelled         → notification-service
  delivery.customer_confirmed → notification-service
"""
import qrcode
import cloudinary.uploader
from io import BytesIO
from decimal import Decimal

from django.db import transaction, DatabaseError
from django.utils import timezone
from django.http import Http404
from rest_framework import generics, status
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated, AllowAny
from drf_spectacular.utils import extend_schema, OpenApiResponse

from .models import Delivery, DeliveryItem
from .serializers import (
    DeliverySerializer,
    AssignDeliverySerializer,
    UpdateStatusSerializer,
    ScanQRRequestSerializer,
    ScanQRResponseSerializer,
)
from events.publisher import publish_delivery_event
from utils.qr_crypto import encrypt_qr_data, decrypt_qr_data
from utils.stock_client import validate_and_fetch_stock, InsufficientStockError, StockClientError

import logging
logger = logging.getLogger(__name__)


def _upload_qr(qr_bytes: bytes, delivery_id: str) -> str:
    result = cloudinary.uploader.upload(
        qr_bytes,
        folder="deliveries/qr_codes",
        public_id=f"delivery_{delivery_id}",
        resource_type="image",
    )
    return result["secure_url"]


# ─────────────────────────────────────────────────────────────────────────────
# List & Detail
# ─────────────────────────────────────────────────────────────────────────────

class DeliveryListView(generics.ListAPIView):
    """GET /deliveries/ — List all deliveries."""
    queryset = Delivery.objects.all()
    serializer_class = DeliverySerializer
    permission_classes = [IsAuthenticated]

    @extend_schema(
        operation_id="deliveries_list",
        summary="List all deliveries",
        responses={
            200: DeliverySerializer(many=True),
            503: OpenApiResponse(description="Database unavailable"),
            500: OpenApiResponse(description="Unexpected server error"),
        },
    )
    def get(self, request, *args, **kwargs):
        try:
            return super().get(request, *args, **kwargs)
        except DatabaseError as exc:
            logger.error("[DeliveryListView] DB error: %s", exc, exc_info=True)
            return Response(
                {"message": "Service temporarily unavailable. Please try again later."},
                status=status.HTTP_503_SERVICE_UNAVAILABLE,
            )
        except Exception as exc:
            logger.exception("[DeliveryListView] Unexpected error: %s", exc)
            return Response(
                {"message": "An unexpected error occurred while fetching deliveries."},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )


class DeliveryDetailView(generics.RetrieveAPIView):
    """GET /deliveries/<pk>/ — Retrieve a single delivery."""
    queryset = Delivery.objects.all()
    serializer_class = DeliverySerializer
    permission_classes = [IsAuthenticated]

    @extend_schema(
        operation_id="deliveries_retrieve",
        summary="Retrieve a delivery by ID",
        responses={
            200: DeliverySerializer,
            404: OpenApiResponse(description="Delivery not found"),
            503: OpenApiResponse(description="Database unavailable"),
            500: OpenApiResponse(description="Unexpected server error"),
        },
    )
    def get(self, request, *args, **kwargs):
        try:
            return super().get(request, *args, **kwargs)
        except (Delivery.DoesNotExist, Http404):
            logger.warning("[DeliveryDetailView] Delivery not found: pk=%s", kwargs.get('pk'))
            return Response(
                {"message": "Delivery not found."},
                status=status.HTTP_404_NOT_FOUND,
            )
        except DatabaseError as exc:
            logger.error("[DeliveryDetailView] DB error: %s", exc, exc_info=True)
            return Response(
                {"message": "Service temporarily unavailable. Please try again later."},
                status=status.HTTP_503_SERVICE_UNAVAILABLE,
            )
        except Exception as exc:
            logger.exception("[DeliveryDetailView] Unexpected error: %s", exc)
            return Response(
                {"message": "An unexpected error occurred while fetching this delivery."},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )


# ─────────────────────────────────────────────────────────────────────────────
# Assign
# ─────────────────────────────────────────────────────────────────────────────

class AssignDeliveryView(generics.CreateAPIView):
    """POST /deliveries/assign — Create delivery and publish event."""
    serializer_class = AssignDeliverySerializer
    permission_classes = [IsAuthenticated]

    @extend_schema(
        operation_id="deliveries_assign",
        summary="Assign a new delivery",
        request=AssignDeliverySerializer,
        responses={
            201: DeliverySerializer,
            500: OpenApiResponse(description="Internal server error"),
        },
    )
    def post(self, request, *args, **kwargs):
        serializer = AssignDeliverySerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data

        medications = data["medications"]

        # ── Step 1: Synchronous stock validation against gateway ──────────
        # Extracts real medicine names, prices from gateway and validates qty.
        auth_token = request.META.get("HTTP_AUTHORIZATION", "").replace("Bearer ", "")
        try:
            items_data = validate_and_fetch_stock(medications, auth_token)
        except InsufficientStockError as exc:
            logger.warning("[AssignDeliveryView] Stock validation failed: %s", exc)
            return Response({"message": str(exc)}, status=status.HTTP_400_BAD_REQUEST)
        except StockClientError as exc:
            logger.error("[AssignDeliveryView] Stock client error: %s", exc)
            return Response({"message": str(exc)}, status=status.HTTP_503_SERVICE_UNAVAILABLE)

        # Compute total from validated (real) prices
        total = sum(
            Decimal(str(item["unit_price"])) * int(item["quantity"])
            for item in items_data
        )

        # ── Step 2: Create delivery + items + QR atomically ───────────────
        try:
            with transaction.atomic():
                delivery = Delivery.objects.create(
                    user_id=request.user.id,
                    driver_id=data["driver_id"],
                    customer_id=data["customer_id"],
                    driver_name=data.get("driver_name", ""),
                    customer_name=data.get("customer_name", ""),
                    customer_email=data.get("customer_email", ""),
                    from_location=data["from_location"],
                    destination=data["destination"],
                    total_amount=total,
                    status=Delivery.Status.PENDING,
                )

                for item in items_data:
                    DeliveryItem.objects.create(
                        delivery=delivery,
                        medicine_id=item["medicine_id"],
                        medicine_name=item["medicine_name"],
                        quantity=item["quantity"],
                        unit_price=Decimal(str(item["unit_price"])),
                    )

                # Generate encrypted QR code
                qr_payload = {
                    "delivery_id": str(delivery.id),
                    "customer_id": str(delivery.customer_id),
                    "driver_id": str(delivery.driver_id),
                }
                encrypted = encrypt_qr_data(qr_payload)
                qr_img = qrcode.make(encrypted)
                buffer = BytesIO()
                qr_img.save(buffer)
                buffer.seek(0)
                qr_url = _upload_qr(buffer.read(), str(delivery.id))

                delivery.qr_code = qr_url
                delivery.save(update_fields=["qr_code"])

        except Exception as exc:
            logger.error("Failed to create delivery: %s", exc)
            return Response(
                {"message": "Failed to create delivery"},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )

        # ── Step 3: Publish event (gateway consumer will deduct stock) ────
        # items_data contains medicine_id + quantity so gateway can deduct.
        publish_delivery_event("delivery.assigned", {
            "event": "delivery.assigned",
            "delivery_id": str(delivery.id),
            "customer_email": delivery.customer_email,
            "customer_name": delivery.customer_name,
            "driver_name": delivery.driver_name,
            "from_location": delivery.from_location,
            "destination": delivery.destination,
            "total_amount": str(delivery.total_amount),
            "qr_code": delivery.qr_code,
            "user_id": str(delivery.user_id),
            "items": items_data,
        })

        return Response(DeliverySerializer(delivery).data, status=status.HTTP_201_CREATED)


# ─────────────────────────────────────────────────────────────────────────────
# Update Status
# ─────────────────────────────────────────────────────────────────────────────

class UpdateDeliveryStatusView(generics.UpdateAPIView):
    """PATCH /deliveries/<pk>/status — Update status and publish event."""
    queryset = Delivery.objects.all()
    serializer_class = UpdateStatusSerializer
    permission_classes = [IsAuthenticated]
    http_method_names = ["patch"]

    @extend_schema(
        operation_id="deliveries_update_status",
        summary="Update delivery status",
        request=UpdateStatusSerializer,
        responses={
            200: DeliverySerializer,
            404: OpenApiResponse(description="Not found"),
        },
    )
    def patch(self, request, *args, **kwargs):
        try:
            delivery = Delivery.objects.get(pk=kwargs["pk"])
        except Delivery.DoesNotExist:
            return Response({"message": "Not found"}, status=status.HTTP_404_NOT_FOUND)

        serializer = UpdateStatusSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        new_status = serializer.validated_data["status"]
        old_status = delivery.status

        if new_status == Delivery.Status.DELIVERED:
            delivery.delivery_time = timezone.now()
        elif new_status == Delivery.Status.CANCELLED:
            delivery.cancellation_reason = serializer.validated_data.get("cancellation_reason", "")

        delivery.status = new_status
        delivery.save()

        routing_key = (
            "delivery.completed" if new_status == Delivery.Status.DELIVERED else
            "delivery.cancelled" if new_status == Delivery.Status.CANCELLED else
            "delivery.status_changed"
        )

        # Build items snapshot for stock restoration on cancellation
        items_snapshot = [
            {
                "medicine_id": str(item.medicine_id),
                "quantity": item.quantity,
            }
            for item in delivery.items.all()
        ] if new_status == Delivery.Status.CANCELLED else []

        publish_delivery_event(routing_key, {
            "event": routing_key,
            "delivery_id": str(delivery.id),
            "old_status": old_status,
            "new_status": new_status,
            "customer_email": delivery.customer_email,
            "customer_name": delivery.customer_name,
            "driver_name": delivery.driver_name,
            "destination": delivery.destination,
            "user_id": str(delivery.user_id),
            "cancellation_reason": delivery.cancellation_reason or "",
            "items": items_snapshot,  # populated only on cancellation
        })

        return Response(DeliverySerializer(delivery).data)


# ─────────────────────────────────────────────────────────────────────────────
# QR Scan
# ─────────────────────────────────────────────────────────────────────────────

class ScanQRView(generics.GenericAPIView):
    """POST /deliveries/scan — Validate encrypted QR payload."""
    serializer_class = ScanQRRequestSerializer
    permission_classes = [AllowAny]

    @extend_schema(
        operation_id="deliveries_scan_qr",
        summary="Scan a delivery QR code",
        request=ScanQRRequestSerializer,
        responses={
            200: ScanQRResponseSerializer,
            400: OpenApiResponse(description="Invalid QR data"),
        },
    )
    def post(self, request, *args, **kwargs):
        encrypted = request.data.get("qr_data", "")
        if not encrypted:
            return Response({"message": "qr_data is required"}, status=status.HTTP_400_BAD_REQUEST)
        try:
            payload = decrypt_qr_data(encrypted)
            delivery_id = payload.get("delivery_id")
            delivery = Delivery.objects.get(pk=delivery_id)

            delivery.warehouse_scan_time = timezone.now()
            delivery.status = Delivery.Status.IN_TRANSIT
            delivery.save(update_fields=["warehouse_scan_time", "status"])

            publish_delivery_event("delivery.scanned", {
                "event": "delivery.scanned",
                "delivery_id": str(delivery.id),
                "customer_email": delivery.customer_email,
                "customer_name": delivery.customer_name,
                "user_id": str(delivery.user_id),
            })

            return Response({"message": "QR verified", "delivery": DeliverySerializer(delivery).data})
        except Exception as exc:
            return Response({"message": f"Invalid QR: {exc}"}, status=status.HTTP_400_BAD_REQUEST)


# ─────────────────────────────────────────────────────────────────────────────
# Customer Scan & Confirm
# ─────────────────────────────────────────────────────────────────────────────

class CustomerScanConfirmView(generics.GenericAPIView):
    """POST /deliveries/<pk>/confirm/ — Customer confirms receipt of delivery."""
    permission_classes = [AllowAny]

    @extend_schema(
        operation_id="deliveries_customer_confirm",
        summary="Customer confirms delivery receipt",
        responses={
            200: DeliverySerializer,
            400: OpenApiResponse(description="Delivery cannot be confirmed (wrong status or already confirmed)"),
            404: OpenApiResponse(description="Delivery not found"),
        },
    )
    def post(self, request, *args, **kwargs):
        try:
            delivery = Delivery.objects.get(pk=kwargs["pk"])
        except Delivery.DoesNotExist:
            return Response({"message": "Delivery not found."}, status=status.HTTP_404_NOT_FOUND)

        if delivery.customer_confirmed:
            return Response(
                {"message": "Delivery has already been confirmed by the customer."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        if delivery.status != Delivery.Status.IN_TRANSIT:
            return Response(
                {"message": f"Cannot confirm delivery in '{delivery.status}' status. Delivery must be in_transit."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        delivery.customer_confirmed = True
        delivery.status = Delivery.Status.DELIVERED
        delivery.delivery_time = timezone.now()
        delivery.save(update_fields=["customer_confirmed", "status", "delivery_time"])

        publish_delivery_event("delivery.customer_confirmed", {
            "event": "delivery.customer_confirmed",
            "delivery_id": str(delivery.id),
            "customer_name": delivery.customer_name,
            "customer_email": delivery.customer_email,
            "driver_name": delivery.driver_name,
            "destination": delivery.destination,
            "user_id": str(delivery.user_id),
        })

        logger.info("[CustomerScanConfirmView] Delivery %s confirmed by customer %s", delivery.id, delivery.customer_name)
        return Response(DeliverySerializer(delivery).data, status=status.HTTP_200_OK)
