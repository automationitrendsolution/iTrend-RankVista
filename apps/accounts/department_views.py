"""Department administration and the role overview, restricted to super admins."""

from __future__ import annotations

from django.contrib import messages
from django.db.models import Count, Q
from django.http import Http404, HttpRequest, HttpResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.views.decorators.http import require_POST

from apps.accounts.forms import DepartmentForm
from apps.accounts.models import Department, Role, User
from apps.accounts.permissions import super_admin_required
from apps.audit.models import AuditAction
from apps.audit.services import record
from apps.common.pagination import parse_page_request

DEPARTMENT_SORT = {
    "name": "name",
    "-name": "-name",
    "members": "member_total",
    "-members": "-member_total",
    "recent": "-created_at",
}


def _department(pk: str) -> Department:
    from bson.errors import InvalidId
    from bson.objectid import ObjectId

    try:
        ObjectId(str(pk))
    except (InvalidId, TypeError):
        raise Http404("No such department.") from None
    return get_object_or_404(Department, pk=pk)


@super_admin_required
def department_list(request: HttpRequest) -> HttpResponse:
    search = request.GET.get("q", "").strip()
    status = request.GET.get("status", "")
    sort = request.GET.get("sort", "name")

    queryset = Department.objects.annotate(
        member_total=Count("members", filter=Q(members__is_deleted=False))
    )
    if search:
        queryset = queryset.filter(Q(name__icontains=search) | Q(code__icontains=search))
    if status == "active":
        queryset = queryset.filter(is_active=True)
    elif status == "inactive":
        queryset = queryset.filter(is_active=False)
    queryset = queryset.order_by(DEPARTMENT_SORT.get(sort, "name"))

    page_req = parse_page_request(request)
    total = queryset.count()
    rows = list(queryset[page_req.offset : page_req.offset + page_req.limit])

    context = {
        "page_obj": page_req.build(rows, total),
        "search": search,
        "status": status,
        "sort": sort,
        "stats": {
            "total": Department.objects.count(),
            "active": Department.objects.filter(is_active=True).count(),
            "unassigned": User.objects.filter(is_deleted=False, department__isnull=True).count(),
        },
        "active_nav": "departments",
    }
    template = (
        "accounts/partials/department_table.html" if request.htmx else "accounts/department_list.html"
    )
    return render(request, template, context)


@super_admin_required
def department_create(request: HttpRequest) -> HttpResponse:
    form = DepartmentForm(request.POST or None)
    if request.method == "POST" and form.is_valid():
        department = form.save()
        record(
            AuditAction.DEPARTMENT_CREATED,
            request=request,
            target=department.name,
            detail=department.code,
        )
        messages.success(request, f"Department '{department.name}' created.")
        return redirect(reverse("useradmin:department_list"))
    return render(
        request,
        "accounts/department_form.html",
        {"form": form, "mode": "create", "active_nav": "departments"},
    )


@super_admin_required
def department_edit(request: HttpRequest, pk: str) -> HttpResponse:
    department = _department(pk)
    form = DepartmentForm(request.POST or None, instance=department)
    if request.method == "POST" and form.is_valid():
        form.save()
        record(AuditAction.DEPARTMENT_UPDATED, request=request, target=department.name)
        messages.success(request, f"Department '{department.name}' updated.")
        return redirect(reverse("useradmin:department_list"))
    return render(
        request,
        "accounts/department_form.html",
        {
            "form": form,
            "mode": "edit",
            "department": department,
            "members": department.members.filter(is_deleted=False).order_by("username")[:25],
            "active_nav": "departments",
        },
    )


@require_POST
@super_admin_required
def department_toggle(request: HttpRequest, pk: str) -> HttpResponse:
    department = _department(pk)
    department.is_active = not department.is_active
    department.save(update_fields=["is_active", "updated_at"])
    record(
        AuditAction.DEPARTMENT_UPDATED,
        request=request,
        target=department.name,
        detail="activated" if department.is_active else "deactivated",
    )
    messages.success(
        request, f"{department.name} {'activated' if department.is_active else 'deactivated'}."
    )
    return redirect(reverse("useradmin:department_list"))


@require_POST
@super_admin_required
def department_delete(request: HttpRequest, pk: str) -> HttpResponse:
    department = _department(pk)
    name = department.name
    # Members are detached rather than deleted; SET_NULL keeps the accounts intact.
    department.delete()
    record(AuditAction.DEPARTMENT_DELETED, request=request, target=name)
    messages.success(request, f"Department '{name}' deleted. Members were left in place.")
    return redirect(reverse("useradmin:department_list"))


@super_admin_required
def role_list(request: HttpRequest) -> HttpResponse:
    """Roles are enforced in code; this screen documents them and who holds them."""
    from apps.accounts.models import ROLE_RANK

    descriptions = {
        Role.SUPER_ADMIN: "Full platform access, including user and department administration.",
        Role.ADMIN: "Full access to project, ASIN, keyword and ranking data. No user administration.",
        Role.USER: "Read and analyse project data. Cannot administer the platform.",
    }
    capabilities = {
        Role.SUPER_ADMIN: ["View all data", "Create & edit projects", "Manage users", "Manage departments"],
        Role.ADMIN: ["View all data", "Create & edit projects"],
        Role.USER: ["View all data"],
    }

    counts = {
        row["role"]: row["total"]
        for row in User.objects.filter(is_deleted=False).values("role").annotate(total=Count("id"))
    }

    roles = [
        {
            "value": value,
            "label": label,
            "rank": ROLE_RANK.get(value, 0),
            "description": descriptions.get(value, ""),
            "capabilities": capabilities.get(value, []),
            "members": counts.get(value, 0),
        }
        for value, label in Role.choices
    ]
    roles.sort(key=lambda role: role["rank"], reverse=True)

    return render(
        request,
        "accounts/role_list.html",
        {"roles": roles, "total_users": sum(counts.values()), "active_nav": "roles"},
    )
