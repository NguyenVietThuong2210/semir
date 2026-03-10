"""
App/analytics/core.py

Main orchestrator for customer analytics.
Entry point that coordinates all analytics calculations.

Uses user-confirmed formula: counts INVOICES, not unique days

Version: 3.3 - Fixed within-season + cross-season returns
Version: 3.4 - Added shop_group filter
"""
import logging
from collections import defaultdict
from decimal import Decimal

from django.db.models import Count, Case, When, IntegerField, Q

from App.models import Customer, SalesTransaction

from .calculations import calculate_return_visits
from .customer_utils import (
    clear_customer_cache,
    get_customer_info,
    build_customer_purchase_map,
)
from .season_utils import get_session_for_range, session_sort_key, month_sort_key
from .aggregators import (
    aggregate_by_grade,
    aggregate_by_season,
    aggregate_by_month,
    aggregate_by_shop,
    calculate_buyer_without_info,
)

logger = logging.getLogger('customer_analytics')


def calculate_return_rate_analytics(date_from=None, date_to=None, shop_group=None):
    """
    🎯 MAIN ANALYTICS FUNCTION - Entry point for all customer analytics
    
    Calculates comprehensive return visit analytics with:
    - Period-level metrics (excluding VIP ID = 0)
    - By VIP Grade breakdown
    - By Season breakdown (cross-season returns)
    - By Shop breakdown (with grade and season sub-breakdowns)
    - Customer details list
    - Buyer without info stats (VIP ID = 0)
    
    Args:
        date_from: Start date for period filter (optional)
        date_to: End date for period filter (optional)
        shop_group: Shop group filter - "Bala Group", "Semir Group", "Others Group" (optional)
    
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
    clear_customer_cache()
    logger.info("START date_from=%s date_to=%s shop_group=%s", date_from, date_to, shop_group)

    # OPT-1: Single query for all Customer aggregate stats (was 3 separate COUNT queries)
    cust_stats = Customer.objects.aggregate(
        total=Count('id'),
        active=Count(Case(When(points__gt=0, then=1), output_field=IntegerField())),
        inactive=Count(Case(When(points=0, then=1), output_field=IntegerField())),
    )
    total_customers_in_db   = cust_stats['total']
    member_active_all_time   = cust_stats['active']
    member_inactive_all_time = cust_stats['inactive']

    # OPT-2: Only select needed fields; clear default model ordering (avoids DB-level sort)
    # OPT-3: select_related with only() to avoid loading unused Customer columns
    SALES_FIELDS = ('vip_id', 'sales_date', 'invoice_number', 'sales_amount', 'shop_name', 'customer')
    CUST_FIELDS  = ('customer__id', 'customer__vip_id', 'customer__vip_grade',
                    'customer__registration_date', 'customer__name')
    qs = (
        SalesTransaction.objects
        .select_related('customer')
        .only(*SALES_FIELDS, *CUST_FIELDS)
        .order_by()           # clears the model Meta ordering (no wasted DB sort)
    )
    if date_from:
        qs = qs.filter(sales_date__gte=date_from)
    if date_to:
        qs = qs.filter(sales_date__lte=date_to)

    if shop_group:
        if shop_group == 'Bala Group':
            qs = qs.filter(Q(shop_name__icontains='Bala') | Q(shop_name__icontains='巴拉'))
        elif shop_group == 'Semir Group':
            qs = qs.filter(Q(shop_name__icontains='Semir') | Q(shop_name__icontains='森马'))
        elif shop_group == 'Others Group':
            qs = qs.exclude(
                Q(shop_name__icontains='Bala') | Q(shop_name__icontains='巴拉') |
                Q(shop_name__icontains='Semir') | Q(shop_name__icontains='森马')
            )

    # OPT-4: Single fetch — no separate exists() call, no second aggregate(Min/Max)
    sales_list = list(qs)
    if not sales_list:
        return None
    date_stats = {
        'start_date': min(s.sales_date for s in sales_list),
        'end_date':   max(s.sales_date for s in sales_list),
    }

    # OPT-5: Only load VIP0 rows with needed fields for all-time stats (was full table scan)
    all_sales_unfiltered = list(
        SalesTransaction.objects
        .filter(Q(vip_id='') | Q(vip_id='0') | Q(vip_id__isnull=True))
        .only('vip_id', 'sales_amount')
    )

    logger.info("Transactions: %d  VIP0-alltime: %d", len(sales_list), len(all_sales_unfiltered))
    
    # Build customer purchase map
    customer_purchases = build_customer_purchase_map(sales_list)
    
    buyer_no_info_invoices = len(customer_purchases.get('0', []))
    logger.info("Customers: %d  buyer_no_info_invoices: %d",
                len(customer_purchases), buyer_no_info_invoices)
    
    # ========================================================================
    # PERIOD-LEVEL METRICS (EXCLUDING VIP ID = 0)
    # ========================================================================
    returning_customers = set()
    new_members_in_period = set()
    customer_details = []
    total_amount_period = Decimal(0)
    
    # NEW: Track returning invoices and amounts
    returning_invoices = 0
    returning_amount = Decimal(0)
    
    # Separate tracking for VIP ID = 0
    vip_0_purchases = customer_purchases.get('0', [])
    vip_0_amount = sum(p['amount'] for p in vip_0_purchases)
    
    # NEW: Track invoice counts for VIP 0 totals
    total_invoices_without_vip0 = 0
    
    for vip_id, purchases in customer_purchases.items():
        # CRITICAL: Skip VIP ID = 0 for customer metrics
        if vip_id == '0':
            continue
        
        purchases_sorted = sorted(purchases, key=lambda x: x['date'])
        n = len(purchases_sorted)
        
        # NEW: Count invoices WITHOUT VIP 0
        total_invoices_without_vip0 += n
        
        # Get customer info
        grade, reg_date, name = get_customer_info(vip_id, purchases_sorted[0]['customer'])
        
        # Calculate total amount (needed for returning tracking)
        amt = sum(p['amount'] for p in purchases_sorted)
        total_amount_period += amt
        
        # Calculate return visits (by unique days)
        rc, is_ret = calculate_return_visits(purchases_sorted, reg_date)
        if is_ret:
            returning_customers.add(vip_id)
            # NEW: Track returning invoices and amount
            returning_invoices += n
            returning_amount += amt
        
        # Track new members in period
        if reg_date and vip_id != '0':
            lo = date_from or date_stats['start_date']
            hi = date_to or date_stats['end_date']
            if lo <= reg_date <= hi:
                new_members_in_period.add(vip_id)
        
        # Build customer detail record
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
    
    # Calculate metrics EXCLUDING VIP ID = 0
    total_active = len([vid for vid in customer_purchases if vid != '0'])
    total_returning = len(returning_customers)
    return_rate_p = round(total_returning / total_active * 100, 2) if total_active else 0
    return_rate_at = round(total_returning / total_customers_in_db * 100, 2) if total_customers_in_db else 0
    
    # NEW: Calculate totals WITH VIP 0
    total_invoices_with_vip0 = total_invoices_without_vip0 + len(vip_0_purchases)
    total_amount_with_vip0 = total_amount_period + vip_0_amount
    
    # ========================================================================
    # AGGREGATE BY DIMENSIONS
    # ========================================================================
    grade_stats = aggregate_by_grade(customer_details, new_members_in_period)
    session_stats = aggregate_by_season(customer_purchases, get_customer_info, new_members_in_period)
    month_stats = aggregate_by_month(customer_purchases, get_customer_info, new_members_in_period)

    all_session_keys = sorted([s['session'] for s in session_stats], key=session_sort_key)
    all_month_keys = sorted([m['month'] for m in month_stats], key=month_sort_key)
    shop_stats = aggregate_by_shop(customer_purchases, get_customer_info, all_session_keys, new_members_in_period, all_month_keys)
    
    buyer_without_info_stats = calculate_buyer_without_info(
        vip_0_purchases,
        all_sales_unfiltered,  # Use unfiltered sales for all-time stats
        date_from,
        date_to,
        total_invoices_with_vip0,
        total_amount_with_vip0,
    )
    
    # Sort customer details by return visits
    customer_details.sort(key=lambda x: x['return_visits'], reverse=True)
    
    logger.info("DONE  total_amount=%.2f  shops=%d  sessions=%d",
                float(total_amount_period), len(shop_stats), len(session_stats))
    
    return {
        'date_range': {'start': date_stats['start_date'], 'end': date_stats['end_date']},
        'session_label': get_session_for_range(date_from, date_to),
        'overview': {
            'active_customers': total_active,
            'returning_customers': total_returning,
            'return_rate': return_rate_p,
            'return_rate_all_time': return_rate_at,
            'returning_invoices': returning_invoices,  # NEW
            'returning_amount': float(returning_amount),  # NEW
            'total_amount_period': float(total_amount_period),
            'buyer_without_info': buyer_no_info_invoices,
            'new_members_in_period': len(new_members_in_period),
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
        'by_shop': shop_stats,
        'customer_details': customer_details,
        'buyer_without_info_stats': buyer_without_info_stats,
        'customer_purchases': customer_purchases,  # NEW: For reconciliation sheet
    }