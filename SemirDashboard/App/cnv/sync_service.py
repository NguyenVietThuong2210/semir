"""
App/cnv/sync_service.py

Production-ready CNV data synchronization service.
Handles bi-directional sync between internal DB and CNV Loyalty API.
"""
import logging
from datetime import datetime
from decimal import Decimal
from typing import Dict, List, Optional, Tuple
from django.utils import timezone
from django.utils.dateparse import parse_datetime

from App.models_cnv import CNVCustomer, CNVOrder, CNVSyncLog
from .api_client import CNVAPIClient

logger = logging.getLogger(__name__)


class CNVSyncService:
    """
    Service for synchronizing CNV Loyalty data.
    
    Features:
    - Incremental sync (only fetch updated records)
    - Bulk operations for performance
    - Comprehensive error tracking
    - Sync history logging
    
    Usage:
        service = CNVSyncService(username="user@example.com", password="secret")
        created, updated, failed = service.sync_customers(incremental=True)
    """
    
    BATCH_SIZE = 500  # Records per database batch
    LOG_INTERVAL = 1000  # Log progress every N records
    
    def __init__(self, username: str, password: str):
        """
        Initialize sync service.
        
        Args:
            username: CNV account username/email
            password: CNV account password
        """
        self.client = CNVAPIClient(username, password)
    
    def _parse_datetime(self, dt_str: Optional[str]) -> Optional[datetime]:
        """
        Parse datetime string to timezone-aware datetime.
        
        Args:
            dt_str: ISO format datetime string
            
        Returns:
            Timezone-aware datetime or None if parsing fails
        """
        if not dt_str:
            return None
        try:
            dt = parse_datetime(dt_str)
            if dt and timezone.is_naive(dt):
                dt = timezone.make_aware(dt)
            return dt
        except Exception:
            return None
    
    def _transform_customer(self, data: Dict) -> Dict:
        """
        Transform CNV API customer data to internal model format.
        
        API Response Fields:
        - id: Customer ID (used as customer_code)
        - first_name, last_name: Name components
        - phone: Phone number
        - email: Email address
        - gender: Gender (female/male/empty)
        - points: Current loyalty points balance
        - total_points: Total points earned historically
        - created_at: Registration datetime
        - updated_at: Last update datetime
        
        Args:
            data: Raw customer dict from API
            
        Returns:
            Transformed dict matching CNVCustomer model fields
        """
        # Combine name fields
        first_name = data.get('first_name', '')
        last_name = data.get('last_name', '')
        full_name = f"{last_name} {first_name}".strip() if last_name else first_name
        
        # Use 'id' as customer_code
        customer_id = str(data.get('id', ''))
        
        return {
            'customer_code': customer_id,
            'customer_id': customer_id,
            'full_name': full_name,
            'phone': data.get('phone'),
            'email': data.get('email') or None,
            'birthday': self._parse_datetime(data.get('birthday')),
            'gender': data.get('gender') or None,
            'address': None,
            'city': None,
            'district': None,
            'ward': None,
            'membership_level': None,
            'points_balance': int(data.get('points', 0)),
            'total_points_earned': int(data.get('total_points', 0)),
            'total_points_spent': 0,
            'registration_date': self._parse_datetime(data.get('created_at')),
            'last_purchase_date': None,
            'is_active': True,
            'status': None,
            'raw_data': data,
            'last_synced_at': timezone.now(),
        }
    
    def _transform_order(self, data: Dict) -> Dict:
        """
        Transform CNV API order data to internal model format.
        
        Args:
            data: Raw order dict from API
            
        Returns:
            Transformed dict matching CNVOrder model fields
        """
        # Extract customer data
        customer = data.get('customer', {})
        
        # Get order code from different possible fields
        order_code = (
            data.get('name') or  # API returns "#103295" format
            data.get('orderCode') or 
            data.get('code') or 
            f"#{data.get('id', '')}"
        )
        
        # Get customer info from nested customer object
        customer_code = str(customer.get('id', '')) if customer else data.get('customerCode')
        customer_name = (
            f"{customer.get('first_name', '')} {customer.get('last_name', '')}".strip() 
            if customer else data.get('customerName', '')
        )
        customer_phone = customer.get('phone') if customer else data.get('customerPhone')
        
        # Parse dates - try created_at first, then orderDate
        order_date = self._parse_datetime(
            data.get('created_at') or data.get('orderDate')
        ) or timezone.now()
        
        return {
            'order_code': order_code,
            'order_id': str(data.get('id', '')),
            'customer_code': customer_code,
            'customer_name': customer_name,
            'customer_phone': customer_phone,
            'order_date': order_date,
            'order_status': data.get('financial_status') or data.get('orderStatus'),  # API uses financial_status
            'payment_status': data.get('financial_status') or data.get('paymentStatus'),
            'payment_method': data.get('paymentMethod'),
            'store_code': str(data.get('location_id', '')) if data.get('location_id') else data.get('storeCode'),
            'store_name': data.get('storeName'),
            'subtotal': Decimal(str(data.get('subtotal_price', 0))),  # API uses subtotal_price with underscore
            'discount_amount': Decimal(str(data.get('total_discounts', 0))),  # API uses total_discounts
            'tax_amount': Decimal(str(data.get('taxAmount', 0))),
            'shipping_fee': Decimal(str(data.get('shipment_fee', 0))),  # API uses shipment_fee
            'total_amount': Decimal(str(data.get('total_price', 0))),  # API uses total_price with underscore
            'points_earned': int(data.get('pointsEarned', 0)),
            'points_used': int(data.get('pointsUsed', 0)),
            'items': data.get('line_items'),  # API uses line_items
            'notes': data.get('notes'),
            'raw_data': data,
            'last_synced_at': timezone.now(),
        }
    
    def _process_customer_batch(self, batch: List[Dict]) -> Tuple[int, int, int]:
        """
        Process batch of customers using bulk operations.
        
        Strategy:
        1. Transform all records
        2. Check which customer_codes already exist
        3. Bulk create new records
        4. Bulk update existing records
        
        Args:
            batch: List of raw customer dicts from API
            
        Returns:
            Tuple of (created_count, updated_count, failed_count)
        """
        if not batch:
            return 0, 0, 0
        
        created_count = 0
        updated_count = 0
        failed_count = 0
        
        codes = []
        transformed_map = {}
        
        # Transform all customers
        for data in batch:
            try:
                transformed = self._transform_customer(data)
                code = transformed.get('customer_code')
                
                if code:
                    codes.append(code)
                    transformed_map[code] = transformed
                else:
                    logger.warning(f"Skipping customer with no ID: {data}")
                    failed_count += 1
                    
            except Exception as e:
                logger.error(f"Transform error: {e}")
                failed_count += 1
        
        if not codes:
            return 0, 0, failed_count
        
        # Check existing records
        existing_codes = set(
            CNVCustomer.objects.filter(customer_code__in=codes)
            .values_list('customer_code', flat=True)
        )
        
        # Separate new vs existing
        new_customers = []
        update_codes = []
        
        for code, data in transformed_map.items():
            if code in existing_codes:
                update_codes.append((code, data))
            else:
                new_customers.append(CNVCustomer(**data))
        
        # Bulk create new records
        if new_customers:
            try:
                CNVCustomer.objects.bulk_create(new_customers, ignore_conflicts=True)
                created_count = len(new_customers)
            except Exception as e:
                logger.error(f"Bulk create failed: {e}")
                failed_count += len(new_customers)
        
        # Update existing records
        for code, data in update_codes:
            try:
                CNVCustomer.objects.filter(customer_code=code).update(**{
                    k: v for k, v in data.items() if k != 'customer_code'
                })
                updated_count += 1
            except Exception as e:
                logger.error(f"Update failed for {code}: {e}")
                failed_count += 1
        
        return created_count, updated_count, failed_count
    
    def _process_order_batch(self, batch: List[Dict]) -> Tuple[int, int, int]:
        """
        Process batch of orders using bulk operations.
        
        Args:
            batch: List of raw order dicts from API
            
        Returns:
            Tuple of (created_count, updated_count, failed_count)
        """
        if not batch:
            return 0, 0, 0
        
        created_count = 0
        updated_count = 0
        failed_count = 0
        
        codes = []
        transformed_map = {}
        
        # Transform all orders
        for data in batch:
            try:
                transformed = self._transform_order(data)
                code = transformed.get('order_code')
                
                if code:
                    codes.append(code)
                    transformed_map[code] = transformed
                else:
                    logger.warning(f"Skipping order with no code: {data}")
                    failed_count += 1
                    
            except Exception as e:
                logger.error(f"Transform error: {e}")
                failed_count += 1
        
        if not codes:
            return 0, 0, failed_count
        
        # Check existing records
        existing_codes = set(
            CNVOrder.objects.filter(order_code__in=codes)
            .values_list('order_code', flat=True)
        )
        
        # Separate new vs existing
        new_orders = []
        update_codes = []
        
        for code, data in transformed_map.items():
            if code in existing_codes:
                update_codes.append((code, data))
            else:
                new_orders.append(CNVOrder(**data))
        
        # Bulk create new records
        if new_orders:
            try:
                CNVOrder.objects.bulk_create(new_orders, ignore_conflicts=True)
                created_count = len(new_orders)
            except Exception as e:
                logger.error(f"Bulk create failed: {e}")
                failed_count += len(new_orders)
        
        # Update existing records
        for code, data in update_codes:
            try:
                CNVOrder.objects.filter(order_code=code).update(**{
                    k: v for k, v in data.items() if k != 'order_code'
                })
                updated_count += 1
            except Exception as e:
                logger.error(f"Update failed for {code}: {e}")
                failed_count += 1
        
        return created_count, updated_count, failed_count
    
    def sync_customers(
        self,
        incremental: bool = True,
        max_pages: Optional[int] = None
    ) -> Tuple[int, int, int]:
        """
        Sync customers from CNV API (max 100 pages per run).
        
        Checkpoint strategy:
        - First sync: Fetch pages 1-100, save latest updated_at
        - Next syncs: Continue from saved checkpoint
        - Each sync processes max 10,000 records (100 pages)
        
        Args:
            incremental: If True, use checkpoint from last successful sync
            max_pages: Override max pages (for testing)
            
        Returns:
            Tuple of (created_count, updated_count, failed_count)
        """
        sync_log = CNVSyncLog.objects.create(sync_type='customers')
        
        try:
            # Get checkpoint from last successful sync
            checkpoint = None
            if incremental:
                last_sync = CNVSyncLog.objects.filter(
                    sync_type='customers',
                    status='completed',
                    checkpoint_updated_at__isnull=False
                ).order_by('-checkpoint_updated_at').first()
                
                if last_sync:
                    checkpoint = last_sync.checkpoint_updated_at
                    logger.info(f"Resuming from checkpoint: {checkpoint}")
                else:
                    logger.info("No checkpoint found - starting full sync")
            
            # Fetch data from API (max 100 pages)
            logger.info("Fetching customers from CNV API...")
            customers_data = self.client.fetch_all_customers(
                updated_since=checkpoint,
                max_pages=max_pages
            )
            
            total = len(customers_data)
            sync_log.total_records = total
            sync_log.save()
            
            if total == 0:
                logger.info("No new customers to sync")
                sync_log.mark_completed()
                return 0, 0, 0
            
            logger.info(f"Processing {total} customers...")
            
            # Process in batches - only track checkpoint from fully successful batches
            total_created = 0
            total_updated = 0
            total_failed = 0
            latest_updated_at = None
            
            for i in range(0, total, self.BATCH_SIZE):
                batch = customers_data[i:i + self.BATCH_SIZE]
                batch_size = len(batch)
                
                created, updated, failed = self._process_customer_batch(batch)
                
                total_created += created
                total_updated += updated
                total_failed += failed
                
                # Only track checkpoint if ENTIRE batch succeeded (no failures)
                if failed == 0 and (created > 0 or updated > 0):
                    # Find latest updated_at in this successful batch
                    for customer in batch:
                        customer_updated = customer.get('updated_at')
                        if customer_updated:
                            customer_dt = self._parse_datetime(customer_updated)
                            if customer_dt:
                                if not latest_updated_at or customer_dt > latest_updated_at:
                                    latest_updated_at = customer_dt
                elif failed > 0:
                    logger.warning(f"Batch had {failed} failures - checkpoint not advanced for this batch")
                
                # Log progress
                if (i + self.BATCH_SIZE) % self.LOG_INTERVAL == 0:
                    logger.info(f"  Processed {i + self.BATCH_SIZE}/{total} customers")
            
            # Save checkpoint for next sync
            if latest_updated_at:
                # Add 1 microsecond to avoid re-fetching the last record
                from datetime import timedelta
                sync_log.checkpoint_updated_at = latest_updated_at + timedelta(microseconds=1)
                logger.info(f"Checkpoint saved: {sync_log.checkpoint_updated_at}")
            elif checkpoint:
                # No successful batches, keep old checkpoint
                sync_log.checkpoint_updated_at = checkpoint
                logger.info(f"No new checkpoint - kept previous: {checkpoint}")
            
            # Update sync log
            sync_log.created_count = total_created
            sync_log.updated_count = total_updated
            sync_log.failed_count = total_failed
            sync_log.mark_completed()
            
            logger.info(
                f"Customers sync completed: "
                f"{total_created} created, {total_updated} updated, {total_failed} failed"
            )
            return total_created, total_updated, total_failed
            
        except Exception as e:
            logger.error(f"Customers sync failed: {e}", exc_info=True)
            sync_log.mark_failed(str(e))
            raise
    
    def _sync_customers_by_date_range(
        self,
        updated_since: datetime,
        updated_until: datetime
    ) -> Tuple[int, int, int]:
        """
        Sync customers for a specific date range (e.g., one day).
        Used by backfill command.
        
        Args:
            updated_since: Start of date range
            updated_until: End of date range
            
        Returns:
            Tuple of (created_count, updated_count, failed_count)
        """
        sync_log = CNVSyncLog.objects.create(sync_type='customers')
        
        try:
            logger.info(f"Syncing customers from {updated_since} to {updated_until}")
            
            # Fetch data for this date range (max 100 pages)
            customers_data = self.client.fetch_all_customers(
                updated_since=updated_since,
                max_pages=100
            )
            
            # Filter by updated_until (API might not support updated_at_to)
            if updated_until:
                customers_data = [
                    c for c in customers_data
                    if self._parse_datetime(c.get('updated_at') or c.get('created_at')) <= updated_until
                ]
            
            total = len(customers_data)
            sync_log.total_records = total
            sync_log.save()
            
            if total == 0:
                logger.info("No customers in this date range")
                sync_log.mark_completed()
                return 0, 0, 0
            
            logger.info(f"Processing {total} customers...")
            
            # Process all batches
            total_created = 0
            total_updated = 0
            total_failed = 0
            
            for i in range(0, total, self.BATCH_SIZE):
                batch = customers_data[i:i + self.BATCH_SIZE]
                created, updated, failed = self._process_customer_batch(batch)
                total_created += created
                total_updated += updated
                total_failed += failed
            
            # Save checkpoint = end of date range
            sync_log.checkpoint_updated_at = updated_until
            sync_log.created_count = total_created
            sync_log.updated_count = total_updated
            sync_log.failed_count = total_failed
            sync_log.mark_completed()
            
            logger.info(
                f"Date range sync completed: {total_created} created, "
                f"{total_updated} updated, {total_failed} failed"
            )
            return total_created, total_updated, total_failed
            
        except Exception as e:
            logger.error(f"Date range sync failed: {e}", exc_info=True)
            sync_log.mark_failed(str(e))
            raise
    
    def sync_orders(
        self,
        incremental: bool = True,
        start_date: Optional[datetime] = None,
        end_date: Optional[datetime] = None,
        max_pages: Optional[int] = None
    ) -> Tuple[int, int, int]:
        """
        Sync orders from CNV API (max 100 pages per run).
        
        Checkpoint strategy:
        - First sync: Fetch pages 1-100, save latest updated_at
        - Next syncs: Continue from saved checkpoint
        - Each sync processes max 10,000 records (100 pages)
        
        Args:
            incremental: If True, use checkpoint from last successful sync
            start_date: Filter orders from this date
            end_date: Filter orders until this date
            max_pages: Override max pages (for testing)
            
        Returns:
            Tuple of (created_count, updated_count, failed_count)
        """
        sync_log = CNVSyncLog.objects.create(sync_type='orders')
        
        try:
            # Get checkpoint from last successful sync
            checkpoint = None
            if incremental and not start_date:
                last_sync = CNVSyncLog.objects.filter(
                    sync_type='orders',
                    status='completed',
                    checkpoint_updated_at__isnull=False
                ).order_by('-checkpoint_updated_at').first()
                
                if last_sync:
                    checkpoint = last_sync.checkpoint_updated_at
                    logger.info(f"Resuming from checkpoint: {checkpoint}")
                else:
                    logger.info("No checkpoint found - starting full sync")
            
            # Fetch data from API (max 100 pages)
            logger.info("Fetching orders from CNV API...")
            orders_data = self.client.fetch_all_orders(
                start_date=start_date,
                end_date=end_date,
                updated_since=checkpoint,
                max_pages=max_pages
            )
            
            total = len(orders_data)
            sync_log.total_records = total
            sync_log.save()
            
            if total == 0:
                logger.info("No new orders to sync")
                sync_log.mark_completed()
                return 0, 0, 0
            
            logger.info(f"Processing {total} orders...")
            
            # Process in batches - only track checkpoint from fully successful batches
            total_created = 0
            total_updated = 0
            total_failed = 0
            latest_updated_at = None
            
            # DEBUG: Check if orders have updated_at field
            if orders_data:
                sample_order = orders_data[0]
                logger.info(f"Sample order keys: {list(sample_order.keys())}")
                if 'updated_at' in sample_order:
                    logger.info(f"Sample order updated_at: {sample_order.get('updated_at')}")
                else:
                    logger.warning("Orders do NOT have 'updated_at' field!")
            
            for i in range(0, total, self.BATCH_SIZE):
                batch = orders_data[i:i + self.BATCH_SIZE]
                batch_size = len(batch)
                
                created, updated, failed = self._process_order_batch(batch)
                
                total_created += created
                total_updated += updated
                total_failed += failed
                
                # Only track checkpoint if ENTIRE batch succeeded (no failures)
                if failed == 0 and (created > 0 or updated > 0):
                    # Find latest updated_at in this successful batch
                    for order in batch:
                        # Try updated_at first, fallback to created_at or order_date
                        order_updated = (
                            order.get('updated_at') or 
                            order.get('created_at') or 
                            order.get('orderDate') or
                            order.get('order_date')
                        )
                        
                        if order_updated:
                            order_dt = self._parse_datetime(order_updated)
                            if order_dt:
                                if not latest_updated_at or order_dt > latest_updated_at:
                                    latest_updated_at = order_dt
                elif failed > 0:
                    logger.warning(f"Batch had {failed} failures - checkpoint not advanced for this batch")
                
                # Log progress
                if (i + self.BATCH_SIZE) % self.LOG_INTERVAL == 0:
                    logger.info(f"  Processed {i + self.BATCH_SIZE}/{total} orders")
            
            # Save checkpoint for next sync
            logger.info(f"DEBUG: Final latest_updated_at for orders: {latest_updated_at}")
            
            if latest_updated_at:
                # Add 1 microsecond to avoid re-fetching the last record
                from datetime import timedelta
                sync_log.checkpoint_updated_at = latest_updated_at + timedelta(microseconds=1)
                logger.info(f"[OK] Orders checkpoint saved: {sync_log.checkpoint_updated_at}")
            elif checkpoint:
                # No successful batches, keep old checkpoint
                sync_log.checkpoint_updated_at = checkpoint
                logger.info(f"[WARN] No new checkpoint - kept previous: {checkpoint}")
            else:
                logger.warning(f"[ERROR] NO CHECKPOINT SAVED - orders have no updated_at field!")
            
            # Update sync log
            sync_log.created_count = total_created
            sync_log.updated_count = total_updated
            sync_log.failed_count = total_failed
            sync_log.mark_completed()
            
            logger.info(
                f"Orders sync completed: "
                f"{total_created} created, {total_updated} updated, {total_failed} failed"
            )
            return total_created, total_updated, total_failed
            
        except Exception as e:
            logger.error(f"Orders sync failed: {e}", exc_info=True)
            sync_log.mark_failed(str(e))
            raise
    
    def _sync_orders_by_date_range(
        self,
        updated_since: datetime,
        updated_until: datetime
    ) -> Tuple[int, int, int]:
        """
        Sync orders for a specific date range (e.g., one day).
        Used by backfill command.
        
        Args:
            updated_since: Start of date range
            updated_until: End of date range
            
        Returns:
            Tuple of (created_count, updated_count, failed_count)
        """
        sync_log = CNVSyncLog.objects.create(sync_type='orders')
        
        try:
            logger.info(f"Syncing orders from {updated_since} to {updated_until}")
            
            # Fetch data for this date range (max 100 pages)
            orders_data = self.client.fetch_all_orders(
                updated_since=updated_since,
                updated_until=updated_until,
                max_pages=100
            )
            
            total = len(orders_data)
            sync_log.total_records = total
            sync_log.save()
            
            if total == 0:
                logger.info("No orders in this date range")
                sync_log.mark_completed()
                return 0, 0, 0
            
            logger.info(f"Processing {total} orders...")
            
            # Process all batches
            total_created = 0
            total_updated = 0
            total_failed = 0
            
            for i in range(0, total, self.BATCH_SIZE):
                batch = orders_data[i:i + self.BATCH_SIZE]
                created, updated, failed = self._process_order_batch(batch)
                total_created += created
                total_updated += updated
                total_failed += failed
            
            # Save checkpoint = end of date range
            sync_log.checkpoint_updated_at = updated_until
            sync_log.created_count = total_created
            sync_log.updated_count = total_updated
            sync_log.failed_count = total_failed
            sync_log.mark_completed()
            
            logger.info(
                f"Date range sync completed: {total_created} created, "
                f"{total_updated} updated, {total_failed} failed"
            )
            return total_created, total_updated, total_failed
            
        except Exception as e:
            logger.error(f"Date range sync failed: {e}", exc_info=True)
            sync_log.mark_failed(str(e))
            raise

    
    def initial_sync_customers_from_ids(self) -> Tuple[int, int, int]:
        """
        Initial sync: Load customer IDs from file and fetch by IDs.
        File: App/cnv/input/customers_ids.txt (~70,000 IDs)
        Strategy: Fetch 100 IDs at a time, save all, then save latest updated_at as checkpoint.
        
        Returns:
            Tuple of (created_count, updated_count, failed_count)
        """
        import os
        from pathlib import Path
        
        sync_log = CNVSyncLog.objects.create(sync_type='customers')
        
        try:
            # Read customer IDs from file
            ids_file = Path(__file__).parent / 'input' / 'customers_ids.txt'
            
            if not ids_file.exists():
                raise FileNotFoundError(f"Customer IDs file not found: {ids_file}")
            
            logger.info(f"Reading customer IDs from: {ids_file}")
            
            with open(ids_file, 'r') as f:
                customer_ids = [int(line.strip()) for line in f if line.strip().isdigit()]
            
            logger.info(f"Loaded {len(customer_ids)} customer IDs")
            
            # Fetch customers by IDs (100 at a time)
            customers_data = self.client.fetch_customers_by_ids(customer_ids, batch_size=100)
            
            total = len(customers_data)
            sync_log.total_records = total
            sync_log.save()
            
            if total == 0:
                logger.warning("No customers returned from API")
                sync_log.mark_completed()
                return 0, 0, 0
            
            logger.info(f"Processing {total} customers...")
            
            # Process in batches
            total_created = 0
            total_updated = 0
            total_failed = 0
            latest_updated_at = None
            
            for i in range(0, total, self.BATCH_SIZE):
                batch = customers_data[i:i + self.BATCH_SIZE]
                
                created, updated, failed = self._process_customer_batch(batch)
                
                total_created += created
                total_updated += updated
                total_failed += failed
                
                # Track latest updated_at
                for customer in batch:
                    customer_updated = customer.get('updated_at') or customer.get('created_at')
                    if customer_updated:
                        customer_dt = self._parse_datetime(customer_updated)
                        if customer_dt:
                            if not latest_updated_at or customer_dt > latest_updated_at:
                                latest_updated_at = customer_dt
                
                if (i + self.BATCH_SIZE) % self.LOG_INTERVAL == 0:
                    logger.info(f"  Processed {i + self.BATCH_SIZE}/{total} customers")
            
            # Save checkpoint
            if latest_updated_at:
                from datetime import timedelta
                sync_log.checkpoint_updated_at = latest_updated_at + timedelta(microseconds=1)
                logger.info(f"[OK] Initial checkpoint saved: {sync_log.checkpoint_updated_at}")
            
            sync_log.created_count = total_created
            sync_log.updated_count = total_updated
            sync_log.failed_count = total_failed
            sync_log.mark_completed()
            
            logger.info(
                f"Initial customers sync completed: "
                f"{total_created} created, {total_updated} updated, {total_failed} failed"
            )
            return total_created, total_updated, total_failed
            
        except Exception as e:
            logger.error(f"Initial customers sync failed: {e}", exc_info=True)
            sync_log.mark_failed(str(e))
            raise
    
    def initial_sync_orders_by_month(self) -> Tuple[int, int, int]:
        """
        Initial sync: Scan orders from June 2024 to now, month by month.
        Each month: Max 100 pages. If page 1-2 is enough, stop early.
        Save latest updated_at from ALL months as checkpoint.
        
        Returns:
            Tuple of (created_count, updated_count, failed_count)
        """
        from datetime import timedelta
        from dateutil.relativedelta import relativedelta
        
        # Start from June 1, 2024
        start_date = timezone.make_aware(datetime(2024, 6, 1))
        end_date = timezone.now()
        
        logger.info(f"Initial orders sync from {start_date} to {end_date}")
        
        total_created = 0
        total_updated = 0
        total_failed = 0
        latest_updated_at = None
        
        current_month = start_date
        
        while current_month <= end_date:
            # Month range
            month_start = current_month.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
            
            # Next month start  
            next_month = month_start + relativedelta(months=1)
            if next_month > end_date:
                month_end = end_date
            else:
                month_end = next_month - timedelta(microseconds=1)
            
            logger.info(f"Syncing month: {month_start.strftime('%Y-%m')}")
            
            sync_log = CNVSyncLog.objects.create(sync_type='orders')
            
            try:
                # Fetch orders for this month (max 100 pages)
                orders_data = self.client.fetch_all_orders(
                    updated_since=month_start,
                    updated_until=month_end,
                    max_pages=100
                )
                
                total = len(orders_data)
                sync_log.total_records = total
                sync_log.save()
                
                if total == 0:
                    logger.info(f"  No orders for {month_start.strftime('%Y-%m')}")
                    sync_log.mark_completed()
                    current_month = next_month
                    continue
                
                logger.info(f"  Processing {total} orders...")
                
                # Process batches
                month_created = 0
                month_updated = 0
                month_failed = 0
                
                for i in range(0, total, self.BATCH_SIZE):
                    batch = orders_data[i:i + self.BATCH_SIZE]
                    
                    created, updated, failed = self._process_order_batch(batch)
                    
                    month_created += created
                    month_updated += updated
                    month_failed += failed
                    
                    # Track latest updated_at
                    for order in batch:
                        order_updated = (
                            order.get('updated_at') or 
                            order.get('created_at') or 
                            order.get('orderDate')
                        )
                        if order_updated:
                            order_dt = self._parse_datetime(order_updated)
                            if order_dt:
                                if not latest_updated_at or order_dt > latest_updated_at:
                                    latest_updated_at = order_dt
                
                total_created += month_created
                total_updated += month_updated
                total_failed += month_failed
                
                # Save month checkpoint
                sync_log.checkpoint_updated_at = month_end
                sync_log.created_count = month_created
                sync_log.updated_count = month_updated
                sync_log.failed_count = month_failed
                sync_log.mark_completed()
                
                logger.info(
                    f"  [OK] {month_start.strftime('%Y-%m')}: "
                    f"{month_created} created, {month_updated} updated"
                )
                
            except Exception as e:
                logger.error(f"Month {month_start.strftime('%Y-%m')} failed: {e}")
                sync_log.mark_failed(str(e))
                # Continue to next month
            
            current_month = next_month
        
        # Save final checkpoint
        if latest_updated_at:
            # Create a summary sync log with final checkpoint
            final_log = CNVSyncLog.objects.create(sync_type='orders')
            final_log.checkpoint_updated_at = latest_updated_at + timedelta(microseconds=1)
            final_log.total_records = total_created + total_updated
            final_log.created_count = total_created
            final_log.updated_count = total_updated
            final_log.failed_count = total_failed
            final_log.mark_completed()
            
            logger.info(f"[OK] Final checkpoint saved: {final_log.checkpoint_updated_at}")
        
        logger.info(
            f"Initial orders sync completed: "
            f"{total_created} created, {total_updated} updated, {total_failed} failed"
        )
        return total_created, total_updated, total_failed