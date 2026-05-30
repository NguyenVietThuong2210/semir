# Description Layout Checklist

## Problem Fixed
Django template tags (`{% load %}`, `{% with %}`, `{% if %}`, `{% else %}`, `{% check_perm %}`) each emit a newline, causing 2–5 blank lines before the first HTML element in injected tab content. This rendered as a visible blank bar above the description row.

**Fix:** Collapse header template tags onto a single line so only 1 blank line precedes the first `<div>`.

**Pattern (broken):**
```
{% load ... %}
{% with ... %}
{% if not rows %}
<div>No data</div>
{% else %}

{% check_perm ... %}
<div class="d-flex...">    ← 5 blank lines before this
```

**Pattern (fixed):**
```
{% load ... %}{% check_perm ... %}{% with ... %}{% if not rows %}<div>No data</div>{% else %}
<div class="d-flex...">    ← 1 blank line before this
```

---

## Phase 1 — Layout fix (description + download on same row)
All tabs changed from `justify-content-end` (download-only) + separate `<p>` below,
to `justify-content-between` (description left, download right).

| # | Template | Status |
|---|----------|--------|
| 1 | `product/tabs/month.html` | ✅ Fixed |
| 2 | `product/tabs/year.html` | ✅ Fixed |
| 3 | `product/tabs/week.html` | ✅ Fixed |
| 4 | `product/tabs/vip_grade.html` | ✅ Fixed (removed alert-info box) |
| 5 | `product/tabs/sales_season.html` | ✅ Fixed (removed alert-info box) |
| 6 | `product/tabs/product_season.html` | ✅ Fixed (removed alert-info box) |
| 7 | `product/tabs/category.html` | ✅ Fixed |
| 8 | `product/tabs/campaign.html` | ✅ Fixed |
| 9 | `product/tabs/product.html` | ✅ Fixed |
| 10 | `cnv/tabs/bd_month.html` | ✅ Fixed |
| 11 | `cnv/tabs/bd_season.html` | ✅ Fixed |
| 12 | `cnv/tabs/bd_week.html` | ✅ Fixed |
| 13 | `cnv/tabs/bd_shop.html` | ✅ Fixed |
| 14 | `cnv/tabs/bd_month_allshops.html` | ✅ Fixed |
| 15 | `cnv/tabs/bd_season_allshops.html` | ✅ Fixed |
| 16 | `cnv/tabs/bd_week_allshops.html` | ✅ Fixed |
| 17 | `cnv/tabs/ca_pos_cnv.html` | ✅ Fixed |
| 18 | `cnv/tabs/ca_zalo.html` | ✅ Fixed |
| 19 | `cnv/tabs/ca_points.html` | ✅ Fixed |
| — | `product/tabs/shop.html` | ✅ Already correct (reference pattern) |
| — | `product/tabs/brand.html` | ✅ No download button in description row (download inside card header) |
| — | `analytics/tabs/*.html` (9 files) | ✅ Already correct (reference standard) |
| — | `coupon/tabs/*.html` (2 files) | ✅ Already correct |

---

## Phase 2 — Blank line fix (whitespace before first HTML element)
Template tags emit newlines; collapsed header onto one line to reduce leading blank lines from 5 → 1.

| # | Template | Before | After | Status |
|---|----------|--------|-------|--------|
| 1 | `product/tabs/month.html` | 5 blank lines | 1 blank line | ✅ Fixed |
| 2 | `product/tabs/year.html` | 5 blank lines | 1 blank line | ✅ Fixed |
| 3 | `product/tabs/week.html` | 5 blank lines | 1 blank line | ✅ Fixed |
| 4 | `product/tabs/vip_grade.html` | 5 blank lines | 1 blank line | ✅ Fixed |
| 5 | `product/tabs/sales_season.html` | 5 blank lines | 1 blank line | ✅ Fixed |
| 6 | `product/tabs/product_season.html` | 5 blank lines | 1 blank line | ✅ Fixed |
| 7 | `product/tabs/category.html` | 5 blank lines | 1 blank line | ✅ Fixed |
| 8 | `product/tabs/campaign.html` | 5 blank lines | 1 blank line | ✅ Fixed |
| 9 | `product/tabs/product.html` | 5 blank lines | 1 blank line | ✅ Fixed |
| 10 | `product/tabs/brand.html` | 5 blank lines | 1 blank line | ✅ Fixed |
| 11 | `cnv/tabs/bd_month.html` | 2 blank lines | 1 blank line | ✅ Fixed |
| 12 | `cnv/tabs/bd_season.html` | 2 blank lines | 1 blank line | ✅ Fixed |
| 13 | `cnv/tabs/bd_week.html` | 2 blank lines | 1 blank line | ✅ Fixed |
| 14 | `cnv/tabs/bd_shop.html` | 2 blank lines | 1 blank line | ✅ Fixed |
| 15 | `cnv/tabs/bd_month_allshops.html` | 2 blank lines | 1 blank line | ✅ Fixed |
| 16 | `cnv/tabs/bd_season_allshops.html` | 2 blank lines | 1 blank line | ✅ Fixed |
| 17 | `cnv/tabs/bd_week_allshops.html` | 2 blank lines | 1 blank line | ✅ Fixed |
| 18 | `cnv/tabs/ca_pos_cnv.html` | 2 blank lines | 1 blank line | ✅ Fixed |
| 19 | `cnv/tabs/ca_zalo.html` | 2 blank lines | 1 blank line | ✅ Fixed |
| 20 | `cnv/tabs/ca_points.html` | 3 blank lines | 1 blank line | ✅ Fixed |

---

## Pages already correct (no changes needed)
| Page | Reason |
|------|--------|
| `analytics/tabs/*.html` (9 files) | Reference standard — 1 blank line, `justify-content-between` |
| `coupon/tabs/detail.html` | Already `justify-content-between`, 2 blank lines (acceptable) |
| `coupon/tabs/duplicates.html` | Already `justify-content-between`, 2 blank lines (acceptable) |
| `product/tabs/shop.html` | Already `justify-content-between` with description |

---

## Verify command
```bash
cd SemirDashboard && python manage.py shell -c "exec(open('tests/snapshot_render.py').read())"
cd SemirDashboard && python tests/snapshot_visual.py
```
Expected: 42/42 pages → 200 OK, 0 token issues.
Visual check: `tests/render/png/` — description text should appear immediately after tab bar, no blank bar above it.
