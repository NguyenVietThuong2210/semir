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
    """
    GET /api/v1/analytics/sales/
    Optional: ?tab=by_grade|by_season|by_month|by_week|by_shop
      — returns only that tab's table data alongside KPIs (lazy loading).
      Omit tab to load KPIs + grade tab (initial page load).
    """
    permission_classes = [IsAuthenticated, make_perm_class('sales.view')]

    def get(self, request):
        from App.analytics.tab_functions import get_sales_tab

        date_from = _parse_date(request.GET.get('date_from'), 'date_from')
        date_to = _parse_date(request.GET.get('date_to'), 'date_to')
        shop_group = request.GET.get('shop_group') or None
        tab = request.GET.get('tab', '').strip()  # empty = initial load (grade tab)

        # grade tab always loads — it carries the overview KPIs
        period_data = get_sales_tab(
            'grade', date_from=date_from, date_to=date_to, shop_group=shop_group
        )
        if period_data is None:
            return Response({'detail': 'No sales data available.'}, status=404)

        # All-time overview (cached; negligible cost on second call)
        if date_from is None and date_to is None:
            at_data = period_data
        else:
            at_data = get_sales_tab('grade', date_from=None, date_to=None, shop_group=shop_group)
            if at_data is None:
                at_data = period_data

        # KPIs — keys are human-readable labels (displayed directly on mobile KPI cards)
        # All-Time section matches web's 4-card layout exactly
        at_ov = at_data['overview']
        all_time_kpis = {
            'Total Customers': _fmt(at_ov.get('total_customers_in_db', 0)),
            'Member Active': _fmt(at_ov.get('member_active_all_time', 0)),
            'Member Inactive': _fmt(at_ov.get('member_inactive_all_time', 0)),
            'Return Rate (All Time)': _pct(at_ov.get('return_rate_all_time', 0)) + '%',
        }

        # Period section matches web's 10-metric layout exactly
        ov = period_data['overview']
        pd_invoices = ov.get('total_invoices_with_vip0', 0)
        pd_active = ov.get('active_customers', 0)
        period_kpis = {
            'New Members': _fmt(ov.get('new_members_in_period', 0)),
            'Returning Customers': _fmt(ov.get('returning_customers', 0)),
            'Active Customers': _fmt(pd_active),
            'Return Visit Rate': _pct(ov.get('return_rate', 0)) + '%',
            'INV(CUS)': _fmt(ov.get('total_invoices_without_vip0', 0)),
            'AMT(CUS)': _fmt(ov.get('total_amount_without_vip0', 0)),
            'INV(RET)': _fmt(ov.get('returning_invoices', 0)),
            'AMT(RET)': _fmt(ov.get('returning_amount', 0)),
            'Total Invoices': _fmt(pd_invoices),
            'Total Amount': _fmt(ov.get('total_amount_with_vip0', 0)),
        }

        # Lazy tab loading: only compute the requested tab
        _tab_map = {
            'by_grade':  lambda: _sales_grade_table(period_data.get('by_grade', [])),
            'by_season': lambda: _sales_season_table(
                get_sales_tab('season', date_from=date_from, date_to=date_to, shop_group=shop_group)),
            'by_month':  lambda: _sales_month_table(
                get_sales_tab('month', date_from=date_from, date_to=date_to, shop_group=shop_group)),
            'by_week':   lambda: _sales_week_table(
                get_sales_tab('week', date_from=date_from, date_to=date_to, shop_group=shop_group)),
            'by_shop':   lambda: _sales_shop_table(
                get_sales_tab('shop', date_from=date_from, date_to=date_to, shop_group=shop_group)),
        }

        if tab and tab in _tab_map:
            # Lazy: return only the requested tab (Flutter loads one tab at a time)
            tabs = {tab: _tab_map[tab]()}
        else:
            # Initial load: grade tab only (fastest — already loaded above)
            tabs = {'by_grade': _sales_grade_table(period_data.get('by_grade', []))}

        # Allshops tabs: only computed when a shop_group filter is active.
        # They show global (unfiltered) period data for comparison.
        allshops_tabs = None
        if shop_group:
            _allshops_map = {
                'by_grade':  lambda: _sales_grade_table(
                    (get_sales_tab('grade', date_from=date_from, date_to=date_to) or {}).get('by_grade', [])),
                'by_season': lambda: _sales_season_table(
                    get_sales_tab('season', date_from=date_from, date_to=date_to)),
                'by_month':  lambda: _sales_month_table(
                    get_sales_tab('month', date_from=date_from, date_to=date_to)),
                'by_week':   lambda: _sales_week_table(
                    get_sales_tab('week', date_from=date_from, date_to=date_to)),
            }
            if tab and tab in _allshops_map:
                allshops_tabs = {tab: _allshops_map[tab]()}
            else:
                allshops_tabs = {'by_grade': _allshops_map['by_grade']()}

        response_data = {
            'all_time_kpis': all_time_kpis,
            'period_kpis': period_kpis,
            'tabs': tabs,
            'available_tabs': list(_tab_map.keys()),
        }
        if allshops_tabs is not None:
            response_data['allshops_tabs'] = allshops_tabs
        return Response(response_data)


