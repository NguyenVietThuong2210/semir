"""
App/analytics/tab_functions.py
──────────────────────────────
Per-tab data functions for lazy AJAX tab loading.

Each function runs ONLY the computation needed for that tab.
No excess queries, no unused data — every function fetches exactly what it needs.

Sales tabs:    get_sales_tab(tab, date_from, date_to, shop_group)
Coupon tabs:   get_coupon_tab(tab, date_from, date_to, prefix, shop_group)
Customer tabs: get_customer_tab(tab, start_date, end_date)

Tab name constants match the template tab IDs.
"""
from datetime import date as _date
from decimal import Decimal

from django.db.models import Count, Q

from App.models import Customer, SalesTransaction
from .calculations import calculate_return_visits
from .customer_utils import get_customer_info, build_customer_purchase_map, normalize_grade, _norm_vid
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

# ── Internal shared loader ────────────────────────────────────────────────────

def _load_sales(date_from=None, date_to=None, shop_group=None):
    """
    Fetch sales + build customer_purchases map.
    Returns (customer_purchases, customer_info_fn, date_stats) or (None, None, None).

    Result is cached for 5 minutes per (date_from, date_to, shop_group) combination so
    that clicking through tabs in the same session reuses the same dataset.
    """
    from django.core.cache import cache as _djc
    _key = f"sales_load:{date_from}:{date_to}:{shop_group}"
    hit = _djc.get(_key)
    if hit is not None:
        cp, info_map, date_stats = hit
        def _ci_cached(vip_id, customer_obj=None):
            c = info_map.get(vip_id)
            return c if c is not None else get_customer_info(vip_id, customer_obj)
        return cp, _ci_cached, date_stats

    # 5 fields only — no customer JOIN (JOIN on 118K rows is the main bottleneck).
    # Customer info is fetched in a separate 74K-row direct table scan below.
    FIELDS = ('vip_id', 'sales_date', 'invoice_number', 'sales_amount', 'shop_name')
    qs = SalesTransaction.objects.values(*FIELDS).order_by()
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

    sales_list = list(qs)
    if not sales_list:
        return None, None, None

    date_stats = {
        'start_date': min(s['sales_date'] for s in sales_list),
        'end_date':   max(s['sales_date'] for s in sales_list),
    }

    customer_purchases = build_customer_purchase_map(sales_list)
    del sales_list

    # Build info_map from Customer table directly — simple 74K-row scan, no JOIN.
    # Much faster than the previous approach of joining 118K sales rows to customer.
    from App.models import Customer as _Cust
    info_map = {
        _norm_vid(str(c['vip_id'])): (
            normalize_grade(c['vip_grade']),
            c['registration_date'],
            c['name'] or 'Unknown',
        )
        for c in _Cust.objects
        .filter(vip_id__isnull=False)
        .exclude(vip_id=0)
        .values('vip_id', 'vip_grade', 'registration_date', 'name')
        if c['vip_id']
    }

    _djc.set(_key, (customer_purchases, info_map, date_stats), timeout=300)

    def _ci_fresh(vip_id, customer_obj=None):
        c = info_map.get(vip_id)
        return c if c is not None else get_customer_info(vip_id, customer_obj)

    return customer_purchases, _ci_fresh, date_stats


# ── Shared helpers ───────────────────────────────────────────────────────────

def _group_periods(by_shop, period_keys, sub_key, match_key, label_fn=None):
    """
    Invert by_shop list into period-first grouping.

    by_shop:     list of shop dicts each with a sub_key array
    period_keys: ordered list of period identifiers to iterate
    sub_key:     key in each shop dict ('by_session', 'by_month', 'by_week', 'by_grade')
    match_key:   field in each sub-row that matches period_keys ('session', 'month', 'week_sort', 'grade')
    label_fn:    optional callable(row) → display label (e.g. lambda r: r['week_label'])

    Returns list of {'label': str, 'shops': [{shop_name, ...row fields}]}
    """
    result = []
    for pk in period_keys:
        shops = []
        label = pk
        for sh in by_shop:
            for row in sh.get(sub_key, []):
                if row.get(match_key) == pk:
                    if label_fn is not None and label == pk:
                        label = label_fn(row)
                    shops.append({'shop_name': sh['shop_name'], **row})
                    break
        result.append({'label': label, 'shops': shops})
    return result


