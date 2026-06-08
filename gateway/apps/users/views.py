from rest_framework import status
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated

from .models import User
from .serializers import UserSerializer, CreateUserSerializer
from apps.audit.permissions import IsSuperAdmin, IsAdminOrSuperAdmin
from utils.throttling import GlobalUserThrottle, BurstThrottle, WriteThrottle


class UserListCreateView(APIView):
    permission_classes = [IsAuthenticated, IsSuperAdmin]
    throttle_classes = [GlobalUserThrottle, BurstThrottle, WriteThrottle]

    def get(self, request):
        try:
            users = User.objects.all().order_by("-created_at")
            serializer = UserSerializer(users, many=True)
            return Response(serializer.data)
        except Exception as exc:
            return Response({"message": str(exc)}, status=status.HTTP_400_BAD_REQUEST)

    def post(self, request):
        try:
            serializer = CreateUserSerializer(data=request.data)
            serializer.is_valid(raise_exception=True)
            user = serializer.save()
            return Response(UserSerializer(user).data, status=status.HTTP_201_CREATED)
        except Exception as exc:
            return Response({"message": str(exc)}, status=status.HTTP_400_BAD_REQUEST)


class UserDetailView(APIView):
    permission_classes = [IsAuthenticated, IsAdminOrSuperAdmin]
    throttle_classes = [GlobalUserThrottle, BurstThrottle, WriteThrottle]

    def get_object(self, pk):
        try:
            return User.objects.get(pk=pk)
        except User.DoesNotExist:
            return None

    def get(self, request, pk):
        try:
            user = self.get_object(pk)
            if not user:
                return Response({"message": "User not found"}, status=status.HTTP_404_NOT_FOUND)
            return Response(UserSerializer(user).data)
        except Exception as exc:
            return Response({"message": str(exc)}, status=status.HTTP_400_BAD_REQUEST)

    def patch(self, request, pk):
        try:
            user = self.get_object(pk)
            if not user:
                return Response({"message": "User not found"}, status=status.HTTP_404_NOT_FOUND)
            serializer = UserSerializer(user, data=request.data, partial=True)
            serializer.is_valid(raise_exception=True)
            serializer.save()
            return Response(serializer.data)
        except Exception as exc:
            return Response({"message": str(exc)}, status=status.HTTP_400_BAD_REQUEST)

    def delete(self, request, pk):
        try:
            user = self.get_object(pk)
            if not user:
                return Response({"message": "User not found"}, status=status.HTTP_404_NOT_FOUND)
            user.is_active = False
            user.save(update_fields=["is_active"])
            return Response({"message": "User deactivated"})
        except Exception as exc:
            return Response({"message": str(exc)}, status=status.HTTP_400_BAD_REQUEST)


class MeView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        try:
            return Response(UserSerializer(request.user).data)
        except Exception as exc:
            return Response({"message": str(exc)}, status=status.HTTP_400_BAD_REQUEST)
