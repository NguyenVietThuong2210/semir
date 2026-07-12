"""
App/services/file_reader.py

Shared file reading and type conversion utilities.
Moved from App/utils.py.
"""
import logging
from datetime import datetime
from decimal import Decimal, InvalidOperation

import pandas as pd

logger = logging.getLogger('customer_analytics')


def read_file(file):
    """Read csv/xlsx with dtype=str (U-06): preserves leading zeros on IDs and
    prevents float artifacts on barcodes/codes. Numeric fields are converted
    downstream via safe_int/safe_decimal, dates via parse_date."""
    logger.debug("read_file: %s", file.name)
    if file.name.lower().endswith('.csv'):
        df = pd.read_csv(file, dtype=str)
    else:
        df = pd.read_excel(file, dtype=str)
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
        except (ValueError, TypeError, OverflowError):
            pass
    if hasattr(value, 'to_pydatetime'):
        try:
            return value.to_pydatetime().date()
        except (ValueError, TypeError, OverflowError):
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
    except (ValueError, OverflowError):
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
        try:
            return Decimal(str(value).strip().replace(',', ''))
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
        # String floats like "28.0" (Excel numeric cells read with dtype=str)
        # must not silently become the default (U-06 prerequisite fix)
        try:
            return int(float(str(value).strip().replace(',', '')))
        except (ValueError, TypeError):
            return default


def safe_str(value):
    try:
        if pd.isna(value):
            return ''
    except (TypeError, ValueError):
        pass
    return str(value).strip()