def _sales_grade_table(by_grade: list) -> dict:
    # Matches web: Grade | Active | Returning | Return Rate | Total (DB) | Return Rate (AT) | INV(RET) | AMT(RET) | Total INV | Total Amount
    headers = ['Grade', 'Active', 'Returning', 'Return Rate', 'Total (DB)', 'Return Rate (AT)', 'INV(RET)', 'AMT(RET)', 'Total INV', 'Total Amount']
    rows = []
    for g in (by_grade or []):
        rows.append([
            str(g.get('grade', '')),
            _fmt(g.get('total_customers', 0)),
            _fmt(g.get('returning_customers', 0)),
            _pct_cell(g.get('return_rate', 0)),
            _fmt(g.get('total_in_db', 0)),
            _pct_cell(g.get('return_rate_all_time', 0)),
            _fmt(g.get('returning_invoices', 0)),
            _fmt(g.get('returning_amount', 0)),
            _fmt(g.get('total_invoices', 0)),
            _fmt(g.get('total_amount', 0)),
        ])
    return {'headers': headers, 'rows': rows}


def _sales_season_table(data: dict | None) -> dict:
    # Matches web: Season | Active | Returning | Return Rate | INV(RET) | AMT(RET) | Total INV | Total Amount
    headers = ['Season', 'Active', 'Returning', 'Return Rate', 'INV(RET)', 'AMT(RET)', 'Total INV', 'Total Amount']
    rows = []
    if data:
        for s in data.get('by_session', []):
            rows.append([
                str(s.get('session', '')),
                _fmt(s.get('total_customers', 0)),
                _fmt(s.get('returning_customers', 0)),
                _pct_cell(s.get('return_rate', 0)),
                _fmt(s.get('returning_invoices', 0)),
                _fmt(s.get('returning_amount', 0)),
                _fmt(s.get('total_invoices_with_vip0', s.get('total_invoices', 0))),
                _fmt(s.get('total_amount_with_vip0', s.get('total_amount', 0))),
            ])
    return {'headers': headers, 'rows': rows}


def _sales_month_table(data: dict | None) -> dict:
    # Matches web: Month | Active | Returning | Return Rate | INV(RET) | AMT(RET) | Total INV | Total Amount
    headers = ['Month', 'Active', 'Returning', 'Return Rate', 'INV(RET)', 'AMT(RET)', 'Total INV', 'Total Amount']
    rows = []
    if data:
        for m in data.get('by_month', []):
            rows.append([
                str(m.get('month', '')),
                _fmt(m.get('total_customers', 0)),
                _fmt(m.get('returning_customers', 0)),
                _pct_cell(m.get('return_rate', 0)),
                _fmt(m.get('returning_invoices', 0)),
                _fmt(m.get('returning_amount', 0)),
                _fmt(m.get('total_invoices_with_vip0', m.get('total_invoices', 0))),
                _fmt(m.get('total_amount_with_vip0', m.get('total_amount', 0))),
            ])
    return {'headers': headers, 'rows': rows}


def _sales_week_table(data: dict | None) -> dict:
    # Matches web: Week | Active | Returning | Return Rate | INV(RET) | AMT(RET) | Total INV | Total Amount
    headers = ['Week', 'Active', 'Returning', 'Return Rate', 'INV(RET)', 'AMT(RET)', 'Total INV', 'Total Amount']
    rows = []
    if data:
        for w in data.get('by_week', []):
            rows.append([
                str(w.get('week_label', w.get('week', ''))),
                _fmt(w.get('total_customers', 0)),
                _fmt(w.get('returning_customers', 0)),
                _pct_cell(w.get('return_rate', 0)),
                _fmt(w.get('returning_invoices', 0)),
                _fmt(w.get('returning_amount', 0)),
                _fmt(w.get('total_invoices_with_vip0', w.get('total_invoices', 0))),
                _fmt(w.get('total_amount_with_vip0', w.get('total_amount', 0))),
            ])
    return {'headers': headers, 'rows': rows}


