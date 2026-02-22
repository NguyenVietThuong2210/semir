"""
App/apps.py

CORRECTED: Safe argv checking to prevent IndexError.
"""
from django.apps import AppConfig
import logging
import sys

logger = logging.getLogger(__name__)


class AppConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'App'
    
    def ready(self):
        """
        Called when Django starts.
        Auto-start CNV sync scheduler in production.
        """
        # Safe check for runserver or gunicorn
        should_start_scheduler = False
        
        if 'runserver' in sys.argv:
            should_start_scheduler = True
        elif sys.argv and len(sys.argv) > 0:
            # Check if gunicorn (safely)
            if 'gunicorn' in sys.argv[0]:
                should_start_scheduler = True
        
        if should_start_scheduler:
            try:
                from App.cnv.scheduler import start_scheduler
                logger.info("Starting CNV sync scheduler...")
                start_scheduler()
                logger.info("CNV sync scheduler started successfully")
            except Exception as e:
                logger.error(f"Failed to start CNV scheduler: {e}", exc_info=True)
        else:
            logger.debug("Skipping scheduler start (not running server)")