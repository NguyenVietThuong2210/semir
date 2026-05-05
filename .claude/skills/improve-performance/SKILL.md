---
name: "improve-performance"
description: "Profile every URL/API (web + mobile), optimize code, verify snapshots unchanged, render HTML, output perf report to docs/"
argument-hint: "Optional: focus area (web / mobile / endpoint name)"
---

Run a full performance audit and optimization pass on **SemirDashboard (Django web)** and **SemirPhone (Flutter mobile)**. Follow every step in order.

**This skill is self-adapting — it discovers URLs, views, routes, and tests dynamically from source files each run. Never hardcode lists.**

---

## WEB AUDIT (SemirDashboard)

---

## Step 1 — Discover all web URLs dynamically

**Read the actual URL files** — do not use any hardcoded list:
```
App/urls.py
App/cnv/urls.py
SemirDashboard/urls.py   ← root dispatcher
```

From these files, extract every `path(...)` and `re_path(...)` entry. For each route record:
- **URL pattern** (e.g. `analytics/tab/<str:tab>/`)
- **View function name** (e.g. `analytics_tab`)
- **View file** — trace the import to find which file the view lives in
- **HTTP methods** it handles (GET / POST / AJAX)
- **Requires auth?** (has `@requires_perm` or `@login_required`)
- **Has period filter?** — read the view source, check if it accepts `start_date`/`end_date`/`date_from`/`date_to` query params

For routes with period filter, tag them `[period-filter]` — they require dual-variant testing (see Step 2b).

Build a TodoWrite list from this extracted data, one entry per route. Mark each `[pending]`.

This list is the single source of truth for Steps 2–5. Every route in `urls.py` must appear here — including any routes added since the last run.

---

## Step 2 — Baseline: audit coverage, create missing UTs, run all tests + capture timing

### 2a — Discover existing tests dynamically

**Read all test files** in `SemirDashboard/tests/`:
```powershell
ls SemirDashboard/tests/test_*.py
```

For each test file, scan its contents to extract:
- Every test method name (`def test_*`)
- Which views/URLs/functions each test calls (grep for URL strings and function names)

Build a coverage map: `{url_pattern: [test_methods that cover it]}`.

For any URL from Step 1 that has **zero** coverage entries → mark as **UNCOVERED**.

### 2b — Create tests for uncovered URLs

For each UNCOVERED URL, create a new test method in the most appropriate existing test file (or create a new `test_<area>.py` if the area has no test file yet).

Rules for new tests:
- Extend `SnapshotTestCase` from `tests/base.py`
- Use `setUpTestData` for fixture-dependent tests — never `setUp` (too slow for 430k-row fixtures)
- Page-render test: `self.client.force_login(superuser)` → `self.client.get(url)` → assert `status_code == 200`
- Data/output test: call the view or service directly → `self.assert_snapshot(name, data)` to lock output
- AJAX view: pass `HTTP_X_REQUESTED_WITH='XMLHttpRequest'`
- POST-only views (triggers, uploads): test with valid payload, assert redirect or JSON response

**For `[period-filter]` URLs — always create two test variants:**

```python
PERIOD_2025 = {'date_from': '2025-01-01', 'date_to': '2025-12-31'}   # or start_date/end_date depending on view

def test_<name>_alltime(self):
    # No date params → all-time data
    data = get_xxx_data(shop, date_from=None, date_to=None)
    self.assert_snapshot('<name>_alltime', _extract_kpis(data))

def test_<name>_period_2025(self):
    # With 2025 filter → period-scoped data
    data = get_xxx_data(shop, **PERIOD_2025)
    self.assert_snapshot('<name>_2025', _extract_kpis(data))
```

Additionally, assert that `all_time` values ≥ `period` values for additive metrics (totals, counts) — this catches filter bugs:
```python
self.assertGreaterEqual(alltime['total_customers'], period['total_customers'])
self.assertGreaterEqual(alltime['returning_invoices'], period['returning_invoices'])
```

Snapshot naming convention: `<area>_alltime` and `<area>_2025` (e.g. `analytics_alltime`, `analytics_2025`, `coupon_shop_alltime`, `coupon_shop_2025`).

After adding new tests, re-scan to confirm every URL now has coverage.

