"""
App/services/sales_import.py

Sales transaction file import.
Moved from App/utils.py.
"""
import logging

import pandas as pd
from django.db import transaction

from App.models import Customer, SalesTransaction
from .file_reader import read_file, parse_date, safe_str, safe_int, safe_decimal

logger = logging.getLogger(__name__)

BATCH_SIZE = 5000


def process_sales_file(file, progress_fn=None):
    """
    OPTIMIZED: Process 100k+ sales records in batches.
    """
    logger.info("=== START OPTIMIZED Sales Import: %s ===", file.name, extra={"step": "sales_import"})
    df = read_file(file)
    df.columns = df.columns.str.strip().str.upper()
    total_rows = len(df)
    logger.info("Total rows to process: %d", total_rows)

    # Pre-load ALL customers once (more efficient than batch queries)
    logger.info("Pre-loading customer map...")
    customer_map = {c.vip_id: c for c in Customer.objects.only('id', 'vip_id')}
    logger.info("customer_map loaded: %d customers", len(customer_map))

    created = updated = 0
    errors = []

    # Process in batches
    for batch_num, batch_start in enumerate(range(0, total_rows, BATCH_SIZE), 1):
        batch_end = min(batch_start + BATCH_SIZE, total_rows)
        batch_df = df.iloc[batch_start:batch_end]
        batch_size = len(batch_df)

        logger.info("[Batch %d] rows %d-%d (%d rows)", batch_num, batch_start + 1, batch_end, batch_size)

        batch_creates = []
        batch_updates = {}

        # Extract invoice numbers for this batch
        invoices_in_batch = [safe_str(row.get('INVOICE NUMBER', '')) for _, row in batch_df.iterrows()]

        # Pre-fetch existing transactions
        existing_invoices = {
            t.invoice_number: t
            for t in SalesTransaction.objects.filter(invoice_number__in=invoices_in_batch)
        }

        logger.info("[Batch %d] existing=%d", batch_num, len(existing_invoices))

        # Process each row
        for idx, row in batch_df.iterrows():
            row_num = idx + 2
            try:
                inv = safe_str(row.get('INVOICE NUMBER', ''))
                if not inv:
                    errors.append(f"Row {row_num}: Missing Invoice Number")
                    continue

                vip_id = safe_str(row.get('VIP ID', ''))
                customer = customer_map.get(vip_id)

                sales_data = {
                    'invoice_number': inv,
                    'shop_id': safe_str(row.get('SHOP ID', '')),
                    'shop_name': safe_str(row.get('SHOP NAME', '')),
                    'country': safe_str(row.get('COUNTRY', '')),
                    'bu': safe_str(row.get('BU', '')),
                    'sales_date': parse_date(row.get('SALES DATE')),
                    'vip_id': vip_id,
                    'vip_name': safe_str(row.get('VIP NAME', '')),
                    'quantity': safe_int(row.get('QUANTITY', 0)),
                    'settlement_amount': safe_decimal(row.get('SETTLEMENT AMOUNT', 0)),
                    'sales_amount': safe_decimal(row.get('SALES AMOUNT', 0)),
                    'tag_amount': safe_decimal(row.get('TAG AMOUNT', 0)),
                    'per_customer_transaction': safe_decimal(row.get('PER CUSTOMER TRANSACTION', 0)),
                    'discount': safe_decimal(row.get('DISCOUNT', 0)),
                    'rounding': safe_decimal(row.get('ROUNDING', 0)),
                    'customer': customer,
                }

                if inv in existing_invoices:
                    batch_updates[inv] = sales_data
                else:
                    batch_creates.append(SalesTransaction(**sales_data))

            except Exception as exc:
                errors.append(f"Row {row_num}: {exc}")
                logger.error("row %d error: %s", row_num, exc)

        # Execute bulk operations
        with transaction.atomic():
            # Bulk create new transactions
            if batch_creates:
                SalesTransaction.objects.bulk_create(batch_creates, batch_size=1000, ignore_conflicts=True)
                created += len(batch_creates)
                logger.info("[Batch %d] created=%d", batch_num, len(batch_creates))

            # Bulk update existing transactions
            if batch_updates:
                transactions_to_update = []
                for inv, data in batch_updates.items():
                    trans = existing_invoices[inv]
                    for field, value in data.items():
                        if field != 'invoice_number':  # Don't update primary key
                            setattr(trans, field, value)
                    transactions_to_update.append(trans)

                if transactions_to_update:
                    SalesTransaction.objects.bulk_update(
                        transactions_to_update,
                        fields=['shop_id', 'shop_name', 'country', 'bu', 'sales_date',
                               'vip_id', 'vip_name', 'quantity', 'settlement_amount',
                               'sales_amount', 'tag_amount', 'per_customer_transaction',
                               'discount', 'rounding', 'customer'],
                        batch_size=1000
                    )
                    updated += len(transactions_to_update)
                    logger.info("[Batch %d] updated=%d", batch_num, len(transactions_to_update))

        if progress_fn:
            progress_fn(min(batch_end, total_rows), total_rows)

    logger.info("=== DONE Sales Import: created=%d updated=%d errors=%d ===",
                created, updated, len(errors), extra={"step": "sales_import"})
    return {
        'created': created,
        'updated': updated,
        'skipped': 0,
        'errors': errors[:50]
    }
