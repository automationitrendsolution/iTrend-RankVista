"""Project screens: grid, detail tabs, ranking matrix and trends.
Views stay thin; querying lives in repositories and selectors."""

from __future__ import annotations

from datetime import timedelta
from typing import Any

from django.contrib import messages
from django.http import Http404, HttpRequest, HttpResponse
from django.shortcuts import redirect, render
from django.urls import reverse
from django.views.decorators.http import require_POST

from apps.accounts.permissions import login_required, page_required
from apps.analytics import charts as chart_builder
from apps.analytics import sales as sales_service
from apps.analytics import services as analytics
from apps.asins import repositories as asin_repo
from apps.common import filters as qp
from apps.common.constants import (
    DATE_RANGE_PRESETS,
    DEFAULT_PROJECT_SORT,
    INTERVALS,
    PROJECT_SORT_OPTIONS,
    marketplace,
)
from apps.common.dates import format_window_label, resolve_window
from apps.common.heatmap import legend as heatmap_legend
from apps.common.sourcedb import SourceUnavailable
from apps.common.htmx import is_partial
from apps.common.modals import is_modal, redirect_response, render_modal
from apps.common.pagination import parse_page_request
from apps.common.validation import touched_fields, validate_response
from apps.keywords import repositories as keyword_repo
from apps.projects import repositories as repo
from apps.projects import services
from apps.projects.forms import ProjectForm
from apps.projects.selectors import require_project, usage_counters
from apps.rankings import repositories as rank_repo
from apps.rankings import selectors as matrix

TAB_PANEL_TARGET = "rv-tab-panel"

PROJECT_FILTER_KEYS = ("q", "marketplace", "status", "min_asins", "min_keywords")
KEYWORD_FILTER_KEYS = ("kq", "tracked", "rank_min", "rank_max", "sales_min", "conv_min")
VIEW_MODES = {"grid", "list"}


def _clamped_window(request: HttpRequest, project_id, asin: str):
    """Resolve the date window, then pull it back to the newest observed date.
    Without this the right-most matrix columns render empty after a sync gap."""
    window = resolve_window(request)
    if not asin:
        return window
    _, newest = rank_repo.available_range(project_id=project_id, asin=asin)
    if newest and newest < window.end:
        span = (window.end - window.start).days
        window.end = newest
        window.start = newest - timedelta(days=span)
    return window


def _tab_render(request: HttpRequest, context: dict, tab: str, inner: str) -> HttpResponse:
    """Pick the narrowest template the request needs: page, tab panel or inner list."""
    panel = f"projects/partials/tab_{tab}.html"
    if not is_partial(request):
        return render(request, f"projects/{tab}.html", context)
    if request.headers.get("HX-Target") == TAB_PANEL_TARGET:
        return render(request, "projects/partials/tab_panel.html", {**context, "panel_template": panel})
    return render(request, inner, context)


def _error_page(request: HttpRequest, message: str, status: int = 503) -> HttpResponse:
    return render(
        request,
        "errors/data_unavailable.html",
        {"message": message, "retry_url": request.get_full_path()},
        status=status,
    )


# --------------------------------------------------------------------------
# Projects grid
# --------------------------------------------------------------------------
@page_required("projects.view")
def project_list(request: HttpRequest) -> HttpResponse:
    search = qp.get_str(request, "q")
    view_mode = qp.get_str(request, "view", "grid", allowed=VIEW_MODES)
    sort = qp.get_str(request, "sort", DEFAULT_PROJECT_SORT)
    page_req = parse_page_request(request)

    query = repo.build_filter(
        search=search,
        marketplace=qp.get_str(request, "marketplace"),
        status=qp.get_str(request, "status"),
        min_asins=qp.get_int(request, "min_asins"),
        min_keywords=qp.get_int(request, "min_keywords"),
    )

    try:
        projects, total = repo.list_projects(
            query=query, sort=sort, offset=page_req.offset, limit=page_req.limit
        )
        counters = usage_counters()
    except SourceUnavailable as exc:
        return _error_page(request, str(exc))

    context = {
        "page_obj": page_req.build(projects, total),
        "counters": counters,
        "search": search,
        "sort": sort,
        "sort_options": PROJECT_SORT_OPTIONS,
        "view_mode": view_mode,
        "marketplaces": repo.distinct_marketplaces(),
        "selected_marketplace": qp.get_str(request, "marketplace"),
        "has_filters": qp.has_active_filters(request, PROJECT_FILTER_KEYS),
        "active_nav": "projects",
    }
    template = "projects/partials/project_results.html" if is_partial(request) else "projects/list.html"
    return render(request, template, context)


