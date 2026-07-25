"""
App/services/sale_detail_import.py

SaleDetail (HQ invoice line-item) file import.
No unique constraint — all rows in file are inserted as-is.
FK to SalesTransaction is resolved softly — null if header not yet imported.
"""
import logging

from django.db import transaction

from App.models import SaleDetail, SalesTransaction
from .file_reader import read_file, safe_str, safe_int, safe_decimal, parse_date

logger = logging.getLogger(__name__)

# Perf plan P2-08: 1700 = floor(65535 / 33 fields incl. id) with margin,
# verified on real PostgreSQL 16. Must match the bulk_create batch_size below
# — previously outer=400 < inner=1000 made the inner cap a no-op; now they're
# equal so both bound the same thing consistently.
BATCH_SIZE = 1700

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
    from decimal import Decimal, InvalidOperation
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


def process_sale_detail_file(file, progress_fn=None, df=None):
    """
    Process sale detail xlsx/csv → INSERT all rows without deduplication.
    Returns {created, skipped, errors}.

    Perf plan P3-01: `df` lets the caller pass a DataFrame already parsed
    during request-thread validation, avoiding a 2nd parse here.
    """
    logger.info("=== START Sale Detail Import: %s ===", file.name, extra={"step": "sale_detail_import"})
    if df is None:
        df = read_file(file)

    df.columns = df.columns.str.strip().str.upper()
    missing = [h for h in ("INVOICE NUMBER", "PRODUCT CODE", "SALES DATE") if h not in df.columns]
    if missing:
        raise ValueError(f"Missing required column(s): {', '.join(missing)}. Found: {list(df.columns)}")
    rename = {col: _COL_MAP[col] for col in df.columns if col in _COL_MAP}
    df = df.rename(columns=rename)

    total_rows = len(df)
    logger.info("Total rows: %d", total_rows, extra={"step": "sale_detail_import"})

    # Pre-load known invoice numbers — perf plan P2-05: scoped to invoices
    # present in THIS file only (was: full-table scan of every invoice ever
    # imported, regardless of file size). Equivalence: every `inv` tested
    # below via `inv in invoice_map` always comes from this file, so
    # narrowing the queried set to file_invoices cannot change any result —
    # it's a set intersection with the exact set membership is tested against.
    logger.info("Pre-loading SalesTransaction invoice set (scoped to file)...", extra={"step": "sale_detail_import"})
    _file_invoices = {safe_str(v) for v in df['invoice_number'].tolist()}
    _file_invoices -= {'', 'nan', 'None'}
    _ilist = list(_file_invoices)
    invoice_map = set()
    for _i in range(0, len(_ilist), 900):
        invoice_map.update(
            SalesTransaction.objects.filter(invoice_number__in=_ilist[_i:_i + 900])
                                     .values_list('invoice_number', flat=True)
        )
    logger.info("Invoice set loaded: %d entries", len(invoice_map), extra={"step": "sale_detail_import"})

    created = skipped = 0
    errors = []

    for batch_num, batch_start in enumerate(range(0, total_rows, BATCH_SIZE), 1):
        batch_end = min(batch_start + BATCH_SIZE, total_rows)
        batch_df = df.iloc[batch_start:batch_end]

        logger.info("[Batch %d] rows %d-%d", batch_num, batch_start + 1, batch_end,
                    extra={"step": "sale_detail_import"})

        to_create = []

        # Perf plan P2-06: to_dict('records') once instead of iterrows()
        # (dstructs a Series) + .to_dict() per row — same dict shape/values
        # (verified: NaN, dtype=str values round-trip identically either way).
        records = batch_df.to_dict('records')
        for idx, rec in zip(batch_df.index, records):
            row_num = idx + 2
            try:
                data = _map_row(rec)
                inv = data['invoice_number']
                pc  = data['product_code']

                if not inv or not pc or not data['sales_date']:
                    skipped += 1
                    continue

                # Soft FK: link to SalesTransaction if header exists
                data['transaction_id'] = inv if inv in invoice_map else None

                to_create.append(SaleDetail(**data))

            except Exception as exc:
                errors.append(f"Row {row_num}: {exc}")
                logger.error("Row %d error: %s", row_num, exc, extra={"step": "sale_detail_import"})

        with transaction.atomic():
            if to_create:
                SaleDetail.objects.bulk_create(to_create, batch_size=BATCH_SIZE)
                created += len(to_create)

        logger.info("[Batch %d] created=%d", batch_num, len(to_create),
                    extra={"step": "sale_detail_import"})

        if progress_fn:
            progress_fn(batch_end, total_rows)

    logger.info("=== DONE Sale Detail Import: created=%d skipped=%d errors=%d ===",
                created, skipped, len(errors), extra={"step": "sale_detail_import"})
    return {'created': created, 'skipped': skipped, 'errors': errors[:50]}
