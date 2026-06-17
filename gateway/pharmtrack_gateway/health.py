"""
Lightweight health check endpoint for the Gateway service.

Used by:
- Docker / Compose healthchecks
- Jenkins pipeline smoke tests (post-deploy verification)
- Prometheus blackbox-exporter probes / readiness checks
"""
from django.db import connections
from django.db.utils import OperationalError
from django.http import JsonResponse


def healthz(request):
    """Returns 200 if the service and its DB connection are alive."""
    db_status = "ok"
    status_code = 200

    try:
        conn = connections["default"]
        conn.cursor()
    except OperationalError:
        db_status = "error"
        status_code = 503

    return JsonResponse(
        {
            "service": "pharmtrack-gateway",
            "status": "ok" if status_code == 200 else "error",
            "database": db_status,
        },
        status=status_code,
    )