@require_POST
@page_required("projects.create")
def project_validate(request: HttpRequest) -> HttpResponse:
    """Validate the project form as it is typed."""
    return validate_response(ProjectForm(request.POST), touched=touched_fields(request))


@page_required("projects.create")
def project_create(request: HttpRequest) -> HttpResponse:
    form = ProjectForm(request.POST or None)
    if request.method == "POST" and form.is_valid():
        try:
            project = services.create_project(data=form.to_document(), request=request)
        except SourceUnavailable as exc:
            return _error_page(request, str(exc))
        messages.success(request, f"Project '{project['name']}' created.")
        target = reverse("projects:detail", args=[project["project_id"]])
        return redirect_response(target) if is_modal(request) else redirect(target)

    if is_modal(request):
        return render_modal(
            request,
            form=form,
            action=reverse("projects:create"),
            validate_url=reverse("projects:validate"),
            title="Create project",
            subtitle="Track a new product line",
            submit_label="Create project",
            wide_fields=("name", "image_url", "tags"),
            status=422 if request.method == "POST" else 200,
        )
    return render(
        request, "projects/form.html", {"form": form, "mode": "create", "active_nav": "projects"}
    )


@page_required("projects.edit")
def project_edit(request: HttpRequest, project_id: int) -> HttpResponse:
    project = require_project(project_id)
    initial = {
        "name": project.get("name", ""),
        "marketplace": project.get("marketplace", "US"),
        "primary_asin": project.get("primary_asin", ""),
        "image_url": project.get("image_url", ""),
        "tags": ", ".join(project.get("tags") or []),
    }
    form = ProjectForm(request.POST or None, initial=initial)
    if request.method == "POST" and form.is_valid():
        try:
            services.update_project(
                project_id=project_id, data=form.to_document(), request=request
            )
        except SourceUnavailable as exc:
            return _error_page(request, str(exc))
        messages.success(request, "Project updated.")
        target = reverse("projects:detail", args=[project_id])
        return redirect_response(target) if is_modal(request) else redirect(target)

    if is_modal(request):
        return render_modal(
            request,
            form=form,
            action=reverse("projects:edit", args=[project_id]),
            validate_url=reverse("projects:validate"),
            title="Edit project",
            subtitle=project.get("name", ""),
            submit_label="Save changes",
            wide_fields=("name", "image_url", "tags"),
            status=422 if request.method == "POST" else 200,
        )
    return render(
        request,
        "projects/form.html",
        {"form": form, "mode": "edit", "project": project, "active_nav": "projects"},
    )


@require_POST
@page_required("projects.archive")
def project_bulk_archive(request: HttpRequest) -> HttpResponse:
    """Archive every selected project. Ranking history is always preserved."""
    ids = [pid for pid in request.POST.getlist("project_ids") if pid.strip()]
    if not ids:
        messages.error(request, "Select at least one project first.")
        return redirect(reverse("projects:list"))

    archived = 0
    for project_id in ids:
        try:
            if services.archive_project(project_id=project_id, request=request):
                archived += 1
        except SourceUnavailable:
            continue

    messages.success(
        request, f"{archived} project{'' if archived == 1 else 's'} archived."
    )
    return redirect(reverse("projects:list"))


@require_POST
@page_required("projects.archive")
def project_archive(request: HttpRequest, project_id: int) -> HttpResponse:
    require_project(project_id)
    try:
        services.archive_project(project_id=project_id, request=request)
    except SourceUnavailable as exc:
        return _error_page(request, str(exc))
    messages.success(request, "Project archived.")
    return redirect(reverse("projects:list"))


# --------------------------------------------------------------------------
# Project detail shell
# --------------------------------------------------------------------------
def _project_context(request: HttpRequest, project_id: int, tab: str) -> dict[str, Any]:
    """Header, tab counts and ASIN selector state shared by every detail tab."""
    project = require_project(project_id)
    repo.touch_last_opened(project_id)

    asin_options = asin_repo.selector_options(project_id)
    requested = qp.get_str(request, "asin")
    known = {option["asin"] for option in asin_options}
    selected = requested if requested in known else (asin_options[0]["asin"] if asin_options else "")

    return {
        "project": project,
        "market": marketplace(project.get("marketplace")),
        "tab": tab,
        "asin_options": asin_options,
        "selected_asin": selected,
        "asin_count": project.get("asin_count", len(asin_options)),
        "keyword_count": project.get("keyword_count", 0),
        "active_nav": "projects",
    }