### 2c — Generate snapshots + run full baseline

```powershell
cd SemirDashboard
$env:UPDATE_SNAPSHOTS=1; python manage.py test tests -v 2 2>&1; Remove-Item Env:UPDATE_SNAPSHOTS
```

Record:
- Each test method: pass/fail, execution time (from `[TIMER]` blocks)
- Snapshot files: which were created new vs only `_last_run` updated
- Total suite time

**Gate:** All tests must pass and every URL must have ≥1 green test before proceeding to Step 3.

---

## Step 3 — Senior-engineer optimization pass

You are now acting as a senior backend engineer doing a production performance review. Your job is not to enumerate issues — it is to **read the code, understand it deeply, and implement the best version of it**. Fix everything you find in the same pass. Leave the code better than you found it.

### 3a — Cold-start benchmark (run FIRST before any optimization)

Before touching any code, clear the cache and measure true cold-start latency for every analytics service function. This gives the real baseline — test suite timings are misleading because earlier test classes warm the cache.

```python
# SemirDashboard/manage.py shell
import time
from datetime import date
from django.core.cache import cache
cache.clear()
print('Cache cleared - cold start')

from App.analytics.tab_functions import get_sales_tab
from App.analytics.coupon_analytics import get_coupon_summary
from App.cnv.service import compute_cnv_breakdown, get_cnv_phone_sets

rows = []
for label, fn, args, kwargs in [
    ('Sales all-time   COLD', get_sales_tab, ['grade'], {'date_from': None, 'date_to': None}),
    ('Sales all-time   WARM', get_sales_tab, ['grade'], {'date_from': None, 'date_to': None}),
    ('Sales 2025       COLD', get_sales_tab, ['grade'], {'date_from': date(2025,1,1), 'date_to': date(2025,12,31)}),
    ('Sales 2025       WARM', get_sales_tab, ['grade'], {'date_from': date(2025,1,1), 'date_to': date(2025,12,31)}),
    ('Coupon           COLD', get_coupon_summary, [], {'date_from': None, 'date_to': None}),
    ('Coupon           WARM', get_coupon_summary, [], {'date_from': None, 'date_to': None}),
]:
    t0 = time.perf_counter()
    fn(*args, **kwargs)
    rows.append((label, time.perf_counter() - t0))

# CNV needs phone sets first
phones_pos, phones_cnv = get_cnv_phone_sets()
for label, pf in [('Customer/CNV     COLD', {}), ('Customer/CNV     WARM', {})]:
    t0 = time.perf_counter()
    compute_cnv_breakdown(pf, phones_pos, phones_cnv)
    rows.append((label, time.perf_counter() - t0))

print(f"{'Endpoint':<25} {'Time':>7}  Limit  Status")
print('-' * 50)
for label, t in rows:
    limit = 15
    flag = 'OK' if t < limit else 'SLOW'
    print(f'{label:<25} {t:>6.2f}s  <{limit}s  {flag}')
```

Record cold vs warm for each. Any cold > 10s is a target for optimization. Proceed to 3b.

### 3b — Instrument each view: count queries + measure wall time

For every view in the URL list, instrument it in a shell session to see exactly what it costs:

```python
from django.test.utils import override_settings
from django.db import connection, reset_queries
import time

with override_settings(DEBUG=True):
    reset_queries()
    t0 = time.perf_counter()
    response = client.get(url)
    elapsed = time.perf_counter() - t0
    queries = connection.queries
    print(f"{url}: {elapsed:.3f}s, {len(queries)} queries")
    # Print the 3 slowest:
    for q in sorted(queries, key=lambda x: float(x['time']), reverse=True)[:3]:
        print(f"  {float(q['time']):.3f}s  {q['sql'][:120]}")
```

Record: total wall time, query count, and the top-3 slowest queries per endpoint. This is your baseline — every optimization must show a measurable delta here.

### 3b — Read every hot function end-to-end

For each view, **fully read** the view function + every function it calls (trace the call tree). Read the actual source — do not skim. You are looking for:

