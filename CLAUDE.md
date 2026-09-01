# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Post-Task Rule (enforced)

**A task is not complete until `docs/`, `.specify/`, and `CLAUDE.md` are consistent with the code.**

After every completed task, review and update each layer that the change touches:

| Layer | Update when… |
|-------|-------------|
| `docs/` | New URL, model, view, service, test file, mobile route, architectural decision |
| `.specify/memory/constitution.md` | New invariant, locked rule change, new platform/technology — bump version |
| `CLAUDE.md` | New run command, folder location change, new rule Claude must apply every session |

If nothing changed in a layer, no update is needed — but the review is still required.

## Resource Discipline (enforced)

The host machine is a single shared resource across Claude and every sub-agent it spawns. Violating this section is a session-ending failure mode (OOM, forced user shutdown) — treat it as seriously as the Critical Business Rules below. Added 2026-08-30 after a session ran the full test suite 5-7 times over ~9 hours (largely back-to-back) plus concurrent sub-agent-driven Docker/Playwright work, degrading the user's machine to the point of a forced stop.

**Rule 1 — One heavy operation at a time, session-wide.** "Heavy" = starting/stopping Docker or docker-compose, running `manage.py test` at any scope, running `prod_visual.py` or `snapshot_visual.py` (both launch real Chrome), or `flutter build`. Before starting any heavy operation, check both:
- `docker ps` — no container from this session should already be running (or you're reusing it, not duplicating it).
- A process check for `python`/`chrome`/`node` — no heavy process from an earlier step should still be alive.
If either check shows a live heavy process, wait for it or stop it first. Never start a second heavy operation "to make progress while the first one runs."

**Rule 2 — Only Claude (the coordinator) runs heavy operations directly. Sub-agents do not.** Do not delegate Docker startup, test-suite runs (any scope), or Playwright/Chrome capture to a sub-agent via the Agent tool — run these yourself with Bash/PowerShell so you keep the PID/container handle. Sub-agent-spawned background processes have been observed to go orphaned (untrackable, unkillable by the coordinator) once the sub-agent's own turn ends. Sub-agents may investigate, read logs, draft code, or report on a run you already performed — they may not launch the run themselves.

**Rule 3 — Never spawn two sub-agents in the same message (or near-simultaneously) if either might touch Docker, the test suite, or Playwright.** Concurrent sub-agents are fine only when confirmed read-only (search, grep, doc review).

**Rule 4 — An unexplained process/container death is a STOP signal, not a retry signal.** When a background process dies with no clear application-level traceback (container disappears, process killed silently, exit code doesn't match a known test failure): don't immediately retry. Check `docker ps -a`, process list, and free memory (`Get-CimInstance Win32_OperatingSystem | Select FreePhysicalMemory,TotalVisibleMemorySize`); report the finding to the user in one short message. Retry at most once, only after confirming a clean process list. If it dies a second time, stop and ask the user how to proceed.

**Rule 5 — If the user says the machine is struggling (CPU/fan/lag/crash complaints), that instruction persists for the rest of the session, not just the next reply.** Do not revert to spawning heavy or concurrent operations later in the same session without re-confirming it's safe.

**Rule 6 — "Testing for Release" (below) runs the full suite twice per invocation (Step 1 + Step 3).** If Step 1 fails, fix and re-run only the failing subset before re-attempting the full two-step sequence — do not re-pay both ~80-minute runs for every fix iteration. Only run the complete Testing for Release checklist once per actual release attempt, not once per fix.

**Rule 7 — One Docker setup: `docker-compose.yml` + a gitignored `docker-compose.override.yml`.** `docker-compose.yml` (bare `docker compose ...`, no `-f`) is the real prod stack (nginx+web+redis+postgres, port 5432) — the same file `scripts/deploy.sh` pulls on the real server, untouched for local dev. Docker Compose auto-merges `docker-compose.override.yml` on top of it on every bare `docker compose up` (no `-f` needed) if that file exists alongside it — it is gitignored (never deployed) and contains just two local-only overrides: `web.environment: DEBUG=True` (prod's `DEBUG=False` makes Django's `settings.py` set `SECURE_SSL_REDIRECT=True`, which gunicorn alone — no nginx — can't serve locally) and `web.ports: 8000:8000` (publish it directly) plus `nginx.restart: "no"` (nginx has no local SSL cert and would otherwise crash-loop forever). This means the user's own habitual command — `docker compose down; docker system prune -f; docker compose up --build -d` — works completely unchanged and IS the correct way to start local dev; no `-f` flag, no second compose file. `docker-compose.local.yml`/`scripts/dev-db.sh` (a separate Postgres-only container on port 5433) no longer exists — do not recreate it, this override-based approach fully replaced it (2026-08-30/31).

**The `web` container has no source bind-mount** (build-time `COPY` only, matching prod). A code edit therefore needs `docker compose cp <file> web:/app/<path>` followed by `docker compose restart web` before it's live — there is no autoreload while iterating through the container. For genuine instant-autoreload dev, run Django on the HOST instead, pointed at the same containerized Postgres (`.env`'s `DB_PORT=5432` matches `docker-compose.yml`'s exposed port): `docker compose stop web` (keep `db`+`redis` running, free port 8000) then `cd SemirDashboard && ../venv/Scripts/python.exe manage.py runserver` — verified working 2026-08-31 (host process reads the same live data the container would).

## Commands

```bash
# Local dev — one stack, the user's own habitual command (docker-compose.override.yml
# auto-merges DEBUG=True + publishes web:8000 + disables nginx, see Rule 7):
docker compose down
docker system prune -f
docker compose up --build -d
docker compose exec web python manage.py migrate
docker compose exec web python manage.py perm sync
docker compose exec web python manage.py collectstatic --noinput

# Applying a code edit inside the running container (no bind-mount — required after every change):
docker compose cp SemirDashboard/App/<path> web:/app/App/<path>
docker compose restart web

# Fast iteration instead (instant autoreload, no cp/restart per change):
docker compose stop web          # keep db+redis running, free host port 8000
cd SemirDashboard && ../venv/Scripts/python.exe manage.py runserver

# Migrations (run inside the container, or via the host venv per above)
docker compose exec web python manage.py makemigrations
docker compose exec web python manage.py migrate

# CNV loyalty sync (manual, one-off — scheduled cron runs hourly via App/cnv/scheduler.py: customers :05, orders :10)
docker compose exec web python manage.py sync_cnv --customers
docker compose exec web python manage.py sync_cnv --orders

# Test the CNV scheduler locally WITHOUT calling the real CNV API (mocked sync + fast interval trigger)
docker compose exec web python manage.py cnv_scheduler_smoketest --duration 30 --interval 3

# CNV customer sync gap check (checkpoint can permanently skip customers tied on updated_at — see docs/project_cnv.md)
docker compose exec web python manage.py check_cnv_gap --export "path/Customers_File_*.xls" --out App/cnv/input/cnv_gap_<date>.txt
docker compose exec web python manage.py sync_cnv --customers --ids-file App/cnv/input/cnv_gap_<date>.txt

# One-time fix: retroactively normalize existing MembershipSnapshotBatch rows' by_store
# attribution to the current live Customer.registration_store per vip_id (manual-import
# backfill batches only inherited stale store-name formats from their upload file — see
# docs/project_business_logic.md → "Customer Membership Snapshot Rules"). Dry-run by
# default (prints what would change, writes nothing) — add --apply to persist.
docker compose exec web python manage.py normalize_membership_stores
docker compose exec web python manage.py normalize_membership_stores --apply
docker compose exec web python manage.py normalize_membership_stores --batch-id 42 --apply

# Run all shop_detail tests (edited test files must be `docker compose cp`'d into
# the container first — no bind-mount, see Rule 7)
docker compose exec web python manage.py test tests.test_shop_detail -v 2

# Run a single test
docker compose exec web python manage.py test tests.test_shop_detail.ShopDetailTest.test_sales_alltime_matches_shop_tab -v 2

# Run all tests
docker compose exec web python manage.py test tests -v 2

# Regenerate stale snapshots (after template or data shape changes)
docker compose exec web python manage.py test tests.test_shop_detail -v 2 -e UPDATE_SNAPSHOTS=1
# (or: docker compose exec -e UPDATE_SNAPSHOTS=1 -T web python manage.py test tests.test_shop_detail -v 2,
# then `docker compose cp web:/app/tests/snapshots/. SemirDashboard/tests/snapshots/` to pull the
# regenerated files onto the host — the container has no bind-mount, so they never land there on their own)

# Regenerate visual UI snapshots (REQUIRED after ANY template change) — MUST run via the
# HOST venv, not the container: snapshot_visual.py needs a local Chrome install, and its
# input (snapshot_render.py's HTML output) must land on the actual host disk for it to read
cd SemirDashboard && ../venv/Scripts/python.exe manage.py shell -c "exec(open('tests/snapshot_render.py').read())"
cd SemirDashboard && ../venv/Scripts/python.exe tests/snapshot_visual.py
```

## Testing for Release

When the user says **"testing for release"**, execute this checklist in full — do not skip steps:

### Step 1 — Run all unit tests (green gate)
```bash
cd SemirDashboard && python manage.py test tests -v 2 2>&1
```
All tests must pass. Fix any failures before proceeding.

### Step 2 — Run mobile API tests with performance assertions
```bash
cd SemirDashboard && python manage.py test tests.test_api -v 2 2>&1
```
Covers: auth guards, structure parity, period ≤ all-time assertions, lazy tab/section loading, response time limits.

### Step 3 — Regenerate all snapshots (confirm no silent data changes)
```bash
cd SemirDashboard && UPDATE_SNAPSHOTS=1 python manage.py test tests -v 2 2>&1
```
Review diff: only `_last_run` lines should differ. Any other field change = regression.

### Step 4 — Verify all web pages render (200 smoke test)
```bash
cd SemirDashboard && python manage.py shell -c "
from django.test import Client, override_settings
from django.contrib.auth.models import User
with override_settings(ALLOWED_HOSTS=['*']):
    c = Client()
    c.force_login(User.objects.filter(is_superuser=True).first())
    pages = ['/', '/analytics/', '/analytics/chart/', '/coupons/', '/coupons/chart/', '/shop-detail/', '/cnv/customer-analytics/', '/cnv/sync-status/', '/membership/']
    for p in pages:
        r = c.get(p, follow=True, SERVER_NAME='localhost')
        print(f'[{r.status_code}] {p}')
"
```
All pages must return 200.

### Step 5 — Visual snapshot check (after any template change)
```bash
cd SemirDashboard && python manage.py shell -c "exec(open('tests/snapshot_render.py').read())"
cd SemirDashboard && python tests/snapshot_visual.py
```
Open `tests/render/png/*.png` and verify UI. Check `tests/render/_index.md` — must show **0 token issues**.

### Step 6 — Mobile build check
```bash
cd semir-phone && flutter analyze 2>&1 | grep -E "error|warning"
cd semir-phone && flutter build apk --debug 2>&1 | tail -5
```
Zero errors required. Warnings reviewed.

### Pass criteria
| Check | Requirement |
|-------|-------------|
| Unit tests | All green |
| API parity tests | All green, perf within limits |
| Snapshot diff | Only `_last_run` lines changed |
| Web pages | All 200 |
| Visual tokens | 0 issues |
| Flutter analyze | 0 errors |

---

## UI Snapshot Rule

After editing **any** template under `App/templates/`, regenerate the visual snapshots in `SemirDashboard/tests/render/`:
1. `python manage.py shell -c "exec(open('tests/snapshot_render.py').read())"` — writes HTML + table summaries + `token_issues.txt` for any hardcoded color violations
2. `python tests/snapshot_visual.py` — generates PDF + PNG via Chrome headless

The `tests/render/` folder is the canonical visual reference — open `tests/render/png/*.png` to verify changes look correct, and check `tests/render/_index.md` for token compliance (must be 0 issues).

Test input files live in `SemirDashboard/tests/input/`. Snapshots live in `SemirDashboard/tests/snapshots/`. Visual renders live in `SemirDashboard/tests/render/`. Run logs are written to `SemirDashboard/tests/output/`.

## Architecture Overview

### Django app layout

All source is under `SemirDashboard/App/`. Models, views, and analytics are split packages (not single files):

- `App/models/` — `pos.py` (Customer, SalesTransaction), `coupon.py` (Coupon, CouponCampaign), `user.py` (Role, UserProfile). All exported from `__init__.py` so `from App.models import Customer` works.
- `App/views/` — one file per page area: `analytics.py`, `coupon.py`, `customer.py`, `upload.py`, `auth.py`, `users.py`, `shop_detail.py`.
- `App/analytics/` — analytics engine (see below).
- `App/cnv/` — CNV Loyalty API integration (models, client, sync service, scheduler, views, Zalo).
- `App/services/` — file import logic (`customer_import.py`, `sales_import.py`, `coupon_import.py`).

URL routing: `SemirDashboard/urls.py` → `/admin/`, `/` → `App/urls.py`, `/cnv/` → `App/cnv/urls.py`.

### Analytics engine (`App/analytics/`)

The main analytics request flow:
1. A view calls `get_sales_tab(tab_name, date_from, date_to, shop_group)` from `tab_functions.py`
2. `tab_functions.py` calls `_load_sales()` which fetches raw transactions, builds `customer_purchases` dict, and caches it 5 min per (date_from, date_to, shop_group)
3. The appropriate aggregator (`aggregate_by_season`, `aggregate_by_shop`, etc.) in `aggregators.py` computes the breakdown
4. `core.py` orchestrates `calculate_return_rate_analytics()` for full-page exports

The **Shop Detail page** (`views/shop_detail.py`) uses direct-query helpers in `tab_functions.py`:
- `get_shop_detail_sales_data(shop, date_from, date_to)` — loads all-time for the shop in 1 DB query, filters to period in Python, returns `{all_time: KPIs, period: KPIs, by_session, by_month, by_week}`
- `get_shop_detail_customer_data(store, start_date, end_date)` — uses `compute_cnv_breakdown` with `store_filter`
- `get_shop_detail_coupon_data(shop, date_from, date_to)` — direct DB filter

Shop Detail partials are loaded via AJAX (`/shop-detail/partial/sales/`, `/customer/`, `/coupon/`) with `X-Requested-With: XMLHttpRequest`. Templates live in `App/templates/shop_detail/_*_partial.html`.

Dropdown lists for Shop Detail are cached 5 min in Django cache under key `"shop_detail_dropdowns"`. The `_get_dropdown_options()` helper uses `.order_by().distinct()` — **never omit `.order_by()`** before `.distinct()` on models that have `Meta.ordering`, or Django will include ordering fields in the SELECT DISTINCT and return every row as unique.

### CNV integration (`App/cnv/`)

CNV Loyalty is an external loyalty platform. Customers are matched POS↔CNV by phone number. `compute_cnv_breakdown()` in `App/cnv/service.py` is the main analytics function. `_fetch_bd_raw(period_filter)` fetches all raw DB data (cached 5 min); `period_filter` must be a dict (`{}` for no filter) — **never pass `None`**, the `.get()` call will crash.

### Permissions

Custom role-based system in `App/permissions.py`. Views use `@requires_perm("permission_string")`. For AJAX partial views that must not redirect on auth failure, use `_ajax_perm_check(request, codename)` which returns a 401/403 `HttpResponse` instead of redirecting (redirect silently followed by `fetch()` would return the wrong page's HTML).

### Template tags

`perm_tags.py` provides `{% check_perm 'codename' as var %}`. `custom_filters.py` provides `|vnd` (VND number format).

## Critical Business Rules

**Return visit formula** (`App/analytics/calculations.py`) — **locked, do not change without user approval:**
```python
if registration_date == first_purchase_date:
    return_visits = total_invoices - 1   # reg-day purchase is NOT a return
else:
    return_visits = total_invoices       # all invoices count as returns
```
Counts invoices, not unique visit days.

**Season definitions** (4 seasons, updated Mar 2026 — old SS/AW definition is obsolete):
| Label | Months |
|-------|--------|
| M2-4  | Feb, Mar, Apr |
| M5-7  | May, Jun, Jul |
| M8-10 | Aug, Sep, Oct |
| M11-1 | Nov, Dec, Jan (cross-year) |

M11-1 label format: `M11-1 2024-2025` (not `2025/2026`). Jan belongs to the *next* year.

**Grade hierarchy:** `No Grade < Member < Silver < Gold < Diamond` — **not** VIP0/VIP1/VIP2/VIP3/DIAMOND (obsolete).

**VIP ID = "0"** → non-VIP customer, excluded from grade analytics. Tracked separately as "buyer without info".

**Coupon campaign prefix** — `CouponCampaign.prefix` is comma-separated. A coupon belongs to a campaign if its `coupon_id` starts with any prefix in the list.

**Membership grade upgrade thresholds** (`App/analytics/calculations.py`) — locked, PO-confirmed 2026-08-14: Silver ≥6,000,000 / Gold ≥12,000,000 / Diamond ≥20,000,000 VND annual spend (calendar year, Jan 1 → date). Downgrade thresholds are informational only — no grade-change-date data exists to enforce them. See `docs/project_business_logic.md` → "Customer Membership Snapshot Rules".

## Test Infrastructure

Tests extend `SnapshotTestCase` from `tests/base.py`. Key features:
- `self.assert_snapshot(name, data)` — compares against JSON in `tests/snapshots/<name>.json`; set `UPDATE_SNAPSHOTS=1` to regenerate
- `self.timer(name)` → `Timer` — records checkpoint timings, writes to run log
- `self.record_page_timing(page, total_s, checkpoints)` — records in summary

All tests that load fixture data (74k customers + 118k sales + 239k coupons) should use `setUpTestData` at the class level to load once per class. Merge test classes that share the same fixture set to avoid duplicate loads.

## Database Notes

Dev and prod both run PostgreSQL 16 via the same `docker-compose.yml` (`db` service, port 5432, see Rule 7) — was SQLite3 until 2026-08-14, switched so Postgres-only code paths (e.g. GinIndex/trigram search) actually run in tests instead of being skipped. `SemirDashboard/db.sqlite3` still exists as a legacy fallback only if `DB_HOST` is unset — not the normal dev path anymore. Note: `postgres:16` (glibc) vs `postgres:16-alpine` (musl) have different default text collation — if the image tag ever changes, string-sorted query results can shift even with byte-identical data (found 2026-08-30, see `docker-compose.yml`'s pinned image).

`Meta.ordering` on `SalesTransaction` and `Customer` models affects `.distinct()` queries — always call `.order_by()` before `.distinct()` to clear model ordering. Indexes exist on `shop_name`, `registration_store`, `using_shop` (migration 0012).

## Detailed Docs

Extended documentation is in `docs/`:
- `ANALYSIS.md` — navigation index + architecture summary (both web + mobile)
- `project_overview.md` — stack, paths, deploy, commands (both web + mobile)
- `project_mobile.md` — SemirPhone Flutter app: auth, navigation, API, widgets, tests, release checklist
- `project_structure.md` — file tree + task→file mapping
- `project_models.md` — all model fields (accurate)
- `project_analytics.md` — analytics engine, season labels, grades, tab_functions.py
- `project_cnv.md` — CNV API, sync service, service.py, scheduler, Zalo
- `project_urls.md` — complete URL map (all 30+ endpoints)
- `project_business_logic.md` — all 20 permissions, business rules, upload flow
- `project_ui.md` — CSS design tokens, color rules, component patterns (dark-tabs, card headers, stat cards)

<!-- SPECKIT START -->
For additional context about technologies to be used, project structure,
shell commands, and other important information, read the current plan at
`specs/003-semir-phone-app/plan.md`.
<!-- SPECKIT END -->
