import uuid
from django.db import models


class Delivery(models.Model):
    class Status(models.TextChoices):
        PENDING = "pending", "Pending"
        IN_TRANSIT = "in_transit", "In Transit"
        DELIVERED = "delivered", "Delivered"
        CANCELLED = "cancelled", "Cancelled"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    # user_id references gateway users — stored as UUID (no FK across services)
    user_id = models.UUIDField()
    driver_id = models.UUIDField()
    customer_id = models.UUIDField()
    driver_name = models.CharField(max_length=255, blank=True)
    customer_name = models.CharField(max_length=255, blank=True)
    customer_email = models.EmailField(blank=True)
    from_location = models.CharField(max_length=500)
    destination = models.CharField(max_length=500)
    total_amount = models.DecimalField(max_digits=10, decimal_places=2, null=True, blank=True)
    qr_code = models.TextField(null=True, blank=True)
    cancellation_reason = models.TextField(null=True, blank=True)
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.PENDING)
    warehouse_scan_time = models.DateTimeField(null=True, blank=True)
    delivery_time = models.DateTimeField(null=True, blank=True)
    customer_confirmed = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "deliveries"
        ordering = ["-created_at"]

    def __str__(self):
        return f"Delivery {self.id} ({self.status})"


class DeliveryItem(models.Model):
    """Medicines included in a delivery (denormalised — no cross-service FK)."""
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    delivery = models.ForeignKey(Delivery, on_delete=models.CASCADE, related_name="items")
    medicine_id = models.UUIDField()
    medicine_name = models.CharField(max_length=255)
    quantity = models.IntegerField()
    unit_price = models.DecimalField(max_digits=10, decimal_places=2)

    class Meta:
        db_table = "delivery_items"
