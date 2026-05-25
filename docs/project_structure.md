---
name: SemirDashboard File Structure
description: Complete file and folder structure of SemirDashboard (accurate as of Apr 2026)
type: project
---

## Root Level
```
semir/
├── docs/                             # All MD docs
├── .env                              # Production environment variables
├── Dockerfile                        # Python 3.11-slim, non-root appuser
├── docker-compose.yml                # redis, db, web, nginx, monitoring stack
├── requirements.txt
├── SemirDashboard/                   # Django project root
└── monitoring/                       # Grafana/Loki/Prometheus configs
```

## Django Project: SemirDashboard/
```
SemirDashboard/
├── manage.py
├── db.sqlite3                        # Dev database
├── logs/                             # app.log, cnv_sync.log, errors.log (JSON format)
├── SemirDashboard/                   # Settings package
│   ├── settings.py
│   ├── urls.py                       # Root router: /admin/, /cnv/, /
│   ├── wsgi.py
│   └── asgi.py
├── tests/                            # Test suite
│   ├── base.py                       # SnapshotTestCase, Timer, INPUT_DIR
│   ├── test_pages.py                 # PageRenderTest (all GET routes smoke), ExportSmokeTest (Excel exports)
│   ├── test_shop_detail.py           # ShopDetailTest (setUpTestData + snapshots)
│   ├── test_sales.py                 # Sales analytics unit tests
│   ├── test_coupon.py                # Coupon analytics unit tests
│   ├── test_customer.py              # Customer analytics unit tests
│   ├── test_customer_chart.py        # CNV customer chart tests
│   ├── test_consistency.py           # Cross-tab consistency assertions
│   ├── test_inventory.py             # InventoryImportTest (import + analytics + AJAX partial)
│   ├── test_sale_detail.py           # SaleDetailImportTest (import + product analytics + tabs, field-level assertions)
│   ├── render_pages.py               # Standalone shell script: renders all GET pages, reports timing
│   └── snapshots/                    # shop_detail_sales.json, shop_detail_customer.json, ...
└── App/                              # Main Django application
```

