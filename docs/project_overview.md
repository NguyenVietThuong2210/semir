---
name: SemirDashboard Project Overview
description: Framework, paths, deployment, infrastructure, dependencies for SemirDashboard
type: project
---

## Identity
- **Name:** SemirDashboard
- **Framework:** Django 4.x (Python 3.11)
- **Purpose:** Retail analytics dashboard + CNV Loyalty API integration for SEMIR brand (Vietnam)

## Paths
- **Project root:** `D:\New-jouney\semir\`
- **Django root:** `D:\New-jouney\semir\SemirDashboard\`
- **Django app:** `D:\New-jouney\semir\SemirDashboard\App\`
- **venv:** `D:\New-jouney\semir\venv\`
- **Docs:** `D:\New-jouney\semir\docs\`
- **Log files:** `SemirDashboard/logs/` → `app.log`, `cnv_sync.log`, `errors.log`

## Run Commands
```bash
# Dev server
cd SemirDashboard && python manage.py runserver

# Migrations
python manage.py makemigrations && python manage.py migrate

# CNV manual sync
python manage.py sync_cnv_customers
python manage.py sync_cnv_orders

# Single test
python manage.py test tests.test_shop_detail.ShopDetailTest.test_snapshot_sales_full

# All tests
python manage.py test tests

# Regenerate snapshots
UPDATE_SNAPSHOTS=1 python manage.py test tests.test_shop_detail
```

## Databases
- **Dev:** SQLite3 (`SemirDashboard/db.sqlite3`)
- **Prod:** PostgreSQL 16 (Alpine, via Docker), `CONN_MAX_AGE=600`

## Cache
- **Dev:** LocMemCache (in-process)
- **Prod:** Redis via django-redis, key prefix `semir`, default TTL 600s

## Deployment
- **Domain:** `analytics-customer-dashboard.com`
- **VPS:** Vietnix SSD 3 — 2 vCPU, 4GB RAM, 60GB SSD, Ubuntu 22.04 LTS
- **Server IP:** 14.225.254.192
- **SSL:** Let's Encrypt (auto-renewal 3 AM daily)
- **Firewall:** ufw (ports 22, 80, 443 open; port 3000 restricted to trusted IPs only) + Fail2ban
- **Stack:** Docker Compose → Nginx → Gunicorn → Django
- **Docker services:** redis, db (postgres:16), web (Django/Gunicorn), nginx, loki, promtail, prometheus, cadvisor, grafana

## Monitoring (added Mar 24 2026)
- **Grafana:** `http://SERVER_IP:3000` — accessible via Tools → Monitoring in Django navbar (superuser only)
- **Loki:** log aggregation — ingests structured JSON logs from all containers via Promtail
- **Structured logging:** `RequestIDFilter` + `JsonFormatter` — all logs are JSON with `request_id`, `step`, `level`, `time`, `message`
- **Prometheus:** scrapes cAdvisor for container CPU/memory/network metrics
- **Configs:** `monitoring/` folder (prometheus.yml, loki-config.yml, promtail-config.yml)

## Key Dependencies
- Django, pandas, openpyxl, requests
- python-dotenv, gunicorn, whitenoise
- psycopg2-binary (PostgreSQL), django-apscheduler (APScheduler)
- django-redis (caching), numpy, xlrd

## Security
- SECURE_SSL_REDIRECT, HSTS (31536000s), secure cookies, CSRF protection
- Non-root Docker user (appuser:1000)
- PBKDF2 password hashing, session timeout 24h with auto-refresh (`SESSION_SAVE_EVERY_REQUEST=True`)
- CNV credentials in settings: `CNV_USERNAME`, `CNV_PASSWORD`
