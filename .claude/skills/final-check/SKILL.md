---
name: "final-check"
description: "Senior QA final release gate: scan all code, find bugs, verify test coverage, run full test suite, evaluate results, produce final report, update docs."
argument-hint: "Optional: focus area or previous report path"
---

## Role

You are a Senior QA Engineer performing the final release gate for SemirDashboard + SemirPhone.
Act methodically. Fix every issue you find. Do not skip steps.

## Execution Steps

### Step 0 — Read previous reports

Read `docs/performance_report.md`, `docs/mobile_audit_report.md`, and any `docs/FINAL_REPORT*.md`
to understand known issues and current status before starting.

---

### Step 1 — Full code scan (backend + mobile)

**Backend (`SemirDashboard/`):**

- Read every file in `App/analytics/`, `App/views/`, `App/services/`, `App/cnv/`, `App/models/`
- Read `App/urls.py`, `App/cnv/urls.py`, `SemirDashboard/urls.py`
- Read `App/permissions.py`, `App/middleware.py` (if exists)

Look for these project-specific bugs (in priority order):

| Pattern | Why it's a bug |
|---------|---------------|
| `.distinct()` without `.order_by()` on `SalesTransaction` or `Customer` | Both models have `Meta.ordering` — Django includes ordering columns in SELECT DISTINCT, producing wrong counts |
| `period_filter=None` passed to `_fetch_bd_raw()` or `_compute_grade_rows()` | These functions call `.get()` on period_filter; `None.get()` crashes. Must pass `{}` |
| `except Exception: pass` (broad catch) | Silences DB errors and real bugs. Narrow to the specific exception type |
| Season labels `SS` / `AW` | Obsolete — correct labels are M2-4, M5-7, M8-10, M11-1 |
| Grade names `VIP0` / `VIP1` / `VIP2` / `VIP3` | Obsolete — correct: No Grade < Member < Silver < Gold < Diamond |
| Return-visit formula changed | Locked formula — alert user, do not auto-fix |
| Missing `@requires_perm` on views | Every view must be protected (AJAX partials use `_ajax_perm_check()`) |
| Hardcoded colors in CSS / inline `style=` | Must use CSS tokens (`var(--token)`) — never raw hex in stylesheets |

- Read all templates in `App/templates/` — check `tbl-hdr-*`, card headers, stat cards against UI token rules

**Mobile (`semir-phone/`):**

Read every Dart file in `lib/features/`, `lib/core/`, `lib/shared/`

| Pattern | Why it's a bug |
|---------|---------------|
| `FutureProvider.family` without `.autoDispose` | Memory leak — each unique key persists forever |
| `.cast<String>()` on API list fields | Throws `CastError` at runtime on mixed-type API responses. Use `.whereType<String>().toList()` |
| Routes in GoRouter with no navigation entry point | Orphaned routes = unreachable UI. Check every route has ≥1 way to reach it |
| New analytics provider not in logout `ref.invalidate()` list | Data from previous user session leaks to next user |
| Hardcoded API URL string (not via `ApiConfig` / `endpoints.dart`) | Breaks env switching |
| `print()` in production code | Leaks PII to device logs |
| `is List` / `is Map` check missing before casting API response fields | `CastError` crash on unexpected server response |

**Docs consistency check:**

- Every URL in `App/urls.py` → must appear in `docs/project_urls.md`
- Every model field → `docs/project_models.md` must be accurate
- Every mobile route → `docs/project_mobile.md` navigation table must be accurate
- Home page card count in `docs/project_mobile.md` must match actual `home_page.dart` card list
- Flutter test count in release checklist must match `flutter test` actual count

Fix every issue found. Document each fix.

---

### Step 2 — Test coverage audit

**Backend:**

- List all view functions → check `SemirDashboard/tests/` for coverage
- List all analytics functions in `tab_functions.py` → check for unit tests
- List all `App/cnv/service.py` public functions → check coverage
- List all API endpoints (`/api/v1/`) → check `tests/test_api.py` coverage
- For period-filter endpoints: both `_alltime` and `_2025` variants must exist
- Any uncovered path → write the missing test

**Mobile:**

- List all pages in `lib/features/` → check `test/widget/` for a widget test
- List all providers → check `test/unit/` for a unit test
- List all service files → check `test/unit/` for a service test
- Any uncovered → write the missing test

---

### Step 3 — Run full test suite

Run tests in this order — stop if a gate fails:

```powershell
# Backend — lightweight tests first (no fixture loading, fast feedback)
cd SemirDashboard
python manage.py test tests.test_pages tests.test_auth tests.test_consistency -v 2 2>&1

# Backend — fixture-heavy tests
python manage.py test tests.test_sales tests.test_api tests.test_shop_detail -v 2 2>&1

# Backend — full suite
python manage.py test tests -v 2 2>&1

# Backend — regenerate snapshots (confirm no silent data changes)
$env:UPDATE_SNAPSHOTS=1; python manage.py test tests -v 2 2>&1; Remove-Item Env:UPDATE_SNAPSHOTS

# Backend — visual render
python manage.py shell -c "exec(open('tests/snapshot_render.py').read())"
python tests/snapshot_visual.py

# Mobile
cd ..\semir-phone
flutter analyze 2>&1
flutter test 2>&1
```

