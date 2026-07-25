"""
App/services/customer_import.py

Customer and used-points file import.
Moved from App/utils.py.
"""
import logging
import io

import pandas as pd
from django.db import transaction

from App.models import Customer
from .file_reader import read_file, parse_date, safe_str, safe_int

logger = logging.getLogger(__name__)

BATCH_SIZE = 5000


def process_customer_file(file, progress_fn=None, df=None):
    """
    OPTIMIZED: Process 100k+ customer records in batches.

    Performance improvements:
    - Batch processing (5000 rows at a time)
    - Bulk creates for new customers
    - Bulk updates for existing customers
    - Pre-fetch existing records to minimize queries

    Perf plan P3-01: `df` lets the caller pass a DataFrame already parsed
    during request-thread validation, avoiding a 2nd parse here.
    """
    logger.info("=== START OPTIMIZED Customer Import: %s ===", file.name, extra={"step": "customer_import"})
    if df is None:
        df = read_file(file)
    df.columns = df.columns.str.strip().str.upper()
    missing = [h for h in ("VIP ID", "PHONE NO.") if h not in df.columns]
    if missing:
        raise ValueError(f"Missing required column(s): {', '.join(missing)}. Found: {list(df.columns)}")
    total_rows = len(df)
    logger.info("Total rows to process: %d", total_rows)

    created = updated = 0
    errors = []

    # Process in batches
    for batch_num, batch_start in enumerate(range(0, total_rows, BATCH_SIZE), 1):
        batch_end = min(batch_start + BATCH_SIZE, total_rows)
        batch_df = df.iloc[batch_start:batch_end]
        batch_size = len(batch_df)

        logger.info("[Batch %d] rows %d-%d (%d rows)", batch_num, batch_start + 1, batch_end, batch_size)

        # Prepare batch data
        batch_creates = []
        batch_updates = {}

        # Perf plan P2-07: to_dict('records') once, reused for both the
        # VIP-ID/phone extraction pass and the main processing pass below
        # (was: 3 separate iterrows() passes over the same batch_df).
        records = batch_df.to_dict('records')

        # Extract VIP IDs and phones for this batch
        vip_ids_in_batch = [safe_str(rec.get('VIP ID', '')) for rec in records]
        phones_in_batch = [safe_str(rec.get('PHONE NO.', '')) for rec in records]

        # Pre-fetch existing customers in one query
        existing_customers = {
            (c.vip_id, c.phone): c
            for c in Customer.objects.filter(
                vip_id__in=vip_ids_in_batch,
                phone__in=phones_in_batch
            )
        }

        logger.info("[Batch %d] existing=%d", batch_num, len(existing_customers))

        # Process each row in batch
        for idx, row in zip(batch_df.index, records):
            row_num = idx + 2
            try:
                vip_id = safe_str(row.get('VIP ID', ''))
                phone = safe_str(row.get('PHONE NO.', ''))

                if not vip_id or not phone:
                    errors.append(f"Row {row_num}: Missing VIP ID or Phone")
                    continue

                customer_data = {
                    'vip_id': vip_id,
                    'phone': phone,
                    'id_number': safe_str(row.get('ID', '')),
                    'birthday_month': safe_int(row.get('BIRTHDAY MONTH')),
                    'vip_grade': safe_str(row.get('VIP GRADE', '')),
                    'name': safe_str(row.get('NAME', '')),
                    'race': safe_str(row.get('RACE', '')),
                    'gender': safe_str(row.get('GENDER', '')),
                    'birthday': parse_date(row.get('BIRTHDAY')),
                    'city_state': safe_str(row.get('CITY-STATE', '')),
                    'postal_code': safe_str(row.get('POSTAL CODE', '')),
                    'country': safe_str(row.get('COUNTRY', '')),
                    'email': safe_str(row.get('EMAIL', '')),
                    'contact_address': safe_str(row.get('CONTACT ADDRESS', '')),
                    'registration_store': safe_str(row.get('REGISTRATION STORE', '')),
                    'registration_date': parse_date(row.get('REGISTRATION DATE')),
                    'points': safe_int(row.get('POINTS', 0)),
                }

                key = (vip_id, phone)
                if key in existing_customers:
                    # Store for bulk update
                    batch_updates[key] = customer_data
                else:
                    # Store for bulk create
                    batch_creates.append(Customer(**customer_data))

            except Exception as exc:
                errors.append(f"Row {row_num}: {exc}")
                logger.error("row %d error: %s", row_num, exc)

        # Execute bulk operations
        with transaction.atomic():
            # Bulk create new customers
            if batch_creates:
                # 2600: floor(65535 params / 22 fields incl. id) with margin — verified on real PostgreSQL 16.
                Customer.objects.bulk_create(batch_creates, batch_size=2600, ignore_conflicts=True)
                created += len(batch_creates)
                logger.info("[Batch %d] created=%d", batch_num, len(batch_creates))

            # Bulk update existing customers
            if batch_updates:
                customers_to_update = []
                for key, data in batch_updates.items():
                    customer = existing_customers[key]
                    for field, value in data.items():
                        setattr(customer, field, value)
                    customers_to_update.append(customer)

                if customers_to_update:
                    Customer.objects.bulk_update(
                        customers_to_update,
                        fields=['id_number', 'birthday_month', 'vip_grade', 'name', 'race',
                               'gender', 'birthday', 'city_state', 'postal_code', 'country',
                               'email', 'contact_address', 'registration_store',
                               'registration_date', 'points'],
                        # 1800: bulk_update costs ~2 params/field + 1, not 1
                        # like bulk_create — floor(65535/(2*15+1)) with margin.
                        batch_size=1800
                    )
                    updated += len(customers_to_update)
                    logger.info("[Batch %d] updated=%d", batch_num, len(customers_to_update))

        if progress_fn:
            progress_fn(min(batch_end, total_rows), total_rows)

    logger.info("=== DONE Customer Import: created=%d updated=%d errors=%d ===",
                created, updated, len(errors), extra={"step": "customer_import"})
    return {
        'created': created,
        'updated': updated,
        'errors': errors[:50],  # Return first 50 errors only
        'total_processed': created + updated
    }


