import logging

from django.core.cache import cache
from django.db import connection
from django.http import HttpRequest, JsonResponse
from django.views.decorators.cache import never_cache
from django.views.decorators.http import require_GET

logger = logging.getLogger(__name__)


@never_cache
@require_GET
def healthz(request: HttpRequest) -> JsonResponse:
    """Load balancer check: database and cache reachable. Returns no data."""
    checks = {"database": True, "cache": True}
    try:
        with connection.cursor() as cursor:
            cursor.execute("SELECT 1")
    except Exception:
        logger.exception("healthz: database check failed")
        checks["database"] = False
    try:
        cache.set("core:healthz", "1", 5)
        checks["cache"] = cache.get("core:healthz") == "1"
    except Exception:
        logger.exception("healthz: cache check failed")
        checks["cache"] = False
    healthy = all(checks.values())
    return JsonResponse(
        {"status": "ok" if healthy else "fail", **checks}, status=200 if healthy else 503
    )
