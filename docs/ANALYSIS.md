# SemirDashboard — Full Project Analysis

**Analyzed:** 2026-03-23
**Last Updated:** 2026-03-25 (logging overhaul + Grafana monitoring stack)
**Analyzer:** Claude Sonnet 4.6
**Status:** Current & accurate

---

## 1. Project Identity

| Property | Value |
|----------|-------|
| Name | SemirDashboard |
| Framework | Django 6.0.2 / Python 3.11 |
| Purpose | Retail analytics + CNV Loyalty integration (SEMIR Vietnam) |
| DB (dev) | SQLite3 |
| DB (prod) | PostgreSQL 16 |
| Production | https://analytics-customer-dashboard.com |
| VPS | Vietnix SSD 3 — 14.225.254.192 (Ubuntu 22.04 LTS) |
| Stack | Docker Compose → Nginx → Gunicorn → Django |

---

## 2. Directory Structure (Current — Post-Refactor)

```
semir/
├── docs/                          ← All MD docs (moved here 2026-03-23)
│   ├── ANALYSIS.md                ← This file
│   ├── project.md                 ← Full docs (updated 2026-03-23)
│   ├── COMPLETED_DEPLOYMENT.md
│   ├── NEXT.md
│   ├── task.md
│   └── archive/customer_chart_README.md
├── .env / .env.example
├── Dockerfile
├── monitoring/                    ← Grafana stack configs (added Mar 2026)
│   ├── prometheus.yml
│   ├── loki-config.yml
│   ├── promtail-config.yml
│   └── grafana/provisioning/datasources/datasources.yml
├── docker-compose.yml             ← 9 services: redis, db, web, nginx + loki, promtail, prometheus, cadvisor, grafana
├── requirements.txt
├── SemirDashboard/
│   ├── manage.py
│   ├── db.sqlite3
│   ├── SemirDashboard/
│   │   ├── settings.py
│   │   ├── urls.py                ← /admin/, /, /cnv/
│   │   ├── wsgi.py / asgi.py
│   └── App/
│       ├── models/                ← Split package (NOT models.py)
│       │   ├── __init__.py        ← exports all models
│       │   ├── pos.py             ← Customer, SalesTransaction
│       │   ├── coupon.py          ← Coupon, CouponCampaign
│       │   └── user.py            ← Role, UserProfile
│       ├── views/                 ← Split package (NOT views.py)
│       │   ├── __init__.py
│       │   ├── home.py            ← home(), formulas_page()
│       │   ├── auth.py            ← login/logout/register
│       │   ├── upload.py          ← upload_*, upload_jobs_list/status
│       │   ├── analytics.py       ← analytics_dashboard/chart/export
│       │   ├── coupon.py          ← coupon_dashboard/chart/export, manage_campaigns
│       │   ├── customer.py        ← customer_detail()
│       │   └── users.py           ← user_management()
│       ├── analytics/             ← Analytics engine
│       │   ├── core.py
│       │   ├── aggregators.py     ← ~40KB
│       │   ├── calculations.py    ← return visit formula (LOCKED)
│       │   ├── season_utils.py
│       │   ├── customer_utils.py
│       │   ├── coupon_analytics.py ← ~37KB
│       │   └── excel_export.py    ← ~85KB
│       ├── cnv/                   ← CNV Loyalty integration
│       │   ├── models.py          ← CNVCustomer, CNVOrder, CNVSyncLog
│       │   ├── api_client.py      ← CNVAPIClient
│       │   ├── sync_service.py    ← CNVSyncService
│       │   ├── scheduler.py
│       │   ├── views.py
│       │   ├── urls.py
│       │   └── zalo_sync.py
│       ├── services/              ← Import services
│       │   ├── file_reader.py
│       │   ├── customer_import.py
│       │   ├── sales_import.py
│       │   └── coupon_import.py
│       ├── management/commands/
│       │   ├── sync_cnv.py        ← python manage.py sync_cnv [--full]
│       │   └── perm.py
│       ├── templatetags/
│       │   ├── custom_filters.py
│       │   └── perm_tags.py
│       ├── templates/
│       │   ├── base.html, home.html, login.html, register.html, formulas.html
│       │   ├── upload_customers/sales/coupons.html
│       │   ├── analytics_dashboard.html
│       │   ├── coupon_dashboard.html
│       │   ├── customer_detail.html
│       │   └── cnv/sync_status.html, cnv/customer_comparison.html
│       ├── migrations/            ← 0001–0010
│       ├── forms.py
│       ├── urls.py
│       ├── admin.py
│       ├── apps.py
│       ├── permissions.py
│       ├── upload_jobs.py
│       ├── logging_utils.py       ← RequestIDFilter, JsonFormatter, thread-local helpers (added Mar 2026)
│       └── middleware.py          ← RequestIDMiddleware — 12-char UUID per request (added Mar 2026)
├── SemirScript/
│   ├── bulk_delete_products.py
│   └── sso_demo.py
└── archive/customer_chart/
```

