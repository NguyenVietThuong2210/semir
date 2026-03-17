"""
App/cnv/zalo_sync.py

Sync Zalo integration data (mini app + OA follow) for CNV customers.
Uses the /api/ecommerce/customers/contactcdp/{id} endpoint with cookie auth.
Runs with ThreadPoolExecutor for 100k+ records.
"""
import logging
import threading
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone as dt_timezone

import requests
from django.utils import timezone

from App.cnv.models import CNVCustomer, CNVSyncLog

logger = logging.getLogger(__name__)

ZALO_API_BASE = "https://app.cnvloyalty.com/api/ecommerce/customers/contactcdp"
THREAD_WORKERS = 10
BATCH_SIZE = 500          # DB bulk_update batch
LOG_INTERVAL = 1000       # progress log every N records

# Global state so UI can poll running status
_zalo_sync_lock = threading.Lock()
_zalo_sync_running = False


def is_zalo_sync_running():
    """Check if a zalo sync thread is active (in-memory guard)."""
    with _zalo_sync_lock:
        return _zalo_sync_running


def _fetch_zalo_data(cnv_id: int, cookie: str, session: requests.Session):
    """
    Fetch contactcdp data for one CNV customer.
    Returns parsed dict or None on error.
    """
    url = f"{ZALO_API_BASE}/{cnv_id}"
    try:
        resp = session.get(url, timeout=10)
        if resp.status_code == 200:
            return resp.json().get("data")
        logger.debug("CNV %s: HTTP %s", cnv_id, resp.status_code)
        return None
    except Exception as exc:
        logger.debug("CNV %s fetch error: %s", cnv_id, exc)
        return None


def _parse_zalo_fields(data: dict):
    """
    Extract zalo_app_id, zalo_oa_id, zalo_app_created_at from contactcdp response.
    zalo_type=2 → mini app (has app_id)
    zalo_type=1 → OA follow  (has oa_id)
    zalo_app_created_at = data["created_at"] (top-level)
    Returns (zalo_app_id, zalo_oa_id, zalo_app_created_at) or (None, None, None)
    """
    zalo_app_id = None
    zalo_oa_id = None
    zalo_app_created_at = None

    channel = data.get("channel") or {}
    zalo_ids = channel.get("zalo_ids") or []

    for entry in zalo_ids:
        ztype = entry.get("zalo_type")
        if ztype == 2:
            zalo_app_id = entry.get("app_id")
        elif ztype == 1:
            zalo_oa_id = entry.get("oa_id")

    if zalo_app_id or zalo_oa_id:
        raw_created = data.get("created_at")
        if raw_created:
            try:
                zalo_app_created_at = datetime.fromisoformat(
                    raw_created.replace("Z", "+00:00")
                )
            except Exception:
                pass

    return zalo_app_id, zalo_oa_id, zalo_app_created_at


def run_zalo_sync(cookie: str):
    """
    Entry point called from the view (runs in a background thread).
    Fetches all CNV customers, queries contactcdp, updates zalo fields.
    """
    global _zalo_sync_running

    # DB-level guard: check CNVSyncLog
    if CNVSyncLog.objects.filter(sync_type="zalo_sync", status="running").exists():
        logger.warning("Zalo sync already running (DB log). Skipping.")
        return

    # In-memory guard
    with _zalo_sync_lock:
        if _zalo_sync_running:
            logger.warning("Zalo sync already running (thread). Skipping.")
            return
        _zalo_sync_running = True

    sync_log = CNVSyncLog.objects.create(
        sync_type="zalo_sync",
        status="running",
        total_records=0,
    )

    try:
        _do_sync(cookie, sync_log)
        sync_log.mark_completed()
        logger.info("Zalo sync completed — updated=%s failed=%s",
                    sync_log.updated_count, sync_log.failed_count)
    except Exception as exc:
        logger.exception("Zalo sync crashed: %s", exc)
        sync_log.mark_failed(str(exc))
    finally:
        with _zalo_sync_lock:
            _zalo_sync_running = False


def _do_sync(cookie: str, sync_log: CNVSyncLog):
    """Core sync loop using ThreadPoolExecutor."""
    # Load only id + cnv_id — minimal memory footprint
    customer_ids = list(
        CNVCustomer.objects.values_list("id", "cnv_id").order_by("cnv_id")
    )
    total = len(customer_ids)
    sync_log.total_records = total
    sync_log.save(update_fields=["total_records"])

    logger.info("Zalo sync: %d customers to process", total)

    session = requests.Session()
    session.headers.update({
        "cookie": cookie,
        "Accept": "application/json",
        "User-Agent": "SemirDashboard/1.0",
    })

    updated_count = 0
    failed_count = 0
    pending_updates = []   # list of CNVCustomer partial objects

    def process_one(pk, cnv_id):
        data = _fetch_zalo_data(cnv_id, cookie, session)
        if data is None:
            return pk, None, None, None, False
        app_id, oa_id, created_at = _parse_zalo_fields(data)
        return pk, app_id, oa_id, created_at, True

    processed = 0

    with ThreadPoolExecutor(max_workers=THREAD_WORKERS) as executor:
        futures = {
            executor.submit(process_one, pk, cnv_id): (pk, cnv_id)
            for pk, cnv_id in customer_ids
        }

        for future in as_completed(futures):
            pk, app_id, oa_id, created_at, ok = future.result()
            processed += 1

            if not ok:
                failed_count += 1
            else:
                obj = CNVCustomer(pk=pk)
                obj.zalo_app_id = app_id
                obj.zalo_oa_id = oa_id
                obj.zalo_app_created_at = created_at
                pending_updates.append(obj)
                updated_count += 1

            # Flush batch to DB
            if len(pending_updates) >= BATCH_SIZE:
                CNVCustomer.objects.bulk_update(
                    pending_updates,
                    ["zalo_app_id", "zalo_oa_id", "zalo_app_created_at"],
                )
                pending_updates.clear()

            if processed % LOG_INTERVAL == 0:
                logger.info("Zalo sync progress: %d/%d", processed, total)
                sync_log.updated_count = updated_count
                sync_log.failed_count = failed_count
                sync_log.save(update_fields=["updated_count", "failed_count"])

    # Final flush
    if pending_updates:
        CNVCustomer.objects.bulk_update(
            pending_updates,
            ["zalo_app_id", "zalo_oa_id", "zalo_app_created_at"],
        )

    sync_log.updated_count = updated_count
    sync_log.failed_count = failed_count
    sync_log.save(update_fields=["updated_count", "failed_count"])
