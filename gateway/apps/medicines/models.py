"""
apps/medicines — complete module (models + serializers + views + urls)
Manages medicine inventory. Publishes stock events to RabbitMQ.
"""
import uuid
from django.db import models


class Medicine(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    name = models.CharField(max_length=255)
    batch = models.CharField(max_length=100)
    expiry_date = models.DateField()
    quantity = models.IntegerField()
    price = models.DecimalField(max_digits=10, decimal_places=2)
    qr_code = models.TextField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "medicines"

    def __str__(self):
        return f"{self.name} ({self.batch})"