### OBSOLETE PATHS (do not use)
| Old | New |
|-----|-----|
| `App/models.py` | `App/models/pos.py` + `coupon.py` + `user.py` |
| `App/models_cnv.py` | `App/cnv/models.py` |
| `App/views.py` | `App/views/*.py` |
| `App/auth_views.py` | `App/views/auth.py` |
| `App/utils.py` | `App/services/` |
| `App/analytics.py` | `App/analytics/` package |

---

## 3. Database Models

### POS — `App/models/pos.py`

**Customer**
- `vip_id` + `phone` (unique_together)
- `name`, `vip_grade` (VIP0/VIP1/VIP2/VIP3/DIAMOND)
- `id_number`, `birthday`, `birthday_month`, `gender`, `race`
- `registration_date` (indexed), `registration_store`
- `city_state`, `postal_code`, `country`, `email`, `contact_address`
- `points`, `created_at`, `updated_at`
- **Rule:** vip_id = "0" → non-VIP, excluded from grade analytics

**SalesTransaction**
- `invoice_number` (unique)
- `shop_id`, `shop_name`, `country`, `bu`
- `sales_date` (indexed), `vip_id` (indexed)
- `vip_name`, `quantity`, `settlement_amount`, `sales_amount`
- `tag_amount`, `per_customer_transaction`, `discount`, `rounding`
- `customer` (FK → Customer, nullable)

### Coupon — `App/models/coupon.py`

**Coupon**
- `coupon_id` (indexed), `used` (0=unused/1=used)
- `face_value`, `begin_date`, `end_date`
- `using_shop`, `using_date` (indexed), `docket_number` (indexed)
- `department`, `creator`, `document_number`, `push`
- `member_id`, `member_name`, `member_phone`

**CouponCampaign**
- `name` (unique), `prefix` (comma-separated), `detail`

### User — `App/models/user.py`

**Role**: `name` (unique), `permissions` (JSONField), `is_system` (bool)
**UserProfile**: OneToOne → User, FK → Role

Permission strings: `page_analytics`, `page_coupons`, `page_cnv_sync`, `manage_users`

### CNV — `App/cnv/models.py` (restructured Feb 27, 2026)

**CNVCustomer**
- `id` (AutoField PK), `cnv_id` (BigIntegerField, unique)
- `last_name`, `first_name` → property `full_name`
- `phone` (indexed), `email`, `gender`
- `birthday_day`, `birthday_month`, `birthday_year`
- `tags`, `physical_card_code`
- `points`, `exp_points`, `total_spending`, `total_points`
- `level_name` (indexed), `used_points`
- `cnv_created_at`, `cnv_updated_at` (both indexed)
- `created_at`, `updated_at`, `last_synced_at` (indexed)
- `zalo_app_id`, `zalo_oa_id`, `zalo_app_created_at`

**CNVOrder** (PK: `order_code`)
- `order_id`, `customer_code/name/phone`, `order_date`
- `order_status`, `payment_status/method`
- `store_code/name`
- `subtotal`, `discount_amount`, `tax_amount`, `shipping_fee`, `total_amount`
- `points_earned`, `points_used`
- `items` (JSON), `notes`, `raw_data` (JSON)

**CNVSyncLog**
- `sync_type` (customers/orders/full/zalo_sync)
- `status` (running/completed/failed)
- `checkpoint_updated_at` (for incremental sync)
- `total_records`, `created_count`, `updated_count`, `failed_count`
- `error_message`, `error_details` (JSON)

### Migrations History
`0001` Customer+SalesTransaction → `0002` Coupon → `0003` CNV models →
`0004` checkpoint_updated_at → `0005-0006` index renames →
`0007` Zalo fields → `0008` Role+UserProfile → `0009` CouponCampaign → `0010` prefix alter

---

## 4. URL Routing

### App URLs (`/`)
```
/                           home
/formulas/                  formulas_page
/login/ /logout/ /register/ auth views
/upload/customers/          upload_customers
/upload/sales/              upload_sales
/upload/coupons/            upload_coupons
/upload/used-points/        upload_used_points
/upload/jobs/               upload_jobs_list
/upload/jobs/<job_id>/      upload_job_status (AJAX)
/analytics/                 analytics_dashboard
/analytics/export/          export_analytics
/analytics/chart/           analytics_chart (AJAX)
/coupons/                   coupon_dashboard
/coupons/export/            export_coupons
/coupons/chart/             coupon_chart (AJAX)
/coupons/campaigns/         manage_campaigns
/customer-detail/           customer_detail
/users/                     user_management
```