**Failure isolation rule:** If the full suite reports failures, always re-run the failing tests in isolation before marking them as real bugs:

```powershell
python manage.py test tests.test_api.ApiParityTest.test_<failing_name> -v 2 2>&1
```

A test that passes in isolation but fails in the full suite = test isolation issue (shared cache, shared state). Document it as a known limitation, not a code bug. Fix: add `cache.clear()` in the test class's `tearDown` if it populates the Django cache.

Record: pass/fail count, failures, timing per test class.

---

### Step 4 — Evaluate results

- Read snapshot JSON files — only `_last_run` field should differ vs previous run; any other field change = data regression
- Read `tests/render/_index.md` — must show 0 token issues
- Review `tests/render/png/*.png` visually for layout regressions
- Compare endpoint timing against `docs/performance_report.md` baseline
- Flag any newly failing test vs previous report
- Confirm Flutter golden count matches expected (currently 226 total)

---

### Step 5 — Write / Update `docs/FINAL_REPORT.md`

Include:

- Date, release branch, auditor
- Code scan findings: every bug found + fix applied (or "none found")
- Test coverage gaps: found + addressed (or "none")
- Full test run results: counts, failures, timing
- Snapshot evaluation: clean or list of changed fields
- Visual render evaluation: token issue count (must be 0)
- Performance delta vs baseline (flag any regression > 10%)
- Flutter analyze result
- Go/No-Go verdict with explicit pass criteria table

---

### Step 6 — Update all affected docs (REQUIRED last step)

After every run, update any doc file touched by changes made in Steps 1–3.
This step is not optional — a task is not complete until docs are consistent with code.

| What changed | Doc to update |
|-------------|---------------|
| New URL added or removed | `docs/project_urls.md` |
| Model field added/changed | `docs/project_models.md` |
| Analytics function changed | `docs/project_analytics.md` |
| CNV service changed | `docs/project_cnv.md` |
| Mobile route added/removed | `docs/project_mobile.md` navigation table |
| Mobile home card count changed | `docs/project_mobile.md` home card table + release checklist test count |
| New analytics provider added | `docs/project_mobile.md` provider rules section + logout invalidation list |
| Performance baseline changed | `docs/performance_report.md` |
| New mobile test file added | `docs/project_mobile.md` test structure section |
| Any structural change | `docs/project_structure.md` |
| New invariant locked | `.specify/memory/constitution.md` (bump version) |
| New run command added | `CLAUDE.md` |

**Verify CLAUDE.md is still accurate** — commands, paths, test class names, snapshot regen commands.

---

### Step 7 — Self-improve this skill

After writing/updating `FINAL_REPORT.md`, read this SKILL.md and update it based on what happened this run.

**What to look for:**

| Situation | Update to make |
|-----------|---------------|
| A new project-specific bug pattern found during Step 1 code scan | Add it to the bug table in Step 1 with its `Why it's a bug` explanation |
| A known false-fail test appeared again | Add it to Step 3 `Failure isolation rule` with the specific test name |
| Docs inconsistency found that isn't covered by Step 6's update table | Add the missing doc↔code pair to the Step 6 table |
| A step's command failed due to wrong directory or path | Fix the command in place |
| A new shared-cache isolation issue appeared | Add the pattern to the `Failure isolation rule` block |
| Code pattern checked in Step 1 no longer exists (refactored away) | Remove or update the pattern from the bug table |

**How to update:**

1. Read the current SKILL.md (`D:\New-jouney\semir\.claude\skills\final-check\SKILL.md`)
2. Make targeted edits to the specific steps that had issues — do not rewrite working steps
3. Append a one-line entry to the changelog below

**Changelog** (append — do not delete prior entries):

| Date | Change |
|------|--------|
| 2026-04-27 | Initial version created — Steps 1-6 based on first full QA run |
| 2026-05-03 | Step 3: added failure isolation rule for cache-state false-fails; named specific tests |
| 2026-05-03 | Step 1: added `.cast<String>()` and chart-provider-not-invalidated patterns to mobile bug table |
| 2026-05-03 | Step 6: added `performance_report.md` baseline-changed entry to update table |
| 2026-05-03 | Added this Step 7 self-improve section |

---

## Pass Criteria (all must be true for Go)

| Check | Requirement |
|-------|-------------|
| Backend unit tests | All green |
| API parity tests | All green when run in isolation (shared-cache artifacts excluded) |
| Snapshot diff | Only `_last_run` lines differ |
| Web pages smoke test | All 200 |
| Visual token issues | 0 |
| Flutter analyze | 0 errors |
| Mobile unit/widget tests | All green |
| Docs consistency | All URLs, models, routes, card counts documented and accurate |
| FINAL_REPORT.md | Written/updated with Go/No-Go verdict |
