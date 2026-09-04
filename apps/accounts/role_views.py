"""Role administration: create, edit and toggle page permissions."""

from __future__ import annotations

from django import forms
from django.contrib import messages
from django.core.exceptions import PermissionDenied
from django.http import Http404, HttpRequest, HttpResponse, JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.views.decorators.http import require_POST

from apps.accounts import pages as page_registry
from apps.accounts import roles as role_service
from apps.accounts.models import User
from apps.accounts.permissions import super_admin_required
from apps.accounts.role_models import RoleDefinition, RolePermission
from apps.audit.models import AuditAction
from apps.audit.services import record
from apps.common.modals import is_modal, redirect_response, render_modal

INPUT_CLASS = "rv-input"


class RoleForm(forms.ModelForm):
    """Create or edit a role. System roles keep their code and minimum rank."""

    class Meta:
        model = RoleDefinition
        fields = ["label", "code", "description", "rank", "is_active"]
        widgets = {
            "label": forms.TextInput(attrs={"class": INPUT_CLASS, "placeholder": "Analyst"}),
            "code": forms.TextInput(attrs={"class": INPUT_CLASS, "placeholder": "ANALYST"}),
            "description": forms.TextInput(
                attrs={"class": INPUT_CLASS, "placeholder": "What this role is for"}
            ),
            "rank": forms.NumberInput(attrs={"class": INPUT_CLASS, "min": 1, "max": 100}),
            "is_active": forms.CheckboxInput(attrs={"class": "rv-check"}),
        }
        help_texts = {"rank": "Higher outranks lower. Super Admin is 30."}

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        if self.instance.pk and self.instance.is_system:
            self.fields["code"].disabled = True
            self.fields["is_active"].disabled = True

    def clean_code(self) -> str:
        if self.instance.pk and self.instance.is_system:
            return self.instance.code
        code = (self.cleaned_data["code"] or "").strip().upper().replace(" ", "_")
        if not code.replace("_", "").isalnum():
            raise forms.ValidationError("A role code is letters, digits and underscores only.")
        clash = RoleDefinition.objects.filter(code=code)
        if self.instance.pk:
            clash = clash.exclude(pk=self.instance.pk)
        if clash.exists():
            raise forms.ValidationError("This role code is already in use.")
        return code

    def clean_rank(self) -> int:
        rank = int(self.cleaned_data["rank"])
        if self.instance.pk and self.instance.is_system:
            # Demoting a built-in role below its baseline would lock people out.
            from apps.accounts.models import ROLE_RANK

            baseline = ROLE_RANK.get(self.instance.code)
            if baseline and rank != baseline:
                raise forms.ValidationError(
                    f"{self.instance.label} is a built-in role and stays at rank {baseline}."
                )
        if not 1 <= rank <= 100:
            raise forms.ValidationError("Rank must be between 1 and 100.")
        return rank


def _role(pk: str) -> RoleDefinition:
    from bson.errors import InvalidId
    from bson.objectid import ObjectId

    try:
        ObjectId(str(pk))
    except (InvalidId, TypeError):
        raise Http404("No such role.") from None
    return get_object_or_404(RoleDefinition, pk=pk)


def _ensure_seeded() -> None:
    """Seed the built-in roles the first time the screen is opened."""
    if not RoleDefinition.objects.exists():
        from django.core.management import call_command

        call_command("sync_roles", verbosity=0)


@super_admin_required
def role_list(request: HttpRequest) -> HttpResponse:
    _ensure_seeded()

    definitions = list(RoleDefinition.objects.prefetch_related("permissions"))
    definitions.sort(key=lambda row: row.rank, reverse=True)

    counts = {
        row["role"]: row["total"]
        for row in User.objects.filter(is_deleted=False)
        .values("role")
        .annotate(total=__import__("django.db.models", fromlist=["Count"]).Count("id"))
    }

    grants = {
        role.code: {p.page_key: p.allowed for p in role.permissions.all()}
        for role in definitions
    }

    rows = []
    for item in page_registry.PAGES:
        rows.append(
            {
                "page": item,
                "cells": [
                    {
                        "role": role,
                        "allowed": grants.get(role.code, {}).get(item.key, item.allows(role.code)),
                        "locked": role.is_system and role.code == "SUPER_ADMIN",
                    }
                    for role in definitions
                ],
            }
        )

    return render(
        request,
        "accounts/role_list.html",
        {
            "definitions": definitions,
            "matrix": rows,
            "total_users": sum(counts.values()),
            "counts": counts,
            "active_nav": "roles",
        },
    )


