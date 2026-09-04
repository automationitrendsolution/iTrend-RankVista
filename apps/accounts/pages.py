"""The page permission matrix: which role may reach which screen.
One registry drives the decorators, the navigation and the Roles screen."""

from __future__ import annotations

from dataclasses import dataclass

from apps.accounts.models import ROLE_RANK, Role


@dataclass(frozen=True, slots=True)
class Page:
    """A protected screen and the minimum role that may open it."""

    key: str
    label: str
    minimum: str
    group: str
    description: str = ""

    @property
    def rank(self) -> int:
        return ROLE_RANK.get(self.minimum, 0)

    def allows(self, role: str) -> bool:
        return ROLE_RANK.get(role, 0) >= self.rank


PAGES: tuple[Page, ...] = (
    Page("projects.view", "Projects", Role.USER, "Workspace",
         "Browse the project grid and open a project."),
    Page("projects.asins", "ASINs", Role.USER, "Workspace",
         "View the ASIN registry for a project."),
    Page("projects.keywords", "Keywords", Role.USER, "Workspace",
         "View tracked keywords and their business metrics."),
    Page("projects.ranks", "Rank matrix", Role.USER, "Workspace",
         "View the historical rank matrix and rank analytics."),
    Page("projects.trends", "Trends", Role.USER, "Workspace",
         "View visibility and position movement over time."),
    Page("projects.create", "Create project", Role.ADMIN, "Workspace",
         "Register a new project."),
    Page("projects.edit", "Edit project", Role.ADMIN, "Workspace",
         "Rename a project or change its marketplace and tags."),
    Page("projects.archive", "Archive project", Role.ADMIN, "Workspace",
         "Hide a project from the listing. Ranking history is preserved."),
    Page("accounts.profile", "Own profile", Role.USER, "Account",
         "Update your own name and password."),
    Page("admin.users", "User management", Role.SUPER_ADMIN, "Administration",
         "Create, edit, activate, reset and delete platform users."),
    Page("admin.departments", "Departments", Role.SUPER_ADMIN, "Administration",
         "Create and maintain organisational departments."),
    Page("admin.roles", "Roles & permissions", Role.SUPER_ADMIN, "Administration",
         "Review which role may reach which screen."),
)

BY_KEY = {page.key: page for page in PAGES}


def page(key: str) -> Page:
    try:
        return BY_KEY[key]
    except KeyError:
        raise KeyError(f"Unknown page permission '{key}'.") from None


def allowed(key: str, role: str) -> bool:
    return page(key).allows(role)


def pages_for(role: str) -> list[Page]:
    """Every page the given role may open."""
    return [item for item in PAGES if item.allows(role)]


def matrix() -> list[dict]:
    """Rows for the Roles screen: one page, with a flag per role."""
    roles = [value for value, _ in Role.choices]
    roles.sort(key=lambda value: ROLE_RANK.get(value, 0), reverse=True)
    return [
        {
            "page": item,
            "grants": [{"role": role, "allowed": item.allows(role)} for role in roles],
        }
        for item in PAGES
    ]


def groups() -> list[str]:
    seen: dict[str, None] = {}
    for item in PAGES:
        seen.setdefault(item.group, None)
    return list(seen)
