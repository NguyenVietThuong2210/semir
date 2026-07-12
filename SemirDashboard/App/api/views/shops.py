"""App/api/views/shops.py — shops list + shop detail endpoints + builders
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
from .analytics import _coupon_detail_table, _sales_month_table, _sales_season_table, _sales_week_table  # noqa: F401

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


