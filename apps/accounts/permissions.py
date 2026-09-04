"""Server-side authorisation decorators and mixins.
Every protected endpoint is guarded here; hidden UI is never an access control."""

from __future__ import annotations

from collections.abc import Callable
from functools import wraps

from django.core.exceptions import PermissionDenied
from django.http import HttpRequest, HttpResponse
from django.shortcuts import redirect

from apps.accounts.models import Role


def login_required(view: Callable[..., HttpResponse]) -> Callable[..., HttpResponse]:
    """Redirect anonymous users to the login page, preserving the target URL."""

    @wraps(view)
    def wrapper(request: HttpRequest, *args, **kwargs) -> HttpResponse:
        user = getattr(request, "user", None)
        if not user or not user.is_authenticated:
            return redirect(f"/login/?next={request.get_full_path()}")
        if not user.is_active or user.is_deleted:
            raise PermissionDenied("This account is no longer active.")
        return view(request, *args, **kwargs)

    return wrapper


def role_required(minimum: str) -> Callable:
    """Require an authenticated user holding at least the given role."""

    def decorator(view: Callable[..., HttpResponse]) -> Callable[..., HttpResponse]:
        @wraps(view)
        @login_required
        def wrapper(request: HttpRequest, *args, **kwargs) -> HttpResponse:
            if not request.user.has_role_at_least(minimum):
                raise PermissionDenied("You do not have permission to perform this action.")
            return view(request, *args, **kwargs)

        return wrapper

    return decorator


def page_required(key: str) -> Callable:
    """Guard a view with the minimum role declared for that page in the matrix."""

    def decorator(view: Callable[..., HttpResponse]) -> Callable[..., HttpResponse]:
        @wraps(view)
        @login_required
        def wrapper(request: HttpRequest, *args, **kwargs) -> HttpResponse:
            from apps.accounts import roles as role_service
            from apps.accounts.pages import page

            required = page(key)
            if not role_service.can(request.user.role, key):
                raise PermissionDenied(f"Your role cannot open {required.label}.")
            return view(request, *args, **kwargs)

        return wrapper

    return decorator


admin_required = role_required(Role.ADMIN)
super_admin_required = role_required(Role.SUPER_ADMIN)