@login_required
def project_detail(request: HttpRequest, project_id: int) -> HttpResponse:
    """Opening a project lands on Ranks; the other tabs are one click away."""
    require_project(project_id)
    return redirect(reverse("projects:ranks", args=[project_id]))


@page_required("projects.asins")
def project_asins(request: HttpRequest, project_id: int) -> HttpResponse:
    context = _project_context(request, project_id, "asins")
    page_req = parse_page_request(request)
    search = qp.get_str(request, "q")
    sort = qp.get_str(request, "sort", asin_repo.DEFAULT_SORT)

    query = asin_repo.build_filter(
        project_id,
        search=search,
        status=qp.get_str(request, "status"),
        marketplace=qp.get_str(request, "marketplace"),
    )
    try:
        rows, total = asin_repo.list_asins(
            query=query, sort=sort, offset=page_req.offset, limit=page_req.limit
        )
    except SourceUnavailable as exc:
        return _error_page(request, str(exc))

    context.update(
        {
            "page_obj": page_req.build(rows, total),
            "search": search,
            "sort": sort,
            "status": qp.get_str(request, "status"),
        }
    )
    return _tab_render(request, context, "asins", "projects/partials/asin_table.html")


def _keyword_page(request: HttpRequest, project_id: int, asin: str):
    """Shared keyword query used by both the keyword tab and the matrix."""
    page_req = parse_page_request(request)
    sort = qp.get_str(request, "sort", keyword_repo.DEFAULT_SORT)
    query = keyword_repo.build_filter(
        project_id,
        asin,
        search=qp.get_str(request, "kq"),
        tracked=qp.get_str(request, "tracked"),
        rank_min=qp.get_int(request, "rank_min"),
        rank_max=qp.get_int(request, "rank_max"),
        sales_min=qp.get_int(request, "sales_min"),
        conversion_min=qp.get_float(request, "conv_min"),
    )
    rows, total = keyword_repo.list_keywords(
        query=query, sort=sort, offset=page_req.offset, limit=page_req.limit
    )
    return page_req.build(rows, total), rows, sort


@page_required("projects.keywords")
def project_keywords(request: HttpRequest, project_id: int) -> HttpResponse:
    context = _project_context(request, project_id, "keywords")
    asin = context["selected_asin"]
    if not asin:
        context.update({"page_obj": None, "keywords": [], "sort": keyword_repo.DEFAULT_SORT})
        return _tab_render(request, context, "keywords", "projects/partials/keyword_table.html")

    try:
        page_obj, rows, sort = _keyword_page(request, project_id, asin)
        summary = keyword_repo.metric_summary(project_id, asin)
    except SourceUnavailable as exc:
        return _error_page(request, str(exc))

    context.update(
        {
            "page_obj": page_obj,
            "keywords": rows,
            "sort": sort,
            "summary": summary,
            "search": qp.get_str(request, "kq"),
            "has_filters": qp.has_active_filters(request, KEYWORD_FILTER_KEYS),
        }
    )
    return _tab_render(request, context, "keywords", "projects/partials/keyword_table.html")


@page_required("projects.ranks")
def project_ranks(request: HttpRequest, project_id: int) -> HttpResponse:
    context = _project_context(request, project_id, "ranks")
    asin = context["selected_asin"]
    window = _clamped_window(request, project_id, asin)

    context.update(
        {
            "window": window,
            "window_label": format_window_label(window),
            "range_presets": DATE_RANGE_PRESETS,
            "intervals": INTERVALS,
            "legend": heatmap_legend(),
            "has_filters": qp.has_active_filters(request, KEYWORD_FILTER_KEYS),
            "search": qp.get_str(request, "kq"),
        }
    )

    if not asin:
        context.update({"page_obj": None, "columns": [], "rows": [], "overview": None})
        return _tab_render(request, context, "ranks", "projects/partials/rank_matrix.html")

    try:
        page_obj, keywords, sort = _keyword_page(request, project_id, asin)
        columns, rows = matrix.build_matrix(
            project_id=project_id, asin=asin, keywords=keywords, window=window
        )
        overview = analytics.build_overview(project_id=project_id, asin=asin, window=window)
    except SourceUnavailable as exc:
        return _error_page(request, str(exc))

    context.update(
        {"page_obj": page_obj, "columns": columns, "rows": rows, "overview": overview, "sort": sort}
    )
    return _tab_render(request, context, "ranks", "projects/partials/rank_matrix.html")


