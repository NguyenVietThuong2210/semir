---
name: SemirDashboard Project Overview
description: Framework, paths, deployment, infrastructure, dependencies for SemirDashboard
type: project
---

## Identity
- **Name:** SemirDashboard
- **Framework:** Django 6.0.2 (Python 3.11)
- **Purpose:** Retail analytics dashboard + CNV Loyalty API integration for SEMIR brand (Vietnam)

## Paths
- **Project root:** `D:\New-jouney\semir\`
- **Django root:** `D:\New-jouney\semir\SemirDashboard\`
- **Django app:** `D:\New-jouney\semir\SemirDashboard\App\`
- **venv:** `D:\New-jouney\semir\venv\`
- **Docs:** `D:\New-jouney\semir\docs\` (project.md, COMPLETED_DEPLOYMENT.md, NEXT.md, task.md moved here Mar 23 2026)
- **Run dev:** `cd SemirDashboard && python manage.py runserver`

## Databases
- **Dev:** SQLite3 (`SemirDashboard/db.sqlite3`)
- **Prod:** PostgreSQL 16 (Alpine, via Docker)

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
- **Promtail:** ships Docker container logs (via Docker socket) to Loki
- **Prometheus:** scrapes cadvisor (container CPU/memory/network metrics)
- **cAdvisor:** exposes Docker container resource metrics to Prometheus
- **Grafana datasources:** auto-provisioned from `monitoring/grafana/provisioning/datasources/datasources.yml`
- **Configs:** `monitoring/` folder (prometheus.yml, loki-config.yml, promtail-config.yml)
- **Env var:** `GRAFANA_PASSWORD` in `.env` (must be set — default "admin" is insecure)
- **UFW rule:** `ufw allow from <office-ip> to any port 3000` — do NOT open to 0.0.0.0

## Key Dependencies
- Django 6.0.2, pandas 3.0.0, openpyxl 3.1.5, requests 2.32.5
- python-dotenv 1.2.1, gunicorn 21.2.0, whitenoise 6.6.0
- psycopg2-binary (PostgreSQL), django-apscheduler (background sync)
- django-redis (caching), numpy 2.4.2, xlrd 2.0.2
- Flask 3.1.2 (legacy/unused — in requirements.txt)

## Security (ASVS Level 1)
- SECURE_SSL_REDIRECT, HSTS (31536000s), secure cookies, CSRF protection
- Non-root Docker user (appuser:1000)
- PBKDF2 password hashing, session timeout 24h with auto-refresh
