"""Read-side queries for user administration.
Filtering, searching and ordering are pushed into the database, never Python."""

from __future__ import annotations

from django.db.models import Q, QuerySet

from apps.accounts.models import Role, User

USER_SORT_FIELDS = {
    "recent": "-date_joined",
    "oldest": "date_joined",
    "name": "username",
    "email": "email",
    "last_login": "-last_login",
    "role": "role",
}
DEFAULT_USER_SORT = "recent"


def list_users(
    *,
    search: str = "",
    role: str = "",
    status: str = "",
    sort: str = DEFAULT_USER_SORT,
    include_deleted: bool = False,
) -> QuerySet[User]:
    qs = User.objects.select_related("department")
    if not include_deleted:
        qs = qs.filter(is_deleted=False)

    if search:
        term = search.strip()
        qs = qs.filter(
            Q(email__icontains=term) | Q(username__icontains=term) | Q(full_name__icontains=term)
        )
    if role and role in Role.values:
        qs = qs.filter(role=role)
    if status == "active":
        qs = qs.filter(is_active=True)
    elif status == "inactive":
        qs = qs.filter(is_active=False)

    return qs.order_by(USER_SORT_FIELDS.get(sort, USER_SORT_FIELDS[DEFAULT_USER_SORT]), "-id")


def user_stats() -> dict[str, int]:
    """Counter row shown above the user table."""
    qs = User.objects.filter(is_deleted=False)
    return {
        "total": qs.count(),
        "active": qs.filter(is_active=True).count(),
        "inactive": qs.filter(is_active=False).count(),
        "admins": qs.filter(role__in=[Role.SUPER_ADMIN, Role.ADMIN]).count(),
    }
