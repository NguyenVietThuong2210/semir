---
name: SemirDashboard URL Structure
description: Complete URL routing for all endpoints in SemirDashboard (accurate Apr 2026)
type: project
---

## Root Router — `SemirDashboard/urls.py`
```
/admin/     → Django admin
/cnv/       → App/cnv/urls.py
/           → App/urls.py
```

---

## App URLs — `App/urls.py`

### Authentication
| URL | View | Notes |
|-----|------|-------|
| `/login/` | `login_view` | |
| `/logout/` | `logout_view` | |
| `/register/` | `register_view` | |

### Home
| URL | View | Notes |
|-----|------|-------|
| `/` | `home` | |
| `/formulas/` | `formulas_page` | |

### Uploads
| URL | View | Notes |
|-----|------|-------|
| `/upload/customers/` | `upload_customers` | GET+POST |
| `/upload/sales/` | `upload_sales` | GET+POST |
| `/upload/coupons/` | `upload_coupons` | GET+POST |
| `/upload/used-points/` | `upload_used_points` | GET+POST |
| `/upload/jobs/` | `upload_jobs_list` | JSON |
| `/upload/jobs/<job_id>/` | `upload_job_status` | JSON |

### Analytics (Sales)
| URL | View | Notes |
|-----|------|-------|
| `/analytics/` | `analytics_dashboard` | requires `page_analytics` |
| `/analytics/tab/<str:tab>/` | `analytics_tab` | AJAX, requires `page_analytics` |
| `/analytics/export/` | `export_analytics` | requires `download_analytics` |
| `/analytics/chart/` | `analytics_chart` | requires `page_chart` |
| `/analytics/chart/export/` | `export_sales_chart_excel` | requires `download_chart_excel` |

### Coupons
| URL | View | Notes |
|-----|------|-------|
| `/coupons/` | `coupon_dashboard` | requires `page_coupons` |
| `/coupons/tab/<str:tab>/` | `coupon_tab` | AJAX, requires `page_coupons` |
| `/coupons/export/` | `export_coupons` | requires `download_coupons` |
| `/coupons/chart/` | `coupon_chart` | requires `page_coupon_chart` |
| `/coupons/chart/export/` | `export_coupon_chart_excel` | requires `download_coupon_chart_excel` |
| `/coupons/campaigns/` | `manage_campaigns` | requires `manage_campaigns` |

### Customer
| URL | View | Notes |
|-----|------|-------|
| `/customer-detail/` | `customer_detail` | requires `page_customer_detail`, search by vip_id or phone |

### Shop Detail
| URL | View | Notes |
|-----|------|-------|
| `/shop-detail/` | `shop_detail` | requires `page_shop_detail` |
| `/shop-detail/export/` | `export_shop_detail_excel` | requires `download_shop_detail` |
| `/shop-detail/partial/sales/` | `shop_detail_sales_partial` | AJAX partial, requires `page_shop_detail` |
| `/shop-detail/partial/customer/` | `shop_detail_customer_partial` | AJAX partial, requires `page_shop_detail` |
| `/shop-detail/partial/coupon/` | `shop_detail_coupon_partial` | AJAX partial, requires `page_shop_detail` |

### Admin
| URL | View | Notes |
|-----|------|-------|
| `/users/` | `user_management` | requires `manage_users` |
| `/admin-logs/` | `admin_logs` | superuser only — reads JSON log files |

---

## CNV URLs — `App/cnv/urls.py`

| URL | View | Notes |
|-----|------|-------|
| `/cnv/sync-status/` | `sync_status` | requires `page_cnv_sync` |
| `/cnv/customer-analytics/` | `customer_analytics` | requires `page_cnv_comparison` |
| `/cnv/customer-analytics/tab/<str:tab>/` | `customer_tab` | AJAX, requires `page_cnv_comparison` |
| `/cnv/export-customer-analytics/` | `export_customer_analytics` | requires `download_cnv` |
| `/cnv/sync-cnv-points/` | `sync_cnv_points` | POST, requires `page_cnv_sync` |
| `/cnv/customer-chart/` | `customer_chart` | requires `page_customer_chart` |
| `/cnv/customer-chart/export/` | `export_customer_chart_excel` | requires `download_cnv` |
| `/cnv/trigger-sync/` | `trigger_sync` | POST, requires `page_cnv_sync` |
| `/cnv/trigger-zalo-sync/` | `trigger_zalo_sync` | POST, requires `page_cnv_sync` |

---

## Production
- **Base:** `https://analytics-customer-dashboard.com`
- **Admin:** `https://analytics-customer-dashboard.com/admin/`
