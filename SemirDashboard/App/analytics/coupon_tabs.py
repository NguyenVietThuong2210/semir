"""
App/analytics/coupon_tabs.py
Coupon analytics tabs: get_coupon_tab (shop/detail/duplicates).
Split from tab_functions.py (R3, 2026-07-12). Import via App.analytics.tab_functions (facade) or directly.
"""
from datetime import date as _date
from decimal import Decimal

from django.db.models import Count, Q

from App.models import Customer, SalesTransaction
from .calculations import calculate_return_visits
from .customer_utils import get_customer_info, build_customer_purchase_map, normalize_grade, _norm_vid, count_new_members_with_invoice
from .season_utils import (
    get_session_for_range, session_sort_key, month_sort_key,
    year_sort_key, week_sort_key,
)
from .aggregators import (
    aggregate_by_grade,
    aggregate_by_season,
    aggregate_by_month,
    aggregate_by_week,
    aggregate_by_shop,
    calculate_buyer_without_info,
)

COUPON_TABS = ('shop', 'detail', 'duplicates')


def _build_coupon_qs(coupon_id_prefix=None, shop_group=None, date_from=None, date_to=None, using_shop_exact=None):
    """
    Build base Coupon queryset with shop_group + prefix filters applied.
    Returns (qs, period_qs).
    """
    from App.models import Coupon
    qs = Coupon.objects.all()

    if using_shop_exact:
        qs = qs.filter(using_shop=using_shop_exact)

    if shop_group:
        if shop_group == 'Bala Group':
            qs = qs.filter(Q(using_shop__icontains='Bala') | Q(using_shop__icontains='巴拉'))
        elif shop_group == 'Semir Group':
            qs = qs.filter(Q(using_shop__icontains='Semir') | Q(using_shop__icontains='森马'))
        elif shop_group == 'Others Group':
            qs = qs.exclude(
                Q(using_shop__icontains='Bala') | Q(using_shop__icontains='巴拉') |
                Q(using_shop__icontains='Semir') | Q(using_shop__icontains='森马')
            )

    if coupon_id_prefix:
        _prefixes = [p.strip() for p in coupon_id_prefix.split(',') if p.strip()]
        if len(_prefixes) == 1:
            qs = qs.filter(coupon_id__istartswith=_prefixes[0])
        elif _prefixes:
            _pq = Q()
            for _p in _prefixes:
                _pq |= Q(coupon_id__istartswith=_p)
            qs = qs.filter(_pq)

    if date_from or date_to:
        usage_filter = Q(using_date__isnull=False)
        if date_from:
            usage_filter &= Q(using_date__gte=date_from)
        if date_to:
            usage_filter &= Q(using_date__lte=date_to)
        period_qs = qs.filter(usage_filter)
    else:
        period_qs = qs

    return qs, period_qs


def get_coupon_tab(tab: str, date_from=None, date_to=None,
                   coupon_id_prefix=None, shop_group=None) -> dict:
    """
    Compute data for a single Coupon Analytics tab.
    Each tab fetches ONLY the data it needs — no excess queries.

    Args:
        tab: one of COUPON_TABS
        date_from / date_to: optional date filter
        coupon_id_prefix: optional prefix filter
        shop_group: optional shop group filter

    Returns:
        Dict with tab-specific data.
    """
    if tab == 'shop':
        return _coupon_shop_tab(date_from, date_to, coupon_id_prefix, shop_group)
    if tab == 'detail':
        return _coupon_detail_tab(date_from, date_to, coupon_id_prefix, shop_group)
    if tab == 'duplicates':
        return _coupon_duplicates_tab(date_from, date_to, coupon_id_prefix, shop_group)
    raise ValueError(f"Unknown coupon tab: {tab!r}")


