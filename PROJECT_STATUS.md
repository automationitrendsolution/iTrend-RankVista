# PROJECT_STATUS

Living status for iTrend RankVista. Updated as work progresses.

## Completed

- **Data layer** — live MySQL warehouse (`powerbidb`, 39.9M rank rows) behind a
  repository abstraction; MongoDB overlay for user-editable project metadata.
- **Datastores** — Django ORM runs entirely on MongoDB via `django-mongodb-backend`
  (contrib migrations regenerated under `mongo_migrations/`). No SQLite anywhere.
- **Authentication** — split-screen login, email-or-username sign-in, show/hide password,
  remember-me session length, safe `next` handling, audit trail on every attempt.
- **RBAC** — `SUPER_ADMIN` / `ADMIN` / `USER` with rank ordering; every endpoint guarded
  server-side by decorator, never by hidden UI.
- **Bootstrap admin** — idempotent `manage.py bootstrap_admin`; creates, repairs, adopts a
  renamed account, and never prints or stores a plaintext password.
- **SaaS administration** — users (create, edit, activate, reset password, soft delete,
  search, filter, paginate), departments (full CRUD, member list) and a roles overview.
- **Projects** — grid and list views, search, marketplace/sort filters, quick-view modal,
  create/edit/archive through the overlay, server-side pagination.
- **ASIN / Keyword modules** — registry listing with search, status filter and sorting;
  keyword table with business metrics, filters and pagination.
- **Ranking matrix** — sticky keyword and metric columns, heat-mapped cells, daily/weekly/
  monthly intervals, date presets plus custom range, legend, smooth horizontal scroll.
- **Analytics** — visibility, average position, Amazon's Choice badges and rank
  distribution, aggregated in SQL and rendered as server-computed SVG.
- **Interaction** — HTMX tab switching without page reloads, skeleton loading, progress
  bar, chart hover tooltips with crosshair markers, styled matrix cell tooltips.
- **Performance** — Redis caching of warehouse aggregates; the correlated snapshot
  subquery was replaced with a cached constant (2.5s → ~160ms warm).
- **Security** — CSRF, secure cookie flags, clickjacking and MIME protections, log
  redaction, optional encryption-at-rest for credentials (`manage.py secrets_tool`).
- **Docker** — Compose stack with MongoDB, Redis and Gunicorn; loopback-only port
  binding; live-reload dev overlay; named volumes and an on-demand `mongodump` backup.
- **Documentation** — README covering architecture, per-OS install, Docker, environment,
  credentials, commands, testing, production and troubleshooting.

## Verified

- **Tests** — 62 passing (`uv run pytest`), exit code 0.
- **Deploy check** — `manage.py check --deploy` clean with production settings.
- **Responsive** — 375 / 768 / 1024 / 1440 / 1920 px: no horizontal overflow anywhere,
  matrix scroll contained, sidebar collapses, KPI grid reflows 4 → 2 → 1.
- **Browser** — no console errors; hover tooltips, skeletons and HTMX tab swaps confirmed.
- **Docker** — image builds; the stack starts under Gunicorn with migrations, indexes,
  static collection and admin bootstrap; `/healthz/` reports mongodb, warehouse and cache up.
- **Native** — `uv sync` + `manage.py runserver` runs against the same stack.

## Current

- Ongoing UI refinement against the reference workflow.

### Recent UI work

- **No page reloads anywhere.** `hx-boost` on the shell plus scoped HTMX targets;
  scripts are deferred in `<head>` so a boosted body swap cannot re-execute them.
- **Editable roles and permissions.** Roles live in MongoDB with a per-screen toggle
  grid; rank is derived from the granted screens, never entered by hand.
- **Custom select, dropdown and confirm dialogs.** The OS select popup and
  `window.confirm` are both replaced; menus are portalled so nothing clips them.
- **Live form validation.** The same Django form validates over HTTP as the user
  types, so uniqueness and format rules are never duplicated in JavaScript.
- **Dark/light theme, live IST clock, skeleton loading, chart hover tooltips.**
- Tables default to 10 rows; every list paginates server-side.

## Remaining

- Export (CSV/Sheets) for the keyword and matrix tables.
- Bulk keyword actions behind the existing row-selection checkboxes.
- Column configuration (show/hide, reorder) for the matrix.
- Saved filter presets per user.
- Multi-marketplace support once the warehouse carries a marketplace column.

## Important decisions

- **Two datastores, one direction.** The warehouse account is read-only, so all writes go
  to the MongoDB overlay and are merged over derived source rows at read time.
- **Projects are derived.** The warehouse has no project-name column; names come from the
  primary ASIN's title, shortened for display, and are overridable in the overlay.
- **Roles stay in code.** They are enforced by decorators on every endpoint; the Roles
  screen documents them rather than making them editable data.
- **Credentials are encrypted, not hashed.** The app must present them to a server, so
  hashing is impossible; `enc:` values are decrypted at load. User passwords remain hashed.
- **`MONGO_ROOT_PASSWORD` stays plaintext.** Docker Compose interpolates `.env` itself and
  cannot decrypt, so encrypting it would seed MongoDB with the wrong password.
- **Charts are server-rendered.** SVG geometry is computed in Python; no chart library was
  added, keeping the bundle to jQuery + HTMX.
- **Pagination precedes filtering in SQL where possible**, and where an overlay filter
  applies, the full roster (about 130 rows) is filtered before paging so the total always
  matches the listing.
- **Ports bind to 127.0.0.1.** `BIND_HOST` must be set deliberately to expose anything.

## Known issues

- Amazon serves per-ASIN images only for part of the catalogue, so many project cards show
  the placeholder. Real image URLs would need an ASIN→image-hash source.
- The warehouse stores a single marketplace, so the marketplace filter currently only ever
  offers `US`; the code path is ready for more.
- `datarova_asin_keyword_summary` reports the same keyword count for every ASIN in a
  project, because upstream tracks the full keyword set against each ASIN. This is faithful
  to the source, not a display bug.
- The first uncached warehouse roster query takes about 1.5s; subsequent loads are served
  from Redis for 30 minutes.
