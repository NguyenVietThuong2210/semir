"""App/views/view_utils.py — Shared helpers for all view modules."""
from datetime import datetime

from django.contrib import messages


def parse_date(val, label, request):
    """Parse 'YYYY-MM-DD' to date, adds Django message warning on failure."""
    if not val:
        return None
    try:
        return datetime.strptime(val, "%Y-%m-%d").date()
    except ValueError:
        messages.warning(request, f"Invalid {label} format")
        return None


def parse_date_silent(val):
    """Parse 'YYYY-MM-DD' to date silently — returns None on failure (no message)."""
    if not val:
        return None
    try:
        return datetime.strptime(str(val).strip(), "%Y-%m-%d").date()
    except ValueError:
        return None


def extract_date_range(request, from_key="start_date", to_key="end_date"):
    """Extract and parse date range GET params. Returns (date_from, date_to, raw_from, raw_to)."""
    raw_from = request.GET.get(from_key, "")
    raw_to = request.GET.get(to_key, "")
    return parse_date_silent(raw_from), parse_date_silent(raw_to), raw_from, raw_to


def filter_params_str(**kwargs):
    """Build a URL query-string fragment from non-empty keyword args.

    Example:
        filter_params_str(start_date='2025-01-01', end_date='', shop_group='Bala Group')
        → 'start_date=2025-01-01&shop_group=Bala+Group'
    """
    return "&".join(f"{k}={v}" for k, v in kwargs.items() if v)