@page_required("projects.trends")
def project_trends(request: HttpRequest, project_id: int) -> HttpResponse:
    context = _project_context(request, project_id, "trends")
    asin = context["selected_asin"]
    window = _clamped_window(request, project_id, asin)
    context.update(
        {
            "window": window,
            "window_label": format_window_label(window),
            "range_presets": DATE_RANGE_PRESETS,
            "intervals": INTERVALS,
        }
    )

    # Niche unit-sales history, one line per year. It covers the whole niche, so it
    # is built before the ASIN guard below and stays useful with nothing selected.
    # The warehouse dates these rows to the start of a month, so monthly is the only
    # bucket that draws a continuous line.
    tracked = tuple(sorted(option["asin"] for option in context["asin_options"]))
    sales_scope = qp.get_str(request, "sales_scope", "niche", allowed={"niche", "tracked"})
    if sales_scope == "tracked" and not tracked:
        sales_scope = "niche"
    sales = sales_service.niche_sales(
        asins=tracked if sales_scope == "tracked" else ()
    )
    context.update(
        {
            "sales": sales,
            "sales_scope": sales_scope,
            "chart": chart_builder.build(labels=sales["labels"], series=sales["years"]),
        }
    )

    if not asin:
        context.update({"overview": None, "metrics": []})
        return _tab_render(request, context, "trends", "projects/partials/trend_panels.html")

    try:
        overview = analytics.build_overview(project_id=project_id, asin=asin, window=window)
    except SourceUnavailable as exc:
        return _error_page(request, str(exc))

    series = overview["series"]
    metrics = [
        {
            "key": "visibility",
            "label": "Visibility",
            "unit": "%",
            "points": analytics.trend_points(series, "visibility"),
            "change": analytics.summarise_change(analytics.trend_points(series, "visibility")),
            "better": "up",
        },
        {
            "key": "avg_position",
            "label": "Average Position",
            "unit": "",
            "points": analytics.trend_points(series, "avg_position"),
            "change": analytics.summarise_change(analytics.trend_points(series, "avg_position")),
            "better": "down",
        },
        {
            "key": "badges",
            "label": "Amazon Choice Badges",
            "unit": "",
            "points": analytics.trend_points(series, "badges"),
            "change": analytics.summarise_change(analytics.trend_points(series, "badges")),
            "better": "up",
        },
        {
            "key": "ranked",
            "label": "Ranked Keywords",
            "unit": "",
            "points": analytics.trend_points(series, "ranked"),
            "change": analytics.summarise_change(analytics.trend_points(series, "ranked")),
            "better": "up",
        },
    ]
    context.update({"overview": overview, "metrics": metrics})
    return _tab_render(request, context, "trends", "projects/partials/trend_panels.html")


@login_required
def keyword_detail(request: HttpRequest, project_id: int, keyword: str) -> HttpResponse:
    """Rank history drawer for a single keyword, loaded over HTMX."""
    context = _project_context(request, project_id, "ranks")
    asin = context["selected_asin"]
    if not asin:
        raise Http404("No ASIN selected.")

    window = _clamped_window(request, project_id, asin)
    try:
        history = rank_repo.keyword_history(
            project_id=project_id, asin=asin, keyword_lower=keyword.lower(), window=window
        )
    except SourceUnavailable as exc:
        return _error_page(request, str(exc))

    ranks = [point["rank"] for point in history if isinstance(point.get("rank"), int) and point["rank"] > 0]
    context.update(
        {
            "keyword": keyword,
            "history": history,
            "window": window,
            "best_rank": min(ranks) if ranks else None,
            "worst_rank": max(ranks) if ranks else None,
            "average_rank": round(sum(ranks) / len(ranks), 1) if ranks else None,
        }
    )
    return render(request, "projects/partials/keyword_detail.html", context)
