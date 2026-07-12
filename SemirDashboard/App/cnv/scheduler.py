"""
App/cnv/scheduler.py

Scheduler for CNV sync jobs.
Uses CNV_USERNAME and CNV_PASSWORD from settings.
"""

import logging
import os
import socket
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
#    the worker that wins the Redis lock runs the scheduler. TTL + periodic
#    refresh makes it self-healing if the leader worker dies.
_SCHEDULER_LOCK_KEY = "cnv_scheduler_leader"
_LOCK_TTL = 900        # 15 min — leader must refresh before this expires
_LOCK_REFRESH = 300    # refresh every 5 min
_leader_token = None   # set on the worker that owns the scheduler


def _refresh_scheduler_leader():
    """Extend the leader lock TTL; runs only inside the leader's scheduler."""
    from django.core.cache import cache
    global _leader_token
    if _leader_token and cache.get(_SCHEDULER_LOCK_KEY) == _leader_token:
        cache.set(_SCHEDULER_LOCK_KEY, _leader_token, _LOCK_TTL)
        logger.debug("Scheduler leader lock refreshed (%s)", _leader_token)


# Get credentials from settings
CNV_USERNAME = settings.CNV_USERNAME
CNV_PASSWORD = settings.CNV_PASSWORD


def sync_cnv_customers_only():
    """Sync customers only. Runs hourly at :05 (single leader worker)."""
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
    """Sync orders only. Runs hourly at :10 (single leader worker)."""
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
    Start APScheduler with CNV sync jobs.

    Note: In development mode, this may be called twice due to Django auto-reload.
    This is normal. Jobs will still only execute once due to max_instances=1.
    """
    logger.info("Initializing scheduler...")

    # Single-leader guard: only the worker that wins the Redis lock runs the
    # scheduler. Other workers return immediately (no duplicate schedulers).
    global _leader_token
    from django.core.cache import cache
    token = f"{socket.gethostname()}:{os.getpid()}"
    if not cache.add(_SCHEDULER_LOCK_KEY, token, _LOCK_TTL):
        holder = cache.get(_SCHEDULER_LOCK_KEY)
        logger.info("Scheduler leader lock held by %s — this worker (%s) will NOT start a scheduler.",
                    holder, token)
        return
    _leader_token = token
    logger.info("Acquired scheduler leader lock (%s) — starting the single scheduler.", token)

    scheduler = BackgroundScheduler(
        job_defaults={"coalesce": True, "max_instances": 1, "misfire_grace_time": 900}
    )

    scheduler.add_jobstore(DjangoJobStore(), "default")

    # Clear any jobs persisted by a previous deploy so a changed trigger always
    # takes effect (DjangoJobStore otherwise keeps the OLD next_run_time).
    try:
        scheduler.remove_all_jobs()
        logger.info("Cleared stale jobs from DjangoJobStore before re-registering.")
    except Exception as exc:
        logger.warning("remove_all_jobs failed (continuing): %s", exc)

    # Hourly for now (stability after the 3-scheduler fix). Bump to a 10-min
    # multi-value CronTrigger once prod is confirmed stable on a single leader.
    scheduler.add_job(
        sync_cnv_customers_only,
        trigger=CronTrigger(minute="35"),
        id="cnv_customers_sync",
        max_instances=1,
        replace_existing=True,
        name="CNV Customers Sync",
    )
    logger.info("Registered job: CNV Customers Sync (hourly at :05)")

    scheduler.add_job(
        sync_cnv_orders_only,
        trigger=CronTrigger(minute="10"),
        id="cnv_orders_sync",
        max_instances=1,
        replace_existing=True,
        name="CNV Orders Sync",
    )
    logger.info("Registered job: CNV Orders Sync (hourly at :10)")

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
        logger.info("  [1] CNV Customers Sync - Hourly at :05")
        logger.info("  [2] CNV Orders Sync - Hourly at :10")
        logger.info("  [3] Cleanup Old Logs - Daily at 2:00 AM")
        logger.info("=" * 60)

        return scheduler

    except Exception as e:
        logger.error("Failed to start scheduler: %s", e)
        logger.exception("Full traceback:")
        raise
