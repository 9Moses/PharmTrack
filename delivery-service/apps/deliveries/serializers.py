from rest_framework import serializers
from .models import Delivery, DeliveryItem


class DeliveryItemSerializer(serializers.ModelSerializer):
    class Meta:
        model = DeliveryItem
        fields = ["medicine_id", "medicine_name", "quantity", "unit_price"]


class DeliverySerializer(serializers.ModelSerializer):
    items = DeliveryItemSerializer(many=True, read_only=True)

    class Meta:
        model = Delivery
        fields = "__all__"
        read_only_fields = ["id", "qr_code", "total_amount", "created_at", "updated_at"]


class AssignDeliverySerializer(serializers.Serializer):
    customer_id = serializers.UUIDField()
    driver_id = serializers.UUIDField()
    driver_name = serializers.CharField(max_length=255, required=False, allow_blank=True, default="")
    customer_name = serializers.CharField(max_length=255, required=False, allow_blank=True, default="")
    customer_email = serializers.EmailField(required=False, allow_blank=True, default="")
    from_location = serializers.CharField(max_length=500)
    destination = serializers.CharField(max_length=500)
    medications = serializers.ListField(
        child=serializers.DictField(),
        min_length=1,
    )


class UpdateStatusSerializer(serializers.Serializer):
    status = serializers.ChoiceField(choices=Delivery.Status.choices)
    cancellation_reason = serializers.CharField(required=False, allow_blank=True)


class ScanQRRequestSerializer(serializers.Serializer):
    qr_data = serializers.CharField(help_text="Encrypted QR code payload string")


class ScanQRResponseSerializer(serializers.Serializer):
    message = serializers.CharField()
    delivery = DeliverySerializer()