def _group_flat_by_period(flat, label_key='label'):
    """
    Group a flat cross list (e.g. season_shop) by period label key.

    Returns list of {'label': str, 'shops': [row, ...]} preserving order.
    """
    seen: dict = {}
    order: list = []
    for row in flat:
        lbl = row[label_key]
        if lbl not in seen:
            seen[lbl] = []
            order.append(lbl)
        seen[lbl].append(row)
    return [{'label': lbl, 'shops': seen[lbl]} for lbl in order]


# ── Sales per-tab functions ───────────────────────────────────────────────────

SALES_TABS = (
    'grade', 'season', 'month', 'week', 'shop',
    'grade_allshops', 'season_allshops', 'month_allshops', 'week_allshops',
)


def get_sales_tab(tab: str, date_from=None, date_to=None, shop_group=None) -> dict | None:
    """
    Compute data for a single Sales Analytics tab.

    For tab='grade': also returns overview, date_range, session_label,
    buyer_without_info_stats — all data needed for the initial page render.

    Args:
        tab: one of SALES_TABS
        date_from / date_to: optional date filter
        shop_group: optional shop group filter

    Returns:
        Dict with tab-specific data, or None if no data.
    """
    cp, ci, date_stats = _load_sales(date_from, date_to, shop_group)
    if cp is None:
        return None

    if tab == 'grade':
        return _sales_grade_with_overview(cp, ci, date_stats, date_from, date_to, shop_group)

    if tab == 'season':
        return {'by_session': aggregate_by_season(cp, ci)}

    if tab == 'month':
        return {'by_month': aggregate_by_month(cp, ci)}

    if tab == 'week':
        return {'by_week': aggregate_by_week(cp, ci)}

    if tab == 'shop':
        all_sk, all_mk, all_yk, all_wk = _get_period_keys(cp)
        return {'by_shop': aggregate_by_shop(cp, ci, all_sk, all_mk, all_yk, all_wk)}

    if tab == 'grade_allshops':
        details = _build_customer_details(cp, ci, date_from, date_to)
        all_sk, all_mk, all_yk, all_wk = _get_period_keys(cp)
        by_shop = aggregate_by_shop(cp, ci, all_sk, all_mk, all_yk, all_wk)
        by_grade = aggregate_by_grade(details)
        grade_keys = [g['grade'] for g in by_grade]
        return {
            'by_grade': by_grade,
            'by_shop': by_shop,
            'periods_by_grade': _group_periods(by_shop, grade_keys, 'by_grade', 'grade'),
        }

    if tab == 'season_allshops':
        all_sk, all_mk, all_yk, all_wk = _get_period_keys(cp)
        by_shop = aggregate_by_shop(cp, ci, all_sk, all_mk, all_yk, all_wk)
        return {
            'by_session': aggregate_by_season(cp, ci),
            'by_shop': by_shop,
            'periods_by_season': _group_periods(by_shop, all_sk, 'by_session', 'session'),
        }

    if tab == 'month_allshops':
        all_sk, all_mk, all_yk, all_wk = _get_period_keys(cp)
        by_shop = aggregate_by_shop(cp, ci, all_sk, all_mk, all_yk, all_wk)
        return {
            'by_month': aggregate_by_month(cp, ci),
            'by_shop': by_shop,
            'periods_by_month': _group_periods(by_shop, all_mk, 'by_month', 'month'),
        }

    if tab == 'week_allshops':
        all_sk, all_mk, all_yk, all_wk = _get_period_keys(cp)
        by_shop = aggregate_by_shop(cp, ci, all_sk, all_mk, all_yk, all_wk)
        return {
            'by_week': aggregate_by_week(cp, ci),
            'by_shop': by_shop,
            'periods_by_week': _group_periods(
                by_shop, all_wk, 'by_week', 'week_sort',
                label_fn=lambda r: r['week_label'],
            ),
        }

    raise ValueError(f"Unknown sales tab: {tab!r}")


