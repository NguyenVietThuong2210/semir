"""
App/api/views.py — SemirPhone JSON API views (Sprint 0)

All endpoints return application/json.
Auth: JWT Bearer token required (except login/refresh/logout).
Permissions: enforced via DRF permission classes.
"""
import logging
from datetime import datetime, timedelta

from django.db.models import Count, Q, Sum
from rest_framework import status
from rest_framework.exceptions import APIException
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView
from rest_framework_simplejwt.tokens import RefreshToken
from rest_framework_simplejwt.exceptions import TokenError, InvalidToken

from App.permissions import user_has_perm, PERMISSION_DEFS
from .permissions import make_perm_class

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
    return Response(
        {'detail': str(exc)},
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
        'cnv.view':         'cnv.view',
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

class LoginView(APIView):
    """POST /api/v1/auth/token/ — Login, returns JWT pair + permissions."""
    permission_classes = [AllowAny]

    def post(self, request):
        from django.contrib.auth import authenticate
        username = request.data.get('username', '')
        password = request.data.get('password', '')

        user = authenticate(request, username=username, password=password)
        if user is None or not user.is_active:
            return Response(
                {'detail': 'No active account found with the given credentials'},
                status=status.HTTP_401_UNAUTHORIZED,
            )

        refresh = RefreshToken.for_user(user)
        access = refresh.access_token
        expires_in = int(
            (access.payload['exp'] - access.payload['iat'])
        )

        return Response({
            'access': str(access),
            'refresh': str(refresh),
            'access_expires_in': expires_in,
            'username': user.username,
            'permissions': _get_user_permissions(user),
        })


class TokenRefreshView(APIView):
    """POST /api/v1/auth/token/refresh/ — Silent JWT refresh."""
    permission_classes = [AllowAny]

    def post(self, request):
        refresh_token = request.data.get('refresh', '')
        if not refresh_token:
            return Response(
                {'detail': 'Refresh token is required'},
                status=status.HTTP_400_BAD_REQUEST,
            )
        try:
            refresh = RefreshToken(refresh_token)
            access = refresh.access_token
            expires_in = int(access.payload['exp'] - access.payload['iat'])
            return Response({
                'access': str(access),
                'access_expires_in': expires_in,
            })
        except (TokenError, InvalidToken):
            return Response(
                {'detail': 'Token is invalid or expired'},
                status=status.HTTP_401_UNAUTHORIZED,
            )


class LogoutView(APIView):
    """POST /api/v1/auth/logout/ — Revoke refresh token. Idempotent."""
    permission_classes = [IsAuthenticated]

    def post(self, request):
        refresh_token = request.data.get('refresh', '')
        try:
            token = RefreshToken(refresh_token)
            token.blacklist()
        except Exception:
            pass  # Already blacklisted or invalid — still return 205
        return Response(status=status.HTTP_205_RESET_CONTENT)


# ═══════════════════════════════════════════════════════════════════════════════
# ANALYTICS ENDPOINTS
# ═══════════════════════════════════════════════════════════════════════════════

class SalesAnalyticsView(APIView):
    """GET /api/v1/analytics/sales/"""
    permission_classes = [IsAuthenticated, make_perm_class('sales.view')]

    def get(self, request):
        from App.analytics.tab_functions import get_sales_tab

        date_from = _parse_date(request.GET.get('date_from'), 'date_from')
        date_to = _parse_date(request.GET.get('date_to'), 'date_to')
        shop_group = request.GET.get('shop_group') or None

        # Period data (grade tab also returns overview metrics)
        period_data = get_sales_tab(
            'grade', date_from=date_from, date_to=date_to, shop_group=shop_group
        )
        if period_data is None:
            return Response({'detail': 'No sales data available.'}, status=404)

        # All-time data (reuse from cache if no date filter applied)
        if date_from is None and date_to is None:
            at_data = period_data
        else:
            at_data = get_sales_tab('grade', date_from=None, date_to=None, shop_group=shop_group)
            if at_data is None:
                at_data = period_data

        # Build all_time_kpis
        at_ov = at_data['overview']
        at_invoices = at_ov.get('total_invoices_with_vip0', 0)
        at_revenue = at_ov.get('total_amount_with_vip0', 0)
        at_customers = at_ov.get('total_customers_in_db', 0)
        at_avg = round(at_revenue / at_invoices, 0) if at_invoices else 0

        all_time_kpis = {
            'total_invoices': at_invoices,
            'total_revenue': _fmt(at_revenue),
            'avg_invoice': _fmt(at_avg),
            'total_customers': at_customers,
        }

        # Build period_kpis
        ov = period_data['overview']
        pd_invoices = ov.get('total_invoices_with_vip0', 0)
        pd_revenue = ov.get('total_amount_with_vip0', 0)
        pd_avg = round(pd_revenue / pd_invoices, 0) if pd_invoices else 0
        pd_active = ov.get('active_customers', 0)
        pd_returning = ov.get('returning_customers', 0)

        period_kpis = {
            'total_invoices': pd_invoices,
            'total_revenue': _fmt(pd_revenue),
            'avg_invoice': _fmt(pd_avg),
            'returning_customers': pd_returning,
            'return_rate': _pct(ov.get('return_rate', 0)),
            'new_customers': ov.get('new_members_in_period', 0),
            'avg_visits': _fmtd(pd_invoices / pd_active if pd_active else 0),
            'new_no_invoice': max(0, ov.get('total_customers_in_db', 0) - pd_active),
        }

        # Build tabs
        tabs = {
            'by_grade': _sales_grade_table(period_data.get('by_grade', [])),
            'by_season': _sales_season_table(
                get_sales_tab('season', date_from=date_from, date_to=date_to, shop_group=shop_group)
            ),
            'by_month': _sales_month_table(
                get_sales_tab('month', date_from=date_from, date_to=date_to, shop_group=shop_group)
            ),
            'by_week': _sales_week_table(
                get_sales_tab('week', date_from=date_from, date_to=date_to, shop_group=shop_group)
            ),
            'by_shop': _sales_shop_table(
                get_sales_tab('shop', date_from=date_from, date_to=date_to, shop_group=shop_group)
            ),
        }

        return Response({
            'all_time_kpis': all_time_kpis,
            'period_kpis': period_kpis,
            'tabs': tabs,
        })


def _sales_grade_table(by_grade: list) -> dict:
    headers = ['Grade', 'Invoices', 'Revenue (VND)', 'Customers', 'Return Rate']
    rows = []
    for g in (by_grade or []):
        rows.append([
            str(g.get('grade', '')),
            _fmt(g.get('total_invoices', 0)),
            _fmt(g.get('total_amount', 0)),
            _fmt(g.get('total_customers', 0)),
            _pct_cell(g.get('return_rate', 0)),
        ])
    return {'headers': headers, 'rows': rows}


def _sales_season_table(data: dict | None) -> dict:
    headers = ['Season', 'Invoices', 'Revenue (VND)', 'Customers', 'Return Rate']
    rows = []
    if data:
        for s in data.get('by_session', []):
            rows.append([
                str(s.get('session', '')),
                _fmt(s.get('total_invoices_with_vip0', s.get('total_invoices', 0))),
                _fmt(s.get('total_amount_with_vip0', s.get('total_amount', 0))),
                _fmt(s.get('total_customers', 0)),
                _pct_cell(s.get('return_rate', 0)),
            ])
    return {'headers': headers, 'rows': rows}


def _sales_month_table(data: dict | None) -> dict:
    headers = ['Month', 'Invoices', 'Revenue (VND)', 'Customers', 'Return Rate']
    rows = []
    if data:
        for m in data.get('by_month', []):
            rows.append([
                str(m.get('month', '')),
                _fmt(m.get('total_invoices_with_vip0', m.get('total_invoices', 0))),
                _fmt(m.get('total_amount_with_vip0', m.get('total_amount', 0))),
                _fmt(m.get('total_customers', 0)),
                _pct_cell(m.get('return_rate', 0)),
            ])
    return {'headers': headers, 'rows': rows}


def _sales_week_table(data: dict | None) -> dict:
    headers = ['Week', 'Invoices', 'Revenue (VND)', 'Customers', 'Return Rate']
    rows = []
    if data:
        for w in data.get('by_week', []):
            rows.append([
                str(w.get('week_label', w.get('week', ''))),
                _fmt(w.get('total_invoices_with_vip0', w.get('total_invoices', 0))),
                _fmt(w.get('total_amount_with_vip0', w.get('total_amount', 0))),
                _fmt(w.get('total_customers', 0)),
                _pct_cell(w.get('return_rate', 0)),
            ])
    return {'headers': headers, 'rows': rows}


def _sales_shop_table(data: dict | None) -> dict:
    headers = ['Shop', 'Invoices', 'Revenue (VND)', 'Customers', 'Return Rate']
    rows = []
    if data:
        for s in data.get('by_shop', []):
            rows.append([
                str(s.get('shop_name', '')),
                _fmt(s.get('total_invoices_with_vip0', s.get('total_invoices', 0))),
                _fmt(s.get('total_amount_with_vip0', s.get('total_amount', 0))),
                _fmt(s.get('total_customers', 0)),
                _pct_cell(s.get('return_rate', 0)),
            ])
    return {'headers': headers, 'rows': rows}


class CustomerAnalyticsView(APIView):
    """GET /api/v1/analytics/customer/"""
    permission_classes = [IsAuthenticated, make_perm_class('cnv.view')]

    def get(self, request):
        from App.analytics.tab_functions import get_customer_tab, _parse_cnv_period_filter
        from App.cnv.service import compute_cnv_breakdown, get_cnv_phone_sets

        date_from_str = request.GET.get('date_from', '')
        date_to_str = request.GET.get('date_to', '')

        # Validate dates
        _parse_date(date_from_str or None, 'date_from')
        _parse_date(date_to_str or None, 'date_to')

        period_filter, _ = _parse_cnv_period_filter(date_from_str, date_to_str)
        all_time_filter = {}

        pos_phones_all, cnv_phones_all = get_cnv_phone_sets()

        # All-time breakdown
        at_bd = compute_cnv_breakdown(all_time_filter, pos_phones_all, cnv_phones_all,
                                      dims=frozenset({'shop', 'month', 'grade'}))
        # Period breakdown
        if period_filter:
            pd_bd = compute_cnv_breakdown(period_filter, pos_phones_all, cnv_phones_all,
                                          dims=frozenset({'shop', 'month', 'grade'}))
        else:
            pd_bd = at_bd

        # KPIs
        at_total_pos = len(pos_phones_all)
        at_total_cnv = len(cnv_phones_all)
        at_both = len(pos_phones_all & cnv_phones_all)
        at_pos_only = at_total_pos - at_both
        at_cnv_only = at_total_cnv - at_both

        # Period counts from breakdown summary
        pd_summary = pd_bd.get('summary', {})
        pd_new_pos = pd_summary.get('new_pos', 0)
        pd_new_cnv = pd_summary.get('new_cnv', 0)
        pd_synced = pd_summary.get('synced', 0)
        pd_active = pd_summary.get('active', 0)

        all_time_kpis = {
            'total_pos_customers': at_total_pos,
            'total_cnv_customers': at_total_cnv,
            'pos_only': at_pos_only,
            'cnv_only': at_cnv_only,
        }
        period_kpis = {
            'new_pos_customers': pd_new_pos,
            'new_cnv_customers': pd_new_cnv,
            'synced_this_period': pd_synced,
            'active_customers': pd_active,
        }

        # Registration breakdown tabs (using period data)
        reg_breakdown = {
            'by_shop': _cnv_shop_table(pd_bd.get('shop', [])),
            'by_month': _cnv_month_table(pd_bd.get('month', [])),
            'by_grade': _cnv_grade_table(pd_bd.get('grade', [])),
        }

        # Customer comparison tabs (all-time)
        customer_comparison = {
            'pos_only': _cnv_pos_only_table(at_bd),
            'cnv_only': _cnv_cnv_only_table(at_bd),
            'both': _cnv_both_table(at_bd),
        }

        return Response({
            'all_time_kpis': all_time_kpis,
            'period_kpis': period_kpis,
            'registration_breakdown': reg_breakdown,
            'customer_comparison': customer_comparison,
        })


def _cnv_shop_table(shop_data: list) -> dict:
    headers = ['Shop', 'POS Customers', 'CNV Customers', 'Synced']
    rows = [[
        str(s.get('store', s.get('shop_name', ''))),
        _fmt(s.get('pos_customers', s.get('total_pos', 0))),
        _fmt(s.get('cnv_customers', s.get('total_cnv', 0))),
        _fmt(s.get('synced', s.get('both', 0))),
    ] for s in (shop_data or [])]
    return {'headers': headers, 'rows': rows}


def _cnv_month_table(month_data: list) -> dict:
    headers = ['Month', 'POS Customers', 'CNV Customers', 'Synced']
    rows = [[
        str(m.get('month', '')),
        _fmt(m.get('pos_customers', m.get('total_pos', 0))),
        _fmt(m.get('cnv_customers', m.get('total_cnv', 0))),
        _fmt(m.get('synced', m.get('both', 0))),
    ] for m in (month_data or [])]
    return {'headers': headers, 'rows': rows}


def _cnv_grade_table(grade_data: list) -> dict:
    headers = ['Grade', 'POS Customers', 'CNV Customers', 'Synced']
    rows = [[
        str(g.get('grade', '')),
        _fmt(g.get('pos_customers', g.get('total_pos', 0))),
        _fmt(g.get('cnv_customers', g.get('total_cnv', 0))),
        _fmt(g.get('synced', g.get('both', 0))),
    ] for g in (grade_data or [])]
    return {'headers': headers, 'rows': rows}


def _cnv_pos_only_table(bd: dict) -> dict:
    headers = ['Grade', 'Customers']
    rows = [[str(g.get('grade', '')), _fmt(g.get('pos_only', 0))]
            for g in bd.get('grade', [])]
    return {'headers': headers, 'rows': rows}


def _cnv_cnv_only_table(bd: dict) -> dict:
    headers = ['Grade', 'Customers']
    rows = [[str(g.get('grade', '')), _fmt(g.get('cnv_only', 0))]
            for g in bd.get('grade', [])]
    return {'headers': headers, 'rows': rows}


def _cnv_both_table(bd: dict) -> dict:
    headers = ['Grade', 'Customers']
    rows = [[str(g.get('grade', '')), _fmt(g.get('both', 0))]
            for g in bd.get('grade', [])]
    return {'headers': headers, 'rows': rows}


class CouponAnalyticsView(APIView):
    """GET /api/v1/analytics/coupon/"""
    permission_classes = [IsAuthenticated, make_perm_class('coupons.view')]

    def get(self, request):
        from App.analytics.tab_functions import get_coupon_tab

        date_from = _parse_date(request.GET.get('date_from'), 'date_from')
        date_to = _parse_date(request.GET.get('date_to'), 'date_to')
        shop_group = request.GET.get('shop_group') or None
        prefix = request.GET.get('prefix') or None

        shop_data = get_coupon_tab('shop', date_from=date_from, date_to=date_to,
                                   coupon_id_prefix=prefix, shop_group=shop_group)
        detail_data = get_coupon_tab('detail', date_from=date_from, date_to=date_to,
                                     coupon_id_prefix=prefix, shop_group=shop_group)
        dup_data = get_coupon_tab('duplicates', date_from=date_from, date_to=date_to,
                                  coupon_id_prefix=prefix, shop_group=shop_group)

        # KPIs come from the shop tab which computes both all-time and period
        ov = shop_data or {}
        at_used = ov.get('all_time_used', 0)
        at_unused = ov.get('all_time_unused', 0)
        at_amount = ov.get('all_time_amount', 0)

        pd_used = ov.get('period_used', 0)
        pd_unused = ov.get('period_unused', 0)
        pd_amount = ov.get('period_amount', 0)

        return Response({
            'all_time_kpis': {
                'used': at_used,
                'unused': at_unused,
                'amount_vnd': _fmt(at_amount),
            },
            'period_kpis': {
                'used': pd_used,
                'unused': pd_unused,
                'amount_vnd': _fmt(pd_amount),
            },
            'tabs': {
                'by_shop': _coupon_shop_table(ov.get('by_shop', [])),
                'detail': _coupon_detail_table(detail_data or {}),
                'duplicates': _coupon_dup_table(dup_data or {}),
            },
        })


def _coupon_shop_table(shop_data: list) -> dict:
    headers = ['Shop', 'Used', 'Unused', 'Amount (VND)', 'Usage Rate']
    rows = [[
        str(s.get('shop_name', s.get('using_shop', ''))),
        _fmt(s.get('used', 0)),
        _fmt(s.get('unused', 0)),
        _fmt(s.get('amount', 0)),
        _pct_cell(s.get('usage_rate', 0)),
    ] for s in (shop_data or [])]
    return {'headers': headers, 'rows': rows}


def _coupon_detail_table(data: dict) -> dict:
    headers = ['Coupon ID', 'Status', 'Amount (VND)', 'Shop', 'Date']
    rows = [[
        str(c.get('coupon_id', '')),
        'Used' if c.get('using_date') else 'Unused',
        _fmt(c.get('amount', 0)),
        str(c.get('shop', '')),
        str(c.get('using_date', '') or '—'),
    ] for c in data.get('details', [])]
    return {'headers': headers, 'rows': rows}


def _coupon_dup_table(data: dict) -> dict:
    headers = ['Invoice', 'Count', 'Coupons']
    rows = [[
        str(d.get('invoice', '')),
        _fmt(d.get('count', 0)),
        str(d.get('coupons', '')),
    ] for d in data.get('duplicates', [])]
    return {'headers': headers, 'rows': rows}


class ShopsListView(APIView):
    """GET /api/v1/analytics/shops/ — dropdown options for Shop Detail."""
    permission_classes = [IsAuthenticated, make_perm_class('shops.view')]

    def get(self, request):
        from django.core.cache import cache
        from App.models import SalesTransaction

        cache_key = 'api_shops_list'
        shops = cache.get(cache_key)
        if shops is None:
            shops = list(
                SalesTransaction.objects
                .exclude(Q(shop_name='') | Q(shop_name__isnull=True))
                .values_list('shop_name', flat=True)
                .order_by('shop_name')
                .distinct()
            )
            cache.set(cache_key, shops, 300)

        return Response({'shops': shops})


class ShopDetailView(APIView):
    """GET /api/v1/analytics/shop-detail/?shop=<name>"""
    permission_classes = [IsAuthenticated, make_perm_class('shops.view')]

    def get(self, request):
        from App.analytics.tab_functions import (
            get_shop_detail_sales_data,
            get_shop_detail_customer_data,
            get_shop_detail_coupon_data,
        )

        shop = request.GET.get('shop', '').strip()
        if not shop:
            return Response({'detail': 'shop parameter is required'}, status=400)

        date_from = _parse_date(request.GET.get('date_from'), 'date_from')
        date_to = _parse_date(request.GET.get('date_to'), 'date_to')

        sales_data = get_shop_detail_sales_data(shop, date_from, date_to)
        if sales_data is None:
            return Response({'detail': 'Shop not found or no data.'}, status=404)

        customer_data = get_shop_detail_customer_data(
            shop,
            start_date=str(date_from) if date_from else '',
            end_date=str(date_to) if date_to else '',
        )

        coupon_data = get_shop_detail_coupon_data(shop, date_from, date_to)

        return Response({
            'shop_name': shop,
            'sales': _build_shop_sales(sales_data),
            'customer': _build_shop_customer(customer_data or {}),
            'coupon': _build_shop_coupon(coupon_data or {}),
        })


def _kpi_dict(kpis: dict) -> dict:
    total_inv = kpis.get('total_invoices_with_vip0', kpis.get('total_invoices', 0))
    total_amt = kpis.get('total_amount_with_vip0', kpis.get('total_amount', 0))
    customers = kpis.get('total_customers', 0)
    avg_inv = round(total_amt / total_inv, 0) if total_inv else 0
    return {
        'total_invoices': total_inv,
        'total_revenue': _fmt(total_amt),
        'avg_invoice': _fmt(avg_inv),
        'total_customers': customers,
        'returning_customers': kpis.get('returning_customers', 0),
        'return_rate': _pct(kpis.get('return_rate', 0)),
    }


def _build_shop_sales(data: dict) -> dict:
    at = _kpi_dict(data.get('all_time_kpis', data.get('at_kpis', {})))
    pd = _kpi_dict(data.get('period_kpis', data.get('pd_kpis', {})))
    return {
        'all_time_kpis': at,
        'period_kpis': pd,
        'by_session': _sales_season_table({'by_session': data.get('by_session', [])}),
        'by_month': _sales_month_table({'by_month': data.get('by_month', [])}),
        'by_week': _sales_week_table({'by_week': data.get('by_week', [])}),
    }


def _build_shop_customer(data: dict) -> dict:
    summary = data.get('summary', {})
    return {
        'all_time_kpis': {
            'total_pos_customers': summary.get('total_pos', 0),
            'total_cnv_customers': summary.get('total_cnv', 0),
        },
        'period_kpis': {
            'new_pos': summary.get('new_pos', 0),
            'new_cnv': summary.get('new_cnv', 0),
        },
        'breakdown': _cnv_shop_table(data.get('shop', [])),
    }


def _build_shop_coupon(data: dict) -> dict:
    return {
        'all_time_kpis': {
            'used': data.get('all_time_used', 0),
            'unused': data.get('all_time_unused', 0),
            'amount_vnd': _fmt(data.get('all_time_amount', 0)),
        },
        'period_kpis': {
            'used': data.get('period_used', 0),
            'unused': data.get('period_unused', 0),
            'amount_vnd': _fmt(data.get('period_amount', 0)),
        },
        'by_shop_table': _coupon_shop_table(data.get('by_shop', [])),
    }


class CustomerDetailView(APIView):
    """GET /api/v1/analytics/customer-detail/?vip_id=<id> OR ?phone=<phone>"""
    permission_classes = [IsAuthenticated, make_perm_class('customers.detail')]

    def get(self, request):
        from App.models import Customer, SalesTransaction
        from App.analytics.customer_utils import normalize_grade

        vip_id = request.GET.get('vip_id', '').strip()
        phone = request.GET.get('phone', '').strip()

        if not vip_id and not phone:
            return Response({'detail': 'vip_id or phone is required'}, status=400)

        try:
            if vip_id:
                customer = Customer.objects.get(vip_id=vip_id)
            else:
                # Strip formatting — match on last 9 digits for flexibility
                digits = ''.join(c for c in phone if c.isdigit())
                customer = Customer.objects.filter(phone__endswith=digits[-9:]).first()
                if customer is None:
                    return Response({'detail': 'Customer not found'}, status=404)
        except Customer.DoesNotExist:
            return Response({'detail': 'Customer not found'}, status=404)

        # Mask phone (middle digits) — FR-006, PII protection
        raw_phone = customer.phone or ''
        masked_phone = _mask_phone(raw_phone)

        # Invoice history (most recent first, cap at 50)
        invoices = list(
            SalesTransaction.objects
            .filter(vip_id=str(customer.vip_id))
            .order_by('-sales_date')
            .values('sales_date', 'shop_name', 'invoice_number', 'sales_amount')[:50]
        )

        total_invoices = len(invoices)
        total_revenue = sum(float(i.get('sales_amount') or 0) for i in invoices)

        # CNV sync status
        try:
            from App.cnv.models import CNVCustomer
            cnv = CNVCustomer.objects.filter(phone__endswith=raw_phone[-9:] if raw_phone else '').first()
            cnv_sync = 'synced' if cnv else 'not_synced'
        except Exception:
            cnv_sync = None

        invoice_history = [
            {
                'date': str(i['sales_date']),
                'shop': i['shop_name'] or '',
                'invoice_id': i['invoice_number'] or '',
                'amount': _fmt(i.get('sales_amount') or 0),
                'coupon_used': '',  # coupon lookup is expensive — omit in v1
            }
            for i in invoices
        ]

        return Response({
            'vip_id': str(customer.vip_id or ''),
            'phone': masked_phone,
            'grade': normalize_grade(customer.vip_grade),
            'registration_store': customer.registration_store or '',
            'registration_date': str(customer.registration_date or ''),
            'total_invoices': total_invoices,
            'total_revenue': _fmt(total_revenue),
            'cnv_sync_status': cnv_sync,
            'invoice_history': invoice_history,
        })


def _mask_phone(phone: str) -> str:
    """Mask middle digits of phone number. e.g. 0912345678 → 09x-xxx-x678"""
    digits = ''.join(c for c in phone if c.isdigit())
    if len(digits) < 7:
        return phone  # too short to mask meaningfully
    # Keep first 2 + last 3, mask middle
    prefix = digits[:2]
    suffix = digits[-3:]
    mid = 'x' * (len(digits) - 5)
    return f"{prefix}x-xxx-x{suffix}"


# ═══════════════════════════════════════════════════════════════════════════════
# CHART ENDPOINTS
# ═══════════════════════════════════════════════════════════════════════════════

class SalesChartView(APIView):
    """GET /api/v1/charts/sales/"""
    permission_classes = [IsAuthenticated, make_perm_class('sales.view')]

    def get(self, request):
        from App.analytics.tab_functions import get_sales_tab

        date_from = _parse_date(request.GET.get('date_from'), 'date_from')
        date_to = _parse_date(request.GET.get('date_to'), 'date_to')
        shop_group = request.GET.get('shop_group') or None

        season_data = get_sales_tab('season', date_from=date_from, date_to=date_to,
                                    shop_group=shop_group)
        month_data = get_sales_tab('month', date_from=date_from, date_to=date_to,
                                   shop_group=shop_group)

        donuts = []
        if season_data:
            donuts.append(_sales_donut('By Season', season_data.get('by_session', []),
                                       'session'))
        if month_data:
            donuts.append(_sales_donut('By Month', month_data.get('by_month', []),
                                       'month'))

        trend = _sales_trend(month_data)

        return Response({'donuts': donuts, 'trend': trend})


DONUT_PALETTE = [
    '#0d6efd', '#6610f2', '#6f42c1', '#d63384', '#dc3545',
    '#fd7e14', '#ffc107', '#198754', '#20c997',
]


def _sales_donut(title: str, items: list, label_key: str) -> dict:
    slices = []
    for i, item in enumerate(items):
        slices.append({
            'label': str(item.get(label_key, '')),
            'value': item.get('total_invoices_with_vip0', item.get('total_invoices', 0)),
            'color': DONUT_PALETTE[i % len(DONUT_PALETTE)],
        })
    return {'title': title, 'slices': slices}


def _sales_trend(month_data: dict | None) -> dict | None:
    if not month_data:
        return None
    data_points = [
        {'date': str(m.get('month', '')), 'value': m.get('return_rate', 0)}
        for m in month_data.get('by_month', [])
    ]
    return {
        'metric': 'return_rate',
        'series': [{'shop': 'All Shops', 'data_points': data_points}],
    }


class CustomerChartView(APIView):
    """GET /api/v1/charts/customer/"""
    permission_classes = [IsAuthenticated, make_perm_class('cnv.view')]

    def get(self, request):
        date_from_str = request.GET.get('date_from', '')
        date_to_str = request.GET.get('date_to', '')

        from App.analytics.tab_functions import _parse_cnv_period_filter
        from App.cnv.service import compute_cnv_breakdown, get_cnv_phone_sets

        period_filter, _ = _parse_cnv_period_filter(date_from_str, date_to_str)
        pos_phones_all, cnv_phones_all = get_cnv_phone_sets()
        bd = compute_cnv_breakdown(period_filter, pos_phones_all, cnv_phones_all,
                                   dims=frozenset({'grade'}))

        grades = bd.get('grade', [])
        donuts = [{
            'title': 'By Grade',
            'slices': [
                {
                    'label': str(g.get('grade', '')),
                    'value': g.get('pos_customers', g.get('total_pos', 0)),
                    'color': DONUT_PALETTE[i % len(DONUT_PALETTE)],
                }
                for i, g in enumerate(grades)
            ],
        }]
        return Response({'donuts': donuts, 'trend': None})


class CouponChartView(APIView):
    """GET /api/v1/charts/coupon/"""
    permission_classes = [IsAuthenticated, make_perm_class('coupons.view')]

    def get(self, request):
        from App.analytics.tab_functions import get_coupon_tab

        date_from = _parse_date(request.GET.get('date_from'), 'date_from')
        date_to = _parse_date(request.GET.get('date_to'), 'date_to')
        prefix = request.GET.get('prefix') or None

        shop_data = get_coupon_tab('shop', date_from=date_from, date_to=date_to,
                                   coupon_id_prefix=prefix)
        by_shop = (shop_data or {}).get('by_shop', [])

        donuts = [{
            'title': 'By Shop',
            'slices': [
                {
                    'label': str(s.get('shop_name', s.get('using_shop', ''))),
                    'value': s.get('used', 0),
                    'color': DONUT_PALETTE[i % len(DONUT_PALETTE)],
                }
                for i, s in enumerate(by_shop[:9])  # cap at 9 for readability
            ],
        }]
        return Response({'donuts': donuts, 'trend': None})
