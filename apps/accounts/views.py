"""Authentication and self-service profile views."""

from __future__ import annotations

from django.conf import settings
from django.contrib import messages
from django.contrib.auth import login as auth_login
from django.contrib.auth import logout as auth_logout
from django.contrib.auth import update_session_auth_hash
from django.http import HttpRequest, HttpResponse
from django.shortcuts import redirect, render
from django.urls import reverse
from django.utils.http import url_has_allowed_host_and_scheme

from apps.accounts.forms import ChangePasswordForm, LoginForm, ProfileForm
from apps.accounts.permissions import login_required
from apps.audit.models import AuditAction
from apps.audit.services import client_ip, record

SESSION_SHORT_AGE = 60 * 60 * 8


def _safe_next(request: HttpRequest) -> str:
    """Only redirect to same-host targets, so `next` cannot be weaponised."""
    target = request.POST.get("next") or request.GET.get("next") or ""
    if target and url_has_allowed_host_and_scheme(
        target, allowed_hosts={request.get_host()}, require_https=request.is_secure()
    ):
        return target
    return settings.LOGIN_REDIRECT_URL


def login_view(request: HttpRequest) -> HttpResponse:
    if request.user.is_authenticated:
        return redirect(_safe_next(request))

    form = LoginForm(request=request)
    if request.method == "POST":
        form = LoginForm(request, data=request.POST)
        if form.is_valid():
            user = form.user
            auth_login(request, user)
            if not form.cleaned_data.get("remember_me"):
                request.session.set_expiry(SESSION_SHORT_AGE)
            user.last_login_ip = client_ip(request)
            user.save(update_fields=["last_login_ip"])
            record(AuditAction.LOGIN_SUCCESS, request=request, actor=user, target=user.email)
            return redirect(_safe_next(request))

        identifier = (request.POST.get("identifier") or "")[:254]
        record(AuditAction.LOGIN_FAILED, request=request, target=identifier)

    return render(
        request,
        "accounts/login.html",
        {"form": form, "next": request.GET.get("next", ""), "hide_shell": True},
    )


def logout_view(request: HttpRequest) -> HttpResponse:
    if request.user.is_authenticated:
        record(AuditAction.LOGOUT, request=request, target=request.user.email)
    auth_logout(request)
    return redirect(settings.LOGOUT_REDIRECT_URL)


@login_required
def profile_view(request: HttpRequest) -> HttpResponse:
    form = ProfileForm(instance=request.user)
    password_form = ChangePasswordForm(request.user)

    if request.method == "POST":
        if request.POST.get("form") == "password":
            password_form = ChangePasswordForm(request.user, data=request.POST)
            if password_form.is_valid():
                request.user.set_password(password_form.cleaned_data["password1"])
                request.user.save(update_fields=["password"])
                update_session_auth_hash(request, request.user)
                record(AuditAction.PASSWORD_CHANGED, request=request, target=request.user.email)
                messages.success(request, "Your password has been updated.")
                return redirect(reverse("accounts:profile"))
        else:
            form = ProfileForm(request.POST, instance=request.user)
            if form.is_valid():
                form.save()
                messages.success(request, "Your profile has been updated.")
                return redirect(reverse("accounts:profile"))

    return render(
        request,
        "accounts/profile.html",
        {"form": form, "password_form": password_form, "active_nav": "profile"},
    )