def _sales_grade_with_overview(customer_purchases, get_ci, date_stats, date_from, date_to, shop_group):
    """
    Compute grade tab data PLUS all overview metrics needed for the initial page render.
    Runs overview metrics and grade aggregation in one pass through customer_purchases.
    """
    from django.db.models import Sum as _Sum

    period_lo = date_from or date_stats['start_date']
    period_hi = date_to or date_stats['end_date']

    # Extra DB queries: total customers + all-time active (cheap aggregate queries)
    total_customers_in_db = Customer.objects.count()
    member_active_all_time = (
        SalesTransaction.objects
        .exclude(Q(vip_id='') | Q(vip_id='0') | Q(vip_id__isnull=True))
        .values('vip_id').distinct().count()
    )
    member_inactive_all_time = max(0, total_customers_in_db - member_active_all_time)

    # VIP0 all-time stats (single aggregate, no row fetch)
    _vip0_q = Q(vip_id='') | Q(vip_id='0') | Q(vip_id__isnull=True)
    _vip0_agg = SalesTransaction.objects.filter(_vip0_q).aggregate(
        cnt=Count('id'), total=_Sum('sales_amount')
    )
    vip0_alltime_invoices = _vip0_agg['cnt'] or 0
    vip0_alltime_amount = float(_vip0_agg['total'] or 0)

    # Single-pass: build customer_details + accumulate overview metrics
    returning_customers = set()
    new_members_count = 0
    customer_details = []
    total_amount_period = Decimal(0)
    returning_invoices = 0
    returning_amount = Decimal(0)
    total_invoices_without_vip0 = 0

    vip_0_purchases = customer_purchases.get('0', [])
    vip_0_amount = sum(p['amount'] for p in vip_0_purchases)

    for vip_id, purchases in customer_purchases.items():
        if vip_id == '0':
            continue
        grade, reg_date, name = get_ci(vip_id, purchases[0]['customer'])
        rc, is_ret = calculate_return_visits(purchases, reg_date)
        n = len(purchases)
        amt = sum(p['amount'] for p in purchases)
        total_amount_period += amt
        total_invoices_without_vip0 += n
        if is_ret:
            returning_customers.add(vip_id)
            returning_invoices += n
            returning_amount += amt
        if reg_date and period_lo <= reg_date <= period_hi:
            new_members_count += 1
        customer_details.append({
            'vip_id': vip_id,
            'name': name,
            'vip_grade': grade,
            'registration_date': reg_date,
            'first_purchase_date': purchases[0]['date'],
            'total_purchases': n,
            'return_visits': rc,
            'total_spent': float(amt),
        })

    total_active = len(customer_details)
    total_returning = len(returning_customers)
    return_rate_p = round(total_returning / total_active * 100, 2) if total_active else 0
    return_rate_at = round(total_returning / total_customers_in_db * 100, 2) if total_customers_in_db else 0
    total_invoices_with_vip0 = total_invoices_without_vip0 + len(vip_0_purchases)
    total_amount_with_vip0 = total_amount_period + vip_0_amount

    buyer_without_info_stats = calculate_buyer_without_info(
        vip_0_purchases, vip0_alltime_invoices, vip0_alltime_amount,
        date_from, date_to, total_invoices_with_vip0, float(total_amount_with_vip0),
    )

    customer_details.sort(key=lambda x: x['return_visits'], reverse=True)

    return {
        'by_grade': aggregate_by_grade(customer_details),
        'overview': {
            'active_customers': total_active,
            'returning_customers': total_returning,
            'return_rate': return_rate_p,
            'return_rate_all_time': return_rate_at,
            'returning_invoices': returning_invoices,
            'returning_amount': float(returning_amount),
            'total_amount_period': float(total_amount_period),
            'buyer_without_info': len(vip_0_purchases),
            'new_members_in_period': new_members_count,
            'total_customers_in_db': total_customers_in_db,
            'member_active_all_time': member_active_all_time,
            'member_inactive_all_time': member_inactive_all_time,
            'total_invoices_without_vip0': total_invoices_without_vip0,
            'total_amount_without_vip0': float(total_amount_period),
            'total_invoices_with_vip0': total_invoices_with_vip0,
            'total_amount_with_vip0': float(total_amount_with_vip0),
        },
        'date_range': {'start': date_stats['start_date'], 'end': date_stats['end_date']},
        'session_label': get_session_for_range(date_from, date_to),
        'customer_details': customer_details[:100],
        'total_detail_count': len(customer_details),
        'buyer_without_info_stats': buyer_without_info_stats,
    }