**DB layer (highest leverage — fix these first):**
- Count queries fired per request. More than 5 for a page load is a smell.
- N+1: any `for item in list: item.related` pattern without prefetch → batch with `select_related` / `prefetch_related` / `filter(id__in=ids)`
- Unnecessary full-table fetch: `Model.objects.all()` when only a filtered subset is needed → add `.filter(...)` before `.values()`
- Fetching all columns when only 2-3 are used → switch to `.values('f1','f2')` or `.only('f1','f2')`
- Unindexed filter fields on hot queries → add `db_index=True` and generate migration
- Python-set intermediate: `set(qs.values_list(..., flat=True))` then `filter(field__in=python_set)` → replace with subquery `filter(field__in=qs.values(...))`
- Duplicate queries: same queryset evaluated twice → compute one, derive the other in Python
- Dual-scan pattern: one query for period data + one for all-time data on same table → merge into single broad fetch + Python filter. **Before merging**, verify that the broader fetch won't silently exclude rows needed by the narrower query (check null/empty values in dev data)
- Aggregate + full-scan on same table: `aggregate(Min, Max)` followed by `list(Model.objects.all())` → skip the aggregate and compute min/max in Python from the already-fetched list
- `.distinct()` on a model with `Meta.ordering` without `.order_by()` → always `.order_by().distinct()`

**Cache layer (second priority):**
- Already cached: `_load_sales()`, `_fetch_bd_raw()`, dropdown options, CNV phone sets, overview count blocks (wrapped in `_djc.get/_djc.set`) — do NOT add a second cache around these. **Before flagging any count/query as an issue, check if it's inside a `if ov is None: ... _djc.set(...)` block.**
- Cache candidates: any pure-read function that: (a) queries >10k rows, (b) result is deterministic for the same inputs, (c) called from multiple requests. Key format: `f"<area>:{param1}:{param2}"`, TTL 5 min for analytics, 10 min for rarely-changing reference data
- Do NOT cache: sync status, upload job list, real-time counters

**Algorithm layer (third priority):**
- O(N×M) list scan inside a loop → pre-group into a dict before the loop, then O(1) lookup inside
- Sorting the same list multiple times → sort once and reuse
- Large intermediate lists that are only iterated once → convert to generator
- String formatting / regex inside a hot loop → precompile / hoist

**Python object overhead:**
- ORM objects in large loops (`.values()` not used) → switch to `.values()` to get plain dicts; avoids descriptor overhead
- `getattr(obj, field)` called N times for same object → cache to local variable

**Template layer (fix at view level, not template):**
- Pass dicts from `.values()`, never raw querysets — templates must not trigger DB queries
- Precompute any value the template computes multiple times (e.g. percentage, formatted date)

### 3c — Implement every fix found

For each issue found in 3b:
1. **Implement the fix immediately** — do not just note it
2. Re-run the instrumentation from 3a for that endpoint and record the new query count and wall time
3. Confirm: query count decreased OR wall time improved by ≥10%
4. If a fix makes no measurable difference → revert it (avoid premature abstraction)

Constraints:
- **Do NOT change business logic** — return values and data shapes must stay identical (snapshots verify this in Step 4)
- **Do NOT refactor for its own sake** — only change what reduces measurable cost
- **Do NOT add caching to already-cached callpaths** — check existing cache keys first

### 3d — Index audit

For every filter field used in a hot query that was slow in 3a:
1. Check if `db_index=True` is set on the model field
2. If missing and the field is used in `.filter(field=...)` on a table >10k rows → add the index
3. Generate and apply the migration: `python manage.py makemigrations && python manage.py migrate`
4. Re-run the query and confirm speedup

### 3e — Summary table

After all fixes are applied, produce a table:

| File | Line | Issue | Fix | Query Δ | Time Δ |
|------|------|-------|-----|---------|--------|
| views/customer.py | 71 | select_related() JOIN not needed | removed | -1q | -120ms |
| tab_functions.py | 1465 | objects.all() full scan | phone__in subquery | -1q | -80ms |

This table goes into the Step 9 report.

---

## Step 4 — Re-run ALL web UTs: verify data + measure speedup

```powershell
cd SemirDashboard
python manage.py test tests -v 2 2>&1
```

**Snapshot integrity:**
- Each snapshot file: only the `_last_run` line should differ from baseline
- If any other field changed → optimization broke data shape → revert that specific change

**Acceptance criteria — all must be true before Step 5:**
- All tests pass (old + new)
- Zero data changes in any snapshot
- Every URL from the todo list has ≥1 green test