def _coupon_shop_tab(date_from, date_to, coupon_id_prefix, shop_group):
    """
    Lean function for the Shop tab.
    Fetches: all_time aggregate stats, period aggregate stats, by_shop breakdown.
    Does NOT load: details list, CNV enrichment, or duplicate_invoices list.
    """
    from App.analytics.coupon_analytics import calc_coupon_amount

    qs, period_qs = _build_coupon_qs(coupon_id_prefix, shop_group, date_from, date_to)

    # All-time counts — single aggregate
    _at = qs.aggregate(
        total=Count('id'),
        used=Count('id', filter=Q(using_date__isnull=False)),
    )
    all_time_total = _at['total']
    all_time_used = _at['used']
    all_time_unused = all_time_total - all_time_used
    all_time_usage_rate = round(all_time_used / all_time_total * 100 if all_time_total else 0, 2)

    # Period counts — single aggregate (or reuse all-time when no date filter)
    if period_qs is qs:
        period_total, period_used = all_time_total, all_time_used
    else:
        _pd = period_qs.aggregate(
            total=Count('id'),
            used=Count('id', filter=Q(using_date__isnull=False)),
        )
        period_total, period_used = _pd['total'], _pd['used']
    period_unused = period_total - period_used
    period_usage_rate = round(period_used / period_total * 100 if period_total else 0, 2)

    # All-time amounts — R1: consolidated via accumulate_coupon_amounts.
    # falsy_uses_face_value=True: this path historically fell back to face_value
    # when sales_amount was 0/None.
    from App.analytics.coupon_analytics import accumulate_coupon_amounts, fetch_docket_txn_amounts
    _all_used = list(qs.filter(using_date__isnull=False).values(
        'pk', 'docket_number', 'face_value'
    ))
    all_time_amount, all_time_coupon_amount, all_time_unique_amount = accumulate_coupon_amounts(
        _all_used, fetch_docket_txn_amounts(_all_used), falsy_uses_face_value=True
    )

    # All-time duplicate count (aggregate query — no row fetch)
    _dup_all_count = (
        qs.filter(using_date__isnull=False, docket_number__isnull=False)
        .exclude(docket_number='')
        .values('docket_number').annotate(_c=Count('id')).filter(_c__gt=1).count()
    )

    # Period: fetch used coupons + their transactions
    _period_used = list(period_qs.filter(using_date__isnull=False).order_by('-using_date').values(
        'pk', 'docket_number', 'face_value', 'using_shop'
    ))
    _period_dockets = [c['docket_number'] for c in _period_used if c['docket_number']]
    _txn_period = {
        t['invoice_number']: t
        for t in SalesTransaction.objects.filter(invoice_number__in=_period_dockets)
        .values('invoice_number', 'sales_amount')
    }

    # Period duplicate count
    _dup_period_count = (
        period_qs.filter(using_date__isnull=False, docket_number__isnull=False)
        .exclude(docket_number='')
        .values('docket_number').annotate(_c=Count('id')).filter(_c__gt=1).count()
    )

    # Accumulate period amounts + by_shop
    period_amount = Decimal(0)
    period_coupon_amount = Decimal(0)
    period_unique_amount = Decimal(0)
    _seen_period = set()
    shop_data: dict = {}

    from App.analytics.coupon_analytics import resolve_invoice_amount
    for c in _period_used:
        _txn = _txn_period.get(c['docket_number']) if c['docket_number'] else None
        inv_amount = resolve_invoice_amount(
            _txn['sales_amount'] if _txn else None, c['face_value'],
            falsy_uses_face_value=True,
        )
        coupon_amt = calc_coupon_amount(c['face_value'], inv_amount)
        period_amount += inv_amount
        period_coupon_amount += coupon_amt
        dk = c['docket_number'] or f'__pk{c["pk"]}'
        if dk not in _seen_period:
            _seen_period.add(dk)
            period_unique_amount += inv_amount
        shop = c['using_shop'] or 'Unknown'
        if shop not in shop_data:
            shop_data[shop] = {
                'total': 0, 'used': 0,
                'amount': Decimal(0), 'coupon_amount': Decimal(0),
                'unique_amount': Decimal(0), 'seen_dockets': set(),
            }
        shop_data[shop]['used'] += 1
        shop_data[shop]['amount'] += inv_amount
        shop_data[shop]['coupon_amount'] += coupon_amt
        if dk not in shop_data[shop]['seen_dockets']:
            shop_data[shop]['seen_dockets'].add(dk)
            shop_data[shop]['unique_amount'] += inv_amount

    # Add unused coupon counts per shop (aggregate — no row fetch)
    for _row in (
        period_qs.filter(using_date__isnull=True)
        .values('using_shop').annotate(_cnt=Count('id'))
    ):
        shop = _row['using_shop'] or 'Unknown'
        if shop not in shop_data:
            shop_data[shop] = {
                'total': 0, 'used': 0,
                'amount': Decimal(0), 'coupon_amount': Decimal(0),
                'unique_amount': Decimal(0), 'seen_dockets': set(),
            }
        shop_data[shop]['total'] += _row['_cnt']

    for sd in shop_data.values():
        sd['total'] += sd['used']

    shop_stats = sorted([
        {
            'shop_name': sn,
            'total': sd['total'],
            'used': sd['used'],
            'unused': sd['total'] - sd['used'],
            'used_pct_of_used': round(sd['used'] / period_used * 100 if period_used else 0, 2),
            'usage_rate': round(sd['used'] / sd['total'] * 100 if sd['total'] else 0, 2),
            'total_amount': float(sd['unique_amount']),
            'coupon_amount': float(sd['coupon_amount']),
        }
        for sn, sd in shop_data.items()
    ], key=lambda x: x['used'], reverse=True)

    return {
        'all_time': {
            'total': all_time_total,
            'used': all_time_used,
            'unused': all_time_unused,
            'used_pct': round(all_time_used / all_time_total * 100, 2) if all_time_total else 0,
            'unused_pct': round(all_time_unused / all_time_total * 100, 2) if all_time_total else 0,
            'usage_rate': all_time_usage_rate,
            'total_amount': float(all_time_amount),
            'total_coupon_amount': float(all_time_coupon_amount),
            'unique_invoice_amount': float(all_time_unique_amount),
            'duplicate_invoice_count': _dup_all_count,
        },
        'period': {
            'total': period_total,
            'used': period_used,
            'unused': period_unused,
            'used_pct': round(period_used / period_total * 100, 2) if period_total else 0,
            'unused_pct': round(period_unused / period_total * 100, 2) if period_total else 0,
            'usage_rate': period_usage_rate,
            'total_amount': float(period_amount),
            'total_coupon_amount': float(period_coupon_amount),
            'unique_invoice_amount': float(period_unique_amount),
            'duplicate_invoice_count': _dup_period_count,
        },
        'by_shop': shop_stats,
    }


