from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated
from rest_framework import status
from .models import Notification
from .serializers import NotificationSerializer

class NotificationListView(APIView):
    """GET /notifications/ — Fetch current user notifications."""
    permission_classes = [IsAuthenticated]

    def get(self, request):
        try:
            user_id = request.user.id
            notifications = Notification.objects.filter(user_id=user_id)
            unread_only = request.query_params.get("unread")
            if unread_only == "true":
                notifications = notifications.filter(is_read=False)
            serializer = NotificationSerializer(notifications, many=True)
            return Response({
                "count": notifications.count(),
                "results": serializer.data,
            })
        except Exception as e:
            return Response({"message": str(e)}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

class MarkReadView(APIView):
    """PATCH /notifications/<pk>/read/ — Mark single notification read."""
    permission_classes = [IsAuthenticated]

    def patch(self, request, pk):
        try:
            notif = Notification.objects.get(pk=pk, user_id=request.user.id)
        except Notification.DoesNotExist:
            return Response({"message": "Not found"}, status=status.HTTP_404_NOT_FOUND)
        notif.is_read = True
        notif.save(update_fields=["is_read", "updated_at"])
        return Response(NotificationSerializer(notif).data)

class MarkAllReadView(APIView):
    """PATCH /notifications/read-all/ — Mark all notifications read."""
    permission_classes = [IsAuthenticated]

    def patch(self, request):
        Notification.objects.filter(user_id=request.user.id, is_read=False).update(is_read=True)
        return Response({"message": "All notifications marked as read"})