---

## Step 5 — Verify web app availability (render all discovered pages)

Using the URL list from Step 1, build the render list dynamically — include every GET-accessible page route. Skip POST-only endpoints and `<str:tab>` variants (test one representative tab each).

**For `[period-filter]` URLs — render both variants:**
- All-time: no query params
- Period 2025: `?date_from=2025-01-01&date_to=2025-12-31`

```python
# python manage.py shell -c "..."
import os; os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'SemirDashboard.settings')
import django; django.setup()
from django.test import Client, override_settings
from django.contrib.auth.models import User

# REQUIRED: override ALLOWED_HOSTS — test Client sends SERVER_NAME=testserver
# which is not in ALLOWED_HOSTS, causing 400 on every page without this.
with override_settings(ALLOWED_HOSTS=['*']):
    c = Client(SERVER_NAME='localhost')
    superuser = User.objects.filter(is_superuser=True).first()
    c.force_login(superuser)

    # Build this list from Step 1 discovery — do not hardcode
    pages = [
        # (url, label) — populated from Step 1 URL list at runtime
    ]

    results = []
    for url, label in pages:
        try:
            r = c.get(url, follow=True)
            ok = r.status_code == 200
            results.append((label, url, r.status_code, 'OK' if ok else 'FAIL'))
        except Exception as e:
            results.append((label, url, 'ERR', str(e)[:80]))

    for label, url, code, status in results:
        print(f'  [{code}] {label:35s} {url}')

    fails = [r for r in results if r[3] != 'OK']
    print(f'\n{len(results) - len(fails)}/{len(results)} pages OK')
```

All pages must return 200. Fix any non-200 before proceeding.

---

## MOBILE AUDIT (SemirPhone)

---

## Step 6 — Discover all mobile routes + providers dynamically

**Read `semir-phone/lib/app.dart`** — extract every `GoRoute(path: ...)` entry:
- Route path (e.g. `/sales`, `/sales/charts`)
- Page widget (e.g. `SalesPage`)
- Permission guard (`_requirePerm('...')` or none)
- Has sub-routes? Has ≥1 navigation entry point in UI?

**Read every provider file** in `semir-phone/lib/features/*/`:
- Provider type (`FutureProvider`, `FutureProvider.family`, `AsyncNotifierProvider`)
- Has `.autoDispose`? — **Required for `.family` providers. Flag any missing.**
- Is it in the logout `ref.invalidate()` list in `auth_provider.dart`? — **Required for analytics providers. Flag any missing.**

**Read every service file** in `semir-phone/lib/features/*/`:
- API endpoint it calls
- Response field access — flag any `.cast<String>()` (must use `.whereType<String>()`)
- Null guards — flag any direct cast without `is List` / `is Map` check

**Read every page file** in `semir-phone/lib/features/*/`:
- Are all static widgets `const`? Flag non-const constructors that could be const.
- Does the page handle error + loading states?
- Does it have pull-to-refresh (`PullToRefresh` wrapper)?
- For tab-based pages: does it use lazy loading?

Build a route+provider audit table. Mark issues `[WARN]` (performance) or `[BUG]` (correctness).

---

## Step 7 — Mobile static analysis + test run

### 7a — Flutter analyze

```powershell
cd semir-phone
flutter analyze 2>&1
```

**Gate: 0 `error`-level issues.** `info` and `warning` level issues in test files are acceptable — do not block on them.

To distinguish errors from infos, check for lines containing ` error -` in the output:
```powershell
flutter analyze 2>&1 | Select-String " error -"
```
If that returns nothing → gate passes even if total issue count > 0.

### 7b — Scan for production anti-patterns

```powershell
cd semir-phone

# print() in production code (leaks PII to device logs)
Select-String -Path "lib\**\*.dart" -Pattern "^\s+print\(" -Recurse

# Hardcoded URL strings (must use endpoints.dart constants)
Select-String -Path "lib\**\*.dart" -Pattern '"/api/' -Recurse

# Unsafe cast
Select-String -Path "lib\**\*.dart" -Pattern "\.cast<" -Recurse

# FutureProvider.family without autoDispose
Select-String -Path "lib\**\*.dart" -Pattern "FutureProvider\.family" -Recurse | Where-Object { $_ -notmatch "autoDispose" }
```

