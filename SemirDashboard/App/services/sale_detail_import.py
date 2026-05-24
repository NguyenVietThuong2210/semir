"""
App/services/sale_detail_import.py

SaleDetail (HQ invoice line-item) file import.
Upserts on unique_together (invoice_number, product_code).
FK to SalesTransaction is resolved softly — null if header not yet imported.
"""
import logging
from decimal import Decimal, InvalidOperation

from django.db import transaction

from App.models import SaleDetail, SalesTransaction
from .file_reader import read_file, safe_str, safe_int, safe_decimal, parse_date

logger = logging.getLogger(__name__)

BATCH_SIZE = 400  # kept low: SQLite IN-clause limit is 999 variables

_COL_MAP = {
    'INVOICE NUMBER':    'invoice_number',
    'SHOP ID':           'shop_id',
    'SHOP NAME':         'shop_name',
    'SALES DATE':        'sales_date',
    'SALES TIME':        'sales_time',
    'BRAND':             'brand',
    'PRODUCT CODE':      'product_code',
    'PRODUCT NAME':      'product_name',
    'BARCODE':           'barcode',
    'PRODUCT ID':        'sku',
    'COLOR NAME':        'color',
    'SIZE NAME':         'size',
    'YEAR':              'year',
    'SEASON':            'season',
    'GENDER':            'gender',
    'LARGE CLASS':       'category_l1',
    'MIDDLE CLASS':      'category_l2',
    'SMALL CLASS':       'category_l3',
    'QUANTITY':          'quantity',
    'FACT RETAIL PRICE': 'fact_retail_price',
    'SALES AMOUNT':      'sales_amount',
    'SETTLEMENT AMOUNT': 'settlement_amount',
    'TAG PRICE':         'tag_price',
    'TAG AMOUNT':        'tag_amount',
    'DISCOUNT':          'discount_pct',
    'VAT RATE':          'vat_rate',
    'SALESMEN':          'salesmen',
    'SALESMEN CODE':     'salesmen_code',
    'PROMOTION':         'promotion',
    'CURRENCY':          'currency',
}


def _parse_year(val):
    try:
        y = int(float(str(val).strip()))
        return y if 1990 < y < 2100 else None
    except (ValueError, TypeError):
        return None


def _parse_time(val):
    """Parse 'HH:MM:SS' string → time object."""
    if val is None:
        return None
    import re
    from datetime import time as _time
    s = str(val).strip()
    m = re.match(r'^(\d{1,2}):(\d{2}):(\d{2})', s)
    if m:
        try:
            return _time(int(m.group(1)), int(m.group(2)), int(m.group(3)))
        except ValueError:
            pass
    return None


def _parse_discount_pct(val):
    """Parse '100.00%' → Decimal('1.0000'), '50.5%' → Decimal('0.5050')."""
    if val is None:
        return None
    s = str(val).strip().rstrip('%')
    try:
        return Decimal(s) / Decimal('100')
    except (InvalidOperation, ValueError):
        return None


def _map_row(row):
    return {
        'invoice_number':    safe_str(row.get('invoice_number', '')),
        'shop_id':           safe_str(row.get('shop_id', '')),
        'shop_name':         safe_str(row.get('shop_name', '')),
        'sales_date':        parse_date(row.get('sales_date')),
        'sales_time':        _parse_time(row.get('sales_time')),
        'brand':             safe_str(row.get('brand', '')),
        'product_code':      safe_str(row.get('product_code', '')),
        'product_name':      safe_str(row.get('product_name', '')),
        'barcode':           safe_str(row.get('barcode', '')),
        'sku':               safe_str(row.get('sku', '')),
        'color':             safe_str(row.get('color', '')),
        'size':              safe_str(row.get('size', '')),
        'year':              _parse_year(row.get('year')),
        'season':            safe_str(row.get('season', '')),
        'gender':            safe_str(row.get('gender', '')),
        'category_l1':       safe_str(row.get('category_l1', '')),
        'category_l2':       safe_str(row.get('category_l2', '')),
        'category_l3':       safe_str(row.get('category_l3', '')),
        'quantity':          safe_int(row.get('quantity', 0)),
        'fact_retail_price': safe_decimal(row.get('fact_retail_price', 0)),
        'sales_amount':      safe_decimal(row.get('sales_amount', 0)),
        'settlement_amount': safe_decimal(row.get('settlement_amount', 0)),
        'tag_price':         safe_decimal(row.get('tag_price', 0)),
        'tag_amount':        safe_decimal(row.get('tag_amount', 0)),
        'discount_pct':      _parse_discount_pct(row.get('discount_pct')),
        'vat_rate':          safe_str(row.get('vat_rate', '')),
        'salesmen':          safe_str(row.get('salesmen', '')),
        'salesmen_code':     safe_str(row.get('salesmen_code', '')),
        'promotion':         safe_str(row.get('promotion', '')),
        'currency':          safe_str(row.get('currency', 'VND')) or 'VND',
    }


