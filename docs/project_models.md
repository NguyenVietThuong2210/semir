---
name: SemirDashboard Database Models
description: All database models, fields, and relationships for SemirDashboard (accurate Apr 2026)
type: project
---

## POS Models — `App/models/pos.py`

### Customer
| Field | Type | Notes |
|-------|------|-------|
| vip_id | CharField(50) | unique, db_index |
| phone | CharField(20) | blank, db_index |
| name | CharField(200) | blank |
| id_number | CharField(50) | blank |
| birthday_month | IntegerField | null, blank (1–12) |
| birthday | DateField | null, blank |
| race | CharField(50) | blank |
| gender | CharField(10) | blank |
| city_state | CharField(100) | blank |
| postal_code | CharField(20) | blank |
| country | CharField(50) | blank |
| vip_grade | CharField(50) | blank — see grade hierarchy below |
| registration_date | DateField | null, blank |
| registration_store | CharField(200) | blank, db_index |
| points | IntegerField | default=0 |
| used_points | IntegerField | default=0 |
| used_points_note | TextField | blank |

**Grade hierarchy (actual):** `No Grade` < `Member` < `Silver` < `Gold` < `Diamond`
(NOT VIP0/VIP1/VIP2/VIP3/DIAMOND — that's obsolete)

**Rule:** `vip_id = "0"` → non-VIP customer → excluded from grade analytics, tracked separately

### SalesTransaction
| Field | Type | Notes |
|-------|------|-------|
| invoice_number | CharField(100) | db_index |
| shop_id | CharField(50) | blank |
| shop_name | CharField(200) | blank, db_index |
| country | CharField(50) | blank |
| bu | CharField(50) | blank |
| sales_date | DateField | db_index |
| vip_id | CharField(50) | db_index |
| vip_name | CharField(200) | blank |
| quantity | IntegerField | default=0 |
| settlement_amount | DecimalField(15,2) | |
| sales_amount | DecimalField(15,2) | |
| tag_amount | DecimalField(15,2) | default=0 |
| per_customer_transaction | DecimalField(15,2) | default=0 |
| discount | DecimalField(15,2) | default=0 |
| rounding | DecimalField(15,2) | default=0 |
| customer | FK → Customer | null, blank, on_delete=SET_NULL |

```python
class Meta:
    ordering = ["sales_date", "invoice_number"]   # ⚠ FOOTGUN
    unique_together = [["invoice_number", "vip_id"]]
```

**⚠ IMPORTANT — `Meta.ordering` footgun:** Django adds ordering fields to `SELECT DISTINCT`.
Always call `.order_by()` before `.distinct()`:
```python
# WRONG — includes sales_date/invoice_number in DISTINCT
SalesTransaction.objects.filter(...).distinct()

# CORRECT
SalesTransaction.objects.filter(...).order_by().distinct()
```

### SaleDetail (line items)
| Field | Type | Notes |
|-------|------|-------|
| invoice_number | CharField(100) | part of unique_together |
| transaction | FK → SalesTransaction | to_field='invoice_number', db_constraint=False, null — soft FK |
| shop_id | CharField(50) | blank |
| shop_name | CharField(200) | blank |
| sales_date | DateField | db_index |
| sales_time | TimeField | null, blank |
| brand | CharField(100) | blank |
| product_code | CharField(100) | blank, part of unique_together |
| product_name | CharField(200) | blank |
| barcode | CharField(100) | blank |
| sku | CharField(100) | blank |
| color | CharField(100) | blank |
| size | CharField(50) | blank |
| year | SmallIntegerField | null, blank |
| season | CharField(50) | blank |
| gender | CharField(50) | blank |
| category_l1/l2/l3 | CharField(100) | blank |
| quantity | IntegerField | default=0 |
| fact_retail_price | DecimalField(15,2) | default=0 |
| sales_amount | DecimalField(15,2) | default=0 |
| settlement_amount | DecimalField(15,2) | default=0 |
| tag_price | DecimalField(15,2) | default=0 |
| tag_amount | DecimalField(15,2) | default=0 |
| discount_pct | DecimalField(7,4) | null, blank — "100.00%" → Decimal("1.0000") |
| vat_rate | CharField(20) | blank |
| salesmen | CharField(100) | blank |
| salesmen_code | CharField(50) | blank |
| promotion | CharField(200) | blank |
| currency | CharField(10) | default='VND' |
| created_at | DateTimeField | auto_now_add |

```python
class Meta:
    unique_together = [['invoice_number', 'product_code']]
```
Indexes: `(sales_date, brand)`, `(sales_date, shop_id)`, `(year, season, brand)`, `(sku, brand)`, `(salesmen, sales_date)`

---

## Inventory Models — `App/models/inventory.py`

### InventorySnapshot
Snapshot of current stock per shop. Re-upload overwrites; no date history.

| Field | Type | Notes |
|-------|------|-------|
| shop_id | CharField(50) | part of unique_together |
| shop_name | CharField(200) | blank |
| brand | CharField(100) | blank |
| product_code | CharField(100) | part of unique_together — encodes color+size variant |
| product_name | CharField(200) | blank |
| product_name_vn | CharField(200) | blank (Chinese name column) |
| barcode | CharField(100) | blank |
| sku | CharField(100) | blank |
| color | CharField(100) | blank |
| size | CharField(50) | blank |
| year | SmallIntegerField | null, blank |
| season | CharField(50) | blank |
| gender | CharField(50) | blank |
| category_l1/l2/l3 | CharField(100) | blank |
| tag_price | DecimalField(15,2) | default=0 |
| inventory_qty | IntegerField | default=0 |
| in_transit_qty | IntegerField | default=0 |
| total_qty | IntegerField | default=0 |
| tag_amount | DecimalField(15,2) | default=0 (on-hand value) |
| total_tag_amount | DecimalField(15,2) | default=0 |
| currency | CharField(10) | default='VND' |
| uploaded_at | DateTimeField | auto_now=True — last upload timestamp |

```python
class Meta:
    unique_together = [['shop_id', 'product_code']]
```
Indexes: `(shop_name, brand)`, `(year, season)`, `(sku, shop_id)`

**Dead stock definition:** `year <= current_year - 1` and `inventory_qty > 0`

---

## Coupon Models — `App/models/coupon.py`

### Coupon
| Field | Type | Notes |
|-------|------|-------|
| department | CharField(100) | blank |
| creator | CharField(100) | blank |
| document_number | CharField(100) | blank |
| coupon_id | CharField(100) | db_index |
| face_value | DecimalField(15,4) | >1 = VND cash; 0<x≤1 = % discount (e.g. 0.9 = pay 90% → 10% off) |
| used | BooleanField | default=False |
| begin_date | DateField | null, blank |
| end_date | DateField | null, blank |
| using_shop | CharField(200) | blank, db_index |
| using_date | DateField | null, blank, db_index |
| push | BooleanField | default=False |
| member_id | CharField(50) | blank, db_index (= vip_id) |
| member_name | CharField(200) | blank |
| member_phone | CharField(20) | blank |
| docket_number | CharField(100) | blank, db_index (= invoice_number) |

### CouponCampaign
| Field | Type | Notes |
|-------|------|-------|
| name | CharField(200) | |
| prefix | CharField(500) | comma-separated coupon_id prefixes e.g. `"BL2024,BL2025"` |

**Coupon → campaign matching:** `coupon.coupon_id.startswith(prefix)` for each prefix in campaign.prefix.split(',')

---

## User Models — `App/models/user.py`

### Role
| Field | Type | Notes |
|-------|------|-------|
| name | CharField(100) | unique |
| description | TextField | blank |
| permissions | JSONField | list of permission keys from PERMISSION_DEFS |

### UserProfile
| Field | Type | Notes |
|-------|------|-------|
| user | OneToOneField → User | Django built-in User |
| role | FK → Role | null, blank, on_delete=SET_NULL |

Permission check: `user.is_superuser` OR `user.userprofile.role.permissions` contains the key.

---

## CNV Models — `App/cnv/models.py`

### CNVCustomer (table: `cnv_customers`)
| Field | Type | Notes |
|-------|------|-------|
| cnv_id | CharField(100) | unique, db_index |
| phone | CharField(20) | blank, db_index — used for POS↔CNV matching |
| name | CharField(200) | blank |
| email | CharField(200) | blank |
| points | **DecimalField(15,2)** | default=0 — current redeemable points |
| exp_points | **DecimalField(15,2)** | default=0 — expiring points |
| total_spending | **DecimalField(15,2)** | default=0 |
| total_points | **DecimalField(15,2)** | default=0 — all-time earned |
| used_points | **DecimalField(15,2)** | default=0 |
| tags | JSONField | default=list |
| physical_card_code | CharField(100) | blank |
| zalo_app_id | CharField(100) | blank — Zalo mini-app user ID |
| zalo_oa_id | CharField(100) | blank — Zalo OA follower ID |
| zalo_app_created_at | DateTimeField | null, blank |
| cnv_created_at | DateTimeField | null, blank |
| cnv_updated_at | DateTimeField | null, blank, db_index |
| synced_at | DateTimeField | auto_now=True |

**Note:** `points`, `exp_points`, `total_spending`, `total_points`, `used_points` are **Decimal**, not Integer.

### CNVOrder (table: `cnv_orders`)
| Field | Type | Notes |
|-------|------|-------|
| order_id | CharField(100) | unique, db_index |
| cnv_customer | FK → CNVCustomer | null, blank, on_delete=SET_NULL |
| phone | CharField(20) | blank, db_index |
| order_date | DateField | null, blank, db_index |
| total_amount | DecimalField(15,2) | default=0 |
| points_earned | DecimalField(15,2) | default=0 |
| order_status | CharField(50) | blank |
| payment_status | CharField(50) | blank |
| payment_method | CharField(50) | blank |
| notes | TextField | blank |
| cnv_updated_at | DateTimeField | null, blank, db_index |
| synced_at | DateTimeField | auto_now=True |

### CNVSyncLog (table: `cnv_sync_logs`)
| Field | Type | Notes |
|-------|------|-------|
| sync_type | CharField(50) | `customers` / `orders` / `zalo_sync` |
| status | CharField(20) | `running` / `completed` / `failed` |
| started_at | DateTimeField | auto_now_add=True |
| completed_at | DateTimeField | null, blank |
| checkpoint_updated_at | DateTimeField | null, blank — incremental sync bookmark |
| total_records | IntegerField | default=0 |
| updated_count | IntegerField | default=0 |
| failed_count | IntegerField | default=0 |
| error_message | TextField | blank |
