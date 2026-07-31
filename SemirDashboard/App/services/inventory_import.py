"""
App/services/inventory_import.py

InventorySnapshot file import.
Upserts on unique_together (shop_id, product_code) — upload overwrites current state.
"""
import logging

from django.db import transaction

from App.models import InventorySnapshot
from .file_reader import read_file, safe_str, safe_int, safe_decimal

logger = logging.getLogger(__name__)

# 2026-07-26: reverted from 2000 to 1000 (uniform across all upload types —
# see customer_import.py for the OOM incident this fixes). This constant
# also bounds the bulk_create batch_size directly below.
BATCH_SIZE = 1000

_COL_MAP = {
    'WAREHOUSE/SHOP ID':          'shop_id',
    'WAREHOUSE/SHOP':             'shop_name',
    'BRAND':                      'brand',
    'PRODUCT CODE':               'product_code',
    'PRODUCT NAME':               'product_name',
    '商品名称':                    'product_name_vn',
    'BARCODE':                    'barcode',
    'SKU':                        'sku',
    'COLOR':                      'color',
    'SIZE':                       'size',
    'YEAR':                       'year',
    'SEASON':                     'season',
    'GENDER':                     'gender',
    'LARGE CLASS':                'category_l1',
    'MIDDLE CLASS':               'category_l2',
    'SMALL CLASS':                'category_l3',
    'TAGPRICE':                   'tag_price',
    'INVENTORY QUANTITY':         'inventory_qty',
    'IN TRANSIT QUANTITY':        'in_transit_qty',
    'TOTAL INVENTORY QUANTITY':   'total_qty',
    'TAG AMOUNT':                 'tag_amount',
    'TOTAL TAG AMOUNT':           'total_tag_amount',
    'CURRENCY':                   'currency',
}


def _parse_year(val):
    try:
        y = int(float(str(val).strip()))
        return y if 1990 < y < 2100 else None
    except (ValueError, TypeError):
        return None


def _map_row(row):
    return {
        'shop_id':         safe_str(row.get('shop_id', '')),
        'shop_name':       safe_str(row.get('shop_name', '')),
        'brand':           safe_str(row.get('brand', '')),
        'product_code':    safe_str(row.get('product_code', '')),
        'product_name':    safe_str(row.get('product_name', '')),
        'product_name_vn': safe_str(row.get('product_name_vn', '')),
        'barcode':         safe_str(row.get('barcode', '')),
        'sku':             safe_str(row.get('sku', '')),
        'color':           safe_str(row.get('color', '')),
        'size':            safe_str(row.get('size', '')),
        'year':            _parse_year(row.get('year')),
        'season':          safe_str(row.get('season', '')),
        'gender':          safe_str(row.get('gender', '')),
        'category_l1':     safe_str(row.get('category_l1', '')),
        'category_l2':     safe_str(row.get('category_l2', '')),
        'category_l3':     safe_str(row.get('category_l3', '')),
        'tag_price':       safe_decimal(row.get('tag_price', 0)),
        'inventory_qty':   safe_int(row.get('inventory_qty', 0)),
        'in_transit_qty':  safe_int(row.get('in_transit_qty', 0)),
        'total_qty':       safe_int(row.get('total_qty', 0)),
        'tag_amount':      safe_decimal(row.get('tag_amount', 0)),
        'total_tag_amount': safe_decimal(row.get('total_tag_amount', 0)),
        'currency':        safe_str(row.get('currency', 'VND')) or 'VND',
    }


def process_inventory_file(file, progress_fn=None, df=None):
    """
    Process inventory xlsx/csv → TRUNCATE existing data, then INSERT all rows.
    Each upload replaces the entire inventory snapshot.
    Returns {created, deleted, skipped, errors}.

    Perf plan P3-01: `df` lets the caller pass a DataFrame already parsed
    during request-thread validation, avoiding a 2nd parse here.
    """
    logger.info("=== START Inventory Import (truncate+replace): %s ===", file.name,
                extra={"step": "inventory_import"})
    if df is None:
        df = read_file(file)

    # Normalize headers: strip + upper, then remap via _COL_MAP
    df.columns = df.columns.str.strip().str.upper()
    missing = [h for h in ("WAREHOUSE/SHOP ID", "PRODUCT CODE") if h not in df.columns]
    if missing:
        raise ValueError(f"Missing required column(s): {', '.join(missing)}. Found: {list(df.columns)}")
    rename = {col: _COL_MAP[col] for col in df.columns if col in _COL_MAP}
    df = df.rename(columns=rename)

    total_rows = len(df)
    logger.info("Total rows: %d", total_rows, extra={"step": "inventory_import"})

    # Parse all rows first — abort if too many errors before touching the DB
    to_create = []
    skipped = 0
    errors = []
    seen_keys = set()

    # Perf plan P2-06: to_dict('records') once instead of iterrows() +
    # .to_dict() per row — identical dict shape/values (NaN, dtype=str
    # values round-trip the same either way).
    _records = df.to_dict('records')
    for idx, rec in zip(df.index, _records):
        row_num = idx + 2
        try:
            data = _map_row(rec)
            shop_id = data['shop_id']
            product_code = data['product_code']

            if not shop_id or not product_code:
                skipped += 1
                continue

            key = (shop_id, product_code)
            if key in seen_keys:
                skipped += 1
                continue
            seen_keys.add(key)
            to_create.append(InventorySnapshot(**data))

        except Exception as exc:
            errors.append(f"Row {row_num}: {exc}")
            logger.error("Row %d error: %s", row_num, exc, extra={"step": "inventory_import"})

    # Guard (U-01): never truncate when the file produced zero valid rows —
    # a bad file must not wipe the existing snapshot.
    if not to_create:
        raise ValueError(
            f"No valid rows to import (skipped={skipped}, errors={len(errors)}). "
            "Existing inventory NOT modified."
        )

    # Truncate old data and insert new in a single atomic transaction
    deleted = 0
    created = 0
    with transaction.atomic():
        deleted, _ = InventorySnapshot.objects.all().delete()
        logger.info("Truncated %d existing rows", deleted, extra={"step": "inventory_import"})

        for batch_start in range(0, len(to_create), BATCH_SIZE):
            batch = to_create[batch_start:batch_start + BATCH_SIZE]
            batch_num = batch_start // BATCH_SIZE + 1
            InventorySnapshot.objects.bulk_create(batch, batch_size=BATCH_SIZE)
            created += len(batch)
            logger.info("[Batch %d] inserted %d rows", batch_num, len(batch),
                        extra={"step": "inventory_import"})
            if progress_fn:
                progress_fn(min(batch_start + BATCH_SIZE, len(to_create)), len(to_create))

    logger.info("=== DONE Inventory Import: deleted=%d created=%d skipped=%d errors=%d ===",
                deleted, created, skipped, len(errors), extra={"step": "inventory_import"})
    return {'created': created, 'deleted': deleted, 'skipped': skipped, 'errors': errors[:50]}