def process_sale_detail_file(file, progress_fn=None):
    """
    Process sale detail xlsx/csv → upsert SaleDetail rows.
    FK to SalesTransaction resolved once via pre-load dict; null if header missing.
    Returns {created, updated, skipped, errors}.
    """
    logger.info("=== START Sale Detail Import: %s ===", file.name, extra={"step": "sale_detail_import"})
    df = read_file(file)

    df.columns = df.columns.str.strip().str.upper()
    rename = {col: _COL_MAP[col] for col in df.columns if col in _COL_MAP}
    df = df.rename(columns=rename)

    total_rows = len(df)
    logger.info("Total rows: %d", total_rows, extra={"step": "sale_detail_import"})

    # Pre-load known invoice numbers (one pass, avoid per-row queries)
    logger.info("Pre-loading SalesTransaction invoice set...", extra={"step": "sale_detail_import"})
    invoice_map = set(
        SalesTransaction.objects.values_list('invoice_number', flat=True)
    )
    logger.info("Invoice set loaded: %d entries", len(invoice_map), extra={"step": "sale_detail_import"})

    created = updated = skipped = 0
    errors = []

    for batch_num, batch_start in enumerate(range(0, total_rows, BATCH_SIZE), 1):
        batch_end = min(batch_start + BATCH_SIZE, total_rows)
        batch_df = df.iloc[batch_start:batch_end]

        logger.info("[Batch %d] rows %d-%d", batch_num, batch_start + 1, batch_end,
                    extra={"step": "sale_detail_import"})

        # Collect unique keys for this batch
        batch_keys = []
        for _, row in batch_df.iterrows():
            inv = safe_str(row.get('invoice_number', ''))
            pc  = safe_str(row.get('product_code', ''))
            batch_keys.append((inv, pc))

        # Pre-fetch existing SaleDetail rows
        inv_nums      = list({k[0] for k in batch_keys})
        product_codes = list({k[1] for k in batch_keys})
        existing = {
            (obj.invoice_number, obj.product_code): obj
            for obj in SaleDetail.objects.filter(
                invoice_number__in=inv_nums,
                product_code__in=product_codes,
            )
        }

        to_create = {}   # key → SaleDetail (deduplicate within batch)
        to_update = {}   # key → SaleDetail (last row wins for intra-batch duplicates)

        for idx, row in batch_df.iterrows():
            row_num = idx + 2
            try:
                data = _map_row(row.to_dict())
                inv = data['invoice_number']
                pc  = data['product_code']

                if not inv or not data['sales_date']:
                    skipped += 1
                    continue

                # Soft FK: link to SalesTransaction if header exists
                data['transaction_id'] = inv if inv in invoice_map else None
                if data['transaction_id'] is None:
                    logger.warning("No SalesTransaction for invoice %s (row %d)", inv, row_num,
                                   extra={"step": "sale_detail_import"})

                key = (inv, pc)
                if key in existing:
                    obj = existing[key]
                    for field, value in data.items():
                        if field != 'invoice_number':
                            setattr(obj, field, value)
                    to_update[key] = obj
                else:
                    # Last row wins for intra-batch duplicates
                    to_create[key] = SaleDetail(**data)

            except Exception as exc:
                errors.append(f"Row {row_num}: {exc}")
                logger.error("Row %d error: %s", row_num, exc, extra={"step": "sale_detail_import"})

        update_fields = [
            'transaction_id', 'shop_id', 'shop_name', 'sales_date', 'sales_time',
            'brand', 'product_code', 'product_name', 'barcode', 'sku', 'color', 'size',
            'year', 'season', 'gender', 'category_l1', 'category_l2', 'category_l3',
            'quantity', 'fact_retail_price', 'sales_amount', 'settlement_amount',
            'tag_price', 'tag_amount', 'discount_pct', 'vat_rate',
            'salesmen', 'salesmen_code', 'promotion', 'currency',
        ]

        create_list = list(to_create.values())
        update_list = list(to_update.values())
        with transaction.atomic():
            if create_list:
                SaleDetail.objects.bulk_create(create_list, batch_size=1000, ignore_conflicts=True)
                created += len(create_list)
            if update_list:
                SaleDetail.objects.bulk_update(update_list, fields=update_fields, batch_size=1000)
                updated += len(update_list)

        logger.info("[Batch %d] created=%d updated=%d", batch_num, len(create_list), len(update_list),
                    extra={"step": "sale_detail_import"})

        if progress_fn:
            progress_fn(batch_end, total_rows)

    logger.info("=== DONE Sale Detail Import: created=%d updated=%d skipped=%d errors=%d ===",
                created, updated, skipped, len(errors), extra={"step": "sale_detail_import"})
    return {'created': created, 'updated': updated, 'skipped': skipped, 'errors': errors[:50]}
