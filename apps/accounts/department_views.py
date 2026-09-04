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
from apps.common.htmx import is_partial
from apps.common.modals import is_modal, redirect_response, render_modal
from apps.common.validation import bind, touched_fields, validate_response
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
        "accounts/partials/department_table.html" if is_partial(request) else "accounts/department_list.html"
    )
    return render(request, template, context)


@require_POST
@super_admin_required
def department_validate(request: HttpRequest) -> HttpResponse:
    """Validate the department form as it is typed, including uniqueness."""
    pk = request.POST.get("_pk") or ""
    instance = _department(pk) if pk else None
    return validate_response(
        bind(DepartmentForm, request, instance=instance), touched=touched_fields(request)
    )


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
        target = reverse("useradmin:department_list")
        return redirect_response(target) if is_modal(request) else redirect(target)

    if is_modal(request):
        return render_modal(
            request,
            form=form,
            action=reverse("useradmin:department_create"),
            validate_url=reverse("useradmin:department_validate"),
            title="Create department",
            subtitle="Group users by team",
            submit_label="Create department",
            wide_fields=("description",),
            status=422 if request.method == "POST" else 200,
        )
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
        target = reverse("useradmin:department_list")
        return redirect_response(target) if is_modal(request) else redirect(target)

    if is_modal(request):
        return render_modal(
            request,
            form=form,
            action=reverse("useradmin:department_edit", args=[pk]),
            validate_url=reverse("useradmin:department_validate"),
            validate_pk=str(pk),
            title="Edit department",
            subtitle=department.name,
            submit_label="Save changes",
            wide_fields=("description",),
            status=422 if request.method == "POST" else 200,
        )
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