Fix every match found. Document each fix.

### 7c — Run full Flutter test suite

```powershell
cd semir-phone
flutter test --reporter expanded 2>&1
```

Record total count, pass/fail, timing. Golden pixel-diff failures → regenerate:
```powershell
flutter test --update-goldens test/golden/golden_test.dart
```

**Gate: 0 failures before proceeding.**

### 7d — Mobile API performance

Cross-reference the API parity test results from `SemirDashboard/tests/test_api.py`:
- Read the latest log in `SemirDashboard/tests/output/` (newest `*_ut_run.log`)
- Extract timing for each API endpoint test
- Flag any endpoint > 5s (backend issue — fix in Django, not Flutter)

---

## Step 8 — Update docs

**Web changes:**

| What changed | Doc to update |
|-------------|---------------|
| New URL route | `docs/project_urls.md` |
| New test file | `docs/project_structure.md` |
| View/service refactored | `docs/project_analytics.md` / `docs/project_cnv.md` |
| Cache key or TTL changed | `docs/project_analytics.md` or `docs/project_cnv.md` |
| DB index added / `.order_by()` fix | `docs/project_models.md` |

**Mobile changes:**

| What changed | Doc to update |
|-------------|---------------|
| New GoRouter route | `docs/project_mobile.md` navigation table |
| New analytics provider | `docs/project_mobile.md` provider rules + logout list |
| Home card count changed | `docs/project_mobile.md` home card table + release checklist count |
| New test file | `docs/project_mobile.md` test structure section |
| Flutter test count changed | `docs/project_mobile.md` release checklist |

If `docs/project_urls.md` is missing any route from Step 1, add it now.
If `docs/project_mobile.md` navigation table is missing any route from Step 6, add it now.

---

## Step 10 — Self-improve this skill

After writing the report, read this SKILL.md file and update it based on what happened this run.

**What to look for:**

| Situation | Update to make |
|-----------|---------------|
| A step produced an error/confusion that wasn't in the instructions | Add the fix to the relevant step |
| A code snippet produced wrong output (wrong exit code, missing flag, wrong path) | Fix the snippet |
| You found a new project-specific anti-pattern not yet in the scan list | Add it to Step 6's audit table |
| A Step 3 "issue" turned out to be already handled (cache, different table, intentional) | Add a note to Step 3 `Cache layer` or `DB layer` to skip that class of issue |
| The Django test Client returned 400/DisallowedHost | Already fixed in Step 5 — do not re-add |
| Flutter analyze exit code 1 for info-only issues | Already fixed in Step 7a — do not re-add |
| A new URL route appeared in urls.py not previously documented | Note: Step 1 handles this automatically — no skill update needed |
| Step 9 report template had a column that didn't apply (e.g. Baseline when no prior report) | Add conditional note to Step 9: "if no prior report exists, omit Delta columns" |

**How to update:**

1. Read the current SKILL.md (`D:\New-jouney\semir\.claude\skills\improve-performance\SKILL.md`)
2. For each lesson learned this run, make a targeted edit to the relevant step
3. Do NOT restructure the skill or rewrite steps that worked fine
4. Keep changes minimal — fix what was wrong, don't over-engineer
5. Append a one-line entry to the changelog at the bottom of this file

**Changelog** (append — do not delete prior entries):

