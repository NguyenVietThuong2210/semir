<!--
SYNC IMPACT REPORT
==================
Version change: 1.1.1 → 1.2.0 → 1.2.1
Modified principles: none
Added sections (1.2.0):
  - VII. Mobile App Standards (new principle — SemirPhone Flutter app)
  - Technical Standards: Flutter/Dart section added
  - Development Workflow: Flutter commands added
  - Title updated: "SemirDashboard Constitution" → "Semir Project Constitution"
Added sections (1.2.1):
  - Development Workflow: Post-task documentation rule (docs/ + .specify/ + CLAUDE.md must
    be updated after every task — task is not complete until all three layers are consistent)
Removed sections: none
Templates requiring updates:
  - .specify/templates/plan-template.md ✅ Constitution Check section covers both platforms
  - .specify/templates/spec-template.md ✅ No amendments needed
  - .specify/templates/tasks-template.md ✅ No amendments needed
Deferred TODOs: none
Source audit: reviewed docs/project_mobile.md, semir-phone/lib/ source — gaps now codified.
-->

# Semir Project Constitution

## Core Principles

### I. Business Logic Lock

The following rules are LOCKED. They MUST NOT be changed without explicit written approval
from the product owner in this conversation:

- **Return visit formula** (`App/analytics/calculations.py`):
  `return_visits = total_invoices - 1` when `registration_date == first_purchase_date`,
  else `return_visits = total_invoices`. Counts invoices, not unique visit days.

- **Season definitions** (4 seasons, updated Mar 2026):
  M2-4 (Feb–Apr), M5-7 (May–Jul), M8-10 (Aug–Oct), M11-1 (Nov–Jan cross-year).
  Label format: `M11-1 2024-2025` (Jan belongs to the next year). SS/AW is obsolete.

- **Grade hierarchy**: No Grade < Member < Silver < Gold < Diamond.
  VIP0/VIP1/VIP2/VIP3/DIAMOND is obsolete — do not use.

- **VIP ID = "0"**: non-VIP customer — excluded from grade analytics, tracked separately
  as "buyer without info".

- **Coupon campaign prefix**: `CouponCampaign.prefix` is comma-separated; a coupon belongs
  to a campaign if `coupon_id.startswith(prefix)` for any prefix in the list.

- **Coupon face_value interpretation** (`App/analytics/coupon_analytics.py` →
  `calc_coupon_amount`):
  - `face_value ≤ 0` or None → 0 (no discount)
  - `face_value > 1` → cash discount in VND (return face_value as-is)
  - `face_value == 1.0` exactly → 0 (customer pays 100%, no discount — special case)
  - `0 < face_value < 1` → percentage (e.g. `0.9` = 90% pay → 10% off invoice amount)
  This rule drives all coupon financial calculations. Inverting it silently mis-reports
  coupon spend across the entire analytics dashboard.

- **Shop grouping** (used in `shop_group` query param on all analytics/coupon pages):
  - `"Bala Group"` → shop_name contains `"Bala"` OR `"巴拉"`
  - `"Semir Group"` → shop_name contains `"Semir"` OR `"森马"`
  - `"Others Group"` → all remaining shops
  Changing these strings breaks filter continuity across historical reports.

Any spec or task that touches these rules MUST include a "Business Logic Lock" section
explicitly noting which locked rule is affected and confirming approval was obtained.

### II. Permission-Gated Access

Every view MUST be protected. No exceptions:

- Page views: `@requires_perm("permission_codename")` or `@login_required`.
- AJAX partial views: `_ajax_perm_check(request, codename)` — returns 401/403 instead of
  redirecting, because a redirect silently followed by `fetch()` returns wrong HTML.
- Superusers bypass all permission checks (`user.is_superuser → True` in `permissions.py`).
- New permissions MUST be documented in `docs/project_business_logic.md`
  (20-permission table under `PERMISSION_DEFS`).

### III. Performance Budget

Every page load MUST stay within measurable bounds:

- DB queries per request: ≤ 10 for analytics pages, ≤ 5 for CRUD pages.
- Analytics data: MUST use `_load_sales()` cache (5-min TTL) — do NOT add a second cache
  around already-cached callpaths.
- `.order_by()` MUST precede `.distinct()` on any model with `Meta.ordering`
  (SalesTransaction, Customer) — omitting it causes ordering fields in SELECT DISTINCT,
  returning every row as unique.
- `parse_cnv_period_filter()` returns `({}, False)` for empty dates — check
  `if not period_filter:`, NEVER `if period_filter is None:`.
- New DB-heavy functions (>10k rows, deterministic) MUST be evaluated for caching.
  Cache key format: `"<area>:<param1>:<param2>"`, TTL 5 min (analytics) / 10 min (reference).
