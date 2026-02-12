"""
utils.py  --  v2.6
File-import utilities for Customer, Sales and Coupon data.
* Duplicate Invoice Number -> UPDATE (overwrite), NOT skip.
* Duplicate Coupon ID      -> UPDATE (overwrite), NOT skip.
* Date columns from Excel come as Timestamp objects -- parse_date handles them.
"""
import logging
from datetime import datetime
from decimal import Decimal, InvalidOperation

import pandas as pd
from django.db import transaction

from .models import Customer, SalesTransaction, Coupon

logger = logging.getLogger('customer_analytics')


def read_file(file):
    logger.debug("read_file: %s", file.name)
    if file.name.lower().endswith('.csv'):
        df = pd.read_csv(file)
    else:
        df = pd.read_excel(file)
    logger.debug("read_file shape: %s", df.shape)
    return df


def parse_date(value):
    """
    Parse a date from a pandas cell.
    Handles: None, NaN, Timestamp, datetime, date, and string formats.
    """
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
    logger.debug("parse_date: cannot parse %r", value)
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


@transaction.atomic
def process_customer_file(file):
    """Import / overwrite customer data. Duplicate (VIP ID + Phone) -> UPDATE."""
    logger.info("START process_customer_file: %s", file.name)
    df = read_file(file)
    df.columns = df.columns.str.strip().str.upper()
    logger.info("Columns: %s  Rows: %d", list(df.columns), len(df))

    created = updated = 0
    errors = []

    for idx, row in df.iterrows():
        row_num = idx + 2
        try:
            vip_id = safe_str(row.get('VIP ID', ''))
            phone  = safe_str(row.get('PHONE NO.', ''))
            if not vip_id or not phone:
                msg = f"Row {row_num}: Missing VIP ID or Phone"
                logger.warning(msg)
                errors.append(msg)
                continue
            data = {
                'vip_id':             vip_id,
                'phone':              phone,
                'id_number':          safe_str(row.get('ID', '')),
                'birthday_month':     safe_int(row.get('BIRTHDAY MONTH')),
                'vip_grade':          safe_str(row.get('VIP GRADE', '')),
                'name':               safe_str(row.get('NAME', '')),
                'race':               safe_str(row.get('RACE', '')),
                'gender':             safe_str(row.get('GENDER', '')),
                'birthday':           parse_date(row.get('BIRTHDAY')),
                'city_state':         safe_str(row.get('CITY-STATE', '')),
                'postal_code':        safe_str(row.get('POSTAL CODE', '')),
                'country':            safe_str(row.get('COUNTRY', '')),
                'email':              safe_str(row.get('EMAIL', '')),
                'contact_address':    safe_str(row.get('CONTACT ADDRESS', '')),
                'registration_store': safe_str(row.get('REGISTRATION STORE', '')),
                'registration_date':  parse_date(row.get('REGISTRATION DATE')),
                'points':             safe_int(row.get('POINTS', 0)),
            }
            _, is_new = Customer.objects.update_or_create(
                vip_id=vip_id, phone=phone, defaults=data)
            if is_new: created += 1
            else:      updated += 1
        except Exception as exc:
            msg = f"Row {row_num}: {exc}"
            logger.error(msg, exc_info=True)
            errors.append(msg)

    logger.info("DONE customers: created=%d updated=%d errors=%d",
                created, updated, len(errors))
    return {'created': created, 'updated': updated,
            'errors': errors, 'total_processed': created + updated}


