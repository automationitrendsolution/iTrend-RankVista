"""Shared fixtures. Mongo-backed tests run against an isolated throwaway database."""

from __future__ import annotations

import os
import uuid
from datetime import datetime, timedelta, timezone

import pytest
from django.test import Client

from apps.accounts.models import Role, User


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
def mongo_db(settings):
    """Point the repositories at a disposable database, dropped after the test."""
    from apps.common import mongo

    pytest.importorskip("pymongo")
    mongo.reset_client()
    if not mongo.ping():
        pytest.skip("MongoDB is not reachable; skipping data-layer test.")

    name = f"rankvista_test_{uuid.uuid4().hex[:10]}"
    settings.MONGODB = {**settings.MONGODB, "DATABASE": name}
    mongo.reset_client()

    from apps.common.schema import ensure_indexes

    ensure_indexes()
    yield mongo.get_database()

    mongo.get_client().drop_database(name)
    mongo.reset_client()


@pytest.fixture
def seeded_project(mongo_db):
    """One project with one ASIN, three keywords and ten days of ranks."""
    from apps.common.schema import ASINS, KEYWORDS, PROJECTS, RANKINGS

    now = datetime.now(timezone.utc).replace(hour=0, minute=0, second=0, microsecond=0)
    project_id, asin = 90001, "B0TESTASIN"

    mongo_db[PROJECTS].insert_one(
        {
            "project_id": project_id,
            "name": "Test Snow Cover",
            "name_lower": "test snow cover",
            "marketplace": "US",
            "primary_asin": asin,
            "image_url": "",
            "asin_count": 1,
            "keyword_count": 3,
            "status": "active",
            "owner_id": None,
            "tags": [],
            "created_at": now,
            "updated_at": now,
            "last_opened_at": now,
        }
    )
    mongo_db[ASINS].insert_one(
        {
            "project_id": project_id,
            "asin": asin,
            "title": "Test Windshield Cover",
            "image_url": "",
            "marketplace": "US",
            "brand": "iTrend Labs",
            "price": 24.99,
            "is_primary": True,
            "status": "active",
            "tracked_keyword_count": 3,
            "created_at": now,
            "updated_at": now,
        }
    )

    keywords = [
        ("snow cover", 12, 250.0, 18.5, 2),
        ("windshield cover", 5, -20.0, 9.1, 14),
        ("ice cover", 0, 0.0, 0.0, 88),
    ]
    for keyword, sales, trend, conversion, rank in keywords:
        mongo_db[KEYWORDS].insert_one(
            {
                "project_id": project_id,
                "asin": asin,
                "keyword": keyword,
                "keyword_lower": keyword,
                "search_volume": 5000,
                "kw_sales": sales,
                "sales_trend_pct": trend,
                "conversion_pct": conversion,
                "is_tracked": True,
                "current_rank": rank,
                "best_rank": rank,
                "created_at": now,
                "updated_at": now,
            }
        )
        mongo_db[RANKINGS].insert_many(
            [
                {
                    "project_id": project_id,
                    "asin": asin,
                    "keyword": keyword,
                    "keyword_lower": keyword,
                    "date": now - timedelta(days=offset),
                    "rank": rank + offset,
                    "is_amazon_choice": offset == 0 and rank <= 3,
                    "is_sponsored": False,
                    "page": 1,
                }
                for offset in range(10)
            ]
        )

    return {"project_id": project_id, "asin": asin}