- **Upload integrity**: all import functions MUST use `bulk_create` + `bulk_update`.
  Two-level batching is intentional and MUST NOT be collapsed:
  - Outer loop `BATCH_SIZE=5000`: slices the pandas DataFrame for memory control
  - Inner Django call `batch_size=1000`: controls DB transaction size / lock duration
  Single-row `.save()` inside a loop is PROHIBITED — causes timeouts on 100k+ row prod datasets.

### IV. Test-First with Snapshots

All analytics output changes MUST be validated via `SnapshotTestCase`:

- Every URL in `App/urls.py` and `App/cnv/urls.py` MUST have ≥ 1 green test.
- Period-filter views MUST have two test variants: `_alltime` (no params) and `_2025`
  (with `start_date=2025-01-01&end_date=2025-12-31`).
- Snapshots lock data shape — if a snapshot changes unexpectedly, the change MUST be
  reviewed before regenerating with `UPDATE_SNAPSHOTS=1`.
- Tests use `setUpTestData` (class-level), never `setUp` (too slow for 430k-row fixtures).
- All test classes that share the same fixture set MUST be merged to avoid duplicate loads.

### V. Spec-Driven Feature Development

All new features MUST follow the full spec-kit workflow before any code is written:

1. `/speckit-specify` — user stories + acceptance criteria
2. `/speckit-clarify` — resolve edge cases (required if requirements are ambiguous)
3. `/speckit-plan` — architecture + technical approach
4. `/speckit-tasks` — dependency-ordered task list with exact file paths
5. `/speckit-implement` — execute tasks

Hotfixes (≤ 5 lines, isolated bug) MAY skip to implement with a one-sentence rationale.
No feature branch without a `specs/<###-feature-name>/spec.md`.

### VII. Mobile App Standards (SemirPhone)

All development on the Flutter iOS/Android companion app (`semir-phone/`) MUST follow these rules:

- **Compile-time config only**: All secrets, base URLs, TLS pins, and Sentry DSN MUST be injected
  via `--dart-define` flags at build time. No `.env` files, no runtime file reads. Source of truth:
  `BuildConfig` in `core/config/app_config.dart`.

- **Single exception source**: `ApiException`, `PermissionException`, and `ParseException` are
  defined ONLY in `shared/models/analytics_models.dart`. MUST NOT be re-defined in any feature
  service file. All services import from this single source.

- **Controlled dropdown widgets**: `ShopGroupFilter` uses `DropdownButton(value:)` inside
  `InputDecorator` — NOT `DropdownButtonFormField(initialValue:)`. The `initialValue:` API is
  uncontrolled (FormField owns state) and will not respond to externally-driven state resets.
  Do not revert this to `DropdownButtonFormField`.

- **Token storage format**: Permissions are stored as `jsonEncode(List<String>)` in
  `flutter_secure_storage`. MUST NOT use CSV (`join(',')`) — JSON handles permission strings
  with commas and is unambiguous to parse.

- **Auth interceptor DI**: `AuthInterceptor._retryClient` MUST be injected via `bareDioProvider`
  in production. An `assert(_retryClient != null)` enforces this. The bare Dio has no auth
  interceptor — this prevents infinite retry loops on token refresh.

- **`ref.listenManual` for router bridge**: `_AuthListenable` in `app.dart` MUST use
  `ref.listenManual` (returns `ProviderSubscription`) so the subscription can be closed in
  `dispose()`. Do NOT use `ref.listen` here — it returns `void` and cannot be closed outside
  a widget context.

- **Permissions at two levels**: Every protected route has a GoRouter `redirect` guard AND the
  corresponding `NavCard` on `HomePage` sets `hasAccess` from the session permissions. Both
  must be kept in sync when adding a new feature.

- **Test gate before release**: All 198 tests (`flutter test`) MUST pass. Golden images MUST be
  regenerated (`--update-goldens`) whenever any visual component changes. No release without
  a clean test run.

### VI. Observability

Every HTTP request MUST be traceable end-to-end:

- `RequestIDMiddleware` assigns a 12-character hex ID (`uuid4().hex[:12]`, e.g. `"a3f9c2b10d44"`)
  to every request, stored in thread-local storage via `set_request_id()`.
- `RequestIDFilter` injects `request_id` into every log record emitted during that request.
- File handlers write structured JSON — one object per line. Actual schema:
  `{"time": ..., "level": ..., "logger": ..., "module": ..., "request_id": ..., "step": ..., "message": ..., ["exception": ...]}`
  Console handler uses human-readable format: `[LEVEL] time name req=... step=... — message`.
- `X-Request-ID` response header MUST be set for client-side correlation.
- Log files: `logs/app.log` (general), `logs/cnv_sync.log` (CNV), `logs/errors.log` (errors ≥ERROR).
- New background jobs (upload threads, sync tasks) MUST log with the triggering `request_id`
  or a job-scoped ID so failures can be traced without grepping full logs.

## Technical Standards

**Backend stack**: Python 3.x / Django, Bootstrap 5, SQLite3 (dev), PostgreSQL 16 (prod).

