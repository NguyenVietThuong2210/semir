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

logger = logging.getLogger('customer_analytics')

BATCH_SIZE = 5000


def process_customer_file(file):
    """
    OPTIMIZED: Process 100k+ customer records in batches.

    Performance improvements:
    - Batch processing (5000 rows at a time)
    - Bulk creates for new customers
    - Bulk updates for existing customers
    - Pre-fetch existing records to minimize queries
    """
    logger.info("=== START OPTIMIZED Customer Import: %s ===", file.name)
    df = read_file(file)
    df.columns = df.columns.str.strip().str.upper()
    total_rows = len(df)
    logger.info("Total rows to process: %d", total_rows)

    created = updated = 0
    errors = []

    # Process in batches
    for batch_num, batch_start in enumerate(range(0, total_rows, BATCH_SIZE), 1):
        batch_end = min(batch_start + BATCH_SIZE, total_rows)
        batch_df = df.iloc[batch_start:batch_end]
        batch_size = len(batch_df)

        logger.info(f"[Batch {batch_num}] Processing rows {batch_start+1} to {batch_end} ({batch_size} rows)")

        # Prepare batch data
        batch_creates = []
        batch_updates = {}

        # Extract VIP IDs and phones for this batch
        vip_ids_in_batch = [safe_str(row.get('VIP ID', '')) for _, row in batch_df.iterrows()]
        phones_in_batch = [safe_str(row.get('PHONE NO.', '')) for _, row in batch_df.iterrows()]

        # Pre-fetch existing customers in one query
        existing_customers = {
            (c.vip_id, c.phone): c
            for c in Customer.objects.filter(
                vip_id__in=vip_ids_in_batch,
                phone__in=phones_in_batch
            )
        }

        logger.info(f"[Batch {batch_num}] Found {len(existing_customers)} existing customers")

        # Process each row in batch
        for idx, row in batch_df.iterrows():
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
                logger.error(f"Row {row_num} error: {exc}")

        # Execute bulk operations
        with transaction.atomic():
            # Bulk create new customers
            if batch_creates:
                Customer.objects.bulk_create(batch_creates, batch_size=1000, ignore_conflicts=False)
                created += len(batch_creates)
                logger.info(f"[Batch {batch_num}] Created {len(batch_creates)} new customers")

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
                        batch_size=1000
                    )
                    updated += len(customers_to_update)
                    logger.info(f"[Batch {batch_num}] Updated {len(customers_to_update)} customers")

    logger.info("=== DONE Customer Import: created=%d updated=%d errors=%d ===",
                created, updated, len(errors))
    return {
        'created': created,
        'updated': updated,
        'errors': errors[:50],  # Return first 50 errors only
        'total_processed': created + updated
    }


def process_used_points_file(file):
    """
    Process an Excel/CSV file to update Customer.used_points and used_points_note.

    Expected columns:
        - VIP ID       (required)
        - Phone NO.    (required)
        - Used Points  (required, integer)
        - Used Points Note (optional)

    Duplicate matching: same VIP ID AND Phone  →  update both fields.
    Returns dict: { total_processed, updated, skipped, errors: [...] }
    """
    # ── Read file ────────────────────────────────────────────────
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

    with transaction.atomic():
        records = df.to_dict('records')
        for i in range(0, len(records), BATCH):
            batch = records[i:i + BATCH]
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

                    rows_updated = Customer.objects.filter(
                        vip_id=vip_id, phone=phone
                    ).update(
                        used_points=used_pts,
                        used_points_note=note or None,
                    )

                    if rows_updated:
                        updated += rows_updated
                    else:
                        skipped += 1
                        errors.append(f"Row {total_processed}: no match for VIP ID={vip_id}, Phone={phone}")

                except Exception as e:
                    errors.append(f"Row {total_processed}: {e}")
                    skipped += 1

    logger.info("=== DONE UsedPoints Import: updated=%d skipped=%d errors=%d ===",
                updated, skipped, len(errors))
    return {
        'total_processed': total_processed,
        'updated': updated,
        'skipped': skipped,
        'errors': errors,
    }