def _get_period_keys(customer_purchases):
    """
    Collect all unique season/month/year/week keys from customer_purchases in a single pass.
    Returns (all_sk, all_mk, all_yk, all_wk) — ready for aggregate_by_shop().

    Replaces running 4 full aggregations just to extract sort keys.
    """
    from .season_utils import get_session_key, get_month_key, get_week_info
    sk, mk, yk, wk = set(), set(), set(), set()
    for purchases in customer_purchases.values():
        for p in purchases:
            d = p['date']
            sk.add(get_session_key(d))
            mk.add(get_month_key(d))
            yk.add(str(d.year))
            ws, _ = get_week_info(d)
            wk.add(ws)
    return (
        sorted(sk, key=session_sort_key),
        sorted(mk, key=month_sort_key),
        sorted(yk, key=year_sort_key),
        sorted(wk, key=week_sort_key),
    )


def _build_customer_details(customer_purchases, get_customer_info_fn, date_from, date_to):
    """Build customer_details list (needed for grade aggregation)."""
    details = []
    for vip_id, purchases in customer_purchases.items():
        if vip_id == '0':
            continue
        grade, reg_date, name = get_customer_info_fn(vip_id, purchases[0]['customer'])
        rc, _ = calculate_return_visits(purchases, reg_date)
        details.append({
            'vip_id': vip_id,
            'name': name,
            'vip_grade': grade,
            'registration_date': reg_date,
            'first_purchase_date': purchases[0]['date'],
            'total_purchases': len(purchases),
            'return_visits': rc,
            'total_spent': float(sum(p['amount'] for p in purchases)),
        })
    return details


# ── Coupon per-tab functions ──────────────────────────────────────────────────

COUPON_TABS = ('shop', 'detail', 'duplicates')


def _build_coupon_qs(coupon_id_prefix=None, shop_group=None, date_from=None, date_to=None):
    """
    Build base Coupon queryset with shop_group + prefix filters applied.
    Returns (qs, period_qs).
    """
    from App.models import Coupon
    qs = Coupon.objects.all()

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

    # All-time amounts: fetch used coupons + their transactions
    _all_used = list(qs.filter(using_date__isnull=False).values(
        'pk', 'docket_number', 'face_value'
    ))
    _all_dockets = [c['docket_number'] for c in _all_used if c['docket_number']]
    _txn_all = {
        t['invoice_number']: t
        for t in SalesTransaction.objects.filter(invoice_number__in=_all_dockets)
        .values('invoice_number', 'sales_amount')
    }

    all_time_amount = Decimal(0)
    all_time_coupon_amount = Decimal(0)
    all_time_unique_amount = Decimal(0)
    _seen_all = set()
    for c in _all_used:
        _txn = _txn_all.get(c['docket_number']) if c['docket_number'] else None
        inv_amount = (
            Decimal(str(_txn['sales_amount'])) if _txn and _txn['sales_amount'] else None
        ) or c['face_value'] or Decimal(0)
        all_time_amount += inv_amount
        all_time_coupon_amount += calc_coupon_amount(c['face_value'], inv_amount)
        dk = c['docket_number'] or f'__pk{c["pk"]}'
        if dk not in _seen_all:
            _seen_all.add(dk)
            all_time_unique_amount += inv_amount

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

    for c in _period_used:
        _txn = _txn_period.get(c['docket_number']) if c['docket_number'] else None
        inv_amount = (
            Decimal(str(_txn['sales_amount'])) if _txn and _txn['sales_amount'] else None
        ) or c['face_value'] or Decimal(0)
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

    duplicate_invoices = []
    for docket in sorted(_dup_dockets):
        coupons_for_docket = [c for c in _dup_coupons if c.docket_number == docket]
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


