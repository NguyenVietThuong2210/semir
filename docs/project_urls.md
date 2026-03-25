---
name: SemirDashboard URL Structure
description: Complete URL routing for all endpoints in SemirDashboard
type: project
---

## Root Router — `SemirDashboard/urls.py`
```
/admin/     → Django admin
/           → App URLs (App/urls.py)
/cnv/       → CNV URLs (App/cnv/urls.py)
```

## App URLs — `App/urls.py`

### Authentication
```
/login/     → login_view
/logout/    → logout_view
/register/  → register_view
```

### Home
```
/           → home
/formulas/  → formulas_page
```

### Uploads
```
/upload/customers/          → upload_customers
/upload/sales/              → upload_sales
/upload/coupons/            → upload_coupons
/upload/used-points/        → upload_used_points
/upload/jobs/               → upload_jobs_list
/upload/jobs/<job_id>/      → upload_job_status (AJAX)
```

### Analytics
```
/analytics/                 → analytics_dashboard
/analytics/export/          → export_analytics
/analytics/chart/           → analytics_chart (AJAX)
```

### Coupons
```
/coupons/                   → coupon_dashboard
/coupons/export/            → export_coupons
/coupons/chart/             → coupon_chart (AJAX)
/coupons/campaigns/         → manage_campaigns
```

### Customer
```
/customer-detail/           → customer_detail (search by VIP ID or phone)
```

### Admin
```
/users/                     → user_management
```

## CNV URLs — `App/cnv/urls.py`
```
/cnv/sync-status/                   → sync_status
/cnv/customer-analytics/            → customer_analytics
/cnv/export-customer-analytics/     → export_customer_analytics
/cnv/sync-cnv-points/               → sync_cnv_points (AJAX POST)
/cnv/trigger-sync/                  → trigger_sync (AJAX POST)
/cnv/trigger-zalo-sync/             → trigger_zalo_sync (AJAX POST)
```

## Production URLs
- Production: `https://analytics-customer-dashboard.com`
- Admin: `https://analytics-customer-dashboard.com/admin/`