def _coupon_detail_tab(date_from, date_to, coupon_id_prefix, shop_group):
    """
    Lean function for the Detail tab.
    Fetches: period used coupons, their transactions, customers, CNV enrichment.
    Does NOT load: all_time amounts loop, by_shop grouping, unused coupon counts.
    """
    from App.models import Customer as _Cust
    from App.cnv.models import CNVCustomer
    from App.analytics.coupon_analytics import calc_coupon_amount, format_face_value

    _, period_qs = _build_coupon_qs(coupon_id_prefix, shop_group, date_from, date_to)

    # Duplicate detection for is_duplicate flag (aggregate, no row fetch)
    _dup_set = set(
        period_qs.filter(using_date__isnull=False, docket_number__isnull=False)
        .exclude(docket_number='')
        .values('docket_number').annotate(_c=Count('id')).filter(_c__gt=1)
        .values_list('docket_number', flat=True)
    )

    # Fetch period used coupons (all fields needed for details)
    _period_used = list(
        period_qs.filter(using_date__isnull=False).order_by('-using_date')
    )
    if not _period_used:
        return {'details': []}

    _dockets = [c.docket_number for c in _period_used if c.docket_number]

    # Bulk-fetch transactions
    _txn_map = {
        t.invoice_number: t
        for t in SalesTransaction.objects.filter(invoice_number__in=_dockets).order_by()
    }

    # Bulk-fetch customers for vip_ids in those transactions
    _vip_ids = {
        t.vip_id for t in _txn_map.values()
        if t.vip_id and t.vip_id != '0'
    }
    _cust_map = {c.vip_id: c for c in _Cust.objects.filter(vip_id__in=_vip_ids).order_by()}

    # Build details list
    coupon_details = []
    for coupon in _period_used:
        vip_id = coupon.member_id or None
        vip_name = coupon.member_name or None
        phone = coupon.member_phone or None
        sales_date = None
        inv_shop = None
        inv_amount = None
        note = None

        if coupon.docket_number:
            txn = _txn_map.get(coupon.docket_number)
            if txn:
                if not vip_id:
                    vip_id = txn.vip_id
                if not vip_name and txn.vip_id and txn.vip_id != '0':
                    cust = _cust_map.get(txn.vip_id)
                    if cust:
                        vip_name = cust.name
                        phone = cust.phone
                    else:
                        vip_name = txn.vip_name
                sales_date = txn.sales_date
                inv_shop = txn.shop_name
                inv_amount = txn.sales_amount
                if coupon.using_shop and inv_shop and coupon.using_shop != inv_shop:
                    note = f'Shop mismatch: Coupon@{coupon.using_shop} vs Invoice@{inv_shop}'
            else:
                note = f'Invoice {coupon.docket_number} not found'

        final_amount = inv_amount or coupon.face_value or Decimal(0)
        coupon_amt = calc_coupon_amount(coupon.face_value, final_amount)
        dk = coupon.docket_number or f'__pk{coupon.pk}'
        is_duplicate = dk in _dup_set and bool(coupon.docket_number)

        coupon_details.append({
            'coupon_id': coupon.coupon_id,
            'creator': coupon.creator or '',
            'face_value': coupon.face_value or 0,
            'face_value_display': format_face_value(coupon.face_value),
            'using_shop': coupon.using_shop or 'Unknown',
            'using_date': coupon.using_date,
            'docket_number': coupon.docket_number or '',
            'vip_id': vip_id or '',
            'customer_name': vip_name or '-',
            'customer_phone': phone or '-',
            'sales_day': sales_date,
            'inv_shop': inv_shop or '-',
            'amount': float(final_amount),
            'coupon_amount': float(coupon_amt),
            'is_duplicate': is_duplicate,
            'note': note or '',
        })

    # CNV enrichment (single bulk query)
    phones = {
        d['customer_phone'] for d in coupon_details
        if d['customer_phone'] and d['customer_phone'] != '-'
    }
    _cnv_map = {
        c['phone']: c
        for c in CNVCustomer.objects.filter(phone__in=phones)
        .values('phone', 'cnv_id', 'points', 'total_points')
    }
    for d in coupon_details:
        cnv = _cnv_map.get(d['customer_phone'])
        if cnv:
            d['cnv_id'] = cnv['cnv_id']
            d['cnv_points'] = cnv['points']
            d['cnv_total_points'] = cnv['total_points']
        else:
            d['cnv_id'] = ''
            d['cnv_points'] = ''
            d['cnv_total_points'] = ''

    return {'details': coupon_details}


