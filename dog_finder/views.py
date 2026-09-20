"""Minimal public landing and operational probes without subscriber data."""

from django.db import DatabaseError, connection
from django.http import HttpRequest, HttpResponse, JsonResponse
from django.shortcuts import render
from django.views.decorators.http import require_safe


@require_safe
def home(request: HttpRequest) -> HttpResponse:
    """Render a truthful placeholder while subscriber flows are being built."""
    return render(request, "home.html")


@require_safe
def health(request: HttpRequest) -> JsonResponse:
    """Report process liveness without contacting the database or providers."""
    return JsonResponse({"status": "ok"})


@require_safe
def ready(request: HttpRequest) -> JsonResponse:
    """Report database reachability without exposing connection details."""
    try:
        with connection.cursor() as cursor:
            cursor.execute("SELECT 1")
    except DatabaseError:
        return JsonResponse({"status": "unavailable"}, status=503)
    return JsonResponse({"status": "ok"})
