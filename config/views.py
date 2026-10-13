from django.core.cache import cache
from django.db import connection
from django.http import HttpResponse, JsonResponse


def healthz(request):
    return HttpResponse("ok", content_type="text/plain", status=200)


def _check_database() -> None:
    with connection.cursor() as cursor:
        cursor.execute("SELECT 1")
        cursor.fetchone()


def _check_cache() -> None:
    cache.set("readyz", "1", timeout=5)
    if cache.get("readyz") != "1":
        raise RuntimeError("Cache Couldn't store the recent value")


CHECKS = {"database": _check_database, "cache": _check_cache}


def readyz(request):
    results = {}
    for name, check in CHECKS.items():
        try:
            check()
            results[name] = "ok"
        except Exception as e:
            results[name] = f"error:{type(e).__name__}"
    healthy = all(value == "ok" for value in results.values())
    return JsonResponse(
        {"status": "ok" if healthy else "unavailable", "checks": results},
        status=200 if healthy else 503,
    )
