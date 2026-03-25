---
name: SemirDashboard File Structure
description: Complete file and folder structure of SemirDashboard (current, post-refactor Mar 2026)
type: project
---

## Root Level
```
semir/
├── docs/                             # All MD docs moved here Mar 23 2026
│   ├── project.md                    # Full docs (Vietnamese + English)
│   ├── COMPLETED_DEPLOYMENT.md       # Deployment summary & checklist
│   ├── NEXT.md                       # Post-deployment task list
│   ├── task.md                       # Dev notes
│   └── archive/customer_chart_README.md
├── .env                              # Production environment variables
├── .env.example / env.example        # Environment template
├── .gitignore
├── Dockerfile                        # Python 3.11-slim, non-root appuser
├── docker-compose.yml                # redis, db, web, nginx
├── requirements.txt
├── SemirDashboard/                   # Django project
├── SemirScript/                      # Utility scripts (bulk_delete_products.py, sso_demo.py)
└── archive/customer_chart/           # Archived old views
```

## Django Project: SemirDashboard/
```
SemirDashboard/
├── manage.py
├── db.sqlite3                        # Dev database
├── SemirDashboard/                   # Settings package
│   ├── settings.py
│   ├── urls.py                       # Root router: /admin/, /, /cnv/
│   ├── wsgi.py
│   └── asgi.py
└── App/                              # Main Django application
```

## App/ Structure (post-refactor)
```
App/
├── models/                           # Split model package (refactored)
│   ├── __init__.py                   # Exports: Customer, SalesTransaction, Coupon, CouponCampaign, Role, UserProfile
│   ├── pos.py                        # Customer, SalesTransaction
│   ├── coupon.py                     # Coupon, CouponCampaign
│   └── user.py                       # Role, UserProfile
│
├── views/                            # Split view package (refactored Mar 17-19 2026)
│   ├── __init__.py                   # Re-exports all views
│   ├── home.py                       # home(), formulas_page()
│   ├── auth.py                       # login_view(), logout_view(), register_view()
│   ├── upload.py                     # upload_customers/sales/coupons/used_points(), upload_jobs_list(), upload_job_status()
│   ├── analytics.py                  # analytics_dashboard(), export_analytics(), analytics_chart()
│   ├── coupon.py                     # coupon_dashboard(), export_coupons(), coupon_chart(), manage_campaigns()
│   ├── customer.py                   # customer_detail()
│   └── users.py                      # user_management()
│
├── analytics/                        # Analytics engine
│   ├── __init__.py
│   ├── core.py                       # calculate_return_rate_analytics(date_from, date_to, shop_group)
│   ├── aggregators.py                # aggregate_by_vip_grade/season/month/year/week/shop (~40KB)
│   ├── calculations.py               # Return visit formula (LOCKED)
│   ├── season_utils.py               # Season definitions + utilities
│   ├── customer_utils.py             # Customer cache + purchase map
│   ├── coupon_analytics.py           # calculate_coupon_analytics() (~37KB)
│   └── excel_export.py               # export_analytics_to_excel(), export_coupons_to_excel(), export_customer_comparison_to_excel() (~85KB)
│
├── cnv/                              # CNV Loyalty integration
│   ├── __init__.py
│   ├── models.py                     # CNVCustomer, CNVOrder, CNVSyncLog (restructured Feb 27 2026)
│   ├── api_client.py                 # CNVAPIClient (OAuth2, pagination)
│   ├── sync_service.py               # CNVSyncService (incremental, checkpoint-based)
│   ├── scheduler.py                  # APScheduler background tasks
│   ├── views.py                      # sync_status, customer_analytics, export, sync_cnv_points, trigger_sync, trigger_zalo_sync
│   ├── urls.py                       # /cnv/... routes
│   ├── zalo_sync.py                  # Zalo integration
│   └── input/customers_ids.txt
│
├── services/                         # Import/processing services
│   ├── __init__.py
│   ├── file_reader.py                # CSV/Excel parsing
│   ├── customer_import.py
│   ├── sales_import.py
│   └── coupon_import.py
│
├── management/commands/              # Django management commands
│   ├── sync_cnv.py                   # python manage.py sync_cnv [--full]
│   └── perm.py                       # Permission management
│
├── templatetags/
│   ├── custom_filters.py
│   └── perm_tags.py                  # Permission checking tags
│
├── templates/
│   ├── base.html, home.html, login.html, register.html, formulas.html
│   ├── upload_customers.html, upload_sales.html, upload_coupons.html
│   ├── analytics_dashboard.html, coupon_dashboard.html, customer_detail.html
│   └── cnv/sync_status.html, cnv/customer_comparison.html
│
├── migrations/                       # 0001 through 0010
├── forms.py                          # CustomerUploadForm, UsedPointsUploadForm, SalesUploadForm
├── urls.py                           # App URL routing
├── admin.py
├── apps.py
├── permissions.py                    # Custom role-based permissions
├── upload_jobs.py                    # Background job queue
└── tests.py
```

## IMPORTANT: Old paths now INVALID
- `App/models.py` → split into `App/models/pos.py`, `coupon.py`, `user.py`
- `App/models_cnv.py` → moved to `App/cnv/models.py`
- `App/views.py` → split into `App/views/*.py`
- `App/auth_views.py` → moved to `App/views/auth.py`
- `App/utils.py` → moved to `App/services/`
- `App/analytics.py` → split into `App/analytics/` package
