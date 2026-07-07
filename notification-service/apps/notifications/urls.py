from django.urls import path
from .views import NotificationListView, MarkReadView, MarkAllReadView

urlpatterns = [
    path("", NotificationListView.as_view(), name="notification-list"),
    path("read-all/", MarkAllReadView.as_view(), name="mark-all-read"),
    path("<uuid:pk>/read/", MarkReadView.as_view(), name="mark-read"),
]