@transaction.atomic
def process_sales_file(file):
    """
    Import / overwrite sales transactions.
    Duplicate Invoice Number -> UPDATE (overwrite), NOT skip.
    """
    logger.info("START process_sales_file: %s", file.name)
    df = read_file(file)
    df.columns = df.columns.str.strip().str.upper()
    logger.info("Columns: %s  Rows: %d", list(df.columns), len(df))

    customer_map = {c.vip_id: c for c in Customer.objects.only('id', 'vip_id')}

    created = updated = 0
    errors = []

    for idx, row in df.iterrows():
        row_num = idx + 2
        try:
            inv = safe_str(row.get('INVOICE NUMBER', ''))
            if not inv:
                errors.append(f"Row {row_num}: Missing Invoice Number")
                continue
            vip_id   = safe_str(row.get('VIP ID', ''))
            customer = customer_map.get(vip_id)
            data = {
                'shop_id':                  safe_str(row.get('SHOP ID', '')),
                'shop_name':                safe_str(row.get('SHOP NAME', '')),
                'country':                  safe_str(row.get('COUNTRY', '')),
                'bu':                       safe_str(row.get('BU', '')),
                'sales_date':               parse_date(row.get('SALES DATE')),
                'vip_id':                   vip_id,
                'vip_name':                 safe_str(row.get('VIP NAME', '')),
                'quantity':                 safe_int(row.get('QUANTITY', 0)),
                'settlement_amount':        safe_decimal(row.get('SETTLEMENT AMOUNT', 0)),
                'sales_amount':             safe_decimal(row.get('SALES AMOUNT', 0)),
                'tag_amount':               safe_decimal(row.get('TAG AMOUNT', 0)),
                'per_customer_transaction': safe_decimal(row.get('PER CUSTOMER TRANSACTION', 0)),
                'discount':                 safe_decimal(row.get('DISCOUNT', 0)),
                'rounding':                 safe_decimal(row.get('ROUNDING', 0)),
                'customer':                 customer,
            }
            _, is_new = SalesTransaction.objects.update_or_create(
                invoice_number=inv, defaults=data)
            if is_new: created += 1
            else:      updated += 1
        except Exception as exc:
            errors.append(f"Row {row_num}: {exc}")
            logger.error("Row %d: %s", row_num, exc, exc_info=True)

    logger.info("DONE sales: created=%d updated=%d errors=%d",
                created, updated, len(errors))
    return {'created': created, 'updated': updated,
            'skipped': 0, 'errors': errors}


def process_coupon_file(file):
    """
    Import / overwrite coupon data from Excel or CSV.
    Duplicate Coupon ID -> UPDATE (overwrite).
    Date columns (Begin Date, End Date, Using Date) are read as Timestamp from Excel.
    Duplicate column 'Coupon ID.1' is automatically ignored.
    """
    logger.info("START process_coupon_file: %s", file.name)

    if file.name.lower().endswith('.csv'):
        df = pd.read_csv(file)
    else:
        df = pd.read_excel(file)

    logger.info("Raw columns: %s  Rows: %d", list(df.columns), len(df))

    COL_MAP = {
        'Department':           'department',
        'Creator':              'creator',
        'Document Number':      'document_number',
        'Coupon ID':            'coupon_id',
        'Face Value':           'face_value',
        'Used':                 'used',
        'Begin Date':           'begin_date',
        'End Date':             'end_date',
        'Using Shop':           'using_shop',
        'Using Date':           'using_date',
        'Do You Want To Push?': 'push',
        'Member ID':            'member_id',
        'Member Name':          'member_name',
        'Member Phone':         'member_phone',
        'Docket Number':        'docket_number',
    }
    mapped  = {k: v for k, v in COL_MAP.items() if k in df.columns}
    missing = [k for k in COL_MAP if k not in df.columns]
    df.rename(columns=mapped, inplace=True)
    if missing:
        logger.warning("Missing columns (will be NULL): %s", missing)

    # Drop duplicate 'Coupon ID.1' column if present
    drop_cols = [c for c in df.columns if c == 'Coupon ID.1']
    if drop_cols:
        df.drop(columns=drop_cols, inplace=True)
        logger.debug("Dropped duplicate column(s): %s", drop_cols)

    created = updated = errors = 0

    for idx, row in df.iterrows():
        row_num = idx + 2
        cid = safe_str(row.get('coupon_id', ''))
        if not cid or cid in ('nan', 'None', ''):
            logger.warning("Row %d: Missing Coupon ID -- skipped", row_num)
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
            _, is_new = Coupon.objects.update_or_create(
                coupon_id=cid,
                defaults={
                    'department':      _s('department'),
                    'creator':         _s('creator'),
                    'document_number': _s('document_number'),
                    'face_value':      fv,
                    'used':            used_val,
                    'begin_date':      parse_date(row.get('begin_date')),
                    'end_date':        parse_date(row.get('end_date')),
                    'using_shop':      _s('using_shop'),
                    'using_date':      parse_date(row.get('using_date')),
                    'push':            _s('push'),
                    'member_id':       _s('member_id'),
                    'member_name':     _s('member_name'),
                    'member_phone':    _s('member_phone'),
                    'docket_number':   _s('docket_number'),
                },
            )
            if is_new: created += 1
            else:      updated += 1
        except Exception as exc:
            errors += 1
            logger.error("Row %d: coupon_id=%s ERROR: %s", row_num, cid, exc, exc_info=True)

    logger.info("DONE process_coupon_file: created=%d updated=%d errors=%d",
                created, updated, errors)
    return {'created': created, 'updated': updated, 'errors': errors}