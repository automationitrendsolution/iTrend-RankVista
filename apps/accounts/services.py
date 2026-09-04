"""User lifecycle operations shared by the SaaS admin UI and management commands.
Each function audits its own outcome and never logs or returns a password."""

from __future__ import annotations

from django.db import transaction
from django.http import HttpRequest
from django.utils import timezone

from apps.accounts.models import Role, User
from apps.audit.models import AuditAction
from apps.audit.services import record


@transaction.atomic
def create_user(*, form, actor: User, request: HttpRequest | None = None) -> User:
    user = form.save(commit=False)
    user.created_by = actor
    user.save()
    record(
        AuditAction.USER_CREATED,
        request=request,
        actor=actor,
        target=user.email,
        detail=f"role={user.role}",
    )
    return user


@transaction.atomic
def update_user(*, form, actor: User, request: HttpRequest | None = None) -> User:
    previous_role = User.objects.values_list("role", flat=True).get(pk=form.instance.pk)
    user = form.save()
    record(
        AuditAction.USER_UPDATED,
        request=request,
        actor=actor,
        target=user.email,
        detail="profile updated",
    )
    if previous_role != user.role:
        record(
            AuditAction.ROLE_CHANGED,
            request=request,
            actor=actor,
            target=user.email,
            detail=f"{previous_role} -> {user.role}",
        )
    return user


@transaction.atomic
def set_active(*, user: User, active: bool, actor: User, request: HttpRequest | None = None) -> User:
    user.is_active = active
    user.deactivated_at = None if active else timezone.now()
    user.save(update_fields=["is_active", "deactivated_at", "is_staff", "is_superuser"])
    record(
        AuditAction.USER_ACTIVATED if active else AuditAction.USER_DEACTIVATED,
        request=request,
        actor=actor,
        target=user.email,
    )
    return user


@transaction.atomic
def reset_password(
    *, user: User, raw_password: str, actor: User, request: HttpRequest | None = None
) -> User:
    user.set_password(raw_password)
    user.save(update_fields=["password"])
    record(AuditAction.PASSWORD_RESET, request=request, actor=actor, target=user.email)
    return user


@transaction.atomic
def soft_delete(*, user: User, actor: User, request: HttpRequest | None = None) -> User:
    """Deactivate and tombstone a user, freeing the email and username."""
    stamp = int(timezone.now().timestamp())
    original_email = user.email
    user.is_active = False
    user.is_deleted = True
    user.deactivated_at = timezone.now()
    user.email = f"deleted+{stamp}.{user.pk}@rankvista.invalid"
    user.username = f"deleted_{stamp}_{user.pk}"
    user.set_unusable_password()
    user.save()
    record(AuditAction.USER_DELETED, request=request, actor=actor, target=original_email)
    return user


def can_modify(actor: User, target: User) -> bool:
    """Guard used by every admin endpoint before mutating another account."""
    return actor.can_manage(target)


def role_options(actor: User) -> list[tuple[str, str]]:
    """Roles an actor may assign, capped at their own privilege level."""
    return [(value, label) for value, label in Role.choices if actor.has_role_at_least(value)]
