"""
App/cnv/scheduler.py

Scheduler for CNV sync jobs.
Uses CNV_USERNAME and CNV_PASSWORD from settings.
"""

import atexit
import logging
import os
import socket
import threading
import time
from datetime import timedelta
from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.cron import CronTrigger
from apscheduler.triggers.interval import IntervalTrigger
from django_apscheduler.jobstores import DjangoJobStore
from django_apscheduler.models import DjangoJobExecution
from django.conf import settings
from django.utils import timezone

from .sync_service import CNVSyncService

# A sync stuck in "running" for longer than this is considered crashed/orphaned
_STALE_SYNC_HOURS = 2

logger = logging.getLogger(__name__)

# ── Single-leader guard (prod runs gunicorn --workers 3; without this every
#    worker starts its own scheduler → jobs fire 3×, causing 429 rate-limit
#    storms, "already running" skips, and DjangoJobStore replace races). Only
#    the worker that wins the Redis lock runs the scheduler.
#
#    TTL is intentionally short: on a redeploy, the OLD container dies without
#    releasing the lock (its Redis key outlives it — Redis is a separate,
#    long-lived container). A long TTL here previously caused a real incident:
#    every new worker saw the dead container's stale key and none started a
#    scheduler until the old TTL expired naturally. Short TTL + a retry loop
#    (below) bounds the gap to ~1 refresh cycle instead of up to 15 minutes.
_SCHEDULER_LOCK_KEY = "cnv_scheduler_leader"
_LOCK_TTL = 120        # 2 min — short so a dead leader's slot frees up fast
_LOCK_REFRESH = 40     # leader refreshes every 40s (3x margin before TTL)
_LEADER_RETRY = 45     # non-leader workers re-attempt to become leader this often
_leader_token = None   # set on the worker that owns the scheduler
_last_logged_holder = None  # 2026-07-15: last "lock held by X" value THIS worker
                            # logged — the retry loop calls _try_become_leader_and_start
                            # every 45s forever for every non-leader worker; logging on
                            # every failed attempt (unchanged steady state) produced
                            # ~2 lines/45s = ~3800 lines/day of pure noise that crowded
                            # out useful INFO entries on /admin-logs/. Only log when the
                            # observed holder actually CHANGES (worth knowing) — startup
                            # and leader handover still get one log line each.


def _refresh_scheduler_leader():
    """Extend the leader lock TTL; runs only inside the leader's scheduler."""
    from django.core.cache import cache
    global _leader_token
    if _leader_token and cache.get(_SCHEDULER_LOCK_KEY) == _leader_token:
        cache.set(_SCHEDULER_LOCK_KEY, _leader_token, _LOCK_TTL)
        logger.debug("Scheduler leader lock refreshed (%s)", _leader_token)


def _release_scheduler_leader():
    """Best-effort release on graceful process exit (atexit) so a standby
    worker can take over almost immediately instead of waiting for TTL."""
    global _leader_token
    if not _leader_token:
        return
    try:
        from django.core.cache import cache
        if cache.get(_SCHEDULER_LOCK_KEY) == _leader_token:
            cache.delete(_SCHEDULER_LOCK_KEY)
            logger.info("Released scheduler leader lock (%s) on process exit.", _leader_token)
    except Exception:
        pass  # best-effort only — TTL is the real safety net


# Get credentials from settings
CNV_USERNAME = settings.CNV_USERNAME
CNV_PASSWORD = settings.CNV_PASSWORD


def sync_cnv_customers_only():
    """Sync customers only. Runs once per hour at :05 (single leader worker)."""
    logger.info("=" * 60)
    logger.info("STARTING CUSTOMERS SYNC JOB")
    logger.info("=" * 60)

    try:
        from App.cnv.models import CNVSyncLog

        # Mark orphaned "running" logs (crashed / container restart) as failed
        stale_threshold = timezone.now() - timedelta(hours=_STALE_SYNC_HOURS)
        stale_qs = CNVSyncLog.objects.filter(
            sync_type="customers",
            status="running",
            started_at__lt=stale_threshold,
        )
        stale_count = stale_qs.update(
            status="failed",
            error_message=f"Auto-failed: stuck for > {_STALE_SYNC_HOURS}h (orphaned after restart)",
            completed_at=timezone.now(),
        )
        if stale_count:
            logger.warning("Cleared %d stale customers sync log(s)", stale_count)

        running = CNVSyncLog.objects.filter(
            sync_type="customers", status="running"
        ).exists()

        if running:
            logger.warning("Customers sync already running - skipping")
            return

        # Check if initial sync needed (no checkpoint exists)
        has_checkpoint = CNVSyncLog.objects.filter(
            sync_type="customers",
            status="completed",
            checkpoint_updated_at__isnull=False,
        ).exists()

        logger.info("CNV Username: %s", CNV_USERNAME)
        logger.info("Creating sync service...")

        service = CNVSyncService(CNV_USERNAME, CNV_PASSWORD)

        if not has_checkpoint:
            logger.info("No checkpoint found - running INITIAL SYNC from IDs file...")
            created, updated, failed = service.initial_sync_customers_from_ids()
        else:
            logger.info("Checkpoint exists - running INCREMENTAL SYNC...")
            created, updated, failed = service.sync_customers(incremental=True)

        logger.info("=" * 60)
        logger.info("CUSTOMERS SYNC COMPLETED")
        logger.info("Created: %d, Updated: %d, Failed: %d", created, updated, failed)
        logger.info("=" * 60)

    except Exception as e:
        logger.error("=" * 60)
        logger.error("CUSTOMERS SYNC FAILED: %s", e)
        logger.error("=" * 60)
        logger.exception("Full traceback:")


