---
name: SemirDashboard Business Logic
description: Core business rules, permissions, formulas, and data conventions for SemirDashboard
type: project
---

## VIP Customer Rules
- `vip_id = "0"` → non-VIP → excluded from grade analytics, tracked separately as "buyer without info"
- Grade hierarchy: `No Grade` < `Member` < `Silver` < `Gold` < `Diamond`
  - **NOT** VIP0/VIP1/VIP2/VIP3/DIAMOND — that's obsolete

## Return Visit Formula (LOCKED — do not change without user approval)
```python
# Source: App/analytics/calculations.py
if registration_date == first_purchase_date:
    return_visits = total_invoices - 1  # Reg-day purchase = not a return
else:
    return_visits = total_invoices

is_returning = (return_visits > 0)
return_rate = returning_count / total_count * 100
```
Counts **INVOICES**, not unique visit days. Intentional.

## Season Definitions (updated Mar 2026)
| Label | Months | Cross-year |
|-------|--------|-----------|
| `M2-4 YYYY` | Feb, Mar, Apr | No |
| `M5-7 YYYY` | May, Jun, Jul | No |
| `M8-10 YYYY` | Aug, Sep, Oct | No |
| `M11-1 YYYY-YYYY` | Nov, Dec, Jan | Yes — `M11-1 2024-2025` format |

Old definition (OBSOLETE): SS = Jan-Jun, AW = Jul-Dec.

## Coupon Face Value Interpretation
- `face_value > 1` → cash discount in VND (use face_value directly as discount amount)
- `0 < face_value ≤ 1` → percentage (e.g. `0.9` means customer pays 90%, so discount = 10% of invoice)
- Logic in: `App/analytics/coupon_analytics.py` → `calc_coupon_amount(face_value, invoice_amount)`

## Shop Grouping
- `"Bala Group"` → shop_name contains "Bala" or "巴拉"
- `"Semir Group"` → shop_name contains "Semir" or "森马"
- `"Others Group"` → all other shops
- Filter via `shop_group` query param on analytics/coupon pages

## POS ↔ CNV Customer Matching
- Match key: **phone number**
- `Customer.phone` ↔ `CNVCustomer.phone` (both db_indexed)
- Cached phone sets via `get_cnv_phone_sets()` (10 min TTL)

## Customer Membership Snapshot Rules (added 2026-08-14)
**Files:** `App/models/membership.py`, `App/analytics/membership.py`, `App/analytics/calculations.py`, `App/services/membership_snapshot.py`, `App/views/membership.py`

Because `Customer.vip_grade` is overwritten on every re-upload with no history kept, the app takes a **snapshot** of the already-computed per-customer state (grade, annual spend, points, annual purchase count) every time customer data changes, so the PO can compare grade-level member counts across time.

**Upgrade thresholds (LOCKED, PO-confirmed 2026-08-14, system-wide, do not change without approval):** annual `settlement_amount` spend, calendar year Jan 1 → the snapshot/as-of date.
| Grade | Annual spend threshold |
|-------|------------------------|
| Silver | ≥ 6,000,000 VND |
| Gold | ≥ 12,000,000 VND |
| Diamond | ≥ 20,000,000 VND |

**Downgrade thresholds — INFORMATIONAL ONLY, not auto-enforced:** the rule is "purchase count within 1 year of the customer's last grade-change date," but that date does not exist anywhere in the source data (no such column on `Customer`, never read from the uploaded file). `MembershipSnapshot.grade_changed_at` is stored but always `NULL` — PO decision (confirmed): leave it blank rather than synthesize a proxy date.
| Grade | Min annual purchases to avoid downgrade |
|-------|-------------------------------------------|
| Silver | 2 |
| Gold | 3 |
| Diamond | 4 |

**Two snapshot mechanisms:**
1. **Automatic** — triggered right after a customer upload finishes successfully (`_membership_done` hook in `App/views/upload.py::upload_customers`), snapshotting the entire current `Customer` table (not just the newly-uploaded delta). Runs in the same background thread as the import; failures are logged but never flip the customer-import job to `status="error"`.
2. **Manual backfill import** — `/membership/backfill-import/`, PO uploads an old customer export file (same column format as the main customer import) and picks a historical `snapshot_date`. Parses the file independently (`_parse_customer_rows()`) and **never writes to the live `Customer` table**.

**"No Grade" exclusion (PO feedback 2026-08-14):** the grade-level KPI views — `get_grade_breakdown()`, `compare_batches()`, `get_all_batch_grade_series()` (KPI comparison table, trend chart) — exclude the `'No Grade'` bucket entirely; it's not an actionable membership tier, just customers with a blank/missing `vip_grade`. Individual "No Grade" customers are still visible and filterable in the per-customer tier progress table (`get_customer_tier_table()`), since they have a genuine upgrade path to Silver. Separately, VIP ID `"0"` (buyer without info, already excluded from all other grade analytics in the codebase) is force-mapped to `'No Grade'` in the snapshot regardless of whatever raw `vip_grade` the import file carries for that row.

