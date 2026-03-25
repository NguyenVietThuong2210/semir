---
name: SemirDashboard Database Models
description: All database models, fields, and relationships for SemirDashboard
type: project
---

## POS Models — `App/models/pos.py`

### Customer
| Field | Type | Notes |
|-------|------|-------|
| vip_id | CharField | Part of unique_together with phone |
| phone | CharField | Part of unique_together with vip_id |
| name | CharField | |
| vip_grade | CharField | VIP0 / VIP1 / VIP2 / VIP3 / DIAMOND |
| registration_date | DateField | |
| points | IntegerField | |
| (other fields) | | |

**Rule:** vip_id = "0" → non-VIP customer, excluded from most analytics

### SalesTransaction
| Field | Type | Notes |
|-------|------|-------|
| invoice_number | CharField | unique |
| shop_id | CharField | e.g. "HN01", "SG02" |
| vip_id | CharField | |
| sales_date | DateField | |
| settlement_amount | DecimalField | |
| customer | FK → Customer | nullable |

---

## Coupon Models — `App/models/coupon.py`

### Coupon
| Field | Type | Notes |
|-------|------|-------|
| coupon_id | CharField | indexed |
| used | IntegerField | 0 = unused, 1 = used |
| face_value | DecimalField | |
| using_date | DateField | nullable |
| docket_number | CharField | |

### CouponCampaign
| Field | Type | Notes |
|-------|------|-------|
| name | CharField | unique |
| prefix | TextField | comma-separated prefixes |
| detail | TextField | |

---

## User Models — `App/models/user.py`

### Role
| Field | Type | Notes |
|-------|------|-------|
| name | CharField | unique |
| permissions | JSONField | list of permission strings |
| is_system | BooleanField | system roles can't be deleted |

### UserProfile
| Field | Type | Notes |
|-------|------|-------|
| user | OneToOne → User | Django built-in User |
| role | FK → Role | |

**Permissions strings:**
- `page_analytics`, `page_coupons`, `page_cnv_sync`, `manage_users`
- etc. (defined in `App/permissions.py`)

---

## CNV Models — `App/cnv/models.py` (restructured Feb 27, 2026)

### CNVCustomer
| Field | Type | Notes |
|-------|------|-------|
| id | AutoField | Primary key (new) |
| cnv_id | BigIntegerField | unique — ID from CNV API |
| last_name | CharField | Split from old full_name |
| first_name | CharField | Split from old full_name |
| phone | CharField | indexed — used for POS↔CNV matching |
| email | CharField | nullable |
| gender | CharField | nullable |
| birthday_day | IntegerField | nullable |
| birthday_month | IntegerField | nullable |
| birthday_year | IntegerField | nullable |
| points | IntegerField | |
| exp_points | IntegerField | |
| total_spending | DecimalField | |
| total_points | IntegerField | |
| level_name | CharField | indexed — membership level |
| used_points | IntegerField | from /membership endpoint |
| cnv_created_at | DateTimeField | renamed from created_at |
| cnv_updated_at | DateTimeField | renamed from updated_at |
| zalo_app_id | CharField | nullable |
| zalo_oa_id | CharField | nullable |
| zalo_app_created_at | DateTimeField | nullable |

**Properties:**
- `full_name` → `f"{last_name} {first_name}"`
- `registration_date` → alias for `cnv_created_at`

### CNVOrder
| Field | Type | Notes |
|-------|------|-------|
| order_code | CharField | Primary key |
| order_id | IntegerField | |
| customer_code | CharField | |
| customer_name | CharField | |
| customer_phone | CharField | |
| order_date | DateTimeField | |
| store_code | CharField | |
| store_name | CharField | |
| subtotal | DecimalField | |
| discount_amount | DecimalField | |
| tax_amount | DecimalField | |
| shipping_fee | DecimalField | |
| total_amount | DecimalField | |
| points_earned | IntegerField | |
| points_used | IntegerField | |
| items | JSONField | |
| raw_data | JSONField | |

### CNVSyncLog
| Field | Type | Notes |
|-------|------|-------|
| sync_type | CharField | customers / orders / full / zalo_sync |
| status | CharField | running / completed / failed |
| checkpoint_updated_at | DateTimeField | for incremental sync |
| total_records | IntegerField | |
| created_count | IntegerField | |
| updated_count | IntegerField | |
| failed_count | IntegerField | |
| error_message | TextField | |
| error_details | JSONField | |

---

## Migrations History
- 0001: Customer, SalesTransaction
- 0002: Coupon
- 0003: CNVCustomer, CNVOrder, CNVSyncLog
- 0004: CNVSyncLog.checkpoint_updated_at
- 0005-0006: Index renames on CNVCustomer
- 0007: Zalo fields on CNVCustomer
- 0008: Role, UserProfile
- 0009: CouponCampaign
- 0010: Alter CouponCampaign.prefix