# ── Customer per-tab functions ────────────────────────────────────────────────

# Session A — Registration Breakdown (7 tabs)
BD_TABS = ('bd_season', 'bd_month', 'bd_week', 'bd_shop',
           'bd_season_allshops', 'bd_month_allshops', 'bd_week_allshops')

# Session B — Customer Analytics (3 tabs)
CA_TABS = ('ca_points', 'ca_zalo', 'ca_pos_cnv')

CUSTOMER_TABS = BD_TABS + CA_TABS


def _parse_cnv_period_filter(start_date, end_date):
    """Delegate to service layer."""
    from App.cnv.service import parse_cnv_period_filter
    return parse_cnv_period_filter(start_date, end_date)


def get_customer_tab(tab: str, start_date: str = '', end_date: str = '') -> dict:
    """
    Compute data for a single Customer Analytics tab.
    Each tab fetches ONLY the data it needs — no excess queries.

    Args:
        tab: one of CUSTOMER_TABS
        start_date / end_date: 'YYYY-MM-DD' strings ('' = all-time)

    Returns:
        Dict with tab-specific data.
    """
    # Session A — Registration Breakdown
    if tab in BD_TABS:
        return _customer_bd_tab(tab, start_date, end_date)

    # Session B — Customer Analytics
    if tab == 'ca_points':
        return _customer_ca_points(start_date, end_date)
    if tab == 'ca_zalo':
        return _customer_ca_zalo(start_date, end_date)
    if tab == 'ca_pos_cnv':
        return _customer_ca_pos_cnv(start_date, end_date)

    raise ValueError(f"Unknown customer tab: {tab!r}")


def _get_cnv_phone_sets():
    """Delegate to service layer."""
    from App.cnv.service import get_cnv_phone_sets
    return get_cnv_phone_sets()


_BD_DIMS = {
    'bd_season':          frozenset({'season'}),
    'bd_month':           frozenset({'month'}),
    'bd_week':            frozenset({'week'}),
    'bd_shop':            frozenset({'shop', 'season_shop', 'month_shop', 'week', 'week_shop'}),
    'bd_season_allshops': frozenset({'season_shop'}),
    'bd_month_allshops':  frozenset({'month_shop'}),
    'bd_week_allshops':   frozenset({'week', 'week_shop'}),
}


def _customer_bd_tab(tab: str, start_date: str, end_date: str) -> dict:
    """
    Lean function for BD breakdown tabs.
    Fetches: phone sets + _compute_cnv_breakdown only.
    Does NOT compute: pos_only_all lists, cnv_only_all lists,
    points_mismatch, zalo stats, period POS/CNV lists.
    """
    from App.cnv.service import compute_cnv_breakdown

    period_filter, _ = _parse_cnv_period_filter(start_date, end_date)
    pos_phones_all, cnv_phones_all = _get_cnv_phone_sets()
    bd = compute_cnv_breakdown(period_filter, pos_phones_all, cnv_phones_all, dims=_BD_DIMS[tab])

    if tab == 'bd_season':
        return {'by_season': bd['season']}
    if tab == 'bd_month':
        return {'by_month': bd['month']}
    if tab == 'bd_week':
        return {'by_week': bd['week']}
    if tab == 'bd_shop':
        return {'by_shop': bd['shop'], 'shop_detail': bd['shop_detail']}
    if tab == 'bd_season_allshops':
        return {
            'season_shop': bd['season_shop'],
            'shop_season': bd['shop_season'],
            'period_season': _group_flat_by_period(bd['season_shop']),
        }
    if tab == 'bd_month_allshops':
        return {
            'month_shop': bd['month_shop'],
            'shop_month': bd['shop_month'],
            'period_month': _group_flat_by_period(bd['month_shop']),
        }
    if tab == 'bd_week_allshops':
        return {
            'week_shop': bd['week_shop'],
            'shop_week': bd['shop_week'],
            'period_week': _group_flat_by_period(bd['week_shop']),
        }
    raise ValueError(f"Unknown BD tab: {tab!r}")


