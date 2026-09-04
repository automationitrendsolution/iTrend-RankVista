"""Shell entry points, health probe and branded error handlers."""

from __future__ import annotations

from django.http import HttpRequest, HttpResponse, JsonResponse
from django.shortcuts import redirect, render
from django.views.decorators.cache import never_cache

from apps.accounts.permissions import login_required
from apps.common import cache as cache_helpers
from apps.common import mongo

ERROR_COPY = {
    400: ("Bad request", "That request could not be understood. Check the link and try again."),
    403: ("Access denied", "You do not have permission to view this page."),
    404: ("Page not found", "The page you are looking for does not exist or has been moved."),
    500: ("Something went wrong", "An unexpected error occurred. The team has been notified."),
}


def home(request: HttpRequest) -> HttpResponse:
    if request.user.is_authenticated:
        return redirect("projects:list")
    return redirect("accounts:login")


@never_cache
def healthz(request: HttpRequest) -> JsonResponse:
    """Liveness probe reporting dependency reachability, never secrets."""
    mongo_ok = mongo.ping()
    cache_ok = cache_helpers.is_available()
    payload = {
        "status": "ok" if mongo_ok else "degraded",
        "mongodb": "up" if mongo_ok else "down",
        "cache": "up" if cache_ok else "down",
    }
    return JsonResponse(payload, status=200 if mongo_ok else 503)


@login_required
def dashboard(request: HttpRequest) -> HttpResponse:
    return redirect("projects:list")


def _error(request: HttpRequest, status: int, exception=None) -> HttpResponse:
    title, message = ERROR_COPY[status]
    return render(
        request,
        "errors/error.html",
        {"status": status, "title": title, "message": message, "hide_shell": False},
        status=status,
    )


def bad_request(request: HttpRequest, exception=None) -> HttpResponse:
    return _error(request, 400, exception)


def permission_denied(request: HttpRequest, exception=None) -> HttpResponse:
    return _error(request, 403, exception)


def page_not_found(request: HttpRequest, exception=None) -> HttpResponse:
    return _error(request, 404, exception)


def server_error(request: HttpRequest) -> HttpResponse:
    return _error(request, 500)