### CNV URLs (`/cnv/`)
```
/cnv/sync-status/                   sync_status
/cnv/customer-analytics/            customer_analytics
/cnv/export-customer-analytics/     export_customer_analytics
/cnv/sync-cnv-points/               sync_cnv_points (AJAX POST)
/cnv/trigger-sync/                  trigger_sync (AJAX POST)
/cnv/trigger-zalo-sync/             trigger_zalo_sync (AJAX POST)
```

---

## 5. Analytics Engine

### Architecture
```
App/analytics/
├── core.py           → calculate_return_rate_analytics(date_from, date_to, shop_group)
├── aggregators.py    → by_grade, by_season, by_month, by_year, by_week, by_shop
├── calculations.py   → return visit formula (LOCKED)
├── season_utils.py   → season labels, sort keys
├── customer_utils.py → customer cache, purchase map
├── coupon_analytics.py → calculate_coupon_analytics()
└── excel_export.py   → export_analytics/coupons/customer_comparison_to_excel()
```

### Return Visit Formula (LOCKED — do not change)
```python
# App/analytics/calculations.py
if registration_date == first_purchase_date:
    return_visits = total_invoices - 1
else:
    return_visits = total_invoices

is_returning = (return_visits > 0)
return_rate = returning_count / total_count * 100
```
Counts INVOICES, not unique days. Confirmed by user.

### Season Definitions (updated Mar 2026)
| Season | Months | Cross-year |
|--------|--------|-----------|
| M2-4 | Feb, Mar, Apr | No |
| M5-7 | May, Jun, Jul | No |
| M8-10 | Aug, Sep, Oct | No |
| M11-1 | Nov, Dec, Jan | Yes |

**OLD (obsolete):** SS = Jan-Jun, AW = Jul-Dec

### Excel Export Sheets (analytics)
Overview, By VIP Grade, By Season, By Month, By Week, By Shop, By Shop Detail,
Grade Comparison, Season Comparison, Month Comparison, Week Comparison,
Customer Details, Buyer Without Info, Reconciliation

### Excel Export Sheets (customer comparison)
POS columns (7): VIP ID, Phone, Name, Grade, Email, Reg Date, Points
CNV columns (8): Customer ID, Phone, Name, **Level**, Email, Reg Date, Points, Used Points

---

## 6. CNV Integration

### API
- Base: `https://apis.cnvloyalty.com`
- Auth: OAuth2 (username/password → access token, cached 30 days)
- Endpoints used:
  - `GET /loyalty/customers.json` (paginated)
  - `GET /loyalty/customers/{id}/membership.json`
  - `GET /loyalty/orders.json` (paginated)

### CNV API Response — Customer
```json
{
  "customer": {
    "id": 35577245,
    "last_name": "Nguyễn Thị Thuỳ Linh",
    "first_name": ".",
    "phone": "0338336011",
    "email": "",
    "gender": "female",
    "birthday_day": 21, "birthday_month": 12, "birthday_year": 2020,
    "points": 29649.0, "exp_points": 25849.0,
    "total_spending": 0.0, "total_points": 0.0,
    "created_at": "2025-06-23T08:51:26.859Z",
    "updated_at": "2026-02-05T17:34:44.533Z"
  }
}
```

### CNV API Response — Membership
```json
{
  "membership": {
    "level_name": "Diamond",
    "total_points": 29649.0,
    "points": 29649.0,
    "used_points": 0.0
  }
}
```

### Sync Strategy
- **Incremental:** uses `checkpoint_updated_at` to fetch only changed records
- **Full:** `python manage.py sync_cnv --full`
- Batch size: 500, membership fetched in parallel per batch
- Zalo sync: separate `zalo_sync.py`, sync_type = "zalo_sync"

### POS ↔ CNV Matching
- Match key: **phone number**
- `Customer.phone` ↔ `CNVCustomer.phone`

---

## 7. Logging & Monitoring (added Mar 2026)

### Structured JSON Logging Pipeline
```
Django app → JSON log lines → Docker stdout → Promtail → Loki → Grafana
```

### Key Files
| File | Role |
|------|------|
| `App/logging_utils.py` | `RequestIDFilter`, `JsonFormatter`, thread-local `get/set/clear_request_id()` |
| `App/middleware.py` | `RequestIDMiddleware` — generates 12-char hex UUID per request, adds `X-Request-ID` header |
| `SemirDashboard/settings.py` LOGGING | 3 file handlers + 2 named loggers |

### Log Format (one JSON object per line)
```json
{"time": "...", "level": "INFO", "logger": "App.views.upload", "module": "upload",
 "request_id": "a1b2c3d4e5f6", "step": "upload_customers", "message": "upload_customers queued job=... file=... user=..."}
```

