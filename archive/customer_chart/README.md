# Customer Analytics Charts — Archived

Archived on: 2026-03-17
Reason: Feature hidden/removed from production. Code preserved here for future reference.

## Files
- `customer_chart.html` — Django template (Chart.js 4, jsPDF, 4 sections)
- `views_customer_chart.py` — View + helper functions extracted from `App/cnv/views.py`

## What was removed from codebase
1. **`App/cnv/views.py`**: Lines 652–857 (`_CUST_CHART_VER_KEY`, `_CUST_CHART_TTL`, `_cust_chart_cache_key`, `_compute_customer_chart_data`, `customer_chart` view)
2. **`App/cnv/urls.py`**: `path('customer-chart/', views.customer_chart, name='customer_chart')`
3. **`App/permissions.py`**: `("page_customer_chart", ...)`, `("download_customer_chart_pdf", ...)`
4. **`App/templates/home.html`**: Customer Analytics Charts card + `check_perm 'page_customer_chart'`
5. **`SemirDashboard/settings.py`**: `SHOW_CUSTOMER_CHART = os.getenv(...)`
6. **`App/context_processors.py`**: `feature_flags` function returning `SHOW_CUSTOMER_CHART`
7. **`SemirDashboard/settings.py` TEMPLATES**: `App.context_processors.feature_flags`

## Page Description
- URL: `/cnv/customer-chart/`
- Permissions: `page_customer_chart`, `download_customer_chart_pdf`
- 4 sections:
  1. **Overview** — 4 donut charts (Active Zalo/CNV, Follow OA/CNV, CNV Only, POS Only)
  2. **Trend Lines** — Multi-line chart (4 metrics × week/month/season/year)
  3. **Bar Chart** — Single metric selector (week/month/season/year)
  4. **YOY Comparison** — Year-over-year grouped bar (all-time data)
- Metrics: `new_pos_users`, `new_cnv_users`, `active_zalo`, `follow_oa`
- Cache: 5 min versioned (`cust_chart_ver`)
- PDF download: 4-page jsPDF export
