---
name: SemirDashboard Business Logic
description: Core business rules, formulas, and data conventions for SemirDashboard
type: project
---

## VIP Customer Rules
- VIP ID = "0" → non-VIP → excluded from grade analytics
- Non-VIP customers tracked separately as "buyer without info" category
- VIP grade hierarchy: VIP0 < VIP1 < VIP2 < VIP3 < DIAMOND

## Return Visit Formula (LOCKED — do not change without user approval)
```python
# Source: App/analytics/calculations.py
if customer.registration_date == first_purchase_date:
    return_visits = total_invoices - 1
else:
    return_visits = total_invoices

is_returning = (return_visits > 0)
return_rate = returning_count / total_count * 100
```
- Counts INVOICES, not unique visit days
- Rationale: Registration-day purchase = first purchase, not a return

## Season Definitions (updated Mar 2026)
| Season Label | Months | Cross-year? |
|-------------|--------|-------------|
| M2-4 | Feb, Mar, Apr | No |
| M5-7 | May, Jun, Jul | No |
| M8-10 | Aug, Sep, Oct | No |
| M11-1 | Nov, Dec, Jan | Yes (Nov-Dec = year N, Jan = year N+1) |

Old definition (OBSOLETE): SS = Jan-Jun, AW = Jul-Dec

## Shop Grouping
- Shop ID format: `{2-letter city code}{2-digit number}` e.g. "HN01", "SG02"
- Shop Group = first 2 chars: "HN" (Hanoi), "SG" (Saigon/HCMC)
- Custom named groups: "Bala Group", "Semir Group", "Others Group"
- Analytics can be filtered by shop_group parameter

## POS ↔ CNV Customer Matching
- Match by phone number
- POS: Customer.phone → CNV: CNVCustomer.phone
- Used to compare loyalty data between systems
- CNV customer_analytics view computes comparison report

## Data Upload Flow
1. User uploads CSV/Excel file via upload views
2. File parsed by `App/services/file_reader.py`
3. Data processed by `App/services/{customer|sales|coupon}_import.py`
4. Background job queued via `App/upload_jobs.py`
5. Job status checkable via AJAX at `/upload/jobs/<job_id>/`

## Coupon Logic
- Coupon.used: 0 = unused, 1 = used
- CouponCampaign.prefix: comma-separated — coupon belongs to campaign if its ID starts with a prefix
- Analytics groups coupons by campaign for reporting

## Permissions System
Custom role-based, defined in `App/permissions.py`:
- Roles stored in `Role` model (JSONField for permissions list)
- UserProfile links Django User → Role
- Permission strings: `page_analytics`, `page_coupons`, `page_cnv_sync`, `manage_users`
- Checked via `perm_tags.py` template tags and view decorators

## CNV Sync Strategy
- **Incremental:** uses `checkpoint_updated_at` to fetch only updated records
- **Full:** fetches all records (via `--full` flag or manual trigger)
- Membership data fetched from separate endpoint per customer
- Bulk operations with batch_size=500 for performance
