from rest_framework.response import Response
from rest_framework import status
from rest_framework.views import exception_handler as drf_exception_handler
import logging

logger = logging.getLogger(__name__)


class ErrorHandler:
    """
    Centralized safe error handler for API responses
    """
    @staticmethod
    def handle(exc, content_message="Request failed",
               error_code="internal_error"):
        logger.exception("%s: %s", content_message, exc)

        return Response({
            "success": False,
            "message": content_message,
            "error_code": error_code
        },
            status=status.HTTP_500_INTERNAL_SERVER_ERROR)


def custom_exception_handler(exc, context):
    """Normalize DRF exceptions into the standard API error shape."""
    response = drf_exception_handler(exc, context)
    if response is None:
        return ErrorHandler.handle(exc, "Internal server error")

    formatted = {"success": False}
    if isinstance(response.data, dict):
        detail = response.data.get("detail")
        if detail is not None:
            formatted["message"] = str(detail)
            extra = {k: v for k, v in response.data.items() if k != "detail"}
            if extra:
                formatted["errors"] = extra
        else:
            formatted["message"] = response.data
    else:
        formatted["message"] = response.data

    response.data = formatted
    return response
