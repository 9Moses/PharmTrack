from rest_framework import serializers
from .models import Vehicle, Driver, Customer

class VehicleSerializer(serializers.ModelSerializer):
    registrationNumber = serializers.CharField(source='registration_number')
    isActive = serializers.BooleanField(source='is_active')
    lastMaintenance = serializers.DateTimeField(source='last_maintenance', allow_null=True)

    class Meta:
        model = Vehicle
        fields = ["id", "registrationNumber", "model", "type", "capacity", "isActive", "lastMaintenance", "created_at", "updated_at"]
        read_only_fields = ["id", "created_at", "updated_at"]

class DriverSerializer(serializers.ModelSerializer):
    class Meta:
        model = Driver
        fields = "__all__"
        read_only_fields = ["id", "created_at", "updated_at"]

class CustomerSerializer(serializers.ModelSerializer):
    class Meta:
        model = Customer
        fields = "__all__"
        read_only_fields = ["id", "created_at", "updated_at"]
