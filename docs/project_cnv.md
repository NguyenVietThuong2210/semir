---
name: CNV Loyalty API Integration
description: CNV API client, sync service, endpoints, scheduler, and Zalo integration details
type: project
---

## Overview
CNV Loyalty is an external loyalty platform integrated via REST API.
- API Base: `https://apis.cnvloyalty.com`
- Auth: OAuth2 authorization code flow (username/password)
- Token cached 30 days

## API Client — `App/cnv/api_client.py` (CNVAPIClient)
Methods:
- `authenticate()` → Get/refresh access token
- `get_customers(page, page_size)` → Paginated customer list
- `get_customer_membership(id)` → `/loyalty/customers/{id}/membership.json` (NEW Feb 2026)
- `get_orders(page, page_size)` → Paginated orders
- `fetch_all_customers(updated_since)` → Full pagination with checkpoint

## Sync Service — `App/cnv/sync_service.py` (CNVSyncService, updated Feb 27 2026)
- **Mode:** Incremental sync (checkpoint-based on `cnv_updated_at`)
- **Batch size:** 500 records
- **Membership:** fetched in parallel for each customer batch
- Key methods:
  - `_transform_customer(data)` → maps API response to DB fields
  - `_fetch_membership(customer_id)` → gets used_points etc.
  - `_transform_order(data)` → maps order API response
  - `_process_customer_batch(batch)` → bulk create/update + membership
  - `sync_customers(incremental=True)` → main sync
  - `sync_orders()` → order sync

## Scheduler — `App/cnv/scheduler.py`
- APScheduler background tasks
- Runs periodic sync automatically

## Management Command
```bash
python manage.py sync_cnv          # Incremental sync
python manage.py sync_cnv --full   # Full sync
```

## CNV Views — `App/cnv/views.py`
- `sync_status()` — Dashboard: latest syncs, stats, running state
- `customer_analytics()` — POS vs CNV comparison (cached)
- `export_customer_analytics()` — Excel export
- `sync_cnv_points()` — AJAX: sync selected customers
- `trigger_sync()` — AJAX: manual sync trigger
- `trigger_zalo_sync()` — AJAX: Zalo sync trigger

## CNV URLs — `/cnv/`
```
/cnv/sync-status/                   → sync_status
/cnv/customer-analytics/            → customer_analytics
/cnv/export-customer-analytics/     → export_customer_analytics
/cnv/sync-cnv-points/               → sync_cnv_points (AJAX)
/cnv/trigger-sync/                  → trigger_sync (AJAX)
/cnv/trigger-zalo-sync/             → trigger_zalo_sync (AJAX)
```

## Zalo Integration — `App/cnv/zalo_sync.py`
- Separate Zalo OA integration
- Fields on CNVCustomer: `zalo_app_id`, `zalo_oa_id`, `zalo_app_created_at`
- sync_type = "zalo_sync" in CNVSyncLog

## POS ↔ CNV Customer Matching
- Match key: **phone number**
- POS: Customer.phone
- CNV: CNVCustomer.phone (indexed)
- Used in customer_analytics view for comparison reports
