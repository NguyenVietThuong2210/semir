---
description: Profile every URL/API, optimize code, verify snapshots unchanged, render HTML, output perf report to docs/
---

Run a full performance audit and optimization pass on SemirDashboard. Follow every step in order.

**This skill is self-adapting — it discovers URLs, views, and tests dynamically from source files each run. Never hardcode lists.**

---

## Step 1 — Discover all URLs dynamically

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
```bash
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

```bash
cd SemirDashboard
UPDATE_SNAPSHOTS=1 python manage.py test tests -v 2 2>&1
```

Record:
- Each test method: pass/fail, execution time (from `[TIMER]` blocks)
- Snapshot files: which were created new vs only `_last_run` updated
- Total suite time

**Gate:** All tests must pass and every URL must have ≥1 green test before proceeding to Step 3.

---

## Step 3 — Scan and optimize each URL/API

For each URL in the todo list, **read the view file** (discovered in Step 1) and trace into every function it calls. Look for:

**Query inefficiencies:**
- N+1 queries — loop that hits DB inside a loop → batch with `select_related`, `prefetch_related`, or `filter(pk__in=ids)`
- Fetching full model rows when only a few fields are needed → add `.only(...)` or `.values(...)`
- `.distinct()` without `.order_by()` on `SalesTransaction` or `Customer` (both have `Meta.ordering`) → must call `.order_by()` first
- Filter fields not in any index → check if `db_index=True` is missing

**Cache opportunities:**
- Repeated identical DB queries across a request → `cache.get_or_set(key, fn, timeout)`
- Already-cached: `_load_sales()` (5 min), `_fetch_bd_raw()` (5 min), dropdown options (5 min), CNV phone sets (10 min) — don't double-cache these
- Do NOT cache: upload job status, sync status, any real-time data

**Python-level:**
- Dict/list lookup repeated inside hot loop → hoist to variable before loop
- Multiple sorts of same list → sort once, slice/reuse
- Building large intermediate lists → switch to generators where possible

**Template:**
- `{% for x in queryset %}` without `.values()` in view → pass dicts instead of ORM objects
- `{{ obj.related_field }}` access N times in loop without prefetch → annotate or prefetch in view

For each optimization: note file + approximate line, issue description, fix applied.

**Do NOT change business logic. Do NOT change return data shape** — snapshots in Step 4 must remain byte-identical (except `_last_run`).

---

## Step 4 — Re-run ALL UTs (old + new): verify data + measure speedup

Run the complete suite — every pre-existing test + every new test from Step 2 — without `UPDATE_SNAPSHOTS`:

```bash
cd SemirDashboard
python manage.py test tests -v 2 2>&1
```

**Snapshot integrity:**
- Each snapshot file: only the `_last_run` line should differ from baseline
- If any other field changed → optimization broke data shape → revert that specific change

**Timing comparison** per test:
- New time vs baseline (Step 2c)
- Delta: `4.14s → 2.80s (-32%)`

**Acceptance criteria — all must be true before Step 5:**
- All tests pass (old + new)
- Zero data changes in any snapshot
- Every URL from the todo list has ≥1 green test

---

## Step 5 — Verify app availability (render all discovered pages)

Using the URL list from Step 1, build the render list dynamically — include every GET-accessible page route. Skip POST-only endpoints and `<str:tab>` variants (test one representative tab each).

**For `[period-filter]` URLs — render both variants:**
- All-time: no query params (e.g. `/analytics/`)
- Period 2025: `?date_from=2025-01-01&date_to=2025-12-31` (or `?start_date=...&end_date=...` depending on the view's param names)

Both must return 200. Record timing for each variant separately to show the cost of filtering.

```python
# python manage.py shell -c "..."
import os; os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'SemirDashboard.settings')
import django; django.setup()
from django.test import Client
from django.contrib.auth.models import User

c = Client()
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

All pages must return 200. For any non-200: read the view, identify the error (missing fixture data / wrong redirect / broken import), fix it.

---

## Step 6 — Update docs if needed

Review what changed during this run and update only the affected doc files. Do not rewrite unrelated sections.

| What changed | Doc to update |
|-------------|---------------|
| New URL route discovered (missing from docs) | `docs/project_urls.md` |
| New test file created | `docs/project_structure.md` |
| View or service function significantly refactored | relevant `docs/project_analytics.md` / `docs/project_cnv.md` |
| Cache key or TTL changed | `docs/project_analytics.md` or `docs/project_cnv.md` |
| DB query pattern changed (index added, `.order_by()` fix) | `docs/project_models.md` |
| No structural changes — template/Python micro-opts only | no doc update needed |

If `docs/project_urls.md` is missing any route discovered in Step 1, add it now.

---

## Step 7 — Write performance report to docs/performance_report.md

Check if `docs/performance_report.md` exists. If yes, read it and extract previous metrics for comparison.

Write the new report to `docs/performance_report.md` (overwrite):

```markdown
# Performance Report

**Generated:** YYYY-MM-DD HH:MM
**URLs audited:** N  (discovered dynamically from urls.py)
**Tests run:** N old + N new = N total

---

## Summary

| Metric | Baseline | After | Delta |
|--------|----------|-------|-------|
| Total test suite time | Xs | Ys | -Z% |
| Slowest endpoint | name (Xs) | name (Ys) | -Z% |
| URLs with test coverage | N/N | N/N | |

---

## URL Coverage

| URL | View | Test(s) | Status |
|-----|------|---------|--------|
| /analytics/ | analytics_dashboard | test_analytics_200 | covered |
| ... (all URLs from Step 1) | | | |

New tests added this run: list them here.

---

## URL Availability (Step 5)

| Page | URL | HTTP Status |
|------|-----|-------------|
| ... (all pages tested) | | 200 OK / FAIL |

---

## Optimizations Applied

### `App/views/analytics.py`
- **Issue:** description
- **Fix:** description
- **Impact:** measured or estimated

(one section per file changed)

If no optimizations found: "No actionable optimizations found."

---

## Test Results

| Test | Baseline | After | Delta | Snapshots |
|------|----------|-------|-------|-----------|
| test_name | Xs | Ys | -Z% | unchanged |

---

## Regressions / Issues

List test failures, snapshot data changes, or non-200 pages.
If none: "None."

---

## Comparison with Previous Report

(Only if previous report existed)
- Improvements since last run: ...
- Regressions since last run: ...
- New URLs added since last run: ...
- New tests added since last run: ...
```
