"""Database-backed roles and per-page permissions.
System roles cannot be deleted or demoted below their built-in rank."""

from __future__ import annotations

from django.db import models
from django.utils import timezone


class RoleDefinition(models.Model):
    """An assignable role. `code` is what User.role stores."""

    code = models.CharField(max_length=32, unique=True)
    label = models.CharField(max_length=80)
    description = models.CharField(max_length=300, blank=True)
    rank = models.PositiveIntegerField(
        default=10, help_text="Higher outranks lower. Used by has_role_at_least."
    )
    is_system = models.BooleanField(default=False, db_index=True)
    is_active = models.BooleanField(default=True, db_index=True)
    created_at = models.DateTimeField(default=timezone.now)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-rank", "label"]

    def __str__(self) -> str:
        return self.label

    def save(self, *args, **kwargs):
        self.code = self.code.strip().upper().replace(" ", "_")
        self.label = self.label.strip()
        super().save(*args, **kwargs)

    @property
    def member_count(self) -> int:
        from apps.accounts.models import User

        return User.objects.filter(role=self.code, is_deleted=False).count()

    def allowed_pages(self) -> set[str]:
        return set(
            self.permissions.filter(allowed=True).values_list("page_key", flat=True)
        )


class RolePermission(models.Model):
    """One page grant for one role."""

    role = models.ForeignKey(
        RoleDefinition, on_delete=models.CASCADE, related_name="permissions"
    )
    page_key = models.CharField(max_length=64, db_index=True)
    allowed = models.BooleanField(default=False)

    class Meta:
        ordering = ["page_key"]
        constraints = [
            models.UniqueConstraint(fields=["role", "page_key"], name="uq_role_page")
        ]

    def __str__(self) -> str:
        return f"{self.role.code}:{self.page_key}={self.allowed}"
