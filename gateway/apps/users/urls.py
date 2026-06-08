from django.urls import path
from .views import UserListCreateView, UserDetailView, MeView

urlpatterns = [
    path("", UserListCreateView.as_view(), name="user-list-create"),
    path("me/", MeView.as_view(), name="me"),
    path("<uuid:pk>/", UserDetailView.as_view(), name="user-detail"),
]
