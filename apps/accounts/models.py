"""Custom user model with role-based access control.
Roles are ordered by privilege so future roles slot in without code churn."""

from __future__ import annotations

from django.contrib.auth.models import AbstractBaseUser, BaseUserManager, PermissionsMixin
from django.db import models
from django.utils import timezone


class Role(models.TextChoices):
    SUPER_ADMIN = "SUPER_ADMIN", "Super Admin"
    ADMIN = "ADMIN", "Admin"
    USER = "USER", "User"


# Higher number = more privilege. New roles are added here only.
ROLE_RANK: dict[str, int] = {
    Role.USER: 10,
    Role.ADMIN: 20,
    Role.SUPER_ADMIN: 30,
}


class Department(models.Model):
    """An organisational unit a user belongs to. Managed from the admin UI."""

    name = models.CharField(max_length=120, unique=True)
    code = models.CharField(max_length=24, unique=True)
    description = models.CharField(max_length=300, blank=True)
    is_active = models.BooleanField(default=True, db_index=True)
    created_at = models.DateTimeField(default=timezone.now)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["name"]

    def __str__(self) -> str:
        return self.name

    def save(self, *args, **kwargs):
        self.code = self.code.strip().upper()
        self.name = self.name.strip()
        super().save(*args, **kwargs)

    @property
    def member_count(self) -> int:
        return self.members.filter(is_deleted=False).count()


class UserManager(BaseUserManager):
    """Manager that normalises email and always hashes passwords."""

    use_in_migrations = True

    def _create_user(self, email: str, username: str, password: str | None, **extra):
        if not email:
            raise ValueError("An email address is required.")
        if not username:
            raise ValueError("A username is required.")
        user = self.model(
            email=self.normalize_email(email).lower(),
            username=username.strip(),
            **extra,
        )
        user.set_password(password)
        user.full_clean(exclude=["password"])
        user.save(using=self._db)
        return user

    def create_user(self, email: str, username: str, password: str | None = None, **extra):
        extra.setdefault("role", Role.USER)
        extra.setdefault("is_staff", False)
        extra.setdefault("is_superuser", False)
        return self._create_user(email, username, password, **extra)

    def create_superuser(self, email: str, username: str, password: str | None = None, **extra):
        extra.setdefault("role", Role.SUPER_ADMIN)
        extra.setdefault("is_staff", True)
        extra.setdefault("is_superuser", True)
        extra.setdefault("is_active", True)
        if extra.get("is_staff") is not True or extra.get("is_superuser") is not True:
            raise ValueError("A superuser must have is_staff and is_superuser set to True.")
        return self._create_user(email, username, password, **extra)

    def active(self):
        return self.get_queryset().filter(is_active=True, is_deleted=False)


class User(AbstractBaseUser, PermissionsMixin):
    """Platform user. Email is the login identifier; username stays unique."""

    email = models.EmailField("email address", unique=True, max_length=254)
    username = models.CharField(max_length=150, unique=True)
    full_name = models.CharField(max_length=180, blank=True)
    role = models.CharField(max_length=32, choices=Role.choices, default=Role.USER, db_index=True)

    is_active = models.BooleanField(default=True, db_index=True)
    is_staff = models.BooleanField(default=False)
    is_deleted = models.BooleanField(default=False, db_index=True)

    date_joined = models.DateTimeField(default=timezone.now)
    deactivated_at = models.DateTimeField(null=True, blank=True)
    last_login_ip = models.GenericIPAddressField(null=True, blank=True)

    department = models.ForeignKey(
        Department,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="members",
    )
    job_title = models.CharField(max_length=120, blank=True)

    created_by = models.ForeignKey(
        "self", null=True, blank=True, on_delete=models.SET_NULL, related_name="created_users"
    )

    objects = UserManager()

    USERNAME_FIELD = "email"
    REQUIRED_FIELDS = ["username"]

    class Meta:
        ordering = ["-date_joined"]
        indexes = [
            models.Index(fields=["role", "is_active"], name="ix_user_role_active"),
            models.Index(fields=["is_deleted", "-date_joined"], name="ix_user_deleted_joined"),
        ]

    def __str__(self) -> str:
        return self.email

    def save(self, *args, **kwargs):
        self.email = self.email.lower().strip()
        # Django admin access mirrors the platform role, never set by hand.
        self.is_staff = self.role in {Role.SUPER_ADMIN, Role.ADMIN}
        self.is_superuser = self.role == Role.SUPER_ADMIN
        super().save(*args, **kwargs)

    @property
    def display_name(self) -> str:
        return self.full_name.strip() or self.username

    @property
    def initials(self) -> str:
        source = self.full_name.strip() or self.username
        parts = [p for p in source.replace(".", " ").split() if p]
        if not parts:
            return "?"
        if len(parts) == 1:
            return parts[0][:2].upper()
        return (parts[0][0] + parts[-1][0]).upper()

    @property
    def rank(self) -> int:
        # Imported lazily: the role table itself lives in this module tree.
        from apps.accounts import roles as role_service

        return role_service.rank(self.role)

    @property
    def is_super_admin(self) -> bool:
        return self.role == Role.SUPER_ADMIN

    @property
    def is_admin(self) -> bool:
        return self.role in {Role.SUPER_ADMIN, Role.ADMIN}

    def has_role_at_least(self, role: str) -> bool:
        from apps.accounts import roles as role_service

        return self.rank >= role_service.rank(role)

    def can_manage(self, other: User) -> bool:
        """Only a super admin manages users, and never one outranking them."""
        if not self.is_super_admin or self.pk == other.pk:
            return False
        return self.rank >= other.rank


# Roles and their page permissions are stored alongside the user model.
from apps.accounts.role_models import RoleDefinition, RolePermission  # noqa: E402,F401
