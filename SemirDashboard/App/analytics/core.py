"""
App/analytics/core.py

Main orchestrator for customer analytics.
Entry point that coordinates all analytics calculations.

Uses user-confirmed formula: counts INVOICES, not unique days

Version: 3.3 - Fixed within-season + cross-season returns
Version: 3.4 - Added shop_group filter
"""
import logging
from decimal import Decimal

from django.db.models import Count, Q

from App.models import Customer, SalesTransaction

from .calculations import calculate_return_visits
from .customer_utils import get_customer_info, count_new_members_with_invoice
from .season_utils import get_session_for_range, session_sort_key, month_sort_key, year_sort_key, week_sort_key
from .aggregators import (
    aggregate_by_grade,
    aggregate_by_season,
    aggregate_by_month,
    aggregate_by_year,
    aggregate_by_week,
    aggregate_by_shop,
    calculate_buyer_without_info,
)

logger = logging.getLogger('customer_analytics')


def calculate_return_rate_analytics(date_from=None, date_to=None, shop_group=None, chart_only=False):
    """
    🎯 MAIN ANALYTICS FUNCTION - Entry point for all customer analytics

    Uses the same cached _load_sales() data as the dashboard tab functions, so
    chart/export views benefit from the 5-minute locmem cache and produce data
    that is guaranteed to be consistent with the dashboard.

    Args:
        date_from: Start date for period filter (optional)
        date_to: End date for period filter (optional)
        shop_group: Shop group filter - "Bala Group", "Semir Group", "Others Group" (optional)
        chart_only: Skip customer_details + buyer_without_info (lighter for chart page)

    Returns:
        Dict with complete analytics data:
        - date_range: {start, end}
        - session_label: Season label if period fits in one season
        - overview: Summary metrics
        - by_grade: Grade breakdown list
        - by_session: Season breakdown list
        - by_shop: Shop breakdown list with sub-breakdowns
        - customer_details: Individual customer data
        - buyer_without_info_stats: VIP ID = 0 analytics
    """
    from App.analytics.tab_functions import _load_sales

    logger.debug("START date_from=%s date_to=%s shop_group=%s", date_from, date_to, shop_group)

    # Cheap aggregate queries (not in _load_sales)
    total_customers_in_db = Customer.objects.count()
    member_active_all_time = (
        SalesTransaction.objects
        .exclude(Q(vip_id='') | Q(vip_id='0') | Q(vip_id__isnull=True))
        .values('vip_id').distinct().count()
    )
    member_inactive_all_time = max(0, total_customers_in_db - member_active_all_time)

    # Heavy fetch — uses 5-min locmem cache so chart + export reuse dashboard data
    customer_purchases, get_ci, date_stats = _load_sales(date_from, date_to, shop_group)
    if customer_purchases is None:
        return None

    # VIP0 all-time stats (single aggregate, no row fetch)
    _vip0_q = Q(vip_id='') | Q(vip_id='0') | Q(vip_id__isnull=True)
    from django.db.models import Sum as _Sum
    _vip0_agg = SalesTransaction.objects.filter(_vip0_q).aggregate(
        cnt=Count('id'), total=_Sum('sales_amount')
    )
    vip0_alltime_invoices = _vip0_agg['cnt'] or 0
    vip0_alltime_amount   = float(_vip0_agg['total'] or 0)

    buyer_no_info_invoices = len(customer_purchases.get('0', []))
    logger.debug("Customers: %d  buyer_no_info_invoices: %d",
                len(customer_purchases), buyer_no_info_invoices)

    # Effective date range for "new member" tracking
    period_lo = date_from or date_stats['start_date']
    period_hi = date_to   or date_stats['end_date']

    # ========================================================================
    # PERIOD-LEVEL METRICS (EXCLUDING VIP ID = 0)
    # ========================================================================
    returning_customers = set()
    customer_details = []
    total_amount_period = Decimal(0)
    returning_invoices = 0
    returning_amount = Decimal(0)

    vip_0_purchases = customer_purchases.get('0', [])
    vip_0_amount = sum(p['amount'] for p in vip_0_purchases)
    total_invoices_without_vip0 = 0

    for vip_id, purchases in customer_purchases.items():
        if vip_id == '0':
            continue

        purchases_sorted = sorted(purchases, key=lambda x: x['date'])
        n = len(purchases_sorted)
        total_invoices_without_vip0 += n

        grade, reg_date, name = get_ci(vip_id, purchases_sorted[0].get('customer'))

        amt = sum(p['amount'] for p in purchases_sorted)
        total_amount_period += amt

        rc, is_ret = calculate_return_visits(purchases_sorted, reg_date)
        if is_ret:
            returning_customers.add(vip_id)
            returning_invoices += n
            returning_amount += amt

        if not chart_only:
            customer_details.append({
                'vip_id': vip_id,
                'name': name,
                'vip_grade': grade,
                'registration_date': reg_date,
                'first_purchase_date': purchases_sorted[0]['date'],
                'total_purchases': n,
                'return_visits': rc,
                'total_spent': float(amt),
            })

    new_members_count = count_new_members_with_invoice(customer_purchases, get_ci, period_lo, period_hi)
    logger.debug("new_members_count=%d", new_members_count)

    total_active = len([vid for vid in customer_purchases if vid != '0'])
    total_returning = len(returning_customers)
    return_rate_p = round(total_returning / total_active * 100, 2) if total_active else 0
    return_rate_at = round(total_returning / total_customers_in_db * 100, 2) if total_customers_in_db else 0

    total_invoices_with_vip0 = total_invoices_without_vip0 + len(vip_0_purchases)
    total_amount_with_vip0 = total_amount_period + vip_0_amount

    # ========================================================================
    # AGGREGATE BY DIMENSIONS
    # ========================================================================
    grade_stats = [] if chart_only else aggregate_by_grade(customer_details)
    session_stats = aggregate_by_season(customer_purchases, get_ci)
    month_stats = aggregate_by_month(customer_purchases, get_ci)
    year_stats = aggregate_by_year(customer_purchases, get_ci)

    all_session_keys = sorted([s['session'] for s in session_stats], key=session_sort_key)
    all_month_keys = sorted([m['month'] for m in month_stats], key=month_sort_key)
    all_year_keys = sorted([y['year'] for y in year_stats], key=year_sort_key)
    week_stats = aggregate_by_week(customer_purchases, get_ci)
    all_week_keys = sorted([w['week_sort'] for w in week_stats], key=week_sort_key)
    shop_stats = aggregate_by_shop(customer_purchases, get_ci, all_session_keys, all_month_keys, all_year_keys, all_week_keys)

    if chart_only:
        buyer_without_info_stats = None
    else:
        buyer_without_info_stats = calculate_buyer_without_info(
            vip_0_purchases,
            vip0_alltime_invoices,
            vip0_alltime_amount,
            date_from,
            date_to,
            total_invoices_with_vip0,
            float(total_amount_with_vip0),
        )
        customer_details.sort(key=lambda x: x['return_visits'], reverse=True)

    logger.debug("DONE  total_amount=%.2f  shops=%d  sessions=%d",
                float(total_amount_period), len(shop_stats), len(session_stats))

    return {
        'date_range': {'start': date_stats['start_date'], 'end': date_stats['end_date']},
        'session_label': get_session_for_range(date_from, date_to),
        'overview': {
            'active_customers': total_active,
            'returning_customers': total_returning,
            'return_rate': return_rate_p,
            'return_rate_all_time': return_rate_at,
            'returning_invoices': returning_invoices,
            'returning_amount': float(returning_amount),
            'total_amount_period': float(total_amount_period),
            'buyer_without_info': buyer_no_info_invoices,
            'new_members_in_period': new_members_count,
            'total_customers_in_db': total_customers_in_db,
            'member_active_all_time': member_active_all_time,
            'member_inactive_all_time': member_inactive_all_time,
            'total_invoices_without_vip0': total_invoices_without_vip0,
            'total_amount_without_vip0': float(total_amount_period),
            'total_invoices_with_vip0': total_invoices_with_vip0,
            'total_amount_with_vip0': float(total_amount_with_vip0),
        },
        'by_grade': grade_stats,
        'by_session': session_stats,
        'by_month': month_stats,
        'by_year': year_stats,
        'by_week': week_stats,
        'by_shop': shop_stats,
        'customer_details': customer_details,
        'buyer_without_info_stats': buyer_without_info_stats,
        'customer_purchases': customer_purchases,  # NEW: For reconciliation sheet
    }