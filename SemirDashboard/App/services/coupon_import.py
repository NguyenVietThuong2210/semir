"""
App/services/coupon_import.py

Coupon file import.
Moved from App/utils.py.
"""
import logging

import pandas as pd
from django.db import transaction

from App.models import Coupon
from .file_reader import parse_date, safe_str

logger = logging.getLogger(__name__)

BATCH_SIZE = 5000


def process_coupon_file(file, progress_fn=None, df=None):
    """
    OPTIMIZED: Process coupons in batches.

    Perf plan P3-01: `df` lets the caller pass a DataFrame already parsed
    during request-thread validation, avoiding a 2nd parse here.
    """
    logger.info("=== START OPTIMIZED Coupon Import: %s ===", file.name, extra={"step": "coupon_import"})

    if df is None:
        # dtype=str (U-03): numeric coupon IDs must not become "123....0" floats
        if file.name.lower().endswith('.csv'):
            df = pd.read_csv(file, dtype=str)
        else:
            df = pd.read_excel(file, dtype=str)

    # Strip header whitespace (U-07) — keep the view-level check and this one consistent
    df.columns = [str(c).strip() for c in df.columns]

    total_rows = len(df)
    logger.info("Raw columns: %s  Rows: %d", list(df.columns), total_rows)
    if "Coupon ID" not in df.columns:
        raise ValueError(f"Missing required column: 'Coupon ID'. Found: {list(df.columns)}")

    # Column mapping
    COL_MAP = {
        'Department': 'department',
        'Creator': 'creator',
        'Document Number': 'document_number',
        'Coupon ID': 'coupon_id',
        'Face Value': 'face_value',
        'Used': 'used',
        'Begin Date': 'begin_date',
        'End Date': 'end_date',
        'Using Shop': 'using_shop',
        'Using Date': 'using_date',
        'Do You Want To Push?': 'push',
        'Member ID': 'member_id',
        'Member Name': 'member_name',
        'Member Phone': 'member_phone',
        'Docket Number': 'docket_number',
    }
    mapped = {k: v for k, v in COL_MAP.items() if k in df.columns}
    df.rename(columns=mapped, inplace=True)

    # Drop duplicate columns
    drop_cols = [c for c in df.columns if c == 'Coupon ID.1']
    if drop_cols:
        df.drop(columns=drop_cols, inplace=True)

    created = updated = 0
    errors = []  # U-09: per-row error details, matching all other import services

    # Process in batches
    for batch_num, batch_start in enumerate(range(0, total_rows, BATCH_SIZE), 1):
        batch_end = min(batch_start + BATCH_SIZE, total_rows)
        batch_df = df.iloc[batch_start:batch_end]

        logger.info("[Batch %d] rows %d-%d", batch_num, batch_start + 1, batch_end)

        batch_creates = []
        batch_updates = {}

        # Extract coupon IDs
        coupon_ids_in_batch = [safe_str(row.get('coupon_id', '')) for _, row in batch_df.iterrows()]
        coupon_ids_in_batch = [c for c in coupon_ids_in_batch if c and c not in ('nan', 'None', '')]

        # Pre-fetch existing coupons
        existing_coupons = {
            c.coupon_id: c
            for c in Coupon.objects.filter(coupon_id__in=coupon_ids_in_batch)
        }

        # Process each row
        seen_in_batch = set()  # U-05: dedup within batch so `created` counter is accurate
        for idx, row in batch_df.iterrows():
            cid = safe_str(row.get('coupon_id', ''))
            if not cid or cid in ('nan', 'None', ''):
                errors.append(f"Row {idx + 2}: empty coupon_id")
                continue

            try:
                used_val = int(float(str(row.get('used', 0)).strip() or '0'))
            except (ValueError, TypeError):
                used_val = 0

            try:
                fv_raw = row.get('face_value')
                fv = float(fv_raw) if fv_raw is not None and not pd.isna(fv_raw) else None
            except (ValueError, TypeError):
                fv = None

            def _s(col):
                v = safe_str(row.get(col, ''))
                return v if v not in ('nan', 'None', '') else None

            try:
                coupon_data = {
                    'coupon_id': cid,
                    'department': _s('department'),
                    'creator': _s('creator'),
                    'document_number': _s('document_number'),
                    'face_value': fv,
                    'used': used_val,
                    'begin_date': parse_date(row.get('begin_date')),
                    'end_date': parse_date(row.get('end_date')),
                    'using_shop': _s('using_shop'),
                    'using_date': parse_date(row.get('using_date')),
                    'push': _s('push'),
                    'member_id': _s('member_id'),
                    'member_name': _s('member_name'),
                    'member_phone': _s('member_phone'),
                    'docket_number': _s('docket_number'),
                }

                if cid in existing_coupons:
                    batch_updates[cid] = coupon_data
                elif cid in seen_in_batch:
                    # U-04/U-05: same coupon_id twice in one batch — last row wins,
                    # replace the pending create instead of inserting a duplicate
                    batch_creates = [c for c in batch_creates if c.coupon_id != cid]
                    batch_creates.append(Coupon(**coupon_data))
                else:
                    seen_in_batch.add(cid)
                    batch_creates.append(Coupon(**coupon_data))

            except Exception as exc:
                errors.append(f"coupon_id={cid}: {exc}")
                logger.error("coupon %s error: %s", cid, exc)

        # Execute bulk operations
        with transaction.atomic():
            if batch_creates:
                # 2026-07-26: reverted from 3000 to 1000 (uniform across all
                # upload types — see customer_import.py for the OOM incident this fixes)
                Coupon.objects.bulk_create(batch_creates, batch_size=1000, ignore_conflicts=True)
                created += len(batch_creates)
                logger.info("[Batch %d] created=%d", batch_num, len(batch_creates))

            if batch_updates:
                coupons_to_update = []
                for cid, data in batch_updates.items():
                    coupon = existing_coupons[cid]
                    for field, value in data.items():
                        if field != 'coupon_id':
                            setattr(coupon, field, value)
                    coupons_to_update.append(coupon)

                if coupons_to_update:
                    Coupon.objects.bulk_update(
                        coupons_to_update,
                        fields=['department', 'creator', 'document_number', 'face_value',
                               'used', 'begin_date', 'end_date', 'using_shop', 'using_date',
                               'push', 'member_id', 'member_name', 'member_phone', 'docket_number'],
                        # 2026-07-26: reverted from 1900 to 1000 (see bulk_create above)
                        batch_size=1000
                    )
                    updated += len(coupons_to_update)
                    logger.info("[Batch %d] updated=%d", batch_num, len(coupons_to_update))

        if progress_fn:
            progress_fn(min(batch_end, total_rows), total_rows)

    logger.info("=== DONE Coupon Import: created=%d updated=%d errors=%d ===",
                created, updated, len(errors), extra={"step": "coupon_import"})
    return {'created': created, 'updated': updated, 'errors': errors[:50]}
