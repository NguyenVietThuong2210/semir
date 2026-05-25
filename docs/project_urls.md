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
| `/upload/sales/` | `upload_sales` | GET+POST — also shows Sale Detail upload section |
| `/upload/sale-detail/` | `upload_sale_detail` | POST only, redirects to upload_sales |
| `/upload/coupons/` | `upload_coupons` | GET+POST |
| `/upload/used-points/` | `upload_used_points` | GET+POST |
| `/upload/inventory/` | `upload_inventory` | GET+POST — InventorySnapshot |
| `/upload/jobs/` | `upload_jobs_list` | JSON |
| `/upload/jobs/<job_id>/` | `upload_job_status` | JSON |

### Analytics (Sales)
| URL | View | Notes |
|-----|------|-------|
| `/analytics/` | `analytics_dashboard` | requires `sales.view` |
| `/analytics/tab/<str:tab>/` | `analytics_tab` | AJAX, requires `sales.view` |
| `/analytics/export/` | `export_analytics` | requires `sales.export` |
| `/analytics/chart/` | `analytics_chart` | requires `sales.chart` |
| `/analytics/chart/export/` | `export_sales_chart_excel` | requires `sales.export_chart` |

### Coupons
| URL | View | Notes |
|-----|------|-------|
| `/coupons/` | `coupon_dashboard` | requires `coupons.view` |
| `/coupons/tab/<str:tab>/` | `coupon_tab` | AJAX, requires `coupons.view` |
| `/coupons/export/` | `export_coupons` | requires `coupons.export` |
| `/coupons/chart/` | `coupon_chart` | requires `coupons.chart` |
| `/coupons/chart/export/` | `export_coupon_chart_excel` | requires `coupons.export_chart` |
| `/coupons/campaigns/` | `manage_campaigns` | requires `coupons.manage` |

### Customer
| URL | View | Notes |
|-----|------|-------|
| `/customer-detail/` | `customer_detail` | requires `customers.detail`, search by vip_id or phone |

### Shop Detail
| URL | View | Notes |
|-----|------|-------|
| `/shop-detail/` | `shop_detail` | requires `shops.view` |
| `/shop-detail/export/` | `export_shop_detail_excel` | requires `shops.export` |
| `/shop-detail/partial/sales/` | `shop_detail_sales_partial` | AJAX partial, requires `shops.view` |
| `/shop-detail/partial/customer/` | `shop_detail_customer_partial` | AJAX partial, requires `shops.view` |
| `/shop-detail/partial/coupon/` | `shop_detail_coupon_partial` | AJAX partial, requires `shops.view` |
| `/shop-detail/partial/inventory/` | `shop_detail_inventory_partial` | AJAX partial, requires `shops.view` |
| `/shop-detail/partial/product/` | `shop_detail_product_partial` | AJAX partial, requires `shops.view` |

### Product Analytics
| URL | View | Notes |
|-----|------|-------|
| `/products/` | `product_dashboard` | requires `products.view` — SaleDetail-based |
| `/products/export/` | `export_product_analytics` | requires `products.export` |
| `/products/tab/<str:tab>/` | `product_tab` | AJAX lazy tab (season/month/week/brand/category) |

### Inventory Analytics
| URL | View | Notes |
|-----|------|-------|
| `/inventory/` | `inventory_dashboard` | requires `inventory.view` — InventorySnapshot-based |
| `/inventory/export/` | `export_inventory_dead_stock` | requires `inventory.export` — dead stock CSV |

### Admin
| URL | View | Notes |
|-----|------|-------|
| `/users/` | `user_management` | requires `manage_users` |
| `/admin-logs/` | `admin_logs` | superuser only — reads JSON log files |

---

## CNV URLs — `App/cnv/urls.py`

| URL | View | Notes |
|-----|------|-------|
| `/cnv/sync-status/` | `sync_status` | requires `cnv.sync` |
| `/cnv/customer-analytics/` | `customer_analytics` | requires `cnv.view` |
| `/cnv/customer-analytics/tab/<str:tab>/` | `customer_tab` | AJAX, requires `cnv.view` |
| `/cnv/export-customer-analytics/` | `export_customer_analytics` | requires `cnv.export` |
| `/cnv/sync-cnv-points/` | `sync_cnv_points` | POST, requires `cnv.sync` |
| `/cnv/customer-chart/` | `customer_chart` | requires `cnv.chart` |
| `/cnv/customer-chart/export/` | `export_customer_chart_excel` | requires `cnv.export_chart` |
| `/cnv/trigger-sync/` | `trigger_sync` | POST, requires `cnv.sync` |
| `/cnv/trigger-zalo-sync/` | `trigger_zalo_sync` | POST, requires `cnv.sync` |

---

## Production
- **Base:** `https://analytics-customer-dashboard.com`
- **Admin:** `https://analytics-customer-dashboard.com/admin/`
