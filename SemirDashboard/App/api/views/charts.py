"""App/api/views/charts.py — chart endpoints (sales / customer / coupon donuts + trends)
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
from .helpers import _fmt, _fmtd, _parse_date  # noqa: F401
from .analytics import _compute_grade_rows  # noqa: F401

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

        # C-11: import from the authoritative module, not a private cross-module delegate
        from App.cnv.service import parse_cnv_period_filter, get_cnv_phone_sets

        period_filter, _ = parse_cnv_period_filter(date_from_str, date_to_str)
        _, cnv_phones_all = get_cnv_phone_sets()

        # C-02: compute_cnv_breakdown never returns a 'grade' key (dims is ignored) —
        # use _compute_grade_rows, the same source the analytics endpoint uses.
        grades = _compute_grade_rows(cnv_phones_all, period_filter)
        _grade_counts = [g.get('new_pos', 0) for g in grades]
        _grade_total = sum(_grade_counts) or 1
        donuts = [{
            'title': 'By Grade',
            'slices': [
                {
                    'label': str(g.get('label', '')),
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