| Date | Change |
|------|--------|
| 2026-05-03 | Step 5: added `override_settings(ALLOWED_HOSTS=['*'])` + `SERVER_NAME='localhost'` to fix DisallowedHost 400 |
| 2026-05-03 | Step 7a: clarified gate is 0 *errors*, not 0 total issues; added `Select-String " error -"` filter command |
| 2026-05-03 | Step 3 Cache layer: added note to check for `_djc.get/_djc.set` cache blocks before flagging count queries as issues |
| 2026-05-03 | Added this Step 10 self-improve section |
| 2026-05-03 | Added Step 3a cold-start benchmark with working shell script |
| 2026-05-03 | `App/cnv/service.py _fetch_bd_raw`: merged dual POSCustomer queries + eliminated 2 aggregate queries (7→4 queries cold all-time). Saved ~0.7s cold. Verify semantics: customers with registration_date but phone=NULL are safe to exclude in practice (count=0 in fixture) |
| 2026-05-04 | Pattern: check for cross-function table scan duplication — `get_cnv_phone_sets` and `_fetch_bd_raw` both scanned POS+CNV tables (6 queries cold). Fix: `get_cnv_phone_sets` now calls `_fetch_bd_raw({})` and derives sets in-memory, priming breakdown cache (4 queries cold). |
| 2026-05-04 | Pattern: check for duplicate calls with same args in views — `_compute_grade_rows(cnv_phones_all, {})` was called twice for all-time (same as `_compute_grade_rows(cnv_phones_all)`). Fix: reuse at_grade_rows when no period filter. |
| 2026-05-04 | API test PERF_LIMIT=5.0s for CNV customer: test was failing not because of test issue but real cold-start latency (6.33s). Fix was code optimization, not test adjustment. Always investigate real code before adjusting test thresholds. |

---

## Step 9 — Write performance report to docs/performance_report.md

Read existing `docs/performance_report.md` for baseline comparison (if exists), then overwrite:

```markdown
# Performance Report

**Generated:** YYYY-MM-DD HH:MM
**Web URLs audited:** N  (discovered dynamically from urls.py)
**Mobile routes audited:** N  (discovered dynamically from app.dart)
**Web tests run:** N old + N new = N total
**Mobile tests run:** N

---

## Web Summary

| Metric | Baseline | After | Delta |
|--------|----------|-------|-------|
| Total web test suite time | Xs | Ys | -Z% |
| Slowest web endpoint | name (Xs) | name (Ys) | -Z% |
| Web URLs with test coverage | N/N | N/N | |
| Web pages returning 200 | N/N | N/N | |

## Mobile Summary

| Metric | Result |
|--------|--------|
| Flutter analyze errors | 0 |
| Mobile tests pass | N/N |
| Routes with nav entry point | N/N |
| Providers with autoDispose | N/N |
| Providers in logout invalidate | N/N |
| print() leaks found | N |
| Unsafe .cast<> found | N |

---

## Web URL Coverage

| URL | View | Test(s) | Status |
|-----|------|---------|--------|
| /analytics/ | analytics_dashboard | test_analytics_200 | covered |
| ... (all URLs from Step 1) | | | |

New web tests added this run: list them here.

---

## Mobile Route Coverage

| Route | Page | Permission | Nav entry | Test |
|-------|------|-----------|-----------|------|
| /sales | SalesPage | sales.view | Home card + AppBar | widget test |
| ... (all routes from Step 6) | | | | |

---

## Web Page Availability (Step 5)

| Page | URL | HTTP Status | Time |
|------|-----|-------------|------|
| ... (all pages tested) | | 200 OK / FAIL | Xs |

---

## Web Optimizations Applied

(one section per file changed — Issue / Fix / Impact)

If no optimizations found: "No actionable web optimizations found."

---

## Mobile Issues Fixed

| File | Issue | Fix | Severity |
|------|-------|-----|----------|
| sales_provider.dart | FutureProvider.family without autoDispose | Added .autoDispose | BUG |

If none: "No mobile issues found."

---

## Web Test Results

| Test | Baseline | After | Delta | Snapshots |
|------|----------|-------|-------|-----------|
| test_name | Xs | Ys | -Z% | unchanged |

---

## Mobile Test Results

| Suite | Tests | Pass | Fail | Time |
|-------|-------|------|------|------|
| unit/ | N | N | 0 | Xs |
| widget/ | N | N | 0 | Xs |
| golden/ | N | N | 0 | Xs |

---

## API Endpoint Timing (from test_api.py)

| Endpoint | All-time | Period (2025) | Under 5s |
|----------|----------|---------------|----------|
| GET /analytics/ | Xs | Xs | ✅/⚠️ |
| GET /cnv/customer-analytics/ | Xs | Xs | ✅/⚠️ |

---

## Regressions / Issues

List test failures, snapshot data changes, non-200 pages, mobile errors.
If none: "None."

---

## Comparison with Previous Report

(Only if previous report existed)
- Web improvements since last run: ...
- Mobile improvements since last run: ...
- Regressions since last run: ...
- New URLs / routes added: ...
```
