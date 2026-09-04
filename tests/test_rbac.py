"""Role-based access control across every administration endpoint."""

from __future__ import annotations

import pytest
from django.urls import reverse

from apps.accounts.models import Role, User

pytestmark = pytest.mark.django_db

ADMIN_GET_ROUTES = [
    "useradmin:user_list",
    "useradmin:user_create",
]


@pytest.mark.parametrize("route", ADMIN_GET_ROUTES)
def test_normal_user_is_denied_admin_screens(client_as_user, route):
    assert client_as_user.get(reverse(route)).status_code == 403


@pytest.mark.parametrize("route", ADMIN_GET_ROUTES)
def test_plain_admin_is_denied_super_admin_screens(client, admin_user, route):
    client.force_login(admin_user)
    assert client.get(reverse(route)).status_code == 403


@pytest.mark.parametrize("route", ADMIN_GET_ROUTES)
def test_super_admin_is_allowed(client_as_super, route):
    assert client_as_super.get(reverse(route)).status_code == 200


def test_anonymous_is_redirected_not_403(client):
    response = client.get(reverse("useradmin:user_list"))
    assert response.status_code == 302
    assert "/login/" in response.url


def test_normal_user_cannot_mutate_other_accounts(client_as_user, admin_user):
    assert client_as_user.post(reverse("useradmin:user_toggle", args=[admin_user.pk])).status_code == 403
    assert client_as_user.post(reverse("useradmin:user_delete", args=[admin_user.pk])).status_code == 403
    assert client_as_user.get(reverse("useradmin:user_edit", args=[admin_user.pk])).status_code == 403


def test_super_admin_cannot_modify_own_account_through_admin(client_as_super, super_admin):
    assert client_as_super.get(reverse("useradmin:user_edit", args=[super_admin.pk])).status_code == 403
    assert client_as_super.post(reverse("useradmin:user_toggle", args=[super_admin.pk])).status_code == 403


def test_role_rank_ordering():
    assert User(role=Role.SUPER_ADMIN).rank > User(role=Role.ADMIN).rank
    assert User(role=Role.ADMIN).rank > User(role=Role.USER).rank


def test_has_role_at_least():
    admin = User(role=Role.ADMIN)
    assert admin.has_role_at_least(Role.USER)
    assert admin.has_role_at_least(Role.ADMIN)
    assert not admin.has_role_at_least(Role.SUPER_ADMIN)


def test_role_drives_staff_flags(db):
    user = User.objects.create_user(
        email="flags@rankvista.test", username="flags", password="Fl4gsPass!123", role=Role.USER
    )
    assert not user.is_staff and not user.is_superuser

    user.role = Role.SUPER_ADMIN
    user.save()
    user.refresh_from_db()
    assert user.is_staff and user.is_superuser


def test_toggle_and_delete_require_post(client_as_super, normal_user):
    assert client_as_super.get(reverse("useradmin:user_toggle", args=[normal_user.pk])).status_code == 405
    assert client_as_super.get(reverse("useradmin:user_delete", args=[normal_user.pk])).status_code == 405


def test_missing_user_returns_404(client_as_super):
    assert client_as_super.get(reverse("useradmin:user_edit", args=[999999])).status_code == 404