def process_used_points_file(file, progress_fn=None, df=None):
    """
    Process an Excel/CSV file to update Customer.used_points and used_points_note.

    Expected columns:
        - VIP ID       (required)
        - Phone NO.    (required)
        - Used Points  (required, integer)
        - Used Points Note (optional)

    Duplicate matching: same VIP ID AND Phone  →  update both fields.
    Returns dict: { total_processed, updated, skipped, errors: [...] }

    Perf plan P3-01: `df` lets the caller pass a DataFrame already parsed
    during request-thread validation, avoiding a 2nd parse here.
    """
    logger.info("=== START UsedPoints Import: %s ===", file.name, extra={"step": "used_points_import"})
    # ── Read file ────────────────────────────────────────────────
    if df is None:
        filename = file.name.lower()
        try:
            if filename.endswith('.csv'):
                df = pd.read_csv(file, dtype=str)
            else:
                df = pd.read_excel(file, dtype=str)
        except Exception as e:
            raise ValueError(f"Cannot read file: {e}")

    df.columns = [str(c).strip() for c in df.columns]
    df = df.dropna(how='all')

    # ── Column mapping ───────────────────────────────────────────
    col_map = {}
    for col in df.columns:
        cl = col.lower().replace(' ', '').replace('.', '').replace('_', '')
        if cl in ('vipid',):
            col_map['vip_id'] = col
        elif cl in ('phoneno', 'phone'):
            col_map['phone'] = col
        elif cl in ('usedpoints',):
            col_map['used_points'] = col
        elif cl in ('usedpointsnote', 'note'):
            col_map['used_points_note'] = col

    missing = [k for k in ('vip_id', 'phone', 'used_points') if k not in col_map]
    if missing:
        raise ValueError(f"Missing required columns: {missing}. Found: {list(df.columns)}")

    total_processed = 0
    updated = 0
    skipped = 0
    errors = []

    BATCH = 2000

    total_records = len(df)
    records = df.to_dict('records')

    # Perf plan P3-04: prefetch Customer objects for this batch's (vip_id,
    # phone) pairs once, then bulk_update — was: 1 UPDATE query per row.
    # `updated` counts per FILE ROW matched (not deduped) to preserve the
    # exact current semantics for duplicate rows; DB value = LAST row's data
    # via dict overwrite (each pk appears at most once in the bulk_update
    # list — required, since Django's CASE WHEN would otherwise take the
    # FIRST match for a repeated pk, the opposite of "last row wins").
    for i in range(0, len(records), BATCH):
        batch = records[i:i + BATCH]
        with transaction.atomic():           # per-batch transaction (not one giant lock)
            batch_keys = []
            parsed_rows = []
            for rec in batch:
                total_processed += 1
                try:
                    vip_id = str(rec.get(col_map['vip_id'], '') or '').strip()
                    phone  = str(rec.get(col_map['phone'], '') or '').strip()
                    pts_raw = str(rec.get(col_map['used_points'], '') or '').strip()
                    note   = str(rec.get(col_map.get('used_points_note', ''), '') or '').strip() \
                             if 'used_points_note' in col_map else ''

                    if not vip_id or not phone:
                        skipped += 1
                        continue

                    try:
                        used_pts = int(float(pts_raw)) if pts_raw else 0
                    except (ValueError, TypeError):
                        errors.append(f"Row {total_processed}: invalid used_points '{pts_raw}' for VIP {vip_id}")
                        skipped += 1
                        continue

                    batch_keys.append((vip_id, phone))
                    parsed_rows.append((total_processed, vip_id, phone, used_pts, note))

                except Exception as e:
                    errors.append(f"Row {total_processed}: {e}")
                    skipped += 1

            customer_map = {
                (c.vip_id, c.phone): c
                for c in Customer.objects.filter(
                    vip_id__in={k[0] for k in batch_keys},
                    phone__in={k[1] for k in batch_keys},
                )
            } if batch_keys else {}

            pending = {}  # (vip_id, phone) -> Customer, dict overwrite = "last row wins"
            for row_num, vip_id, phone, used_pts, note in parsed_rows:
                cust = customer_map.get((vip_id, phone))
                if cust is None:
                    skipped += 1
                    errors.append(f"Row {row_num}: no match for VIP ID={vip_id}, Phone={phone}")
                    continue
                cust.used_points = used_pts
                cust.used_points_note = note or None
                pending[(vip_id, phone)] = cust
                updated += 1  # counts per FILE ROW matched, not deduped — see comment above

            if pending:
                Customer.objects.bulk_update(
                    list(pending.values()), ['used_points', 'used_points_note'], batch_size=1800
                )

        if progress_fn:
            progress_fn(min(i + BATCH, total_records), total_records)

    logger.info("=== DONE UsedPoints Import: updated=%d skipped=%d errors=%d ===",
                updated, skipped, len(errors), extra={"step": "used_points_import"})
    return {
        'total_processed': total_processed,
        'updated': updated,
        'skipped': skipped,
        'errors': errors,
    }
