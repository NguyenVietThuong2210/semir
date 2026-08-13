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
| `fetch_all_customers(updated_since, max_pages)` | Bulk fetch up to `DEFAULT_MAX_SYNC_PAGES` pages — 100 pages / 10K records per run (briefly 500/50K on 2026-07-14, reverted 2026-07-15 per user request; override via `settings.CNV_MAX_SYNC_PAGES`). **Perf plan P1-05 (2026-07-18):** each page fetch now calls `get_membership_rate_limiter().acquire()` before the request — shares the membership budget rather than a new unconfirmed rate, since no CNV documentation exists for the list endpoint specifically. |
| `fetch_all_orders(...)` | Bulk fetch orders with date/checkpoint filtering — same shared rate limiter as above |
| `fetch_customers_by_ids(customer_ids, batch_size)` | Batch fetch by ID (max 100 per call) |
| `get_customer_membership(customer_id)` | Fetch loyalty membership data |
| `_make_request(method, endpoint, **kwargs)` | Base authenticated HTTP request |

---

## Sync Service — `App/cnv/sync_service.py` (CNVSyncService)

Checkpoint-based incremental sync. Batch size: 500.

**Rate limiter (updated 2026-07-14):** `get_membership_rate_limiter()` in `App/cnv/rate_limit.py` — a **distributed** (Redis/Django-cache-backed) fixed-window limiter, default 50 req/s (CNV limit is 100/s; override via `settings.CNV_MEMBERSHIP_RATE_LIMIT`). `acquire()` called before every `get_customer_membership()` call — **both** in `CNVSyncService._fetch_membership()` (scheduled cron sync) **and** in `App/cnv/views.py sync_cnv_points` (manual admin "sync points" action), so the combined call rate across all gunicorn workers and both call sites stays under CNV's cap. The old per-process `_RateLimiter` class in `sync_service.py` is kept only for direct unit tests — production code no longer uses it, because a purely in-process limiter could not prevent the 2026-07-12 incident (3 concurrent schedulers × 50 req/s = 150 req/s → 429s). **Perf plan P1-05 (2026-07-18):** `api_client.py`'s list-pagination fetch (`fetch_all_customers`/`fetch_all_orders`) now also acquires from this SAME limiter (see API Client section above). **Perf plan P1-04:** a separate `get_zalo_rate_limiter()` (default 30 req/s, `settings.CNV_ZALO_RATE_LIMIT`) protects the Zalo contactcdp endpoint (`App/cnv/zalo_sync.py`) — its own key/budget, never shared with membership.

**Concurrency (perf plan P1-03, 2026-07-18):** membership fetches in `_process_customer_batch` use `ThreadPoolExecutor(max_workers=30)` (was 10) — safe to raise because the rate limiter above is the actual hard cap regardless of thread count; more threads just means less time spent waiting on `acquire()` when per-call latency is high.

| Method | Purpose |
|--------|---------|
| `sync_customers(incremental=True)` | Main customer sync |
| `sync_orders()` | Order sync |
| `_process_customer_batch(batch)` | Bulk create/update customers |
| `_transform_customer(data)` | Map API response → CNVCustomer fields — **does NOT include** `points`, `total_points`, `used_points`, `level_name` (those come only from `_fetch_membership`) |
| `_fetch_membership(customer_id)` | Fetch membership data — rate-limited, retries once on 429 |
| `_transform_order(data)` | Map API response → CNVOrder fields |

**Zero-overwrite rule (2026-05-10):** `_transform_customer` intentionally omits `points`, `total_points`, `used_points`, `level_name`. Only `_fetch_membership` sets these. If membership fetch fails → these columns are NOT in the update dict → DB keeps existing values (never reset to 0).

**Perf plan P3-02 (2026-07-18):** `_process_customer_batch`'s existing-record update path changed from 1 `.update()` query per record to grouped `bulk_update()` calls — grouped by the exact set of fields present in each record's transform dict (preserving the zero-overwrite rule above: a group missing the 4 membership fields never gets a `bulk_update(fields=...)` call that includes them, so those DB columns are never touched). `_process_order_batch` uses a single `bulk_update()` (no grouping needed — `_transform_order` always sets every field). Existing-record lookup now fetches both `id` (real PK, required by `bulk_update`) and `cnv_id` (natural key).

**Flow:**
1. Check for orphaned running sync (>2h → mark failed)
2. Create `CNVSyncLog(status='running')`
3. Fetch pages from API using checkpoint `cnv_updated_at`
4. Bulk create/update in batches of 500 (profile data only)
5. For each customer: `_fetch_membership` (rate-limited) → merge into update dict if successful
6. Update `checkpoint_updated_at` + mark `status='completed'`