### Logger Hierarchy
| Logger | Handler | File |
|--------|---------|------|
| `App.cnv.*` | `cnv_file` + `error_file` | `cnv_sync.log` + `errors.log` |
| `App.*` | `app_file` + `error_file` | `app.log` + `errors.log` |
| `django.request` | `error_file` | `errors.log` (WARNING+) |
| root | console | stderr (WARNING+) |

### Step Values (for Grafana filtering with `| json | step="..."`)
| Step | Where |
|------|-------|
| `auth` | login, logout, register |
| `upload_customers` / `upload_sales` / `upload_coupons` / `upload_used_points` | upload views (queued) |
| `upload_job` | background thread done/error + auto-fail |
| `analytics_chart` / `export_analytics` | analytics views |
| `export_coupons` / `manage_campaigns` | coupon views |
| `cnv_comparison` / `export_customer_analytics` | CNV comparison views |
| `cnv_points_sync` | sync_cnv_points AJAX |
| `cnv_sync` | trigger_sync AJAX |
| `zalo_sync` | trigger_zalo_sync AJAX |
| `user_management` | users.py (role/perm mutations) |

### Useful Grafana/Loki Queries
```logql
# All errors
{container_name="semirdashboard-web-1"} | json | level="ERROR"

# Track one request end-to-end
{container_name="semirdashboard-web-1"} | json | request_id="<id>"

# All upload activity
{container_name="semirdashboard-web-1"} | json | step=~"upload_.*"

# CNV sync progress
{container_name="semirdashboard-web-1"} | json | step="cnv_sync"

# Failed logins
{container_name="semirdashboard-web-1"} | json | step="auth" | message=~"login_failed.*"
```

### Monitoring Stack (port 3000)
| Service | Role |
|---------|------|
| Grafana `:3000` | Dashboards — restricted by ufw (not public) |
| Loki `:3100` | Log aggregation (7-day retention, tsdb v13) |
| Promtail | Reads Docker container logs via `/var/run/docker.sock` |
| Prometheus `:9090` | Scrapes cAdvisor container metrics |
| cAdvisor `:8080` | Exposes CPU/memory/network per container |

**UFW rule for Grafana:**
```bash
ufw allow from <office-ip> to any port 3000
```

---

## 8. Business Rules

| Rule | Detail |
|------|--------|
| VIP ID = "0" | Non-VIP, excluded from grade analytics, tracked as "buyer without info" |
| VIP Grades | VIP0 < VIP1 < VIP2 < VIP3 < DIAMOND |
| Shop Group | First 2 chars of shop_id ("HN01" → "HN") |
| Season (new) | M2-4, M5-7, M8-10, M11-1 |
| Return visits | Count invoices, not unique days |
| Coupon campaign | Coupon belongs to campaign if ID starts with any prefix in comma-separated list |
| Upload flow | File → file_reader → *_import service → upload_jobs (background) |
| Permissions | Role-based, stored in Role.permissions JSONField |

---

## 8. Development Rules (task.md)

When adding a new page:
- Apply cache if possible
- Apply permission check
- Follow overall dashboard style
- Add back-to-home button in base

---

## 9. Deployment

| Item | Value |
|------|-------|
| Domain | analytics-customer-dashboard.com |
| Server | 14.225.254.192 (Vietnix SSD 3, Ubuntu 22.04 LTS) |
| SSL | Let's Encrypt, auto-renewal Sundays 3 AM |
| Docker services | redis, db (postgres:16), web (gunicorn), nginx, loki, promtail, prometheus, cadvisor, grafana |
| Grafana | http://14.225.254.192:3000 (superuser only, restricted by ufw) |
| Deploy | `cd ~/semir && ./scripts/deploy.sh` |
| Backup | Daily 2 AM, 7-day retention (`scripts/backup.sh`) |
| Monthly cost | ~350,000 VND/month |

### Key Commands
```bash
# Deploy
./scripts/deploy.sh

# Logs
docker compose logs -f web

# Django shell
docker compose exec web python manage.py shell

# DB access
docker compose exec db psql -U semir_user -d semir_db

# Sync CNV
docker compose exec web python manage.py sync_cnv
docker compose exec web python manage.py sync_cnv --full

# SSL
sudo certbot certificates

# Monitoring
docker compose logs grafana
docker compose logs loki
docker compose logs promtail
# Grafana UI: http://14.225.254.192:3000
```

---

## 10. Dependencies

```
Django==6.0.2        openpyxl==3.1.5      pandas==3.0.0
requests==2.32.5     python-dotenv==1.2.1  gunicorn==21.2.0
whitenoise==6.6.0    psycopg2-binary       django-apscheduler
django-redis         numpy==2.4.2          xlrd==2.0.2
beautifulsoup4       lxml
Flask==3.1.2         (legacy, possibly unused)
```
