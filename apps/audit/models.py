"""Append-only audit trail for security-relevant actions.
Values are summarised as text; no password, token or cookie is ever stored."""

from __future__ import annotations

from django.conf import settings
from django.db import models


class AuditAction(models.TextChoices):
    LOGIN_SUCCESS = "LOGIN_SUCCESS", "Login succeeded"
    LOGIN_FAILED = "LOGIN_FAILED", "Login failed"
    LOGOUT = "LOGOUT", "Logout"
    USER_CREATED = "USER_CREATED", "User created"
    USER_UPDATED = "USER_UPDATED", "User updated"
    USER_ACTIVATED = "USER_ACTIVATED", "User activated"
    USER_DEACTIVATED = "USER_DEACTIVATED", "User deactivated"
    USER_DELETED = "USER_DELETED", "User deleted"
    ROLE_CHANGED = "ROLE_CHANGED", "Role changed"
    PASSWORD_RESET = "PASSWORD_RESET", "Password reset"
    PASSWORD_CHANGED = "PASSWORD_CHANGED", "Password changed"
    ADMIN_BOOTSTRAPPED = "ADMIN_BOOTSTRAPPED", "Administrator bootstrapped"
    PROJECT_CREATED = "PROJECT_CREATED", "Project created"
    PROJECT_UPDATED = "PROJECT_UPDATED", "Project updated"
    PROJECT_DELETED = "PROJECT_DELETED", "Project deleted"


class AuditLog(models.Model):
    """One immutable record per audited action."""

    action = models.CharField(max_length=48, choices=AuditAction.choices, db_index=True)
    actor = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="audit_entries",
    )
    actor_label = models.CharField(max_length=254, blank=True)
    target = models.CharField(max_length=254, blank=True)
    detail = models.CharField(max_length=500, blank=True)
    ip_address = models.GenericIPAddressField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)

    class Meta:
        ordering = ["-created_at"]
        indexes = [models.Index(fields=["action", "-created_at"], name="ix_audit_action_time")]

    def __str__(self) -> str:
        return f"{self.created_at:%Y-%m-%d %H:%M} {self.action} {self.target}".strip()
