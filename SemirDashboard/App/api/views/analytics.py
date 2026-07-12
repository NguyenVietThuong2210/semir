"""App/api/views/analytics.py — sales / customer / coupon analytics endpoints + table builders
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
from .helpers import _fmt, _fmtd, _pct, _pct_cell, _parse_date  # noqa: F401

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
        # C-11: import from the authoritative module, not a private cross-module delegate
        from App.cnv.service import parse_cnv_period_filter as _parse_cnv_period_filter
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
        pd_grade_rows = _compute_grade_rows(cnv_phones_all, period_filter) if period_filter else at_grade_rows
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