def _sales_shop_table(data: dict | None) -> dict:
    # Matches web: Shop | Active | Returning | Return Rate | INV(RET) | AMT(RET) | Total INV | Total Amount
    headers = ['Shop', 'Active', 'Returning', 'Return Rate', 'INV(RET)', 'AMT(RET)', 'Total INV', 'Total Amount']
    rows = []
    if data:
        for s in data.get('by_shop', []):
            rows.append([
                str(s.get('shop_name', '')),
                _fmt(s.get('total_customers', 0)),
                _fmt(s.get('returning_customers', 0)),
                _pct_cell(s.get('return_rate', 0)),
                _fmt(s.get('returning_invoices', 0)),
                _fmt(s.get('returning_amount', 0)),
                _fmt(s.get('total_invoices_with_vip0', s.get('total_invoices', 0))),
                _fmt(s.get('total_amount_with_vip0', s.get('total_amount', 0))),
            ])
    return {'headers': headers, 'rows': rows}


class CustomerAnalyticsView(APIView):
    """GET /api/v1/analytics/customer/"""
    permission_classes = [IsAuthenticated, make_perm_class('cnv.view')]

    def get(self, request):
        from App.analytics.tab_functions import _parse_cnv_period_filter
        from App.cnv.service import compute_cnv_breakdown, get_cnv_phone_sets, get_cnv_customer_kpis

        date_from_str = request.GET.get('date_from', '')
        date_to_str = request.GET.get('date_to', '')

        # Validate dates
        _parse_date(date_from_str or None, 'date_from')
        _parse_date(date_to_str or None, 'date_to')

        period_filter, has_filter = _parse_cnv_period_filter(date_from_str, date_to_str)
        all_time_filter = {}

        pos_phones_all, cnv_phones_all = get_cnv_phone_sets()

        # Shared KPI computation (same function used by web view)
        kpis = get_cnv_customer_kpis(period_filter, has_filter, pos_phones_all, cnv_phones_all)

        # All-time breakdown (for comparison tabs)
        at_bd = compute_cnv_breakdown(all_time_filter, pos_phones_all, cnv_phones_all)
        # Period breakdown (for registration breakdown tabs)
        if period_filter:
            pd_bd = compute_cnv_breakdown(period_filter, pos_phones_all, cnv_phones_all)
        else:
            pd_bd = at_bd

        # Map shared kpis to mobile KPI card labels
        at_pos_only  = kpis['pos_only_all']
        at_cnv_only  = kpis['cnv_only_all']
        pd_new_pos   = kpis['new_pos']
        pd_new_cnv   = kpis['new_cnv']
        pd_synced    = kpis['synced_period']
        pd_active    = kpis['active_period']

        # Human-readable labels displayed directly on mobile KPI cards.
        all_time_kpis = {
            'Total POS Customers': _fmt(kpis['total_pos']),
            'Total CNV Customers': _fmt(kpis['total_cnv']),
            'POS Only': _fmt(at_pos_only),
            'CNV Only': _fmt(at_cnv_only),
        }
        period_kpis = {
            'New POS Customers': _fmt(pd_new_pos),
            'New CNV Customers': _fmt(pd_new_cnv),
            'Synced This Period': _fmt(pd_synced),
            'Active Customers': _fmt(pd_active),
        }

        # Grade rows — computed directly from POSCustomer (compute_cnv_breakdown has no grade dim)
        at_grade_rows = _compute_grade_rows(cnv_phones_all)
        pd_grade_rows = _compute_grade_rows(cnv_phones_all, period_filter if period_filter else {})
        at_bd['grade'] = at_grade_rows  # inject so _cnv_pos_only_table / _cnv_both_table can use it

        # Registration breakdown tabs (using period data) — 5 tabs matching web bd_* tabs
        reg_breakdown = {
            'by_shop':   _cnv_shop_table(pd_bd.get('shop', [])),
            'by_season': _cnv_season_table(pd_bd.get('season', [])),
            'by_month':  _cnv_month_table(pd_bd.get('month', [])),
            'by_week':   _cnv_week_table(pd_bd.get('week', [])),
            'by_grade':  _cnv_grade_table(pd_grade_rows),
        }

        # Customer comparison tabs (all-time)
        customer_comparison = {
            'pos_only': _cnv_pos_only_table(at_bd),
            'cnv_only': _cnv_cnv_only_table(at_bd),
            'both': _cnv_both_table(at_bd),
            'zalo': _cnv_zalo_stats_table(at_bd),
        }

        return Response({
            'all_time_kpis': all_time_kpis,
            'period_kpis': period_kpis,
            'registration_breakdown': reg_breakdown,
            'customer_comparison': customer_comparison,
        })


