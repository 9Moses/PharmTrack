from rest_framework.viewsets import ModelViewSet
from rest_framework.permissions import IsAuthenticated
from .models import Vehicle, Driver, Customer
from .serializers import VehicleSerializer, DriverSerializer, CustomerSerializer
from apps.audit.permissions import IsAdminOrSuperAdmin
from utils.throttling import GlobalUserThrottle, BurstThrottle, WriteThrottle

class VehicleViewSet(ModelViewSet):
    queryset = Vehicle.objects.all().order_by("-created_at")
    serializer_class = VehicleSerializer
    permission_classes = [IsAuthenticated, IsAdminOrSuperAdmin]
    throttle_classes = [GlobalUserThrottle, BurstThrottle, WriteThrottle]

class DriverViewSet(ModelViewSet):
    queryset = Driver.objects.all().order_by("-created_at")
    serializer_class = DriverSerializer
    permission_classes = [IsAuthenticated, IsAdminOrSuperAdmin]
    throttle_classes = [GlobalUserThrottle, BurstThrottle, WriteThrottle]

class CustomerViewSet(ModelViewSet):
    queryset = Customer.objects.all().order_by("-created_at")
    serializer_class = CustomerSerializer
    permission_classes = [IsAuthenticated, IsAdminOrSuperAdmin]
    throttle_classes = [GlobalUserThrottle, BurstThrottle, WriteThrottle]