def sync_cnv_orders_only():
    """Sync orders only. Runs once per hour at :10 (single leader worker)."""
    logger.info("=" * 60)
    logger.info("STARTING ORDERS SYNC JOB")
    logger.info("=" * 60)

    try:
        from App.cnv.models import CNVSyncLog

        # Mark orphaned "running" logs (crashed / container restart) as failed
        stale_threshold = timezone.now() - timedelta(hours=_STALE_SYNC_HOURS)
        stale_qs = CNVSyncLog.objects.filter(
            sync_type="orders",
            status="running",
            started_at__lt=stale_threshold,
        )
        stale_count = stale_qs.update(
            status="failed",
            error_message=f"Auto-failed: stuck for > {_STALE_SYNC_HOURS}h (orphaned after restart)",
            completed_at=timezone.now(),
        )
        if stale_count:
            logger.warning("Cleared %d stale orders sync log(s)", stale_count)

        running = CNVSyncLog.objects.filter(
            sync_type="orders", status="running"
        ).exists()

        if running:
            logger.warning("Orders sync already running - skipping")
            return

        # Check if initial sync needed (no checkpoint exists)
        has_checkpoint = CNVSyncLog.objects.filter(
            sync_type="orders", status="completed", checkpoint_updated_at__isnull=False
        ).exists()

        logger.info("CNV Username: %s", CNV_USERNAME)
        logger.info("Creating sync service...")

        service = CNVSyncService(CNV_USERNAME, CNV_PASSWORD)

        if not has_checkpoint:
            logger.info(
                "No checkpoint found - running INITIAL SYNC from June 2024 by month..."
            )
            created, updated, failed = service.initial_sync_orders_by_month()
        else:
            logger.info("Checkpoint exists - running INCREMENTAL SYNC...")
            created, updated, failed = service.sync_orders(incremental=True)

        logger.info("=" * 60)
        logger.info("ORDERS SYNC COMPLETED")
        logger.info("Created: %d, Updated: %d, Failed: %d", created, updated, failed)
        logger.info("=" * 60)

    except Exception as e:
        logger.error("=" * 60)
        logger.error("ORDERS SYNC FAILED: %s", e)
        logger.error("=" * 60)
        logger.exception("Full traceback:")


def delete_old_job_executions(max_age=604_800):
    """Delete old job execution records (7 days)."""
    try:
        DjangoJobExecution.objects.delete_old_job_executions(max_age)
        logger.info("Deleted job executions older than %d seconds", max_age)
    except Exception as e:
        logger.error("Failed to delete old job executions: %s", e)


def start_scheduler():
    """
    Elect a single leader worker (across all gunicorn workers) to run
    APScheduler, then start it in that worker only.

    Note: In development mode, this may be called twice due to Django auto-reload.
    This is normal — the leader election handles it the same way as multiple
    gunicorn workers.
    """
    logger.info("Initializing scheduler (leader election)...")

    if _try_become_leader_and_start():
        return

    # Lost the race at startup — do NOT give up permanently. Keep retrying in
    # the background so this worker takes over automatically if the current
    # leader dies later (crash, OOM, redeploy) without THIS worker restarting.
    logger.info(
        "Did not win scheduler leader election — will retry every %ss in the background.",
        _LEADER_RETRY,
    )
    t = threading.Thread(target=_leader_retry_loop, daemon=True, name="cnv-scheduler-leader-retry")
    t.start()


def _try_become_leader_and_start() -> bool:
    """Attempt to acquire the leader lock; if won, build and start the
    scheduler in this process. Returns True iff this call became leader."""
    global _leader_token, _last_logged_holder
    from django.core.cache import cache
    token = f"{socket.gethostname()}:{os.getpid()}"
    if not cache.add(_SCHEDULER_LOCK_KEY, token, _LOCK_TTL):
        holder = cache.get(_SCHEDULER_LOCK_KEY)
        # Only log when the holder is different from what THIS worker last
        # logged — avoids re-logging the same "still not leader" fact every
        # 45s forever (see _last_logged_holder comment above).
        if holder != _last_logged_holder:
            logger.info("Scheduler leader lock held by %s — this worker (%s) will NOT start a scheduler.",
                        holder, token)
            _last_logged_holder = holder
        return False
    _leader_token = token
    _last_logged_holder = token
    atexit.register(_release_scheduler_leader)
    logger.info("Acquired scheduler leader lock (%s) — starting the single scheduler.", token)
    _build_and_start_scheduler()
    return True