def _compute_grade_rows(cnv_phones_all: set, period_filter=None) -> list:
    """POS customer grade breakdown. CNV has no grade concept, so CNV-only columns are always 0."""
    from collections import defaultdict
    from App.models import Customer as _POS
    from App.analytics.customer_utils import normalize_grade
    _GRADE_ORDER = ['No Grade', 'Member', 'Silver', 'Gold', 'Diamond']
    qs = _POS.objects.filter(vip_id__isnull=False).exclude(vip_id=0).exclude(phone='').exclude(phone__isnull=True)
    if period_filter and period_filter.get('start') and period_filter.get('end'):
        qs = qs.filter(registration_date__gte=period_filter['start'], registration_date__lte=period_filter['end'])
    grade_phones: dict[str, set] = defaultdict(set)
    for phone, raw_grade in qs.values_list('phone', 'vip_grade'):
        grade_phones[normalize_grade(raw_grade)].add(phone)
    rows = []
    for grade in _GRADE_ORDER:
        phones = grade_phones.get(grade, set())
        if not phones:
            continue
        rows.append({
            'label': grade,
            'new_pos': len(phones),
            'new_cnv': 0,
            'new_pos_only': len(phones - cnv_phones_all),
            'new_cnv_only': 0,
            'zalo_app': 0,
        })
    return rows


def _cnv_shop_table(shop_data: list) -> dict:
    # Rows from compute_cnv_breakdown 'shop' dim: label=store_name, new_pos, new_cnv, new_pos_only, new_cnv_only, zalo_app
    headers = ['Shop', 'New POS', 'New CNV', 'POS Only', 'CNV Only', 'Zalo']
    rows = [[
        str(s.get('label', s.get('store', s.get('shop_name', '')))),
        _fmt(s.get('new_pos', 0)),
        _fmt(s.get('new_cnv', 0)),
        _fmt(s.get('new_pos_only', 0)),
        _fmt(s.get('new_cnv_only', 0)),
        _fmt(s.get('zalo_app', 0)),
    ] for s in (shop_data or [])]
    return {'headers': headers, 'rows': rows}


def _cnv_month_table(month_data: list) -> dict:
    # Rows from compute_cnv_breakdown 'month' dim: label=month_key, new_pos, new_cnv, ...
    headers = ['Month', 'New POS', 'New CNV', 'POS Only', 'CNV Only', 'Zalo']
    rows = [[
        str(m.get('label', m.get('month', ''))),
        _fmt(m.get('new_pos', 0)),
        _fmt(m.get('new_cnv', 0)),
        _fmt(m.get('new_pos_only', 0)),
        _fmt(m.get('new_cnv_only', 0)),
        _fmt(m.get('zalo_app', 0)),
    ] for m in (month_data or [])]
    return {'headers': headers, 'rows': rows}


def _cnv_season_table(season_data: list) -> dict:
    # Rows from compute_cnv_breakdown 'season' dim
    headers = ['Season', 'New POS', 'New CNV', 'POS Only', 'CNV Only', 'Zalo']
    rows = [[
        str(s.get('label', s.get('season', ''))),
        _fmt(s.get('new_pos', 0)),
        _fmt(s.get('new_cnv', 0)),
        _fmt(s.get('new_pos_only', 0)),
        _fmt(s.get('new_cnv_only', 0)),
        _fmt(s.get('zalo_app', 0)),
    ] for s in (season_data or [])]
    return {'headers': headers, 'rows': rows}


def _cnv_week_table(week_data: list) -> dict:
    # Rows from compute_cnv_breakdown 'week' dim
    headers = ['Week', 'New POS', 'New CNV', 'POS Only', 'CNV Only', 'Zalo']
    rows = [[
        str(w.get('label', w.get('week', ''))),
        _fmt(w.get('new_pos', 0)),
        _fmt(w.get('new_cnv', 0)),
        _fmt(w.get('new_pos_only', 0)),
        _fmt(w.get('new_cnv_only', 0)),
        _fmt(w.get('zalo_app', 0)),
    ] for w in (week_data or [])]
    return {'headers': headers, 'rows': rows}