## App/ Structure
```
App/
├── models/
│   ├── __init__.py                   # Re-exports: Customer, SalesTransaction, SaleDetail, Coupon, CouponCampaign, Role, UserProfile, InventorySnapshot
│   ├── pos.py                        # Customer, SalesTransaction, SaleDetail
│   ├── inventory.py                  # InventorySnapshot
│   ├── coupon.py                     # Coupon, CouponCampaign
│   └── user.py                       # Role, UserProfile
│
├── cnv/                              # CNV Loyalty integration
│   ├── models.py                     # CNVCustomer, CNVOrder, CNVSyncLog
│   ├── urls.py                       # /cnv/* routes
│   ├── views.py                      # sync_status, customer_analytics, customer_tab, customer_chart, trigger_sync, trigger_zalo_sync
│   ├── service.py                    # compute_cnv_breakdown, parse_cnv_period_filter, _fetch_bd_raw, get_cnv_phone_sets
│   ├── sync_service.py               # CNVSyncService (OAuth2 + checkpoint-based batch sync)
│   ├── api_client.py                 # CNVAPIClient (OAuth2, pagination, token cache 30d)
│   ├── scheduler.py                  # APScheduler: customers :05, orders :10, cleanup 2AM
│   ├── zalo_sync.py                  # run_zalo_sync (ThreadPoolExecutor 10 workers)
│   └── apps.py
│
├── analytics/                        # Analytics engine
│   ├── calculations.py               # calculate_return_visits — LOCKED return formula
│   ├── season_utils.py               # get_season_label, get_week_info, GRADE_ORDER
│   ├── aggregators.py                # aggregate_by_grade, aggregate_by_season, aggregate_by_month
│   ├── core.py                       # Main analytics pipeline (fetch + aggregate)
│   ├── customer_utils.py             # Customer cache + purchase map builder
│   ├── coupon_analytics.py           # calc_coupon_amount, calculate_coupon_analytics, calculate_coupon_trend_data, export_*
│   ├── tab_functions.py              # KEY: get_sales_tab, get_customer_tab, get_coupon_tab, get_shop_detail_*, _load_sales
│   ├── inventory_functions.py        # get_inventory_overview(shop_group, year, season) — inventory KPIs, dead stock top 50, per-shop breakdown
│   ├── product_analytics.py          # get_product_tab(tab, date_from, date_to, shop_group) — season/month/week/brand/category
│   └── __init__.py
│
├── services/
│   ├── customer_import.py            # process_customer_file, process_used_points_file
│   ├── sales_import.py               # process_sales_file
│   ├── coupon_import.py              # process_coupon_file
│   ├── inventory_import.py           # process_inventory_file — upserts InventorySnapshot (77k rows, 21 shops)
│   ├── sale_detail_import.py         # process_sale_detail_file — upserts SaleDetail with soft FK to SalesTransaction
│   └── file_reader.py                # read_file, parse_date, safe_decimal, safe_int, safe_str
│
├── views/
│   ├── analytics.py                  # analytics_dashboard, analytics_tab, analytics_chart, export_analytics
│   ├── coupon.py                     # coupon_dashboard, coupon_tab, coupon_chart, export_coupons
│   ├── upload.py                     # upload_customers/sales/coupons/used_points/inventory/sale_detail, upload_job_status, upload_jobs_list
│   ├── product.py                    # product_dashboard, product_tab, export_product_analytics (SaleDetail-based, 5 tabs)
│   ├── inventory.py                  # inventory_dashboard, export_inventory_dead_stock (InventorySnapshot-based)
│   ├── shop_detail.py                # shop_detail, export_shop_detail_excel, shop_detail_*_partial (4 AJAX partials)
│   ├── customer.py                   # customer_detail
│   ├── admin_logs.py                 # admin_logs (superuser only, reads JSON log files)
│   └── view_utils.py                 # parse_date, filter_params_str
│
├── templates/
│   ├── base.html
│   ├── home.html
│   ├── login.html
│   ├── register.html
│   ├── shop_detail.html              # Shop-level analytics page (AJAX 3 sections)
│   ├── user_management.html
│   ├── formulas.html
│   ├── admin/
│   │   └── log_viewer.html           # Superuser log viewer
│   ├── analytics/
│   │   ├── dashboard.html
│   │   ├── chart.html
│   │   └── tabs/                     # grade, grade_allshops, season, season_allshops,
│   │                                 # month, month_allshops, week, week_allshops, _empty
│   ├── cnv/
│   │   ├── sync_status.html
│   │   ├── customer_analytics.html
│   │   ├── customer_chart.html
│   │   └── tabs/                     # bd_season, bd_month, bd_week, bd_shop,
│   │                                 # bd_season_allshops, bd_month_allshops, bd_week_allshops,
│   │                                 # ca_points, ca_pos_cnv, ca_zalo
│   ├── coupon/
│   │   ├── dashboard.html
│   │   ├── chart.html
│   │   └── tabs/                     # detail, duplicates
│   ├── customer/
│   │   └── detail.html
│   ├── product/
│   │   ├── dashboard.html            # Product analytics page (filter bar + 5 tabs)
│   │   └── tabs/                     # season, month, week, brand, category
│   ├── inventory/
│   │   └── dashboard.html            # Inventory dashboard (filter bar, KPI cards, dead stock top 50, per-shop)
│   ├── shop_detail/
│   │   ├── _sales_partial.html       # AJAX partial for sales section
│   │   ├── _customer_partial.html    # AJAX partial for customer section
│   │   ├── _coupon_partial.html      # AJAX partial for coupon section
│   │   └── _inventory_partial.html   # AJAX partial for inventory section (Section 4)
│   ├── upload/
│   │   ├── customers.html
│   │   ├── sales.html                # Now includes Sale Detail upload card (Card 2)
│   │   ├── coupons.html
│   │   ├── inventory.html            # Upload InventorySnapshot xlsx
│   │   └── _upload_status.html
│   └── components/
│       ├── lazy_tabs_js.html         # Lazy tab loading JS component
│       └── lazy_tab_session.html
│
├── urls.py                           # App-level URL patterns (see project_urls.md)
├── permissions.py                    # PERMISSION_DEFS (24 permissions), Role helpers, @requires_perm
├── forms.py                          # CustomerUploadForm, UsedPointsUploadForm, SalesUploadForm
├── upload_jobs.py                    # Job store backed by Django cache (create_job, update_job, get_job)
├── logging_utils.py                  # RequestIDFilter, JsonFormatter, thread-local request_id helpers
├── middleware.py                     # RequestIDMiddleware (UUID4 per request, X-Request-ID header)
├── templatetags/
│   ├── custom_filters.py
│   └── perm_tags.py                  # Permission checking template tags
├── management/commands/
│   ├── perm.py                       # perm sync: renames old codenames, upserts admin/viewer roles
│   ├── sync_cnv_customers.py
│   └── sync_cnv_orders.py
├── migrations/
└── apps.py
```

## Key File → Task Mapping

| Task | File |
|------|------|
| Return visit formula | `analytics/calculations.py` |
| Season labels / grade order | `analytics/season_utils.py` |
| Shop detail data (sales/customer/coupon) | `analytics/tab_functions.py` → `get_shop_detail_*` |
| Inventory dashboard data (KPIs, dead stock, per-shop) | `analytics/inventory_functions.py` → `get_inventory_overview` |
| Lazy tab data for analytics/coupon/cnv pages | `analytics/tab_functions.py` → `get_sales_tab`, `get_customer_tab`, `get_coupon_tab` |
| Product analytics (season/month/week/brand/category) | `analytics/product_analytics.py` → `get_product_tab` |
| Aggregation (grade/season/month) | `analytics/aggregators.py` |
| Coupon analytics + Excel export | `analytics/coupon_analytics.py` |
| CNV comparison breakdown | `cnv/service.py` → `compute_cnv_breakdown` |
| CNV API HTTP calls | `cnv/api_client.py` |
| CNV hourly background jobs | `cnv/scheduler.py` |
| Zalo sync (threaded) | `cnv/zalo_sync.py` |
| All 24 permissions | `permissions.py` |
| Data import (bulk CSV/Excel) | `services/customer_import.py`, `sales_import.py`, `coupon_import.py`, `inventory_import.py`, `sale_detail_import.py` |
| Upload job tracking (cache-backed) | `upload_jobs.py` |
| Admin log viewer | `views/admin_logs.py` |
| Request ID correlation | `logging_utils.py` + `middleware.py` |