## Permissions System
**File:** `App/permissions.py`

26 permissions in `PERMISSION_DEFS`, named `{domain}.{action}` and grouped into 10 domains:

| Codename | Display label | Domain group |
|---|---|---|
| `sales.view` | View Sales Analytics | Sales Analytics |
| `sales.chart` | View Sales Chart | Sales Analytics |
| `sales.export` | Export Sales Analytics (Excel) | Sales Analytics |
| `sales.export_chart` | Export Sales Chart (Excel) | Sales Analytics |
| `coupons.view` | View Coupon Dashboard | Coupons |
| `coupons.chart` | View Coupon Chart | Coupons |
| `coupons.export` | Export Coupons (Excel) | Coupons |
| `coupons.export_chart` | Export Coupon Chart (Excel) | Coupons |
| `coupons.manage` | Manage Coupon Campaigns | Coupons |
| `cnv.view` | View Customer Analytics (CNV) | CNV / Customer Analytics |
| `cnv.chart` | View Customer Chart (CNV) | CNV / Customer Analytics |
| `cnv.sync` | View CNV Sync Status | CNV / Customer Analytics |
| `cnv.export` | Export Customer Analytics (Excel) | CNV / Customer Analytics |
| `cnv.export_chart` | Export Customer Chart (Excel) | CNV / Customer Analytics |
| `customers.detail` | View Customer Detail | Customers |
| `shops.view` | View Shop Detail | Shop Detail |
| `shops.export` | Export Shop Detail (Excel) | Shop Detail |
| `products.view` | View Product Analytics | Product Analytics |
| `products.export` | Export Product Analytics (Excel) | Product Analytics |
| `inventory.view` | View Inventory Analytics | Inventory Analytics |
| `inventory.export` | Export Inventory Dead Stock (CSV) | Inventory Analytics |
| `data.upload` | Upload Data | Data Management |
| `data.formulas` | View Formulas | Data Management |
| `admin.users` | Manage Users | Admin |
| `membership.view` | View Customer Membership | Customer Membership |
| `membership.import` | Backfill Membership Snapshot Import | Customer Membership |

**Built-in:** `VIEWER_PERMISSIONS = ["sales.view", "products.view", "inventory.view"]` — minimal viewer role.

**Check flow:**
1. `user.is_superuser` → all permissions granted
2. `@requires_perm('sales.view')` → checks `user.userprofile.role.permissions`
3. `_ajax_perm_check(request, 'shops.view')` → used in AJAX views instead of `@requires_perm` (avoids 302 redirect on 401)

## Data Upload Flow
1. User uploads CSV/Excel via upload views (`/upload/customers/` etc.)
2. `forms.py` validates file form
3. View spawns background thread: `_start_thread(job_id, fn, file_bytes, ...)`
4. Thread runs import function → updates job status via `upload_jobs.update_job()`
5. Frontend polls `/upload/jobs/<job_id>/` (JSON) until status=done/error
6. Job store backed by Django cache (Redis prod / LocMemCache dev), 24h TTL

**Import batch sizes:** 5000 rows per batch, `bulk_create` + `bulk_update` (no save-per-row).

**Job statuses:** `queued` → `running` → `done` / `error`

## CNV Sync Strategy
- **Incremental:** uses `checkpoint_updated_at` (= last `cnv_updated_at` seen) to fetch only updated records
- **Batch size:** 500 records per sync batch
- **Orphan detection:** sync running >2h → auto-mark as `failed`
- **Scheduler:** customers at :05, orders at :10, cleanup at 2AM daily
- Zalo sync: manual trigger only, 10-thread pool, 500 rows per `bulk_update`

## SalesTransaction.Meta.ordering Footgun
`Meta.ordering = ["sales_date", "invoice_number"]` causes Django to include these fields in `SELECT DISTINCT`.
**Always** call `.order_by()` before `.distinct()`:
```python
# CORRECT:
SalesTransaction.objects.filter(...).order_by().distinct()
```

## Logging & Request Tracking
- Every HTTP request gets a UUID4 `request_id` assigned by `RequestIDMiddleware`
- `request_id` injected into all log records by `RequestIDFilter`
- Logs emitted as JSON (Loki-compatible): `{"time": ..., "level": ..., "request_id": ..., "step": ..., "message": ...}`
- Log files: `logs/app.log`, `logs/cnv_sync.log`, `logs/errors.log`
- `X-Request-ID` response header set for client-side correlation