def _cnv_grade_table(grade_data: list) -> dict:
    # Rows from compute_cnv_breakdown 'grade' dim: label=grade, new_pos, new_cnv, ...
    headers = ['Grade', 'New POS', 'New CNV', 'POS Only', 'CNV Only', 'Zalo']
    rows = [[
        str(g.get('label', g.get('grade', ''))),
        _fmt(g.get('new_pos', 0)),
        _fmt(g.get('new_cnv', 0)),
        _fmt(g.get('new_pos_only', 0)),
        _fmt(g.get('new_cnv_only', 0)),
        _fmt(g.get('zalo_app', 0)),
    ] for g in (grade_data or [])]
    return {'headers': headers, 'rows': rows}


def _cnv_pos_only_table(bd: dict) -> dict:
    headers = ['Grade', 'POS Only']
    rows = [[str(g.get('label', g.get('grade', ''))), _fmt(g.get('new_pos_only', 0))]
            for g in bd.get('grade', [])]
    return {'headers': headers, 'rows': rows}


def _cnv_cnv_only_table(bd: dict) -> dict:
    headers = ['Grade', 'CNV Only']
    rows = [[str(g.get('label', g.get('grade', ''))), _fmt(g.get('new_cnv_only', 0))]
            for g in bd.get('grade', [])]
    return {'headers': headers, 'rows': rows}


def _cnv_both_table(bd: dict) -> dict:
    headers = ['Grade', 'New POS', 'New CNV']
    rows = [[
        str(g.get('label', g.get('grade', ''))),
        _fmt(g.get('new_pos', 0)),
        _fmt(g.get('new_cnv', 0)),
    ] for g in bd.get('grade', [])]
    return {'headers': headers, 'rows': rows}


def _cnv_zalo_stats_table(bd: dict) -> dict:
    # Zalo Stats: shop-level breakdown of Zalo App and OA connections
    headers = ['Shop', 'New CNV', 'Zalo App', '% App', 'Zalo OA', '% OA']
    rows = []
    for s in (bd.get('shop', [])):
        new_cnv = s.get('new_cnv', 0)
        zalo_app = s.get('zalo_app', 0)
        zalo_oa = s.get('zalo_oa', 0)
        pct_app = _pct_cell(zalo_app / new_cnv * 100) if new_cnv else '–'
        pct_oa = _pct_cell(zalo_oa / new_cnv * 100) if new_cnv else '–'
        rows.append([
            str(s.get('label', s.get('store', s.get('shop_name', '')))),
            _fmt(new_cnv),
            _fmt(zalo_app),
            pct_app,
            _fmt(zalo_oa),
            pct_oa,
        ])
    return {'headers': headers, 'rows': rows}


class CouponAnalyticsView(APIView):
    """
    GET /api/v1/analytics/coupon/
    Optional: ?tab=by_shop|detail|duplicates  — lazy load one tab at a time.
    Omit tab to load KPIs + by_shop (initial page load).
    """
    permission_classes = [IsAuthenticated, make_perm_class('coupons.view')]

    def get(self, request):
        from App.analytics.tab_functions import get_coupon_tab

        date_from = _parse_date(request.GET.get('date_from'), 'date_from')
        date_to = _parse_date(request.GET.get('date_to'), 'date_to')
        shop_group = request.GET.get('shop_group') or None
        prefix = request.GET.get('prefix') or None
        tab = request.GET.get('tab', '').strip()

        # shop tab always loads — it carries KPIs (all_time + period)
        shop_data = get_coupon_tab('shop', date_from=date_from, date_to=date_to,
                                   coupon_id_prefix=prefix, shop_group=shop_group)

        # get_coupon_tab('shop') returns {'all_time': {...}, 'period': {...}, 'by_shop': [...]}
        ov = shop_data or {}
        at = ov.get('all_time', {})
        pd = ov.get('period', {})

        # KPI keys are human-readable labels — displayed directly on mobile KPI cards.
        # 6 cards matching web's All-Time Summary layout.
        all_time_kpis = {
            'Total Coupons': _fmt(at.get('total', 0)),
            'Used': _fmt(at.get('used', 0)),
            'Unused': _fmt(at.get('unused', 0)),
            'Total Amount (VND)': _fmt(at.get('total_amount', 0)),
            'Coupon Amount (VND)': _fmt(at.get('total_coupon_amount', 0)),
            'Unique Invoice Amt (VND)': _fmt(at.get('unique_invoice_amount', 0)),
        }
        period_kpis = {
            'Total Coupons': _fmt(pd.get('total', 0)),
            'Used': _fmt(pd.get('used', 0)),
            'Unused': _fmt(pd.get('unused', 0)),
            'Total Amount (VND)': _fmt(pd.get('total_amount', 0)),
            'Coupon Amount (VND)': _fmt(pd.get('total_coupon_amount', 0)),
            'Unique Invoice Amt (VND)': _fmt(pd.get('unique_invoice_amount', 0)),
        }

        _tab_map = {
            'by_shop':    lambda: _coupon_shop_table(ov.get('by_shop', [])),
            'detail':     lambda: _coupon_detail_table(
                get_coupon_tab('detail', date_from=date_from, date_to=date_to,
                               coupon_id_prefix=prefix, shop_group=shop_group) or {}),
            'duplicates': lambda: _coupon_dup_table(
                get_coupon_tab('duplicates', date_from=date_from, date_to=date_to,
                               coupon_id_prefix=prefix, shop_group=shop_group) or {}),
        }

        if tab and tab in _tab_map:
            tabs = {tab: _tab_map[tab]()}
        else:
            tabs = {'by_shop': _coupon_shop_table(ov.get('by_shop', []))}

        return Response({
            'all_time_kpis': all_time_kpis,
            'period_kpis': period_kpis,
            'tabs': tabs,
            'available_tabs': list(_tab_map.keys()),
        })