def _customer_ca_points(start_date: str, end_date: str) -> dict:
    """
    Lean function for ca_points tab.
    Fetches: CNV customers with used_points > 0, pos_phones for in_pos flag.
    Does NOT compute: breakdown, zalo, pos_only/cnv_only lists, points_mismatch.
    """
    from App.cnv.models import CNVCustomer

    # pos_phones_all needed only for in_pos flag
    pos_phones_all, _ = _get_cnv_phone_sets()

    _raw = list(
        CNVCustomer.objects.filter(used_points__gt=0)
        .values(
            'cnv_id', 'phone', 'last_name', 'first_name', 'level_name',
            'email', 'cnv_created_at', 'points', 'total_points', 'used_points',
        )
        .order_by('-used_points')
    )
    cnv_used_points_list = [
        {**r, 'in_pos': bool(r['phone']) and r['phone'] in pos_phones_all}
        for r in _raw
    ]
    return {
        'cnv_used_points_count': len(cnv_used_points_list),
        'cnv_used_points_list': cnv_used_points_list,
    }


def _customer_ca_zalo(start_date: str, end_date: str) -> dict:
    """
    Lean function for ca_zalo tab.
    Fetches: zalo counts + zalo lists + pos_phones for in_pos flag.
    Does NOT compute: breakdown, pos_only/cnv_only lists, points_mismatch, used_points.
    """
    from App.cnv.models import CNVCustomer
    from django.db.models import Count as _Count, Q as _Q

    period_filter, _ = _parse_cnv_period_filter(start_date, end_date)

    # All-time zalo counts — single aggregate
    total_cnv_all = CNVCustomer.objects.count()
    _zalo_counts = CNVCustomer.objects.aggregate(
        app=_Count('id', filter=_Q(zalo_app_id__isnull=False) & ~_Q(zalo_app_id='')),
        oa=_Count('id',  filter=_Q(zalo_oa_id__isnull=False)  & ~_Q(zalo_oa_id='')),
    )
    zalo_app_all_count = _zalo_counts['app']
    zalo_oa_all_count  = _zalo_counts['oa']
    zalo_app_all_pct = round(zalo_app_all_count / total_cnv_all * 100, 1) if total_cnv_all else 0
    zalo_oa_all_pct  = round(zalo_oa_all_count  / total_cnv_all * 100, 1) if total_cnv_all else 0

    # Period zalo counts
    zalo_app_period_count = zalo_oa_period_count = 0
    zalo_app_period_pct   = zalo_oa_period_pct   = 0
    if period_filter:
        _pqs = CNVCustomer.objects.filter(
            zalo_app_created_at__gte=period_filter['start'],
            zalo_app_created_at__lte=period_filter['end'],
        )
        _pz = _pqs.aggregate(
            app=_Count('id', filter=_Q(zalo_app_id__isnull=False) & ~_Q(zalo_app_id='')),
            oa=_Count('id',  filter=_Q(zalo_oa_id__isnull=False)  & ~_Q(zalo_oa_id='')),
        )
        zalo_app_period_count = _pz['app']
        zalo_oa_period_count  = _pz['oa']
        zalo_app_period_pct = round(zalo_app_period_count / total_cnv_all * 100, 1) if total_cnv_all else 0
        zalo_oa_period_pct  = round(zalo_oa_period_count  / total_cnv_all * 100, 1) if total_cnv_all else 0

    # Zalo lists + in_pos flag (pos_phones needed only for this)
    pos_phones_all, _ = _get_cnv_phone_sets()

    _zf = (
        'cnv_id', 'phone', 'last_name', 'first_name', 'level_name',
        'email', 'cnv_created_at', 'points', 'zalo_app_id', 'zalo_oa_id', 'zalo_app_created_at',
    )
    zalo_app_qs = CNVCustomer.objects.filter(
        zalo_app_id__isnull=False
    ).exclude(zalo_app_id='')
    zalo_oa_qs = CNVCustomer.objects.filter(
        zalo_oa_id__isnull=False
    ).exclude(zalo_oa_id='')

    zalo_mini_app_list = list(zalo_app_qs.order_by('-zalo_app_created_at').values(*_zf))
    zalo_oa_list       = list(zalo_oa_qs.order_by('-zalo_app_created_at').values(*_zf))

    _all_z_phones = {r['phone'] for r in zalo_mini_app_list + zalo_oa_list if r['phone']}
    _pos_z_phones = _all_z_phones & pos_phones_all
    for r in zalo_mini_app_list:
        r['in_pos'] = r['phone'] in _pos_z_phones
    for r in zalo_oa_list:
        r['in_pos'] = r['phone'] in _pos_z_phones

    return {
        'zalo_app_all_count':    zalo_app_all_count,
        'zalo_oa_all_count':     zalo_oa_all_count,
        'zalo_app_all_pct':      zalo_app_all_pct,
        'zalo_oa_all_pct':       zalo_oa_all_pct,
        'zalo_app_period_count': zalo_app_period_count,
        'zalo_oa_period_count':  zalo_oa_period_count,
        'zalo_app_period_pct':   zalo_app_period_pct,
        'zalo_oa_period_pct':    zalo_oa_period_pct,
        'zalo_mini_app_list':    zalo_mini_app_list,
        'zalo_oa_list':          zalo_oa_list,
    }


