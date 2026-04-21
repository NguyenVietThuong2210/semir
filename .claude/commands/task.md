---
description: Execute a dev task — implement, check download buttons, run UTs, update docs
---

Execute a full development task on SemirDashboard following this workflow:

**Task:** $ARGUMENTS

---

## Step 1 — Load context

Read these files before touching any code:
- `docs/ANALYSIS.md` — architecture overview and critical rules
- Any doc file relevant to the task area (e.g. `docs/project_analytics.md` for analytics work, `docs/project_cnv.md` for CNV work, `docs/project_urls.md` if adding routes)

Identify:
- Which files need to change
- Whether the task involves a **download/export** feature
- Which existing tests cover the affected area

---

## Step 2 — Implement

Make all code changes. Follow project conventions:
- Views use `@requires_perm("codename")` — for AJAX views use `_ajax_perm_check(request, codename)` instead
- New URL routes go in `App/urls.py` (app-level) or `App/cnv/urls.py`; update `docs/project_urls.md` after
- Season labels: M2-4, M5-7, M8-10, M11-1. M11-1 format: `M11-1 2024-2025` (NOT `2025/2026`)
- Grades: No Grade / Member / Silver / Gold / Diamond (NOT VIP0–DIAMOND)
- Always `.order_by()` before `.distinct()` on SalesTransaction and Customer queries
- `parse_cnv_period_filter()` returns `({}, False)` for empty input — check `if not period_filter:`, never `if period_filter is None:`

---

## Step 3 — Check download button (if task involves export/download)

If the task adds or changes a download/export feature, verify all three layers:

**A. Permission gate in template:**
Search for the download button in the relevant template. Confirm it is wrapped with:
```django
{% check_perm 'download_xxx' as can_download %}
{% if can_download %} ... {% endif %}
```

**B. View permission check:**
Confirm the export view has `@requires_perm("download_xxx")` decorator.

**C. Permission exists in PERMISSION_DEFS:**
Search `App/permissions.py` — confirm `download_xxx` is defined in `PERMISSION_DEFS`.

If any layer is missing, fix it before proceeding.

---

## Step 4 — Find and run relevant tests

**Find relevant tests** by searching `SemirDashboard/tests/` for methods that reference the changed files, views, functions, or templates. Do NOT run all tests — only the ones that cover the changed area.

Mapping to guide selection:

| Changed area | Test file / method pattern |
|-------------|---------------------------|
| `views/customer.py`, `templates/customer/` | `tests/test_customer*` or grep for `customer_detail` |
| `views/shop_detail.py`, `templates/shop_detail/` | `tests/test_shop_detail.py` → `ShopDetailTest` |
| `analytics/tab_functions.py` (sales) | `ShopDetailTest.test_sales_*` or `test_snapshot_sales_*` |
| `analytics/tab_functions.py` (customer) | `ShopDetailTest.test_customer_*` or `test_snapshot_customer_*` |
| `analytics/coupon_analytics.py` | `ShopDetailTest.test_coupon_*` |
| `cnv/service.py`, `cnv/views.py` | grep for relevant function names in tests/ |
| Template-only change (no data shape change) | No snapshot regeneration needed — run the AJAX/page tests only |

**Run only the matched tests:**
```bash
cd SemirDashboard

# Single method
python manage.py test tests.<file>.<Class>.<method> -v 2

# All methods in a class
python manage.py test tests.<file>.<Class> -v 2
```

**If snapshots are stale** (data shape changed, not just template change):
```bash
UPDATE_SNAPSHOTS=1 python manage.py test tests.<file>.<Class>.<method> -v 2
```

**If no test covers the changed area:** note it in the summary — do not run unrelated tests to compensate.

All matched tests must pass before proceeding. Fix any failures.

---

## Step 5 — Update docs

Update only the docs files affected by the change. Do not rewrite unrelated sections.

| Changed area | Doc to update |
|-------------|---------------|
| New URL route | `docs/project_urls.md` |
| Model field added/changed | `docs/project_models.md` |
| Analytics formula or season logic | `docs/project_analytics.md` |
| CNV service / API / sync | `docs/project_cnv.md` |
| New permission | `docs/project_business_logic.md` |
| New file or package | `docs/project_structure.md` |
| Architecture change | `docs/ANALYSIS.md` |

Keep edits minimal and accurate — only update what actually changed.

---

## Step 6 — Summary

Report:
- What was changed (files + brief description)
- Download button check result (if applicable)
- Test results (pass/fail counts, any snapshot updates)
- Docs sections updated