def _coupon_shop_table(shop_data: list) -> dict:
    # by_shop rows: shop_name, total, used, unused, used_pct_of_used, usage_rate, total_amount, coupon_amount
    headers = ['Shop', 'Used', '% of Used', 'Coupon Amount (VND)', 'Total Amount (VND)', 'Usage Rate']
    rows = [[
        str(s.get('shop_name', s.get('using_shop', ''))),
        _fmt(s.get('used', 0)),
        _pct_cell(s.get('used_pct_of_used', 0)),
        _fmt(s.get('coupon_amount', 0)),
        _fmt(s.get('total_amount', 0)),
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
    """
    GET /api/v1/analytics/shop-detail/?shop=<name>
    Optional: ?section=sales|customer|coupon  — lazy load one section at a time.
    Omit section to load all three (initial page load returns sales KPIs only for speed).
    """
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
        section = request.GET.get('section', '').strip()

        # Sales data always loads (fastest, also validates the shop exists)
        sales_data = get_shop_detail_sales_data(shop, date_from, date_to)
        if sales_data is None:
            return Response({'detail': 'Shop not found or no data.'}, status=404)

        _date_str_from = str(date_from) if date_from else ''
        _date_str_to = str(date_to) if date_to else ''

        if section == 'customer':
            customer_data = get_shop_detail_customer_data(
                shop, start_date=_date_str_from, end_date=_date_str_to
            )
            return Response({
                'shop_name': shop,
                'customer': _build_shop_customer(customer_data or {}),
            })

        if section == 'coupon':
            coupon_data = get_shop_detail_coupon_data(shop, date_from, date_to)
            return Response({
                'shop_name': shop,
                'coupon': _build_shop_coupon(coupon_data or {}),
            })

        if section == 'sales':
            return Response({
                'shop_name': shop,
                'sales': _build_shop_sales(sales_data),
            })

        # No section param: initial load — return sales only (customer/coupon lazy-loaded)
        return Response({
            'shop_name': shop,
            'sales': _build_shop_sales(sales_data),
            'available_sections': ['sales', 'customer', 'coupon'],
        })


def _kpi_dict(kpis: dict) -> dict:
    # Human-readable labels matching shop detail web KPI cards:
    # Active | Returning | Return Rate | INV(RET) | AMT(RET) | Total INV | Total Amt
    total_inv = kpis.get('total_invoices_with_vip0', kpis.get('total_invoices', 0))
    total_amt = kpis.get('total_amount_with_vip0', kpis.get('total_amount', 0))
    return {
        'Active': _fmt(kpis.get('total_customers', 0)),
        'Returning': _fmt(kpis.get('returning_customers', 0)),
        'Return Rate': _pct(kpis.get('return_rate', 0)) + '%',
        'INV(RET)': _fmt(kpis.get('returning_invoices', 0)),
        'AMT(RET)': _fmt(kpis.get('returning_amount', 0)),
        'Total INV': _fmt(total_inv),
        'Total Amt (VND)': _fmt(total_amt),
    }


def _build_shop_sales(data: dict) -> dict:
    # get_shop_detail_sales_data() returns {'all_time': kpis, 'period': kpis, 'by_session', 'by_month', 'by_week'}
    at = _kpi_dict(data.get('all_time', {}))
    pd = _kpi_dict(data.get('period', {}))
    return {
        'all_time_kpis': at,
        'period_kpis': pd,
        'by_session': _sales_season_table({'by_session': data.get('by_session', [])}),
        'by_month': _sales_month_table({'by_month': data.get('by_month', [])}),
        'by_week': _sales_week_table({'by_week': data.get('by_week', [])}),
    }


def _build_shop_customer(data: dict) -> dict:
    # Human-readable labels matching web's 7 KPI cards exactly:
    # New POS | POS (w/ INV) | New CNV | POS Only | CNV Only | Zalo App | Zalo OA
    at = data.get('all_time') or {}
    pd = data.get('period') or {}
    return {
        'all_time_kpis': {
            'New POS': _fmt(at.get('new_pos', 0)),
            'POS (w/ INV)': _fmt(at.get('new_pos_inv', 0)),
            'New CNV': _fmt(at.get('new_cnv', 0)),
            'POS Only': _fmt(at.get('new_pos_only', 0)),
            'CNV Only': _fmt(at.get('new_cnv_only', 0)),
            'Zalo App': _fmt(at.get('zalo_app', 0)),
            'Zalo OA': _fmt(at.get('zalo_oa', 0)),
        },
        'period_kpis': {
            'New POS': _fmt(pd.get('new_pos', 0)),
            'POS (w/ INV)': _fmt(pd.get('new_pos_inv', 0)),
            'New CNV': _fmt(pd.get('new_cnv', 0)),
            'POS Only': _fmt(pd.get('new_pos_only', 0)),
            'CNV Only': _fmt(pd.get('new_cnv_only', 0)),
            'Zalo App': _fmt(pd.get('zalo_app', 0)),
            'Zalo OA': _fmt(pd.get('zalo_oa', 0)),
        },
        'by_season': _cnv_period_table(data.get('by_season', [])),
        'by_month': _cnv_period_table(data.get('by_month', [])),
        'by_week': _cnv_period_table(data.get('by_week', [])),
        'zalo_active': _zalo_active_table(data.get('zalo_active_list', [])),
    }


def _zalo_active_table(zalo_list: list) -> dict:
    # Matches web Excel sheet: CNV ID | Phone | Name | Level | Zalo App ID | Zalo OA ID | Zalo Active date
    headers = ['CNV ID', 'Phone', 'Name', 'Level', 'Zalo App ID', 'Zalo OA ID', 'Active Date']
    rows = []
    for z in (zalo_list or []):
        name = f"{z.get('last_name') or ''} {z.get('first_name') or ''}".strip()
        active_date = z.get('zalo_app_created_at')
        rows.append([
            str(z.get('cnv_id', '')),
            str(z.get('phone', '')),
            name,
            str(z.get('level_name', '') or ''),
            str(z.get('zalo_app_id', '') or ''),
            str(z.get('zalo_oa_id', '') or ''),
            str(active_date.date() if hasattr(active_date, 'date') else active_date or ''),
        ])
    return {'headers': headers, 'rows': rows}


def _cnv_period_table(rows: list) -> dict:
    # 11 columns matching web's shop detail customer breakdown tables exactly:
    # Season/Month/Week | POS(INV) | POS(NO INV) | POS Total | POS Only | New CNV | CNV Only | Zalo App | %App | Zalo OA | %OA
    headers = ['Period', 'POS(INV)', 'POS(NO INV)', 'POS Total', 'POS Only',
               'New CNV', 'CNV Only', 'Zalo App', '%App', 'Zalo OA', '%OA']
    data_rows = [[
        str(r.get('label', '')),
        _fmt(r.get('new_pos_inv', 0)),
        _fmt(r.get('new_pos_no_inv', 0)),
        _fmt(r.get('new_pos', 0)),
        _fmt(r.get('new_pos_only', 0)),
        _fmt(r.get('new_cnv', 0)),
        _fmt(r.get('new_cnv_only', 0)),
        _fmt(r.get('zalo_app', 0)),
        _pct_cell(r.get('zalo_app_pct', 0)),
        _fmt(r.get('zalo_oa', 0)),
        _pct_cell(r.get('zalo_oa_pct', 0)),
    ] for r in (rows or [])]
    return {'headers': headers, 'rows': data_rows}


def _build_shop_coupon(data: dict) -> dict:
    # Human-readable labels matching web coupon KPI cards.
    at = data.get('all_time', {})
    pd = data.get('period', {})
    return {
        'all_time_kpis': {
            'Total Coupons': _fmt(at.get('total', 0)),
            'Used': _fmt(at.get('used', 0)),
            'Unused': _fmt(at.get('unused', 0)),
            'Total Amount (VND)': _fmt(at.get('total_amount', 0)),
            'Coupon Amount (VND)': _fmt(at.get('total_coupon_amount', 0)),
            'Unique Invoice Amt (VND)': _fmt(at.get('unique_invoice_amount', 0)),
        },
        'period_kpis': {
            'Total Coupons': _fmt(pd.get('total', 0)),
            'Used': _fmt(pd.get('used', 0)),
            'Unused': _fmt(pd.get('unused', 0)),
            'Total Amount (VND)': _fmt(pd.get('total_amount', 0)),
            'Coupon Amount (VND)': _fmt(pd.get('total_coupon_amount', 0)),
            'Unique Invoice Amt (VND)': _fmt(pd.get('unique_invoice_amount', 0)),
        },
        'detail_table': _coupon_detail_table(data),
    }


class CustomerDetailView(APIView):
    """GET /api/v1/analytics/customer-detail/?vip_id=<id> OR ?phone=<phone>"""
    permission_classes = [IsAuthenticated, make_perm_class('customers.detail')]

    def get(self, request):
        from App.models import Customer
        from App.analytics.customer_utils import normalize_grade, get_customer_detail_data

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
        masked_phone = _mask_phone(customer.phone or '')

        # Shared data fetch (same function used by web view — no cap, full parity)
        detail = get_customer_detail_data(customer, include_coupons=False)
        cnv_sync = 'synced' if detail['is_synced_to_cnv'] else 'not_synced'
        total_invoices = detail['total_invoice_count']
        invoices = detail['invoices']
        total_revenue = sum(float(inv.get('amount') or 0) for inv in invoices)

        invoice_history = [
            {
                'date': str(inv['sales_day'] or ''),
                'shop': inv['shop_name'] or '',
                'invoice_id': inv['invoice_no'] or '',
                'amount': _fmt(inv.get('amount') or 0),
                'coupon_used': '',
            }
            for inv in invoices
        ]

        return Response({
            'name': customer.name or '',
            'vip_id': str(customer.vip_id or ''),
            'phone': masked_phone,
            'grade': normalize_grade(customer.vip_grade),
            'registration_store': customer.registration_store or '',
            'registration_date': str(customer.registration_date or ''),
            'email': customer.email or '',
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
    counts = [item.get('total_invoices_with_vip0', item.get('total_invoices', 0)) for item in items]
    total = sum(counts) or 1
    slices = []
    for i, (item, count) in enumerate(zip(items, counts)):
        slices.append({
            'label': str(item.get(label_key, '')),
            'value': _fmt(count),
            'color': DONUT_PALETTE[i % len(DONUT_PALETTE)],
            'percentage': round(count / total * 100, 1),
        })
    return {'title': title, 'slices': slices}


def _sales_trend(month_data: dict | None) -> list | None:
    if not month_data:
        return None
    points = month_data.get('by_month', [])
    if not points:
        return None
    return [
        {'label': str(m.get('month', '')), 'value': float(m.get('return_rate', 0))}
        for m in points
    ]


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
        _grade_counts = [g.get('pos_customers', g.get('total_pos', 0)) for g in grades]
        _grade_total = sum(_grade_counts) or 1
        donuts = [{
            'title': 'By Grade',
            'slices': [
                {
                    'label': str(g.get('grade', '')),
                    'value': _fmt(count),
                    'color': DONUT_PALETTE[i % len(DONUT_PALETTE)],
                    'percentage': round(count / _grade_total * 100, 1),
                }
                for i, (g, count) in enumerate(zip(grades, _grade_counts))
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

        top_shops = by_shop[:9]  # cap at 9 for readability
        _shop_counts = [s.get('used', 0) for s in top_shops]
        _shop_total = sum(_shop_counts) or 1
        donuts = [{
            'title': 'By Shop',
            'slices': [
                {
                    'label': str(s.get('shop_name', s.get('using_shop', ''))),
                    'value': _fmt(count),
                    'color': DONUT_PALETTE[i % len(DONUT_PALETTE)],
                    'percentage': round(count / _shop_total * 100, 1),
                }
                for i, (s, count) in enumerate(zip(top_shops, _shop_counts))
            ],
        }]
        return Response({'donuts': donuts, 'trend': None})