def _leader_retry_loop():
    """Runs in a background thread on every non-leader worker. Periodically
    re-attempts the leader election so the fleet self-heals without a
    redeploy if the current leader disappears."""
    while True:
        time.sleep(_LEADER_RETRY)
        try:
            if _try_become_leader_and_start():
                logger.info("Became scheduler leader on retry — scheduler now running in this worker.")
                return
        except Exception:
            logger.exception("Scheduler leader retry attempt failed")


def _build_and_start_scheduler(customers_trigger=None, orders_trigger=None,
                                use_django_jobstore=True, refresh_lock=True):
    """Register jobs and start APScheduler.

    Parameters exist so this can be exercised locally/in tests WITHOUT hitting
    the real CNV API and WITHOUT waiting real hours for a CronTrigger to fire:
      - customers_trigger / orders_trigger: override the production
        CronTrigger with e.g. an IntervalTrigger(seconds=2) for a fast local
        smoke test. Defaults (None) use the real production cadence.
      - use_django_jobstore=False: use APScheduler's in-memory MemoryJobStore
        instead of DjangoJobStore, so a test doesn't need a background
        thread touching the Django test DB across the test's transaction.
      - refresh_lock=False: skip registering the leader-lock-refresh job
        (irrelevant for a single-process local test).

    Called only in the elected leader in production.
    """
    scheduler = BackgroundScheduler(
        job_defaults={"coalesce": True, "max_instances": 1, "misfire_grace_time": 900}
    )

    if use_django_jobstore:
        scheduler.add_jobstore(DjangoJobStore(), "default")
        # Clear any jobs persisted by a previous deploy so a changed trigger
        # always takes effect (DjangoJobStore otherwise keeps the OLD
        # next_run_time).
        try:
            scheduler.remove_all_jobs()
            logger.info("Cleared stale jobs from DjangoJobStore before re-registering.")
        except Exception as exc:
            logger.warning("remove_all_jobs failed (continuing): %s", exc)

    # Production cadence (changed 2026-07-26, was every 10 min): once per
    # hour — customers at :05, orders at :10. A single CronTrigger(minute=N)
    # value fires exactly once per hour (unlike the old comma-separated list
    # which fired every 10 min); the two jobs are offset by 5 min so they
    # don't both hit the CNV API / rate limiter at the same instant.
    customers_desc = ("hourly at :05" if customers_trigger is None
                       else f"TEST/custom trigger {customers_trigger}")
    orders_desc = ("hourly at :10" if orders_trigger is None
                   else f"TEST/custom trigger {orders_trigger}")

    scheduler.add_job(
        sync_cnv_customers_only,
        trigger=customers_trigger or CronTrigger(minute="5"),
        id="cnv_customers_sync",
        max_instances=1,
        replace_existing=True,
        name="CNV Customers Sync",
    )
    logger.info("Registered job: CNV Customers Sync (%s)", customers_desc)

    scheduler.add_job(
        sync_cnv_orders_only,
        trigger=orders_trigger or CronTrigger(minute="10"),
        id="cnv_orders_sync",
        max_instances=1,
        replace_existing=True,
        name="CNV Orders Sync",
    )
    logger.info("Registered job: CNV Orders Sync (%s)", orders_desc)

    if refresh_lock:
        # Keep the leader lock alive while this worker runs the scheduler.
        scheduler.add_job(
            _refresh_scheduler_leader,
            trigger=IntervalTrigger(seconds=_LOCK_REFRESH),
            id="scheduler_lock_refresh",
            max_instances=1,
            replace_existing=True,
            name="Scheduler Leader Lock Refresh",
        )

    # Cleanup daily at 2 AM
    scheduler.add_job(
        delete_old_job_executions,
        trigger=CronTrigger(hour=2, minute=0),
        id="delete_old_job_executions",
        max_instances=1,
        replace_existing=True,
        name="Delete Old Job Executions",
    )
    logger.info("Registered job: Delete Old Job Executions (Daily 2 AM)")

    try:
        logger.info("Starting scheduler...")
        scheduler.start()

        logger.info("=" * 60)
        logger.info("SCHEDULER STARTED SUCCESSFULLY")
        logger.info("=" * 60)
        logger.info("Scheduled jobs:")
        logger.info("  [1] CNV Customers Sync - %s", customers_desc)
        logger.info("  [2] CNV Orders Sync - %s", orders_desc)
        logger.info("  [3] Cleanup Old Logs - Daily at 2:00 AM")
        logger.info("=" * 60)

        return scheduler

    except Exception as e:
        logger.error("Failed to start scheduler: %s", e)
        logger.exception("Full traceback:")
        raise
