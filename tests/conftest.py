"""Shared fixtures.
Warehouse-backed tests run read-only against the configured source and skip when absent."""

from __future__ import annotations

import pytest
from django.core.cache import cache
from django.test import Client

from apps.accounts.models import Role, User


@pytest.fixture(autouse=True)
def isolated_mongo(settings):
    """Point the overlay at a throwaway database.
    Without this the suite writes project overlays into the live database."""
    import uuid

    from apps.common import mongo

    name = f"rankvista_test_{uuid.uuid4().hex[:10]}"
    settings.MONGODB = {**settings.MONGODB, "DATABASE": name}
    mongo.reset_client()
    yield
    try:
        mongo.get_client().drop_database(name)
    except Exception:
        pass
    mongo.reset_client()


@pytest.fixture(autouse=True)
def clear_cache(settings):
    """Isolate cached warehouse aggregates so one test never leaks into the next."""
    settings.CACHES = {
        "default": {
            "BACKEND": "django.core.cache.backends.locmem.LocMemCache",
            "LOCATION": "rankvista-tests",
        }
    }
    cache.clear()
    yield
    cache.clear()


@pytest.fixture
def super_admin(db) -> User:
    return User.objects.create_user(
        email="super@rankvista.test",
        username="superadmin",
        password="Sup3rSecret!Pass",
        role=Role.SUPER_ADMIN,
    )


@pytest.fixture
def admin_user(db) -> User:
    return User.objects.create_user(
        email="admin@rankvista.test",
        username="adminuser",
        password="Adm1nSecret!Pass",
        role=Role.ADMIN,
    )


@pytest.fixture
def normal_user(db) -> User:
    return User.objects.create_user(
        email="user@rankvista.test",
        username="normaluser",
        password="Us3rSecret!Pass",
        role=Role.USER,
    )


@pytest.fixture
def inactive_user(db) -> User:
    return User.objects.create_user(
        email="inactive@rankvista.test",
        username="inactiveuser",
        password="Us3rSecret!Pass",
        role=Role.USER,
        is_active=False,
    )


@pytest.fixture
def client_as_super(client: Client, super_admin: User) -> Client:
    client.force_login(super_admin)
    return client


@pytest.fixture
def client_as_user(client: Client, normal_user: User) -> Client:
    client.force_login(normal_user)
    return client


@pytest.fixture
def client_as_admin(client: Client, admin_user: User) -> Client:
    client.force_login(admin_user)
    return client


@pytest.fixture
def warehouse():
    """Skip the test unless the read-only rank warehouse is reachable."""
    from apps.common import sourcedb

    if not sourcedb.is_enabled():
        pytest.skip("SOURCE_DB is not configured.")
    if not sourcedb.ping():
        pytest.skip("The rank warehouse is unreachable.")
    return sourcedb


@pytest.fixture
def live_project(warehouse, db):
    """The busiest real project, with its primary ASIN. Read-only."""
    from apps.asins import repositories as asin_repo
    from apps.projects import repositories as repo

    projects, total = repo.list_projects(
        query=repo.build_filter(), sort="keywords_desc", offset=0, limit=1
    )
    if not projects:
        pytest.skip("The warehouse holds no projects.")

    project = projects[0]
    asin = asin_repo.default_asin(project["project_id"])
    if not asin:
        pytest.skip("The selected project has no ASINs.")

    return {"project_id": project["project_id"], "asin": asin, "project": project, "total": total}
