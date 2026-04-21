---
name: CNV Loyalty API Integration
description: CNV API client, sync service, scheduler, service.py breakdown, Zalo integration
type: project
---

## Overview
CNV Loyalty is an external loyalty platform integrated via REST API.
- **API Base:** `https://apis.cnvloyalty.com`
- **SSO URL:** `https://id.cnv.vn`
- **Auth:** OAuth2 authorization code flow (username/password)
- **Token cache:** 30 days via Django cache

---

## API Client — `App/cnv/api_client.py` (CNVAPIClient)

OAuth2 HTTP client with token lifecycle management.

| Method | Purpose |
|--------|---------|
| `authenticate()` | OAuth2 login via SSO, caches token 30d |
| `get_customers(page, page_size, updated_since, ids)` | Paginated customer list (100/page) |
| `get_orders(page, page_size, start_date, end_date, updated_since, updated_until)` | Paginated orders |
| `fetch_all_customers(updated_since, max_pages)` | Bulk fetch up to 100 pages (10K records) |
| `fetch_all_orders(...)` | Bulk fetch orders with date/checkpoint filtering |
| `fetch_customers_by_ids(customer_ids, batch_size)` | Batch fetch by ID (max 100 per call) |
| `get_customer_membership(customer_id)` | Fetch loyalty membership data |
| `_make_request(method, endpoint, **kwargs)` | Base authenticated HTTP request |

---

## Sync Service — `App/cnv/sync_service.py` (CNVSyncService)

Checkpoint-based incremental sync. Batch size: 500.

| Method | Purpose |
|--------|---------|
| `sync_customers(incremental=True)` | Main customer sync |
| `sync_orders()` | Order sync |
| `_process_customer_batch(batch)` | Bulk create/update customers |
| `_transform_customer(data)` | Map API response → CNVCustomer fields |
| `_transform_order(data)` | Map API response → CNVOrder fields |

**Flow:**
1. Check for orphaned running sync (>2h → mark failed)
2. Create `CNVSyncLog(status='running')`
3. Fetch pages from API using checkpoint `cnv_updated_at`
4. Bulk create/update in batches of 500
5. Update `checkpoint_updated_at` + mark `status='completed'`

---

## Service Module — `App/cnv/service.py` (KEY — not in old docs)

Powers the CNV customer comparison analytics (POS vs CNV breakdown).

### `parse_cnv_period_filter(start_date, end_date)`
```python
# Returns (filter_dict, has_filter_bool)
parse_cnv_period_filter('2025-01-01', '2025-12-31')  → ({'start': date, 'end': date}, True)
parse_cnv_period_filter('', '')                       → ({}, False)
```
**⚠ CRITICAL:** Returns `{}` (empty dict), NOT `None` when no dates given.
Always check with `if not period_filter:` — NOT `if period_filter is None:`.

### `get_cnv_phone_sets()`
- Cached 10 min
- Returns `(pos_phones_all, cnv_phones_all)` as Python sets
- Used for POS↔CNV phone matching

### `_fetch_bd_raw(period_filter)`
- Cached 5 min per period_filter
- **Must receive a dict** (either `{'start': ..., 'end': ...}` or `{}`), never `None`
- Crashes with `AttributeError` if passed `None` (calls `.get()` on it)

### `compute_cnv_breakdown(period_filter, store=None, ...)`
- `period_filter` must be `{}` for no-filter (all-time), or `{'start': date, 'end': date}` for period
- Returns breakdown: new POS customers, CNV-matched, Zalo registrations by store/season/month/week

---

## Scheduler — `App/cnv/scheduler.py`

APScheduler jobs registered on app startup (`start_scheduler()`):

| Job | Schedule | Purpose |
|-----|----------|---------|
| `sync_cnv_customers_only` | Every hour at :05 | Incremental customer sync |
| `sync_cnv_orders_only` | Every hour at :10 | Incremental order sync |
| `delete_old_job_executions` | Daily at 2:00 AM | Cleanup old job records (7d retention) |

**Settings:**
- `coalesce=True` (skip missed jobs)
- `max_instances=1` (no overlapping runs)
- `misfire_grace_time=900s`
- Stale sync threshold: 2 hours

---

## Zalo Sync — `App/cnv/zalo_sync.py`

Multi-threaded Zalo mini-app integration sync (100K+ customer records).

| Function | Purpose |
|----------|---------|
| `run_zalo_sync(cookie)` | Entry point; spawns background thread |
| `_do_sync(cookie, sync_log)` | Core sync loop (ThreadPoolExecutor) |
| `_fetch_zalo_data(cnv_id, cookie)` | Per-thread HTTP fetch to Zalo API |
| `_parse_zalo_fields(data)` | Extract `zalo_app_id`, `zalo_oa_id`, `zalo_app_created_at` |
| `is_zalo_sync_running()` | Check in-memory lock |

**Constants:**
- `ZALO_API_BASE`: `https://app.cnvloyalty.com/api/ecommerce/customers/contactcdp`
- `THREAD_WORKERS`: 10 (ThreadPoolExecutor)
- `BATCH_SIZE`: 500 rows per `bulk_update`
- `LOG_INTERVAL`: log progress every 1000 records
- `STALE_ZALO_HOURS`: 4

**Zalo type codes:**
- `zalo_type=2` → mini app → `zalo_app_id`
- `zalo_type=1` → OA follow → `zalo_oa_id`

**Guard:** DB-level `status='running'` check + in-memory lock + thread-local session objects.

---

## CNV Views — `App/cnv/views.py`

All under `/cnv/`, see `App/cnv/urls.py`.

| View | URL | Permission | Purpose |
|------|-----|-----------|---------|
| `sync_status` | `/cnv/sync-status/` | `page_cnv_sync` | Latest sync logs + running state |
| `customer_analytics` | `/cnv/customer-analytics/` | `page_cnv_comparison` | POS vs CNV comparison overview |
| `customer_tab` | `/cnv/customer-analytics/tab/<tab>/` | `page_cnv_comparison` | AJAX tab (bd_season, bd_month, ...) |
| `customer_chart` | `/cnv/customer-chart/` | `page_customer_chart` | Comparison charts |
| `trigger_sync` | `/cnv/trigger-sync/` | `page_cnv_sync` | Manual sync trigger (POST) |
| `trigger_zalo_sync` | `/cnv/trigger-zalo-sync/` | `page_cnv_sync` | Manual Zalo sync trigger (POST) |

---

## POS ↔ CNV Customer Matching
- Match key: **phone number**
- `Customer.phone` ↔ `CNVCustomer.phone` (both db_indexed)
- Sets computed by `get_cnv_phone_sets()` → cached 10 min
- Used in `customer_analytics` view for POS vs CNV comparison

---

## Management Commands
```bash
python manage.py sync_cnv_customers   # Run customer sync
python manage.py sync_cnv_orders      # Run order sync
```
