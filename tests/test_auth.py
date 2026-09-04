"""Authentication: login, logout, bad credentials, inactive accounts, redirects."""

from __future__ import annotations

import pytest
from django.urls import reverse

from apps.audit.models import AuditAction, AuditLog

pytestmark = pytest.mark.django_db


def test_login_page_renders_for_anonymous(client):
    response = client.get(reverse("accounts:login"))
    assert response.status_code == 200
    assert b"Sign in" in response.content


def test_login_succeeds_with_email(client, normal_user):
    response = client.post(
        reverse("accounts:login"),
        {"identifier": normal_user.email, "password": "Us3rSecret!Pass"},
    )
    assert response.status_code == 302
    assert response.url == "/projects/"
    assert AuditLog.objects.filter(action=AuditAction.LOGIN_SUCCESS).exists()


def test_login_succeeds_with_username(client, normal_user):
    response = client.post(
        reverse("accounts:login"),
        {"identifier": normal_user.username, "password": "Us3rSecret!Pass"},
    )
    assert response.status_code == 302


def test_login_rejects_wrong_password(client, normal_user):
    response = client.post(
        reverse("accounts:login"),
        {"identifier": normal_user.email, "password": "not-the-password"},
    )
    assert response.status_code == 200
    assert b"Incorrect email or password" in response.content
    assert AuditLog.objects.filter(action=AuditAction.LOGIN_FAILED).exists()


def test_login_rejects_unknown_account(client):
    response = client.post(
        reverse("accounts:login"),
        {"identifier": "nobody@example.com", "password": "whatever-pass"},
    )
    assert response.status_code == 200
    assert b"Incorrect email or password" in response.content


def test_login_rejects_inactive_account(client, inactive_user):
    response = client.post(
        reverse("accounts:login"),
        {"identifier": inactive_user.email, "password": "Us3rSecret!Pass"},
    )
    assert response.status_code == 200
    assert b"Incorrect email or password" in response.content


def test_remember_me_controls_session_length(client, normal_user, settings):
    client.post(
        reverse("accounts:login"),
        {"identifier": normal_user.email, "password": "Us3rSecret!Pass"},
    )
    assert client.session.get_expiry_age() <= 60 * 60 * 8

    client.logout()
    client.post(
        reverse("accounts:login"),
        {"identifier": normal_user.email, "password": "Us3rSecret!Pass", "remember_me": "on"},
    )
    assert client.session.get_expiry_age() > 60 * 60 * 8


def test_anonymous_is_redirected_to_login_with_next(client):
    response = client.get("/projects/")
    assert response.status_code == 302
    assert response.url.startswith("/login/?next=/projects/")


def test_logout_clears_session(client_as_user):
    response = client_as_user.post(reverse("accounts:logout"))
    assert response.status_code == 302
    assert client_as_user.get("/projects/").status_code == 302


def test_login_next_rejects_external_host(client, normal_user):
    response = client.post(
        reverse("accounts:login"),
        {
            "identifier": normal_user.email,
            "password": "Us3rSecret!Pass",
            "next": "https://evil.example.com/steal",
        },
    )
    assert response.url == "/projects/"


def test_authenticated_user_skips_login_page(client_as_user):
    response = client_as_user.get(reverse("accounts:login"))
    assert response.status_code == 302


def test_profile_password_change_requires_current_password(client_as_user, normal_user):
    response = client_as_user.post(
        reverse("accounts:profile"),
        {
            "form": "password",
            "current_password": "wrong-current",
            "password1": "BrandNewPass!99",
            "password2": "BrandNewPass!99",
        },
    )
    assert response.status_code == 200
    assert b"current password is incorrect" in response.content