**⚠️ Known checkpoint gap (found 2026-07-25, unfixed — root cause, not yet patched):** the checkpoint saved after each run is `max(updated_at across this run's fetched records) + 1 microsecond`; the next run then fetches `updated_at_from >= checkpoint`. The CNV API sorts by `updated_at` ascending. If several customers share the *exact same* `updated_at` (a batch-write tie on CNV's side — e.g. a bulk import or reprocessing event on their platform) and that tie straddles a run's `max_pages` cutoff (100 pages × 100/page = 10,000 records, `sync_customers`/`fetch_all_customers`), the customers past the cutoff are not fetched this run — and since the checkpoint already advanced past their exact `updated_at`, every future incremental run's `>=` filter excludes them too, permanently. Nothing throws and nothing logs an error — nothing "failed", the records are just structurally unreachable by the incremental cursor from then on. Confirmed via a full CNV admin-portal export diffed against production (2026-07-25): 165 customers existed in CNV but had never synced, 100% grade=Member (consistent with never having been updated since their tied creation), clustered heavily on specific days (104 of 165 on one single day). `sync_orders()` uses the identical `latest_updated_at + 1us` checkpoint pattern and is structurally exposed to the same class of bug — not yet audited/confirmed against a real order export.

**Diagnosis & one-off recovery tools (added 2026-07-25, not a fix for the underlying checkpoint design):**
- `python manage.py check_cnv_gap --export "path/Customers_File_*.xls" --out App/cnv/input/cnv_gap_<date>.txt` — diffs a CNV admin-portal customer export (column `Id khách hàng`) against `CNVCustomer`, reports/writes missing IDs.
- `python manage.py sync_cnv --customers --ids-file App/cnv/input/cnv_gap_<date>.txt` — fetches those specific IDs directly via `CNVSyncService.backfill_customers_by_ids()` (reuses the existing `fetch_customers_by_ids` + `_process_customer_batch` pipeline) and upserts them. Deliberately does **not** touch `checkpoint_updated_at` — it's a gap-fill for already-identified stragglers, not a replacement for the scheduled incremental sync.
- Tests: `tests/test_cnv_sync.py::BackfillCustomersByIdsTest`.
- **Not yet done:** a structural fix to the checkpoint itself (e.g. dedupe-by-ID + refetch the tied boundary timestamp inclusively every run, since re-processing an already-synced customer is a harmless idempotent upsert) would close this permanently — flagged for the business/technical owner to prioritize, not applied without sign-off since it changes a live, business-critical incremental sync path.

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
- Cached 5 min (300s) — docstring previously said "10 minutes", corrected 2026-07-18; must match `_fetch_bd_raw`'s TTL (see comment `C-10` in the code)
- Returns `(pos_phones_all, cnv_phones_all)` as Python sets
- Used for POS↔CNV phone matching
- **Implementation (2026-05-04):** cold path calls `_fetch_bd_raw({})` and derives sets in-memory — eliminates the 2 separate POSCustomer+CNVCustomer phone-only queries that used to duplicate the BD raw fetch. Calling `get_cnv_phone_sets()` now also primes the `_fetch_bd_raw({})` cache for the subsequent `compute_cnv_breakdown({})` call.

### `get_cnv_customer_kpis(period_filter, has_filter, pos_phones_all, cnv_phones_all)`
- **Perf plan P2-03 (2026-07-18):** now cached 300s, key `f"cnv_kpis:{start}:{end}:{has_filter}"`. Costs exactly 6 DB queries when `has_filter=True` (2 `.count()`, 2 `.exclude().count()`, 2 inline-subquery `values_list`), 0 when `has_filter=False` (pure Python on already-passed-in phone sets). Used by both the web `customer_analytics` view and the mobile `CustomerAnalyticsView` API.

### `_fetch_bd_raw(period_filter)`
- Cached 5 min per period_filter
- **Must receive a dict** (either `{'start': ..., 'end': ...}` or `{}`), never `None`
- Crashes with `AttributeError` if passed `None` (calls `.get()` on it)
- **Query count:** 4 queries cold (was 7 before 2026-05-03, then 6 before 2026-05-04): single broad POSCustomer scan + CNVCustomer + CNV Zalo + `build_inv_bucket_map_from_db`. Date bounds computed in Python from fetched data (no aggregate queries).
- **Returns 10-tuple** (added `_all_pos_rows` as 10th element 2026-05-04): `(pos_list, cnv_list, zalo_list, phone_to_store, _phone_to_inv, _inv_vid_map, _inv_pk_map, _pop_lo, _pop_hi, _all_pos_rows)`
- **⚠️ 2026-08-10 OOM incident:** on a memory-constrained (1.9GB) prod host, every cold-cache hit on `/cnv/customer-analytics/` was SIGKILL'ing the gunicorn worker within ~5s ("Perhaps out of memory?"). Root cause: `build_inv_bucket_map_from_db()` (`App/analytics/customer_utils.py`) was building 9 sets per VIP customer with an invoice (`sessions`/`months`/`years`/`weeks` + `shops`/`session_shops`/`month_shops`/`week_shops`/`year_shops`), measured at ~152MB / ~65% of this function's total request cost (44,017-customer local scale) — but the only consumer, `classify_new_inv()`, only ever reads the 4 time-only sets (its own docstring: "shop is NEVER part of the inv check"). The 5 shop-combined sets were pure write-only dead weight. Fixed by building only the 4 read sets (and dropping `shop_name` from the underlying query). Verified bit-for-bit output-identical via snapshot diff across the full test fixture (every changed `tests/snapshots/customer*.json` differs only in `_last_run`) — see `tests/test_customer.py::InvBucketMapMemoryOptTest`. Measured: this function's own RSS 152MB→92MB, full cold-page peak 293MB→206MB (−30%), and `get_cnv_phone_sets()` cold call ~10x faster (fewer set insertions). The sibling `build_inv_bucket_map()` (no `_from_db` suffix, same file) still builds all 9 sets — confirmed zero callers anywhere in the codebase (dead code), left untouched since it's out of scope for this fix.

### `compute_cnv_breakdown(period_filter, store=None, ...)`
- `period_filter` must be `{}` for no-filter (all-time), or `{'start': date, 'end': date}` for period
- Returns breakdown: new POS customers, CNV-matched, Zalo registrations by store/season/month/week

---

## Scheduler — `App/cnv/scheduler.py`

APScheduler jobs, started via `start_scheduler()` → single-leader election → `_build_and_start_scheduler()`:

| Job | Schedule | Purpose |
|-----|----------|---------|
| `sync_cnv_customers_only` | Hourly at :05 (changed 2026-07-26, was every 10 min) | Incremental customer sync |
| `sync_cnv_orders_only` | Hourly at :10 (changed 2026-07-26, was every 10 min) | Incremental order sync |
| `scheduler_lock_refresh` | Every `_LOCK_REFRESH`s (40s) | Keeps this worker's leader lock alive |
| `delete_old_job_executions` | Daily at 2:00 AM | Cleanup old job records (7d retention) |

**Settings:**
- `coalesce=True` (skip missed jobs)
- `max_instances=1` (no overlapping runs)
- `misfire_grace_time=900s`
- Stale sync threshold: 2 hours

**Single-leader guard (added 2026-07-12, incident fix):** prod runs `gunicorn --workers 3`. Without a guard, every worker starts its own scheduler → jobs fire 3× → CNV 429 storms + DjangoJobStore replace races. Only the worker that wins a Redis-backed lock (`cache.add("cnv_scheduler_leader", ...)`) runs the scheduler:
- `_LOCK_TTL = 120s`, `_LOCK_REFRESH = 40s` — kept short deliberately. A long TTL previously caused a real outage: when the `web` container is redeployed, the OLD container dies without releasing the lock (Redis is a separate long-lived container, so its key outlives the process that set it); every new worker saw the dead container's stale key and refused to start a scheduler until the old TTL expired naturally (was up to 900s/15min before this fix).
- `_LEADER_RETRY = 45s` — a worker that loses the initial election keeps retrying in a background thread (`_leader_retry_loop`) instead of giving up permanently. Before this, a worker that lost the startup race would NEVER become leader until the next full redeploy, even if the leader later died.
- `_release_scheduler_leader()` registered via `atexit` — best-effort immediate release on graceful shutdown so a standby worker can take over in seconds instead of waiting for TTL.
- **Immediate manual unblock** if a stale lock is ever suspected on prod: `docker exec -it semir_redis redis-cli DEL cnv_scheduler_leader` (the retry loop will pick it up within `_LEADER_RETRY` seconds — no restart needed after this fix, unlike the pre-2026-07-14 code).

**Local testability without calling CNV:**
- `python manage.py cnv_scheduler_smoketest [--duration N] [--interval N]` — mocks the sync functions, substitutes a fast `IntervalTrigger` for the production `CronTrigger`, and prints live fire counts. Proves cron mechanics work on a given machine before ever deploying.
- `tests/test_bugfixes.py::SchedulerCronMechanicsLocalTest` — same idea as an automated, CI-safe test (~4.5s wall time, zero CNV calls).
- Both rely on `_build_and_start_scheduler(customers_trigger=..., orders_trigger=..., use_django_jobstore=False, refresh_lock=False)` — override params that default to the real production behavior when omitted.

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

**Mobile API (`App/api/views/analytics.py`, `charts.py`) — perf plan P2-04 (2026-07-18):** `_compute_grade_rows(cnv_phones_all, period_filter)` (mobile-only, no web caller) is now cached 300s, key `f"grade_rows:{period}"`. Before this, `CustomerAnalyticsView` calling it twice (all-time + period) plus `CustomerChartView` calling it again independently could trigger up to 3 full `Customer` table scans for overlapping data within one user session.

---

## POS ↔ CNV Customer Matching
- Match key: **phone number**
- `Customer.phone` ↔ `CNVCustomer.phone` (both db_indexed)
- Sets computed by `get_cnv_phone_sets()` → cached 5 min (300s)
- Used in `customer_analytics` view for POS vs CNV comparison

---

## Management Commands
```bash
python manage.py sync_cnv_customers   # Run customer sync
python manage.py sync_cnv_orders      # Run order sync
```
