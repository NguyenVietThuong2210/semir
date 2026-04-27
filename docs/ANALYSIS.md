# Semir — Full Project Analysis

**Last Updated:** 2026-04-27
**Status:** Current & accurate

---

## Quick Navigation

### SemirDashboard (Django web app)

| Question | Doc |
|----------|-----|
| How do I run/deploy this? | [project_overview.md](project_overview.md) |
| Where is X file? | [project_structure.md](project_structure.md) |
| What fields does model Y have? | [project_models.md](project_models.md) |
| How does analytics/return formula work? | [project_analytics.md](project_analytics.md) |
| How does CNV sync work? | [project_cnv.md](project_cnv.md) |
| What URLs exist? | [project_urls.md](project_urls.md) |
| What permissions/business rules exist? | [project_business_logic.md](project_business_logic.md) |
| UI design system, tokens, color rules | [project_ui.md](project_ui.md) |
| Snapshot test checklist | [SNAPSHOT_CHECKLIST.md](SNAPSHOT_CHECKLIST.md) |
| Post-deployment tasks | [NEXT.md](NEXT.md) |

### SemirPhone (Flutter mobile app)

| Question | Doc |
|----------|-----|
| Architecture, auth, navigation, API, tests | [project_mobile.md](project_mobile.md) |

---

## Project Identity

### SemirDashboard

| Property | Value |
|----------|-------|
| Name | SemirDashboard |
| Framework | Django 4.x / Python 3.11 |
| Purpose | Retail analytics + CNV Loyalty integration (SEMIR Vietnam) |
| DB (dev) | SQLite3 |
| DB (prod) | PostgreSQL 16 |
| Production | https://analytics-customer-dashboard.com (14.225.254.192) |
| Stack | Docker Compose → Nginx → Gunicorn → Django |

### SemirPhone

| Property | Value |
|----------|-------|
| Name | SemirPhone (`semir_phone`) |
| Framework | Flutter 3.x / Dart 3 |
| Purpose | iOS/Android companion app consuming SemirDashboard REST API |
| API base | `https://analytics-customer-dashboard.com/api/v1` (prod) |
| State mgmt | Riverpod 2 (`AsyncNotifierProvider`) |
| Navigation | GoRouter 13 |

---

## Architecture Summary

### System Overview

```
SemirPhone (Flutter iOS/Android)
        │ HTTPS /api/v1/
        ▼
SemirDashboard (Django)  ←── CSV/Excel uploads
        │
        ├── PostgreSQL 16 (prod) / SQLite3 (dev)
        ├── Redis cache
        └── CNV Loyalty API (external, hourly sync)
```

### SemirDashboard Core Data Flow
1. **Data in:** CSV/Excel uploads → `services/{customer|sales|coupon}_import.py` → DB (bulk insert)
2. **Analytics:** `analytics/tab_functions.py` → `_load_sales()` cache → `aggregators.py` → per-tab data
3. **Frontend:** Lazy AJAX tab loading — initial page renders one tab, rest load on click
4. **CNV sync:** APScheduler (hourly) → `cnv/sync_service.py` → `cnv/api_client.py` → `CNVCustomer`/`CNVOrder`
5. **Mobile API:** `App/api/views.py` exposes `/api/v1/` DRF endpoints consumed by SemirPhone

### SemirPhone Core Data Flow
1. GoRouter redirect checks `authProvider` on every navigation — unauthenticated → `/login`
2. `AuthInterceptor` intercepts 401s — serialises to 1 refresh call, queues all concurrent requests
3. Each analytics page: `ConsumerWidget` → `AsyncNotifierProvider` → `*Service` → `/api/v1/*` → parse → `KpiItem`/`TableTab`

### Key Architectural Decisions (SemirDashboard)
- **No JOIN bottleneck:** `_load_sales()` fetches `SalesTransaction` (5 fields) + loads `Customer` separately
- **Cache hierarchy:** `_load_sales()` 5min TTL, CNV phone sets 10min, BD raw 5min, dropdowns 5min
- **AJAX partials:** Shop detail page fires 3 parallel AJAX calls for sales/customer/coupon sections
- **Thread safety:** Upload jobs use cache.add() as distributed lock; Zalo sync uses in-memory lock + thread-local sessions
- **Structured logging:** All logs are JSON with `request_id` + `step` fields (Loki-compatible)

### Key Architectural Decisions (SemirPhone)
- **Compile-time config:** All secrets/URLs via `--dart-define` (no `.env` files) — `BuildConfig`
- **Circular DI prevention:** `bareDioProvider` (no auth interceptor) used by `AuthInterceptor` for retries
- **Single exception source:** `ApiException`, `PermissionException`, `ParseException` all in `analytics_models.dart`
- **Controlled dropdowns:** `ShopGroupFilter` uses `DropdownButton(value:)` not `DropdownButtonFormField(initialValue:)`

### Critical Business Rules
- Return formula: counts **invoices**, not unique days (`calculations.py` — LOCKED)
- Seasons: M2-4, M5-7, M8-10, M11-1 (NOT SS/AW)
- M11-1 label: `M11-1 2024-2025` format (cross-year)
- Grades: `No Grade < Member < Silver < Gold < Diamond` (NOT VIP0-DIAMOND)
- `vip_id = "0"` → non-VIP → excluded from grade analytics
- `SalesTransaction.Meta.ordering` → always call `.order_by()` before `.distinct()`
- `parse_cnv_period_filter()` returns `({}, False)` for no dates — check with `if not period_filter:`

### Permission System
20 permissions defined in `App/permissions.py` (web). Same permission strings checked in SemirPhone via `UserSession.hasPermission()` (mobile):
- `page_analytics`, `page_coupons`, `page_cnv_comparison`, `page_shop_detail`
- `download_analytics`, `download_coupons`, `download_shop_detail`
- `manage_users`, `manage_campaigns`

### Test Suites
**SemirDashboard:**
- `tests/test_shop_detail.py` — `ShopDetailTest` with `setUpTestData` (single 430k-row fixture load)
- Snapshots in `tests/snapshots/` — regenerate with `UPDATE_SNAPSHOTS=1 python manage.py test tests`
- Visual renders in `tests/render/` — regenerate with `snapshot_render.py` + `snapshot_visual.py`

**SemirPhone:**
- 198 tests (unit + widget + golden) — `flutter test`
- Golden images in `test/goldens/` — regenerate with `flutter test --update-goldens`
