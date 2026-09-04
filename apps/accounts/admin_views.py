"""SaaS user-administration screens, restricted to super admins.
Every endpoint re-checks authorisation server-side before mutating anything."""

from __future__ import annotations

from django.contrib import messages
from django.core.exceptions import PermissionDenied
from django.http import Http404, HttpRequest, HttpResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.views.decorators.http import require_POST

from apps.accounts import services
from apps.accounts.forms import PasswordResetForm, UserCreateForm, UserUpdateForm
from apps.accounts.models import Role, User
from apps.accounts.permissions import super_admin_required
from apps.accounts.selectors import DEFAULT_USER_SORT, list_users, user_stats
from apps.common.modals import is_modal, redirect_response, render_modal
from apps.common.pagination import parse_page_request


def _target(request: HttpRequest, pk: str) -> User:
    """Fetch a user and confirm the actor is allowed to modify it.
    An unparseable ObjectId is a 404, never a 500."""
    from bson.errors import InvalidId
    from bson.objectid import ObjectId

    try:
        ObjectId(str(pk))
    except (InvalidId, TypeError):
        raise Http404("No such user.") from None

    user = get_object_or_404(User, pk=pk, is_deleted=False)
    if not services.can_modify(request.user, user):
        raise PermissionDenied("You cannot modify this account.")
    return user


@super_admin_required
def user_list(request: HttpRequest) -> HttpResponse:
    search = request.GET.get("q", "").strip()
    role = request.GET.get("role", "")
    status = request.GET.get("status", "")
    sort = request.GET.get("sort", DEFAULT_USER_SORT)

    queryset = list_users(search=search, role=role, status=status, sort=sort)
    page_req = parse_page_request(request)
    total = queryset.count()
    users = list(queryset[page_req.offset : page_req.offset + page_req.limit])

    context = {
        "page_obj": page_req.build(users, total),
        "stats": user_stats(),
        "search": search,
        "role": role,
        "status": status,
        "sort": sort,
        "roles": Role.choices,
        "active_nav": "users",
    }
    template = "accounts/partials/user_table.html" if request.htmx else "accounts/user_list.html"
    return render(request, template, context)


@super_admin_required
def user_create(request: HttpRequest) -> HttpResponse:
    form = UserCreateForm(request.POST or None)
    if request.method == "POST" and form.is_valid():
        user = services.create_user(form=form, actor=request.user, request=request)
        messages.success(request, f"User {user.email} created.")
        target = reverse("useradmin:user_list")
        return redirect_response(target) if is_modal(request) else redirect(target)

    if is_modal(request):
        return render_modal(
            request,
            form=form,
            action=reverse("useradmin:user_create"),
            title="Create user",
            subtitle="Provision access to the platform",
            submit_label="Create user",
            size="rv-modal--wide",
            status=422 if request.method == "POST" else 200,
        )
    return render(
        request, "accounts/user_form.html", {"form": form, "mode": "create", "active_nav": "users"}
    )


@super_admin_required
def user_edit(request: HttpRequest, pk: str) -> HttpResponse:
    user = _target(request, pk)
    form = UserUpdateForm(request.POST or None, instance=user)
    if request.method == "POST" and form.is_valid():
        services.update_user(form=form, actor=request.user, request=request)
        messages.success(request, f"User {user.email} updated.")
        target = reverse("useradmin:user_list")
        return redirect_response(target) if is_modal(request) else redirect(target)

    if is_modal(request):
        return render_modal(
            request,
            form=form,
            action=reverse("useradmin:user_edit", args=[pk]),
            title="Edit user",
            subtitle=user.email,
            submit_label="Save changes",
            size="rv-modal--wide",
            status=422 if request.method == "POST" else 200,
        )
    return render(
        request,
        "accounts/user_form.html",
        {"form": form, "mode": "edit", "target_user": user, "active_nav": "users"},
    )


@super_admin_required
def user_password(request: HttpRequest, pk: str) -> HttpResponse:
    user = _target(request, pk)
    form = PasswordResetForm(request.POST or None)
    if request.method == "POST" and form.is_valid():
        services.reset_password(
            user=user,
            raw_password=form.cleaned_data["password1"],
            actor=request.user,
            request=request,
        )
        messages.success(request, f"Password reset for {user.email}.")
        target = reverse("useradmin:user_list")
        return redirect_response(target) if is_modal(request) else redirect(target)

    if is_modal(request):
        return render_modal(
            request,
            form=form,
            action=reverse("useradmin:user_password", args=[pk]),
            title="Reset password",
            subtitle=user.email,
            submit_label="Reset password",
            status=422 if request.method == "POST" else 200,
        )
    return render(
        request,
        "accounts/user_password.html",
        {"form": form, "target_user": user, "active_nav": "users"},
    )


@require_POST
@super_admin_required
def user_toggle_active(request: HttpRequest, pk: str) -> HttpResponse:
    user = _target(request, pk)
    services.set_active(
        user=user, active=not user.is_active, actor=request.user, request=request
    )
    messages.success(
        request, f"{user.email} {'activated' if user.is_active else 'deactivated'}."
    )
    return redirect(reverse("useradmin:user_list"))


@require_POST
@super_admin_required
def user_delete(request: HttpRequest, pk: str) -> HttpResponse:
    user = _target(request, pk)
    email = user.email
    services.soft_delete(user=user, actor=request.user, request=request)
    messages.success(request, f"User {email} deleted.")
    return redirect(reverse("useradmin:user_list"))
