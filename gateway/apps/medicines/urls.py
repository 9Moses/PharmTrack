from django.urls import path
from .views import MedicineListCreateView, MedicineDetailView, MedicineBulkUploadView

urlpatterns = [
    path("", MedicineListCreateView.as_view()),
    path("bulk-upload/", MedicineBulkUploadView.as_view(), name="bulk-upload"),
    path("<uuid:pk>/", MedicineDetailView.as_view()),
]
