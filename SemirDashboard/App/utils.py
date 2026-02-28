"""
utils.py  --  v3.0 - OPTIMIZED FOR LARGE FILES (100k+ records)

Key improvements:
1. Batch processing (5000 records at a time)
2. Bulk create/update operations
3. Pre-loading related data
4. Progress logging
5. Reduced database queries from 100k to ~20
"""
import logging
from datetime import datetime
from decimal import Decimal, InvalidOperation

import pandas as pd
from django.db import transaction

from .models import Customer, SalesTransaction, Coupon

logger = logging.getLogger('customer_analytics')

# Batch size for processing
BATCH_SIZE = 5000


def read_file(file):
    logger.debug("read_file: %s", file.name)
    if file.name.lower().endswith('.csv'):
        df = pd.read_csv(file)
    else:
        df = pd.read_excel(file)
    logger.debug("read_file shape: %s", df.shape)
    return df


def parse_date(value):
    """Parse a date from a pandas cell."""
    if value is None:
        return None
    try:
        if pd.isna(value):
            return None
    except (TypeError, ValueError):
        pass
    if hasattr(value, 'date') and callable(value.date):
        try:
            return value.date()
        except Exception:
            pass
    if hasattr(value, 'to_pydatetime'):
        try:
            return value.to_pydatetime().date()
        except Exception:
            pass
    raw = str(value).strip()
    if not raw or raw in ('nan', 'None', 'NaT', ''):
        return None
    for fmt in ('%Y-%m-%d', '%Y-%m-%d %H:%M:%S', '%d/%m/%Y',
                '%m/%d/%Y', '%d-%m-%Y', '%Y/%m/%d'):
        try:
            return datetime.strptime(raw.split('.')[0].strip(), fmt).date()
        except ValueError:
            continue
    try:
        return pd.to_datetime(raw).date()
    except Exception:
        pass
    return None


def safe_decimal(value, default=0):
    try:
        if pd.isna(value):
            return Decimal(default)
    except (TypeError, ValueError):
        pass
    try:
        return Decimal(str(value))
    except (InvalidOperation, TypeError):
        return Decimal(default)


def safe_int(value, default=0):
    try:
        if pd.isna(value):
            return default
    except (TypeError, ValueError):
        pass
    try:
        return int(value)
    except (ValueError, TypeError):
        return default


def safe_str(value):
    try:
        if pd.isna(value):
            return ''
    except (TypeError, ValueError):
        pass
    return str(value).strip()


# ============================================================================
# OPTIMIZED: Customer Import with Batch Processing
# ============================================================================

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


# ============================================================================
# OPTIMIZED: Sales Import with Batch Processing
# ============================================================================

def process_sales_file(file):
    """
    OPTIMIZED: Process 100k+ sales records in batches.
    """
    logger.info("=== START OPTIMIZED Sales Import: %s ===", file.name)
    df = read_file(file)
    df.columns = df.columns.str.strip().str.upper()
    total_rows = len(df)
    logger.info("Total rows to process: %d", total_rows)

    # Pre-load ALL customers once (more efficient than batch queries)
    logger.info("Pre-loading customer map...")
    customer_map = {c.vip_id: c for c in Customer.objects.only('id', 'vip_id')}
    logger.info(f"Loaded {len(customer_map)} customers")

    created = updated = 0
    errors = []

    # Process in batches
    for batch_num, batch_start in enumerate(range(0, total_rows, BATCH_SIZE), 1):
        batch_end = min(batch_start + BATCH_SIZE, total_rows)
        batch_df = df.iloc[batch_start:batch_end]
        batch_size = len(batch_df)
        
        logger.info(f"[Batch {batch_num}] Processing rows {batch_start+1} to {batch_end} ({batch_size} rows)")
        
        batch_creates = []
        batch_updates = {}
        
        # Extract invoice numbers for this batch
        invoices_in_batch = [safe_str(row.get('INVOICE NUMBER', '')) for _, row in batch_df.iterrows()]
        
        # Pre-fetch existing transactions
        existing_invoices = {
            t.invoice_number: t 
            for t in SalesTransaction.objects.filter(invoice_number__in=invoices_in_batch)
        }
        
        logger.info(f"[Batch {batch_num}] Found {len(existing_invoices)} existing transactions")
        
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
                logger.error(f"Row {row_num} error: {exc}")
        
        # Execute bulk operations
        with transaction.atomic():
            # Bulk create new transactions
            if batch_creates:
                SalesTransaction.objects.bulk_create(batch_creates, batch_size=1000, ignore_conflicts=False)
                created += len(batch_creates)
                logger.info(f"[Batch {batch_num}] Created {len(batch_creates)} new transactions")
            
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
                    logger.info(f"[Batch {batch_num}] Updated {len(transactions_to_update)} transactions")

    logger.info("=== DONE Sales Import: created=%d updated=%d errors=%d ===",
                created, updated, len(errors))
    return {
        'created': created,
        'updated': updated,
        'skipped': 0,
        'errors': errors[:50]
    }


# ============================================================================
# OPTIMIZED: Coupon Import with Batch Processing
# ============================================================================

def process_coupon_file(file):
    """
    OPTIMIZED: Process coupons in batches.
    """
    logger.info("=== START OPTIMIZED Coupon Import: %s ===", file.name)

    if file.name.lower().endswith('.csv'):
        df = pd.read_csv(file)
    else:
        df = pd.read_excel(file)

    total_rows = len(df)
    logger.info("Raw columns: %s  Rows: %d", list(df.columns), total_rows)

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

    created = updated = errors = 0

    # Process in batches
    for batch_num, batch_start in enumerate(range(0, total_rows, BATCH_SIZE), 1):
        batch_end = min(batch_start + BATCH_SIZE, total_rows)
        batch_df = df.iloc[batch_start:batch_end]
        
        logger.info(f"[Batch {batch_num}] Processing rows {batch_start+1} to {batch_end}")
        
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
        for idx, row in batch_df.iterrows():
            cid = safe_str(row.get('coupon_id', ''))
            if not cid or cid in ('nan', 'None', ''):
                errors += 1
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
                else:
                    batch_creates.append(Coupon(**coupon_data))
                    
            except Exception as exc:
                errors += 1
                logger.error(f"Coupon {cid} error: {exc}")

        # Execute bulk operations
        with transaction.atomic():
            if batch_creates:
                Coupon.objects.bulk_create(batch_creates, batch_size=1000, ignore_conflicts=False)
                created += len(batch_creates)
                logger.info(f"[Batch {batch_num}] Created {len(batch_creates)} coupons")
            
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
                        batch_size=1000
                    )
                    updated += len(coupons_to_update)
                    logger.info(f"[Batch {batch_num}] Updated {len(coupons_to_update)} coupons")

    logger.info("=== DONE Coupon Import: created=%d updated=%d errors=%d ===",
                created, updated, errors)
    return {'created': created, 'updated': updated, 'errors': errors}

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
    import io
    import pandas as pd
    from django.db import transaction

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