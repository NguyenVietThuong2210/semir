"""App/views/view_utils.py — Shared helpers for all view modules."""
from datetime import datetime

from django.contrib import messages


def parse_date(val, label, request):
    """Parse a 'YYYY-MM-DD' string to a date object, or None on failure."""
    if not val:
        return None
    try:
        return datetime.strptime(val, "%Y-%m-%d").date()
    except ValueError:
        messages.warning(request, f"Invalid {label} format")
        return None


def filter_params_str(**kwargs):
    """Build a URL query-string fragment from non-empty keyword args.

    Example:
        filter_params_str(start_date='2025-01-01', end_date='', shop_group='Bala Group')
        → 'start_date=2025-01-01&shop_group=Bala+Group'
    """
    return "&".join(f"{k}={v}" for k, v in kwargs.items() if v)
