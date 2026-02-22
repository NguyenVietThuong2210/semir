"""
App/management/commands/sync_cnv.py

Django management command for manual CNV data sync.

Usage:
    python manage.py sync_cnv                    # Full incremental sync
    python manage.py sync_cnv --full             # Full sync (all data)
    python manage.py sync_cnv --customers        # Sync customers only
    python manage.py sync_cnv --orders           # Sync orders only
    python manage.py sync_cnv --start-date 2024-01-01 --end-date 2024-12-31
"""
from django.core.management.base import BaseCommand
from django.conf import settings
from datetime import datetime
import logging

from App.cnv.sync_service import CNVSyncService

logger = logging.getLogger(__name__)


class Command(BaseCommand):
    help = 'Sync customers and orders from CNV Loyalty API'
    
    def add_arguments(self, parser):
        parser.add_argument(
            '--customers',
            action='store_true',
            help='Sync customers only',
        )
        
        parser.add_argument(
            '--orders',
            action='store_true',
            help='Sync orders only',
        )
        
        parser.add_argument(
            '--full',
            action='store_true',
            help='Full sync (ignore last sync timestamp)',
        )
        
        parser.add_argument(
            '--initial',
            action='store_true',
            help='Initial sync: customers from IDs file, orders from June 2024',
        )
        
        parser.add_argument(
            '--start-date',
            type=str,
            help='Start date for orders (YYYY-MM-DD)',
        )
        
        parser.add_argument(
            '--end-date',
            type=str,
            help='End date for orders (YYYY-MM-DD)',
        )
        
        parser.add_argument(
            '--max-pages',
            type=int,
            help='Maximum pages to fetch (for testing)',
        )
    
    def handle(self, *args, **options):
        self.stdout.write(self.style.SUCCESS('=' * 60))
        self.stdout.write(self.style.SUCCESS('CNV DATA SYNC'))
        self.stdout.write(self.style.SUCCESS('=' * 60))
        
        # Get credentials from settings
        username = settings.CNV_USERNAME
        password = settings.CNV_PASSWORD
        
        if not username or not password:
            self.stdout.write(
                self.style.ERROR('[ERROR] CNV credentials not configured in settings.py')
            )
            self.stdout.write('Please set CNV_USERNAME and CNV_PASSWORD')
            return
        
        # Initialize service
        service = CNVSyncService(username, password)
        
        # Parse dates
        start_date = None
        end_date = None
        
        if options['start_date']:
            try:
                start_date = datetime.strptime(options['start_date'], '%Y-%m-%d')
                self.stdout.write(f"Start date: {start_date}")
            except ValueError:
                self.stdout.write(
                    self.style.ERROR(f"Invalid start date: {options['start_date']}")
                )
                return
        
        if options['end_date']:
            try:
                end_date = datetime.strptime(options['end_date'], '%Y-%m-%d')
                self.stdout.write(f"End date: {end_date}")
            except ValueError:
                self.stdout.write(
                    self.style.ERROR(f"Invalid end date: {options['end_date']}")
                )
                return
        
        # Determine sync mode
        incremental = not options['full']
        max_pages = options['max_pages']
        
        if options['full']:
            self.stdout.write(self.style.WARNING('Running FULL sync (all data)'))
        else:
            self.stdout.write('Running incremental sync (only changes)')
        
        if max_pages:
            self.stdout.write(self.style.WARNING(f'Limited to {max_pages} pages (testing mode)'))
        
        try:
            # Check if initial sync requested
            if options['initial']:
                self.stdout.write(self.style.WARNING('Running INITIAL sync'))
                
                if options['customers']:
                    # Initial sync: customers from IDs file
                    self.stdout.write(self.style.SUCCESS('\n[SYNC] INITIAL SYNC: Reading customer IDs from file...'))
                    created, updated, failed = service.initial_sync_customers_from_ids()
                    
                    self.stdout.write(self.style.SUCCESS('\n[OK] INITIAL CUSTOMERS SYNC COMPLETED'))
                    self.stdout.write(f'  Created: {created}')
                    self.stdout.write(f'  Updated: {updated}')
                    self.stdout.write(f'  Failed: {failed}')
                
                if options['orders']:
                    # Initial sync: orders from June 2024 by month
                    self.stdout.write(self.style.SUCCESS('\n[SYNC] INITIAL SYNC: Scanning orders from June 2024...'))
                    created, updated, failed = service.initial_sync_orders_by_month()
                    
                    self.stdout.write(self.style.SUCCESS('\n[OK] INITIAL ORDERS SYNC COMPLETED'))
                    self.stdout.write(f'  Created: {created}')
                    self.stdout.write(f'  Updated: {updated}')
                    self.stdout.write(f'  Failed: {failed}')
                
                self.stdout.write(self.style.SUCCESS('\n' + '=' * 60))
                return
            
            # Normal sync based on options
            if options['customers']:
                # Customers only
                self.stdout.write(self.style.SUCCESS('\n[SYNC] Syncing CUSTOMERS...'))
                created, updated, failed = service.sync_customers(
                    incremental=incremental,
                    max_pages=max_pages
                )
                
                self.stdout.write(self.style.SUCCESS('\n[OK] CUSTOMERS SYNC COMPLETED'))
                self.stdout.write(f'  Created: {created}')
                self.stdout.write(f'  Updated: {updated}')
                self.stdout.write(f'  Failed: {failed}')
                
            elif options['orders']:
                # Orders only
                self.stdout.write(self.style.SUCCESS('\n[SYNC] Syncing ORDERS...'))
                created, updated, failed = service.sync_orders(
                    incremental=incremental,
                    start_date=start_date,
                    end_date=end_date,
                    max_pages=max_pages
                )
                
                self.stdout.write(self.style.SUCCESS('\n[OK] ORDERS SYNC COMPLETED'))
                self.stdout.write(f'  Created: {created}')
                self.stdout.write(f'  Updated: {updated}')
                self.stdout.write(f'  Failed: {failed}')
                
            else:
                # Full sync (both)
                self.stdout.write(self.style.SUCCESS('\n[SYNC] Syncing CUSTOMERS & ORDERS...'))
                results = service.sync_all(
                    incremental=incremental,
                    max_pages=max_pages
                )
                
                self.stdout.write(self.style.SUCCESS('\n[OK] FULL SYNC COMPLETED'))
                self.stdout.write('\nCustomers:')
                self.stdout.write(f"  Created: {results['customers']['created']}")
                self.stdout.write(f"  Updated: {results['customers']['updated']}")
                self.stdout.write(f"  Failed: {results['customers']['failed']}")
                
                self.stdout.write('\nOrders:')
                self.stdout.write(f"  Created: {results['orders']['created']}")
                self.stdout.write(f"  Updated: {results['orders']['updated']}")
                self.stdout.write(f"  Failed: {results['orders']['failed']}")
            
            self.stdout.write(self.style.SUCCESS('\n' + '=' * 60))
            
        except Exception as e:
            self.stdout.write(
                self.style.ERROR(f'\n[ERROR] Sync failed: {e}')
            )
            logger.error('Sync failed', exc_info=True)
            raise