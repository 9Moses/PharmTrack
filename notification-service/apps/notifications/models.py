import uuid
from django.db import models

class NotificationType(models.TextChoices):
    DELIVERY_ASSIGNED = "delivery_assigned", "Delivery Assigned"
    DELIVERY_SCANNED = "delivery_scanned", "Delivery Scanned"
    DELIVERY_COMPLETED = "delivery_completed", "Delivery Completed"
    DELIVERY_CANCELLED = "delivery_cancelled", "Delivery Cancelled"
    DELIVERY_STATUS_CHANGED = "delivery_status_changed", "Status Changed"
    USER_LOGIN = "user_login", "User Login"
    GENERAL = "general", "General"

class Notification(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    user_id = models.UUIDField(db_index=True)
    notification_type = models.CharField(max_length=40, choices=NotificationType.choices, default=NotificationType.GENERAL)
    title = models.CharField(max_length=255)
    message = models.TextField()
    metadata = models.JSONField(default=dict, blank=True)
    is_read = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    class Meta:
        db_table = "notifications"
        ordering = ["-created_at"]