def _customer_ca_pos_cnv(start_date: str, end_date: str) -> dict:
    """
    Lean function for ca_pos_cnv tab.
    Fetches: pos_only / cnv_only lists + points mismatch data.
    Does NOT compute: breakdown, zalo, used_points.
    """
    from App.models import Customer as _POS
    from App.cnv.models import CNVCustomer
    from django.db.models import Count as _Count, Q as _Q

    period_filter, has_filter = _parse_cnv_period_filter(start_date, end_date)

    pos_all = (
        _POS.objects.filter(vip_id__isnull=False, phone__isnull=False)
        .exclude(vip_id=0).exclude(phone='')
    )
    cnv_all = CNVCustomer.objects.filter(phone__isnull=False).exclude(phone='')
    _cnv_phone_qs = cnv_all.values('phone')
    _pos_phone_qs = pos_all.values('phone')

    # All-time pos_only + cnv_only lists
    pos_only_all = list(
        pos_all.exclude(phone__in=_cnv_phone_qs)
        .values('vip_id', 'phone', 'name', 'vip_grade', 'email', 'registration_date', 'points')
        .order_by('-registration_date')
    )
    cnv_only_all = list(
        cnv_all.exclude(phone__in=_pos_phone_qs)
        .values(
            'cnv_id', 'phone', 'last_name', 'first_name', 'level_name',
            'email', 'cnv_created_at', 'points', 'total_points', 'used_points',
        )
        .order_by('-cnv_created_at')
    )

    # Period lists
    pos_only_period = []
    cnv_only_period = []
    pos_only_period_count = cnv_only_period_count = 0
    new_pos_count = new_cnv_count = 0
    new_pos_inv_count = new_pos_no_inv_count = 0

    if has_filter:
        pos_period = pos_all.filter(
            registration_date__gte=period_filter['start'],
            registration_date__lte=period_filter['end'],
        )
        new_pos_count = pos_period.count()
        _pos_period_phones = set(pos_period.values_list('phone', flat=True))

        from App.models import SalesTransaction as _ST
        _inv_qs = (
            _ST.objects
            .filter(
                sales_date__gte=period_filter['start'].date(),
                sales_date__lte=period_filter['end'].date(),
            )
            .exclude(vip_id__isnull=True).exclude(vip_id='').exclude(vip_id='0')
        )
        _pks_wi_qs  = _inv_qs.filter(customer__isnull=False).values('customer_id')
        _vids_wi_qs = _inv_qs.values('vip_id')
        _inv_phones = set(
            _POS.objects
            .filter(_Q(id__in=_pks_wi_qs) | _Q(vip_id__in=_vids_wi_qs))
            .exclude(phone__isnull=True).exclude(phone='')
            .values_list('phone', flat=True)
        )
        new_pos_inv_count    = len(_pos_period_phones & _inv_phones)
        new_pos_no_inv_count = new_pos_count - new_pos_inv_count

        cnv_period = cnv_all.filter(
            cnv_created_at__gte=period_filter['start'],
            cnv_created_at__lte=period_filter['end'],
        )
        new_cnv_count = cnv_period.count()

        pos_only_period_qs = pos_period.exclude(phone__in=_cnv_phone_qs)
        pos_only_period_count = pos_only_period_qs.count()
        pos_only_period = list(
            pos_only_period_qs
            .values('vip_id', 'phone', 'name', 'vip_grade', 'email', 'registration_date', 'points')
            .order_by('-registration_date')
        )
        cnv_only_period_qs = cnv_period.exclude(phone__in=_pos_phone_qs)
        cnv_only_period_count = cnv_only_period_qs.count()
        cnv_only_period = list(
            cnv_only_period_qs
            .values(
                'cnv_id', 'phone', 'last_name', 'first_name', 'level_name',
                'email', 'cnv_created_at', 'points', 'total_points', 'used_points',
            )
            .order_by('-cnv_created_at')
        )

    # Points mismatch — SQL join avoids >65535 param limit
    _pos_map = {
        c['phone']: c
        for c in pos_all.filter(phone__in=_cnv_phone_qs)
        .values('vip_id', 'phone', 'name', 'vip_grade', 'points', 'used_points')
    }
    _cnv_map = {
        c['phone']: c
        for c in cnv_all.filter(phone__in=_pos_phone_qs)
        .values(
            'cnv_id', 'phone', 'last_name', 'first_name', 'level_name',
            'points', 'total_points', 'used_points',
        )
    }
    points_mismatch = []
    total_points_mismatch = []
    for phone, pos_c in _pos_map.items():
        cnv_c = _cnv_map.get(phone)
        if not cnv_c:
            continue
        pos_pts  = int(pos_c.get('points') or 0)
        pos_used = int(pos_c.get('used_points') or 0)
        pos_net  = pos_pts - pos_used
        cnv_pts  = int(cnv_c.get('points') or 0)
        cnv_total = int(float(cnv_c.get('total_points') or 0))
        base = {
            'phone':          phone,
            'pos_vip_id':     pos_c['vip_id'],
            'pos_name':       pos_c['name'],
            'pos_grade':      pos_c['vip_grade'],
            'pos_points':     pos_pts,
            'pos_used_points': pos_used,
            'pos_net_points': pos_net,
            'cnv_id':         cnv_c['cnv_id'],
            'cnv_name':       f"{cnv_c.get('last_name') or ''} {cnv_c.get('first_name') or ''}".strip(),
            'cnv_level':      cnv_c['level_name'],
            'cnv_points':     cnv_pts,
            'cnv_total_points': cnv_c.get('total_points') or 0,
            'cnv_used_points':  cnv_c.get('used_points') or 0,
        }
        if pos_net != cnv_pts:
            points_mismatch.append({**base, 'diff': cnv_pts - pos_net})
        if pos_net != cnv_total:
            total_points_mismatch.append({**base, 'diff': cnv_total - pos_net})
    points_mismatch.sort(key=lambda x: abs(x['diff']), reverse=True)
    total_points_mismatch.sort(key=lambda x: abs(x['diff']), reverse=True)

    return {
        'pos_only_all':              pos_only_all,
        'cnv_only_all':              cnv_only_all,
        'pos_only_period':           pos_only_period,
        'cnv_only_period':           cnv_only_period,
        'pos_only_all_count':        len(pos_only_all),
        'cnv_only_all_count':        len(cnv_only_all),
        'pos_only_period_count':     pos_only_period_count,
        'cnv_only_period_count':     cnv_only_period_count,
        'new_pos_count':             new_pos_count,
        'new_pos_inv_count':         new_pos_inv_count,
        'new_pos_no_inv_count':      new_pos_no_inv_count,
        'new_cnv_count':             new_cnv_count,
        'points_mismatch':           points_mismatch,
        'points_mismatch_count':     len(points_mismatch),
        'total_points_mismatch':     total_points_mismatch,
        'total_points_mismatch_count': len(total_points_mismatch),
    }