**Mobile stack**: Flutter 3.x / Dart 3, Riverpod 2 (`AsyncNotifierProvider`), GoRouter 13,
Dio 5 (JWT interceptor), `flutter_secure_storage` 9, `fl_chart` 0.67, Sentry Flutter 8.

**App layout**:
- Models: `App/models/` (pos.py, coupon.py, user.py) — import via `from App.models import X`.
- Views: `App/views/` — one file per page area.
- Analytics engine: `App/analytics/` — `tab_functions.py` is the main entry point.
- CNV integration: `App/cnv/` — matched POS↔CNV by phone number.

**Model type gotcha — CNVCustomer points fields are `DecimalField`, not `IntegerField`**:
`points`, `exp_points`, `total_spending`, `total_points`, `used_points` — treat as Decimal
in all arithmetic. Mixing with Python `int` causes silent truncation on some DB backends.

**CNV rules**:
- `_fetch_bd_raw(period_filter)` — `period_filter` MUST be a dict (`{}` for no filter),
  never `None`. Passing `None` causes `AttributeError` on `.get()` call.
- Sync commands: `python manage.py sync_cnv_customers` / `sync_cnv_orders`.
- CNV sync stale threshold: 2h (auto-mark failed). Zalo sync stale threshold: 4h.

**Template rules**:
- Views MUST pass plain dicts (`.values()` output), never raw querysets, to templates.
- Templates MUST NOT trigger DB queries.
- Custom filters: `|vnd` (VND number format) from `custom_filters.py`.

**Migration discipline**:
- Every model field change requires `makemigrations` + `migrate` before PR merge.
- Index additions MUST be verified for speedup via query instrumentation.

## Development Workflow

**Branch naming**: `<###>-<feature-name>` (e.g., `001-customer-export`).

**Test run commands (SemirDashboard)**:
```bash
cd SemirDashboard && python manage.py test tests -v 2
cd SemirDashboard && UPDATE_SNAPSHOTS=1 python manage.py test tests -v 2
cd SemirDashboard && python manage.py test tests.test_shop_detail.ShopDetailTest.test_sales_alltime_matches_shop_tab -v 2
```

**Test run commands (SemirPhone)**:
```bash
cd semir-phone && flutter test
cd semir-phone && flutter test test/golden/golden_test.dart --update-goldens
```

**Snapshot policy**: Snapshot changes from pure optimization (no business logic change)
MUST show zero data-shape delta. If `assert_snapshot` fails after an optimization,
revert the optimization — correctness over performance.

**Post-task documentation rule** (REQUIRED after every completed task):

After any task is done — feature, fix, refactor, or config change — review and update all
three layers if the change affects them. This is not optional and is part of task completion.

1. **`docs/`** — update the relevant doc file(s):
   - New URL → `docs/project_urls.md`
   - New test file → `docs/project_structure.md`
   - View/service refactor → `docs/project_analytics.md` or `docs/project_cnv.md`
   - Cache key / TTL change → same docs as above
   - Model index added → `docs/project_models.md`
   - New mobile route or permission → `docs/project_mobile.md`
   - New shared widget or model type → `docs/project_mobile.md`
   - Any architectural decision → `docs/ANALYSIS.md` or `docs/project_overview.md`

2. **`.specify/memory/constitution.md`** — amend if the task:
   - Establishes a new invariant or non-obvious rule that future tasks must not violate
   - Changes a locked business rule (requires product owner approval first)
   - Introduces a new platform, layer, or technology to the project
   - Bumps version per semantic versioning and updates `LAST_AMENDED_DATE`

3. **`CLAUDE.md`** — update if the task:
   - Adds or changes a run command, test command, or migration step
   - Changes the location of a canonical folder (e.g., render/, snapshots/)
   - Introduces a new non-obvious rule that Claude needs to apply in every session
   - Adds a new doc file to the Detailed Docs list

A task is NOT complete until these three layers are consistent with the code.

## Governance

This constitution is the highest-authority document for all Semir project development
(SemirDashboard + SemirPhone). It supersedes any conflicting guidance in other files.

**Amendment procedure**:
1. Propose the change in conversation with the product owner.
2. Receive explicit written approval for changes touching Principle I (Business Logic Lock).
3. Update this file, increment version per semantic versioning, update `LAST_AMENDED_DATE`.
4. Run consistency propagation: verify plan/spec/tasks templates still align.
5. Commit with message: `docs: amend constitution to vX.Y.Z (<summary>)`.

**Versioning policy**:
- MAJOR: Locked business rule changed or principle removed.
- MINOR: New principle added or material guidance added to existing principle.
- PATCH: Wording clarification, typo fix, non-semantic refinement.

**Compliance**: Every PR description MUST include a one-line "Constitution Check" confirming
no locked rules were modified (or citing the approval if they were).

**Version**: 1.2.1 | **Ratified**: 2026-04-22 | **Last Amended**: 2026-04-27
