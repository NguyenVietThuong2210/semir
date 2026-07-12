"""
App/analytics/sales_tabs.py
Sales analytics tabs: get_sales_tab + shared _load_sales loader.
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

    # A-05: cache a plain dict — locmem stores by reference, and a cached
    # defaultdict would grow phantom keys if any future caller subscripts a
    # missing vip_id, silently corrupting the cache for the whole TTL.
    customer_purchases = dict(customer_purchases)
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

def _get_cached_by_shop(cp, ci, date_from, date_to, shop_group):
    """Return (by_shop, all_sk, all_mk, all_yk, all_wk), cached per filter combo."""
    from django.core.cache import cache as _djc
    _key = f"sales_by_shop:{date_from}:{date_to}:{shop_group}"
    hit = _djc.get(_key)
    if hit is not None:
        return hit
    all_sk, all_mk, all_yk, all_wk = _get_period_keys(cp)
    by_shop = aggregate_by_shop(cp, ci, all_sk, all_mk, all_yk, all_wk)
    result = (by_shop, all_sk, all_mk, all_yk, all_wk)
    _djc.set(_key, result, timeout=300)
    return result


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
        return _sales_grade_with_overview(cp, ci, date_stats, date_from, date_to)

    if tab == 'season':
        return {'by_session': aggregate_by_season(cp, ci)}

    if tab == 'month':
        return {'by_month': aggregate_by_month(cp, ci)}

    if tab == 'week':
        return {'by_week': aggregate_by_week(cp, ci)}

    if tab == 'shop':
        by_shop, all_sk, all_mk, all_yk, all_wk = _get_cached_by_shop(cp, ci, date_from, date_to, shop_group)
        return {'by_shop': by_shop}

    if tab == 'grade_allshops':
        details = _build_customer_details(cp, ci, date_from, date_to)
        by_shop, all_sk, all_mk, all_yk, all_wk = _get_cached_by_shop(cp, ci, date_from, date_to, shop_group)
        grade_keys = [g['grade'] for g in aggregate_by_grade(details)]
        return {'periods_by_grade': _group_periods(by_shop, grade_keys, 'by_grade', 'grade')}

    if tab == 'season_allshops':
        by_shop, all_sk, all_mk, all_yk, all_wk = _get_cached_by_shop(cp, ci, date_from, date_to, shop_group)
        return {'periods_by_season': _group_periods(by_shop, all_sk, 'by_session', 'session')}

    if tab == 'month_allshops':
        by_shop, all_sk, all_mk, all_yk, all_wk = _get_cached_by_shop(cp, ci, date_from, date_to, shop_group)
        return {'periods_by_month': _group_periods(by_shop, all_mk, 'by_month', 'month')}

    if tab == 'week_allshops':
        by_shop, all_sk, all_mk, all_yk, all_wk = _get_cached_by_shop(cp, ci, date_from, date_to, shop_group)
        return {'periods_by_week': _group_periods(
            by_shop, all_wk, 'by_week', 'week_sort',
            label_fn=lambda r: r['week_label'],
        )}

    raise ValueError(f"Unknown sales tab: {tab!r}")


def _sales_grade_with_overview(customer_purchases, get_ci, date_stats, date_from, date_to):
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
        .values('vip_id').order_by().distinct().count()
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

    new_members_count = count_new_members_with_invoice(customer_purchases, get_ci, period_lo, period_hi)

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

