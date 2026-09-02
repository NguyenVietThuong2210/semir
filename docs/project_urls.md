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

### Customer Membership
| URL | View | Notes |
|-----|------|-------|
| `/membership/` | `membership_dashboard` | requires `membership.view` — grade KPI comparison + grade-by-store breakdown + trend chart + tier table + Manage Snapshots list. `registration_stores` in context is the LIVE `Customer` table (shares `shop_detail.py`'s `_get_dropdown_options()` cache), not scoped to any snapshot batch |
| `/membership/backfill-import/` | `membership_backfill_import` | POST only, requires `membership.import` — uploads a historical customer export, creates a `manual_import` snapshot batch for a PO-chosen date, never touches the live `Customer` table |
| `/membership/delete-batch/<int:batch_id>/` | `membership_delete_batch` | POST only, requires `membership.delete` — deletes a `MembershipSnapshotBatch` row (its `grade_counts`/`grade_members` JSON goes with it — no child model/cascade since the 2026-09-01 redesign) |
| `/membership/partial/table/` | `membership_table_partial` | AJAX partial, requires `membership.view` — Customer Tier Progress table. Reads the LIVE `Customer` table (`get_live_customer_tier_table()`), NOT a snapshot batch — no `batch` param, works even with zero snapshot batches |
| `/membership/partial/store-breakdown/` | `membership_store_breakdown_partial` | AJAX partial, requires `membership.view`, rewritten 2026-09-01 — always renders the full From/To matrix for all stores (`get_grade_breakdown_by_store_comparison(from_batch_id, to_batch_id)`); the old single-store `store=` drill-down param was removed (superseded by the movers section below). Since 2026-09-02 the returned list's last element is always an `'All Stores'` total row (`is_total=True`, computed from `get_grade_breakdown()`'s `overall` bucket, not summed from the per-store rows) — flows through to the `section=store` Excel export automatically |
| `/membership/partial/trend/` | `membership_trend_partial` | AJAX partial, requires `membership.view` — JSON (not HTML, the trend chart is built client-side by Chart.js) `{"series": [...]}`, same shape as `get_all_batch_grade_series()`. `store=<name>` scopes every batch's counts to one registration store |
| `/membership/partial/movers/` | `membership_movers_partial` | AJAX partial, requires `membership.view`, added 2026-09-01 — "Comparison / Members Who Changed Grade" list. Params `from_batch`/`to_batch`/`store`/`grade` → `get_grade_changes(...)`, renders `membership/_movers_partial.html` (scrollable, capped) |
| `/membership/partial/movers-overview/` | `membership_movers_overview_partial` | AJAX partial, requires `membership.view`, added 2026-09-02 — aggregate overview sitting above the movers list: for every store × grade, how many customers' new grade is that grade via downgrade vs upgrade. Requires both `from_batch`/`to_batch` (same "select both" warning HTML as `membership_movers_partial` if either is missing) → `get_grade_changes_overview_by_store(from_batch_id, to_batch_id)`, renders `membership/_movers_overview_partial.html` with context `{"rows": rows, "grades": DISPLAY_GRADES}` (same shape as the store-breakdown partial). Exactly 2 DB queries total (one per batch, via `_grade_members_json()`) — never one query per store |
| `/membership/export/` | `export_membership_excel` | requires `membership.export` (new permission), added 2026-09-01 — per-section Excel download, one view branching on `?section=` in `{comparison, store, movers, trend, tier}` (mirrors `shop_detail.py::export_shop_detail_excel`'s single-view pattern). `section=comparison`/`store` need `from_batch`/`to_batch`; `movers` needs both plus optional `store`/`grade`/`direction`; `trend` takes optional `store`; `tier` takes optional `grade`/`shop`. `movers`/`tier` pass `limit=None` to `get_grade_changes()`/`get_live_customer_tier_table()` so the export contains the full result set, not the on-screen partial's row cap. `tier`'s columns now include `Last Grade Change`/`Direction`/`Purchases Needed to Avoid Downgrade` (added 2026-09-02, `—` for non-`ok` `grade_progress_status` rows). Missing/invalid section or missing required batch params → `messages.error` + redirect to `membership_dashboard` (no crash). No `section=movers-overview` export exists yet — the new overview table (added 2026-09-02) has no dedicated Excel export |
| `/membership/compute-grade-progress/` | `compute_grade_progress` | POST only, requires `membership.compute` (new permission, added 2026-09-02) — kicks off a full-DB recompute of `CustomerGradeProgress` (`App/services/grade_progress_calc.py::compute_all_grade_progress()`) as a background `upload_jobs.py` job of type `grade_progress_calc`, same async pattern as `membership_backfill_import` minus the file upload. Guarded by `is_type_running`/`acquire_type_lock` so only one recompute runs at a time; redirects back to `membership_dashboard` with a status message either way |

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
