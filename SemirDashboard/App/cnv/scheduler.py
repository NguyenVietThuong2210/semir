"""
App/cnv/scheduler.py

Scheduler for CNV sync jobs.
Uses CNV_USERNAME and CNV_PASSWORD from settings.
"""
import logging
from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.cron import CronTrigger
from django_apscheduler.jobstores import DjangoJobStore
from django_apscheduler.models import DjangoJobExecution
from django.conf import settings

from .sync_service import CNVSyncService

logger = logging.getLogger(__name__)


# Get credentials from settings
CNV_USERNAME = settings.CNV_USERNAME
CNV_PASSWORD = settings.CNV_PASSWORD


def sync_cnv_customers_only():
    """Sync customers only. Runs every 10 minutes at :05, :15, :25, :35, :45, :55."""
    logger.info("=" * 60)
    logger.info("STARTING CUSTOMERS SYNC JOB")
    logger.info("=" * 60)
    
    try:
        # Check if already running
        from App.models_cnv import CNVSyncLog
        running = CNVSyncLog.objects.filter(
            sync_type='customers',
            status='running'
        ).exists()
        
        if running:
            logger.warning("Customers sync already running - skipping")
            return
        
        # Check if initial sync needed (no checkpoint exists)
        has_checkpoint = CNVSyncLog.objects.filter(
            sync_type='customers',
            status='completed',
            checkpoint_updated_at__isnull=False
        ).exists()
        
        logger.info(f"CNV Username: {CNV_USERNAME}")
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
        logger.info(f"Created: {created}, Updated: {updated}, Failed: {failed}")
        logger.info("=" * 60)
        
    except Exception as e:
        logger.error("=" * 60)
        logger.error(f"CUSTOMERS SYNC FAILED: {e}")
        logger.error("=" * 60)
        logger.exception("Full traceback:")


def sync_cnv_orders_only():
    """Sync orders only. Runs every 10 minutes at :00, :10, :20, :30, :40, :50."""
    logger.info("=" * 60)
    logger.info("STARTING ORDERS SYNC JOB")
    logger.info("=" * 60)
    
    try:
        # Check if already running
        from App.models_cnv import CNVSyncLog
        running = CNVSyncLog.objects.filter(
            sync_type='orders',
            status='running'
        ).exists()
        
        if running:
            logger.warning("Orders sync already running - skipping")
            return
        
        # Check if initial sync needed (no checkpoint exists)
        has_checkpoint = CNVSyncLog.objects.filter(
            sync_type='orders',
            status='completed',
            checkpoint_updated_at__isnull=False
        ).exists()
        
        logger.info(f"CNV Username: {CNV_USERNAME}")
        logger.info("Creating sync service...")
        
        service = CNVSyncService(CNV_USERNAME, CNV_PASSWORD)
        
        if not has_checkpoint:
            logger.info("No checkpoint found - running INITIAL SYNC from June 2024 by month...")
            created, updated, failed = service.initial_sync_orders_by_month()
        else:
            logger.info("Checkpoint exists - running INCREMENTAL SYNC...")
            created, updated, failed = service.sync_orders(incremental=True)
        
        logger.info("=" * 60)
        logger.info("ORDERS SYNC COMPLETED")
        logger.info(f"Created: {created}, Updated: {updated}, Failed: {failed}")
        logger.info("=" * 60)
        
    except Exception as e:
        logger.error("=" * 60)
        logger.error(f"ORDERS SYNC FAILED: {e}")
        logger.error("=" * 60)
        logger.exception("Full traceback:")


def delete_old_job_executions(max_age=604_800):
    """Delete old job execution records (7 days)."""
    try:
        DjangoJobExecution.objects.delete_old_job_executions(max_age)
        logger.info(f"Deleted job executions older than {max_age} seconds")
    except Exception as e:
        logger.error(f"Failed to delete old job executions: {e}")


def start_scheduler():
    """
    Start APScheduler with CNV sync jobs.
    
    Note: In development mode, this may be called twice due to Django auto-reload.
    This is normal. Jobs will still only execute once due to max_instances=1.
    """
    logger.info("Initializing scheduler...")
    
    scheduler = BackgroundScheduler(
        job_defaults={
            'coalesce': True,
            'max_instances': 1,
            'misfire_grace_time': 900
        }
    )
    
    scheduler.add_jobstore(DjangoJobStore(), "default")
    
    # Customers sync every 1 hour at :5
    scheduler.add_job(
        sync_cnv_customers_only,
        trigger=CronTrigger(minute='5,15,25,35,45,55'),
        id="cnv_customers_sync",
        max_instances=1,
        replace_existing=True,
        name="CNV Customers Sync"
    )
    logger.info("Registered job: CNV Customers Sync ( every 1 hour at :05)")
    
    # Orders sync every 1 hour at :35
    scheduler.add_job(
        sync_cnv_orders_only,
        trigger=CronTrigger(minute='0,10,20,30,40,50'),
        id="cnv_orders_sync",
        max_instances=1,
        replace_existing=True,
        name="CNV Orders Sync"
    )
    logger.info("Registered job: CNV Orders Sync ( every 1 hour at :35)")
    
    # Cleanup daily at 2 AM
    scheduler.add_job(
        delete_old_job_executions,
        trigger=CronTrigger(hour=2, minute=0),
        id="delete_old_job_executions",
        max_instances=1,
        replace_existing=True,
        name="Delete Old Job Executions"
    )
    logger.info("Registered job: Delete Old Job Executions (Daily 2 AM)")
    
    try:
        logger.info("Starting scheduler...")
        scheduler.start()
        
        logger.info("=" * 60)
        logger.info("SCHEDULER STARTED SUCCESSFULLY")
        logger.info("=" * 60)
        logger.info("Scheduled jobs:")
        logger.info("  [1] CNV Customers Sync - Every 10 min at :05, :15, :25, :35, :45, :55")
        logger.info("  [2] CNV Orders Sync - Every 10 min at :00, :10, :20, :30, :40, :50")
        logger.info("  [3] Cleanup Old Logs - Daily at 2:00 AM")
        logger.info("=" * 60)
        
        return scheduler
        
    except Exception as e:
        logger.error(f"Failed to start scheduler: {e}")
        logger.exception("Full traceback:")
        raise