from django.urls import path
from .views import (
    AssignDeliveryView, DeliveryListView, DeliveryDetailView,
    UpdateDeliveryStatusView, ScanQRView, CustomerScanConfirmView,
)

urlpatterns = [
    path("", DeliveryListView.as_view(), name="delivery-list"),
    path("assign/", AssignDeliveryView.as_view(), name="delivery-assign"),
    path("scan/", ScanQRView.as_view(), name="delivery-scan"),
    path("<uuid:pk>/", DeliveryDetailView.as_view(), name="delivery-detail"),
    path("<uuid:pk>/status/", UpdateDeliveryStatusView.as_view(), name="delivery-status"),
    path("<uuid:pk>/confirm/", CustomerScanConfirmView.as_view(), name="delivery-confirm"),
]
