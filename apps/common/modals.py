"""Helpers for rendering create/edit forms inside a modal.
An HTMX post re-renders the modal on error and returns HX-Redirect on success."""

from __future__ import annotations

from typing import Any

from django.http import HttpRequest, HttpResponse
from django.shortcuts import render


def render_modal(
    request: HttpRequest,
    *,
    form,
    action: str,
    title: str,
    submit_label: str = "Save",
    subtitle: str = "",
    size: str = "",
    wide_fields: tuple[str, ...] = (),
    validate_url: str = "",
    validate_pk: str = "",
    extra: dict[str, Any] | None = None,
    status: int = 200,
) -> HttpResponse:
    context = {
        "validate_url": validate_url,
        "validate_pk": validate_pk,
        "form": form,
        "form_action": action,
        "modal_title": title,
        "modal_subtitle": subtitle,
        "modal_size": size,
        "submit_label": submit_label,
        "wide_fields": wide_fields,
        **(extra or {}),
    }
    return render(request, "partials/form_modal.html", context, status=status)


def redirect_response(url: str) -> HttpResponse:
    """Tell HTMX to navigate after a successful modal submit."""
    response = HttpResponse(status=204)
    response["HX-Redirect"] = url
    return response


def is_modal(request: HttpRequest) -> bool:
    """A modal submit is a targeted HTMX request.
    A boosted navigation is excluded: it expects a whole page."""
    from apps.common.htmx import is_partial

    return is_partial(request)