@super_admin_required
def role_create(request: HttpRequest) -> HttpResponse:
    form = RoleForm(request.POST or None)
    if request.method == "POST" and form.is_valid():
        role = form.save()
        # A new role starts with the same grants as the lowest built-in role.
        for item in page_registry.PAGES:
            RolePermission.objects.create(
                role=role, page_key=item.key, allowed=item.allows("USER")
            )
        role_service.invalidate()
        record(AuditAction.ROLE_CHANGED, request=request, target=role.code, detail="created")
        messages.success(request, f"Role '{role.label}' created.")
        target = reverse("useradmin:role_list")
        return redirect_response(target) if is_modal(request) else redirect(target)

    if is_modal(request):
        return render_modal(
            request,
            form=form,
            action=reverse("useradmin:role_create"),
            title="Create role",
            subtitle="Define a new access level",
            submit_label="Create role",
            wide_fields=("description",),
            status=422 if request.method == "POST" else 200,
        )
    return redirect(reverse("useradmin:role_list"))


@super_admin_required
def role_edit(request: HttpRequest, pk: str) -> HttpResponse:
    role = _role(pk)
    form = RoleForm(request.POST or None, instance=role)
    if request.method == "POST" and form.is_valid():
        form.save()
        role_service.invalidate()
        record(AuditAction.ROLE_CHANGED, request=request, target=role.code, detail="updated")
        messages.success(request, f"Role '{role.label}' updated.")
        target = reverse("useradmin:role_list")
        return redirect_response(target) if is_modal(request) else redirect(target)

    if is_modal(request):
        return render_modal(
            request,
            form=form,
            action=reverse("useradmin:role_edit", args=[pk]),
            title="Edit role",
            subtitle=role.label,
            submit_label="Save changes",
            wide_fields=("description",),
            status=422 if request.method == "POST" else 200,
        )
    return redirect(reverse("useradmin:role_list"))


@require_POST
@super_admin_required
def role_permission_toggle(request: HttpRequest, pk: str) -> HttpResponse:
    """Flip one page grant for one role. Answers the toggle switch directly."""
    role = _role(pk)
    page_key = request.POST.get("page_key", "")
    allowed = request.POST.get("allowed") == "true"

    try:
        page = page_registry.page(page_key)
    except KeyError:
        raise Http404("No such page.") from None

    if role.code == "SUPER_ADMIN":
        raise PermissionDenied("Super Admin keeps access to every screen.")

    permission, _ = RolePermission.objects.get_or_create(
        role=role, page_key=page_key, defaults={"allowed": allowed}
    )
    if permission.allowed != allowed:
        permission.allowed = allowed
        permission.save(update_fields=["allowed"])

    role_service.invalidate()
    record(
        AuditAction.ROLE_CHANGED,
        request=request,
        target=role.code,
        detail=f"{page.label}={'granted' if allowed else 'revoked'}",
    )
    return JsonResponse({"ok": True, "role": role.code, "page": page_key, "allowed": allowed})


@require_POST
@super_admin_required
def role_delete(request: HttpRequest, pk: str) -> HttpResponse:
    role = _role(pk)
    if role.is_system:
        raise PermissionDenied("Built-in roles cannot be deleted.")
    if role.member_count:
        messages.error(
            request, f"'{role.label}' still has {role.member_count} user(s). Reassign them first."
        )
        return redirect(reverse("useradmin:role_list"))

    label = role.label
    role.delete()
    role_service.invalidate()
    record(AuditAction.ROLE_CHANGED, request=request, target=label, detail="deleted")
    messages.success(request, f"Role '{label}' deleted.")
    return redirect(reverse("useradmin:role_list"))
