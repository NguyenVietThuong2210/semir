"""App/api/views/helpers.py — shared formatters, date parsing, permissions, exception handler
Split from api/views.py (R4, 2026-07-12).
"""
import logging
from datetime import datetime, timedelta

from django.db.models import Count, Q, Sum
from rest_framework import status
from rest_framework.exceptions import APIException
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.response import Response
from rest_framework.throttling import AnonRateThrottle
from rest_framework.views import APIView
from rest_framework_simplejwt.tokens import RefreshToken
from rest_framework_simplejwt.exceptions import TokenError, InvalidToken

from App.permissions import user_has_perm, PERMISSION_DEFS
from App.api.permissions import make_perm_class

logger = logging.getLogger('App')


# ── VND / % formatters (mobile app renders strings as-is) ────────────────────

def _fmt(value: float | int) -> str:
    """Format number with thousands commas. e.g. 1234567 → '1,234,567'"""
    try:
        return f"{int(round(value)):,}"
    except (TypeError, ValueError):
        return "0"


def _fmtd(value: float, decimals: int = 2) -> str:
    """Format decimal with fixed precision."""
    try:
        return f"{float(value):.{decimals}f}"
    except (TypeError, ValueError):
        return "0.00"


def _pct(value: float) -> str:
    """Format as percentage string without % sign (for KPI objects)."""
    return _fmtd(value, 2)


def _pct_cell(value: float) -> str:
    """Format as percentage string with % sign (for table cells)."""
    return f"{_fmtd(value, 2)}%"


# ── Custom exception handler ──────────────────────────────────────────────────

def custom_exception_handler(exc, context):
    from rest_framework.views import exception_handler
    response = exception_handler(exc, context)
    if response is not None:
        return response
    logger.exception("Unhandled API error: %s", exc)
    return Response(
        {'detail': 'An internal error occurred.'},
        status=status.HTTP_500_INTERNAL_SERVER_ERROR,
    )


# ── Auth helpers ──────────────────────────────────────────────────────────────

def _get_user_permissions(user) -> list[str]:
    """
    Return the 5 mobile permission strings the app recognises.
    Maps Django codenames → mobile API strings.
    """
    mobile_perm_map = {
        'sales.view':       'sales.view',
        'cnv.view':         'customers.view',        # mobile uses 'customers.view'
        'coupons.view':     'coupons.view',
        'shops.view':       'shop_detail.view',      # Django → mobile alias
        'customers.detail': 'customer_detail.view',  # Django → mobile alias
    }
    result = []
    for django_perm, mobile_perm in mobile_perm_map.items():
        if user_has_perm(user, django_perm):
            result.append(mobile_perm)
    return result


# ── Date param parsing ────────────────────────────────────────────────────────

def _parse_date(val: str | None, param_name: str):
    if not val:
        return None
    try:
        return datetime.strptime(val, '%Y-%m-%d').date()
    except ValueError:
        raise APIException(
            f"Invalid {param_name}: expected YYYY-MM-DD, got {val!r}",
            code=status.HTTP_400_BAD_REQUEST,
        )


# ═══════════════════════════════════════════════════════════════════════════════
# AUTH ENDPOINTS
# ═══════════════════════════════════════════════════════════════════════════════

class _LoginThrottle(AnonRateThrottle):
    scope = "login"


