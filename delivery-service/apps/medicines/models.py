import uuid
from django.db import models


class Medicine(models.Model):
    """Local read-only replica populated by gateway medicine.created events."""
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    name = models.CharField(max_length=255)
    batch = models.CharField(max_length=100)
    expiry_date = models.DateField()
    quantity = models.IntegerField()
    price = models.DecimalField(max_digits=10, decimal_places=2)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        app_label = "medicines"
        db_table = "delivery_medicines_catalog"


class Driver(models.Model):
    """Lightweight local copy synced from gateway."""
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    name = models.CharField(max_length=255)
    email = models.EmailField(unique=True)
    is_active = models.BooleanField(default=True)

    class Meta:
        app_label = "vehicles"
        db_table = "delivery_drivers"


class Customer(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    name = models.CharField(max_length=255)
    email = models.EmailField(unique=True)
    is_active = models.BooleanField(default=True)

    class Meta:
        app_label = "vehicles"
        db_table = "delivery_customers"