def _coupon_duplicates_tab(date_from, date_to, coupon_id_prefix, shop_group):
    """
    Lean function for the Duplicates tab.
    Fetches: only duplicate invoice coupons + their transactions.
    Does NOT load: all_time data, customer enrichment, by_shop, details list.
    """
    from App.analytics.coupon_analytics import calc_coupon_amount, format_face_value

    _, period_qs = _build_coupon_qs(coupon_id_prefix, shop_group, date_from, date_to)

    # Detect duplicate dockets
    _dup_dockets = set(
        period_qs.filter(using_date__isnull=False, docket_number__isnull=False)
        .exclude(docket_number='')
        .values('docket_number').annotate(_c=Count('id')).filter(_c__gt=1)
        .values_list('docket_number', flat=True)
    )

    if not _dup_dockets:
        return {'duplicate_invoices': []}

    # Fetch only duplicate coupons (not all period coupons)
    _dup_coupons = list(
        period_qs.filter(using_date__isnull=False, docket_number__in=_dup_dockets)
        .order_by('docket_number', 'coupon_id')
    )

    # Fetch only those transactions
    _txn_map = {
        t['invoice_number']: t
        for t in SalesTransaction.objects.filter(invoice_number__in=_dup_dockets)
        .values('invoice_number', 'sales_amount', 'shop_name', 'sales_date')
    }

    # Pre-group by docket to avoid O(N×M) scan per docket
    _by_docket: dict = {}
    for c in _dup_coupons:
        _by_docket.setdefault(c.docket_number, []).append(c)

    duplicate_invoices = []
    for docket in sorted(_dup_dockets):
        coupons_for_docket = _by_docket.get(docket, [])
        txn = _txn_map.get(docket)
        if txn:
            inv_amount = txn['sales_amount'] or Decimal(0)
            shop_name = txn['shop_name'] or ''
            sales_date = txn['sales_date']
        else:
            inv_amount = Decimal(0)
            shop_name = ''
            sales_date = None
        for c in coupons_for_docket:
            duplicate_invoices.append({
                'docket_number': docket,
                'coupon_id': c.coupon_id,
                'face_value_display': format_face_value(c.face_value),
                'coupon_amount': float(calc_coupon_amount(c.face_value, inv_amount)),
                'using_date': c.using_date,
                'using_shop': c.using_shop or '',
                'inv_amount': float(inv_amount),
                'shop_name': shop_name,
                'sales_date': sales_date,
                'member_id': c.member_id or '',
                'member_name': c.member_name or '',
                'member_phone': c.member_phone or '',
            })

    return {'duplicate_invoices': duplicate_invoices}


