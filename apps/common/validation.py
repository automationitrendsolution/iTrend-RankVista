"""Live field validation for modal forms.
The same Django form validates, so the browser never duplicates a rule."""

from __future__ import annotations

from typing import Any

from django.http import HttpRequest, JsonResponse


def validate_response(form, *, touched: set[str] | None = None) -> JsonResponse:
    """Report per-field errors for the fields the user has actually touched.
    Untouched fields stay quiet so a blank form is not a wall of red."""
    form.is_valid()

    errors: dict[str, str] = {}
    valid: list[str] = []
    for name in form.fields:
        if touched is not None and name not in touched:
            continue
        field_errors = form.errors.get(name)
        if field_errors:
            errors[name] = field_errors[0]
        elif form.data.get(name):
            valid.append(name)

    return JsonResponse(
        {
            "errors": errors,
            "valid": valid,
            "non_field": (form.non_field_errors() or [None])[0],
            "ok": not form.errors,
        }
    )


def touched_fields(request: HttpRequest) -> set[str]:
    """Fields the client says the user has interacted with."""
    raw = request.POST.get("_touched", "")
    return {name.strip() for name in raw.split(",") if name.strip()}


def bind(form_class, request: HttpRequest, instance: Any = None):
    kwargs: dict[str, Any] = {"data": request.POST}
    if instance is not None:
        kwargs["instance"] = instance
    return form_class(**kwargs)
