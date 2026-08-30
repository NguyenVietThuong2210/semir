"""
App/analytics/shop_detail_data.py
Shop Detail direct-query data providers (sales/customer/coupon).
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
from .coupon_tabs import _build_coupon_qs
from .customer_tabs import _get_cnv_phone_sets, _parse_cnv_period_filter

def get_shop_detail_sales_data(shop_name: str, date_from=None, date_to=None) -> dict | None:
    """
    Return sales analytics for a single shop, identical to what aggregate_by_shop
    produces for that shop, but via a direct DB query filtered to shop_name.

    Reuses: build_customer_purchase_map, aggregate_by_season, aggregate_by_month,
            aggregate_by_week, calculate_return_visits — same functions as production path.

    Returns shop dict matching the shape of each entry in get_sales_tab('shop')['by_shop'],
    or None if no data.
    """
    from App.analytics.customer_utils import build_customer_purchase_map, _norm_vid
    from App.analytics.calculations import calculate_return_visits
    from App.analytics.aggregators import aggregate_by_season, aggregate_by_month, aggregate_by_week

    from decimal import Decimal
    from django.core.cache import cache as _djc2
    from App.models import Customer as _Cust

    FIELDS = ('vip_id', 'sales_date', 'invoice_number', 'sales_amount', 'shop_name')

    # ── Load ALL-TIME sales for this shop (no date filter) — cached 5 min,
    # same pattern as _load_sales() and info_map below. The date_from/date_to
    # filter always runs in Python AFTER this (cache-hit or not), so caching
    # here never affects period-filtered results.
    _alltime_key = f"shop_detail_sales_alltime:{shop_name}"
    all_time_list = _djc2.get(_alltime_key)
    if all_time_list is None:
        all_time_list = list(
            SalesTransaction.objects.filter(shop_name=shop_name).values(*FIELDS).order_by()
        )
        _djc2.set(_alltime_key, all_time_list, 300)
    if not all_time_list:
        return None

    # ── Filter to period in Python — avoids a second DB round-trip ───────────
    has_filter = bool(date_from or date_to)
    if has_filter:
        period_list = [
            s for s in all_time_list
            if (date_from is None or s['sales_date'] >= date_from)
            and (date_to is None or s['sales_date'] <= date_to)
        ]
    else:
        period_list = all_time_list

    # ── Customer info_map — cached 5 min to avoid loading 74k rows per call ─
    _info_key = "shop_detail_sales_info_map"
    info_map = _djc2.get(_info_key)
    if info_map is None:
        info_map = {
            _norm_vid(str(c['vip_id'])): (
                normalize_grade(c['vip_grade']),
                c['registration_date'],
                c['name'] or 'Unknown',
            )
            for c in _Cust.objects
            .filter(vip_id__isnull=False).exclude(vip_id=0)
            .values('vip_id', 'vip_grade', 'registration_date', 'name')
            if c['vip_id']
        }
        _djc2.set(_info_key, info_map, 300)

    def _get_ci(vip_id, customer_obj=None):
        c = info_map.get(vip_id)
        if c is not None:
            return c
        from App.analytics.customer_utils import get_customer_info
        return get_customer_info(vip_id, customer_obj)

    # ── Build purchase maps ───────────────────────────────────────────────────
    at_purchases = build_customer_purchase_map(all_time_list)
    pd_purchases = build_customer_purchase_map(period_list) if has_filter else at_purchases

    # ── KPI helper (same logic as aggregate_by_shop) ─────────────────────────
    def _kpis(purchases):
        cust = set(); ret = set()
        inv = ret_inv = vip0_inv = 0
        amt = ret_amt = vip0_amt = Decimal(0)
        for vid, purch in purchases.items():
            if vid == '0':
                vip0_inv += len(purch)
                vip0_amt += sum(p['amount'] for p in purch)
                continue
            _, reg_date, _ = _get_ci(vid, purch[0].get('customer'))
            _, is_ret = calculate_return_visits(purch, reg_date)
            a = sum(p['amount'] for p in purch)
            cust.add(vid); inv += len(purch); amt += a
            if is_ret:
                ret.add(vid); ret_inv += len(purch); ret_amt += a
        ac, rc = len(cust), len(ret)
        return {
            'total_customers':          ac,
            'returning_customers':      rc,
            'return_rate':              round(rc / ac * 100 if ac else 0, 2),
            'returning_invoices':       ret_inv,
            'returning_amount':         float(ret_amt),
            'total_invoices_with_vip0': inv + vip0_inv,
            'total_amount_with_vip0':   float(amt + vip0_amt),
        }

    at_kpis = _kpis(at_purchases)
    pd_kpis  = _kpis(pd_purchases) if has_filter else at_kpis

    # ── Sub-breakdowns from period data ───────────────────────────────────────
    by_session = aggregate_by_season(pd_purchases, _get_ci)
    by_month   = aggregate_by_month(pd_purchases, _get_ci)
    by_week    = aggregate_by_week(pd_purchases, _get_ci)

    return {
        'shop_name':  shop_name,
        'all_time':   at_kpis,
        'period':     pd_kpis,
        'by_session': by_session,
        'by_month':   by_month,
        'by_week':    by_week,
    }


def get_shop_detail_customer_data(registration_store: str,
                                  start_date: str = '', end_date: str = '') -> dict | None:
    """
    Return customer analytics for a single registration_store.

    Returns:
        {
            'all_time': summary-row (no date filter),
            'period':   summary-row (date-filtered, same as all_time if no filter),
            'by_season': [...],   # period
            'by_month':  [...],   # period
            'by_week':   [...],   # period
        }
    or None if no data for this store.
    """
    from App.cnv.service import compute_cnv_breakdown

    period_filter, _ = _parse_cnv_period_filter(start_date, end_date)
    pos_phones_all, cnv_phones_all = _get_cnv_phone_sets()

    # ── Period data (includes breakdowns) ─────────────────────────────────────
    # P3-03 revert (2026-07-25): store_filter=None was measured to make the
    # cold-cache path ~3.3x slower (0.76s -> 2.51s on prod-scale data, 23
    # shops) because compute_cnv_breakdown ignores `dims` and always builds
    # all 7 aggregation tables per record — store_filter's early `continue`
    # is what used to skip ~22/23 of all records. Company-wide caching also
    # means every shop's cold view forces one shared expensive recompute
    # instead of N small independent ones. Back to per-shop scoping.
    bd_period = compute_cnv_breakdown(
        period_filter, pos_phones_all, cnv_phones_all,
        dims=frozenset({'shop', 'season_shop', 'month_shop', 'week_shop'}),
        store_filter=registration_store,
    )
    period_summary = next((r for r in bd_period['shop'] if r['label'] == registration_store), None)
    detail         = next((sh for sh in bd_period['shop_detail'] if sh['shop'] == registration_store), None)

    if not period_summary and not detail:
        return None

    # ── All-time data (only shop summary needed) ──────────────────────────────
    # period_filter is {} (falsy) when no dates given — not None — so use `not`
    if not period_filter:
        at_summary = period_summary
    else:
        bd_at = compute_cnv_breakdown(
            {}, pos_phones_all, cnv_phones_all,
            dims=frozenset({'shop'}),
            store_filter=registration_store,
        )
        at_summary = next((r for r in bd_at['shop'] if r['label'] == registration_store), None)

    # ── Zalo-active CNV customers for this shop ───────────────────────────────
    # Match via phone: POS Customer.registration_store → CNVCustomer phone
    # Use subquery to keep filtering in DB (avoids loading large phone set into Python)
    from App.cnv.models import CNVCustomer as _CNVCust
    _shop_phone_qs = (
        Customer.objects.filter(registration_store=registration_store)
        .exclude(phone='').exclude(phone__isnull=True)
        .values('phone')
    )
    _zalo_qs = (
        _CNVCust.objects.filter(phone__in=_shop_phone_qs)
        .filter(zalo_app_id__isnull=False)
        .exclude(zalo_app_id='')
    )
    if period_filter:
        _zalo_qs = _zalo_qs.filter(
            zalo_app_created_at__gte=period_filter['start'],
            zalo_app_created_at__lte=period_filter['end'],
        )
    zalo_active_list = list(
        _zalo_qs.order_by('-zalo_app_created_at')
        .values('cnv_id', 'phone', 'last_name', 'first_name',
                'level_name', 'cnv_created_at', 'zalo_app_id',
                'zalo_oa_id', 'zalo_app_created_at')
    )

    return {
        'all_time':         at_summary,
        'period':           period_summary,
        'by_season':        detail['by_season'] if detail else [],
        'by_month':         detail['by_month']  if detail else [],
        'by_week':          detail['by_week']   if detail else [],
        'zalo_active_list': zalo_active_list,
    }


def get_shop_detail_coupon_data(using_shop: str, date_from=None, date_to=None,
                                coupon_id_prefix=None) -> dict:
    """
    Return coupon overview (all_time + period) and detail list filtered to a
    single using_shop.  Used by the Shop Detail page.

    Returns:
        {
            'all_time': {...},
            'period': {...},
            'details': [...],
        }
    """
    from decimal import Decimal
    from App.analytics.coupon_analytics import calc_coupon_amount, format_face_value

    qs, period_qs = _build_coupon_qs(
        coupon_id_prefix=coupon_id_prefix,
        shop_group=None,
        date_from=date_from,
        date_to=date_to,
        using_shop_exact=using_shop,
    )

    # ── All-time overview ─────────────────────────────────────────────────────
    _at = qs.aggregate(
        total=Count('id'),
        used=Count('id', filter=Q(using_date__isnull=False)),
    )
    at_total = _at['total']
    at_used  = _at['used']
    at_unused = at_total - at_used
    at_usage_rate = round(at_used / at_total * 100 if at_total else 0, 2)

    # R1: consolidated (family A — falsy sales_amount falls back to face_value)
    from App.analytics.coupon_analytics import accumulate_coupon_amounts, fetch_docket_txn_amounts
    _at_used_rows = list(qs.filter(using_date__isnull=False).values('pk', 'docket_number', 'face_value'))
    at_amount, at_coupon_amount, at_unique_amount = accumulate_coupon_amounts(
        _at_used_rows, fetch_docket_txn_amounts(_at_used_rows), falsy_uses_face_value=True
    )

    # .order_by() clears qs's 'coupon_id' ordering (from _build_coupon_qs)
    # before .values()/.annotate() — otherwise it leaks into the GROUP BY
    # (same footgun CLAUDE.md documents for .distinct()), and since coupon_id
    # is unique every group becomes size 1, silently zeroing this count.
    # Same root cause as the fix in coupon_analytics.py/coupon_tabs.py —
    # missed here initially (discovered 2026-08-30 via independent review).
    _dup_at = (
        qs.filter(using_date__isnull=False, docket_number__isnull=False)
        .exclude(docket_number='')
        .order_by()
        .values('docket_number').annotate(_c=Count('id')).filter(_c__gt=1).count()
    )

    # ── Period overview ───────────────────────────────────────────────────────
    if period_qs is qs:
        pd_total, pd_used = at_total, at_used
        pd_amount, pd_coupon_amount, pd_unique_amount = at_amount, at_coupon_amount, at_unique_amount
        _dup_pd = _dup_at
    else:
        _pd = period_qs.aggregate(
            total=Count('id'),
            used=Count('id', filter=Q(using_date__isnull=False)),
        )
        pd_total = _pd['total']
        pd_used  = _pd['used']

        _pd_used_rows = list(period_qs.filter(using_date__isnull=False).values('pk', 'docket_number', 'face_value'))
        pd_amount, pd_coupon_amount, pd_unique_amount = accumulate_coupon_amounts(
            _pd_used_rows, fetch_docket_txn_amounts(_pd_used_rows), falsy_uses_face_value=True
        )

    pd_unused = pd_total - pd_used
    pd_usage_rate = round(pd_used / pd_total * 100 if pd_total else 0, 2)

    # ── Detail list (period used coupons) ────────────────────────────────────
    # _dup_set fetched once; _dup_pd derived from len to avoid a duplicate COUNT query
    from App.models import Customer as _Cust

    # .order_by() clears the leaked ordering, see comment on _dup_at above.
    _dup_set = set(
        period_qs.filter(using_date__isnull=False, docket_number__isnull=False)
        .exclude(docket_number='')
        .order_by()
        .values('docket_number').annotate(_c=Count('id')).filter(_c__gt=1)
        .values_list('docket_number', flat=True)
    )
    if period_qs is not qs:
        _dup_pd = len(_dup_set)

    # 'coupon_id' tie-breaker: using_date alone is not unique, so without it
    # row order for same-day ties (and therefore which 500 rows this slice
    # keeps) is undefined on Postgres — see the identical fix + comment in
    # App/analytics/coupon_tabs.py::_coupon_detail_tab.
    _period_used = list(period_qs.filter(using_date__isnull=False).order_by('-using_date', 'coupon_id')[:500])
    if _period_used:
        _dockets = [c.docket_number for c in _period_used if c.docket_number]
        _txn_map = {t.invoice_number: t for t in SalesTransaction.objects.filter(invoice_number__in=_dockets).order_by()}
        _vip_ids = {t.vip_id for t in _txn_map.values() if t.vip_id and t.vip_id != '0'}
        _cust_map = {c.vip_id: c for c in _Cust.objects.filter(vip_id__in=_vip_ids).order_by()}

        details = []
        for coupon in _period_used:
            vip_id   = coupon.member_id or None
            vip_name = coupon.member_name or None
            phone    = coupon.member_phone or None
            sales_date = inv_shop = inv_amount = note = None

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

            _coupon_amount = calc_coupon_amount(coupon.face_value, inv_amount)
            details.append({
                'coupon_id':       coupon.coupon_id,
                'creator':         coupon.creator,
                'face_value_display': format_face_value(coupon.face_value),
                'using_shop':      coupon.using_shop,
                'using_date':      coupon.using_date,
                'vip_id':          vip_id,
                'customer_name':   vip_name,
                'customer_phone':  phone,
                'sales_day':       sales_date,
                'inv_shop':        inv_shop,
                'amount':          inv_amount or Decimal(0),
                'coupon_amount':   _coupon_amount,
                'note':            note,
                'cnv_id':          '',
                'cnv_points':      '',
                'cnv_total_points': '',
                'is_duplicate':    coupon.docket_number in _dup_set if coupon.docket_number else False,
            })

        # CNV enrichment: filter only phones present in details (avoids loading all CNV rows)
        from App.cnv.models import CNVCustomer
        _phones = {d['customer_phone'] for d in details if d['customer_phone']}
        _cnv_map = {
            c['phone']: c
            for c in CNVCustomer.objects.filter(phone__in=_phones)
            .values('phone', 'cnv_id', 'points', 'total_points')
        }
        for d in details:
            cnv = _cnv_map.get(d['customer_phone'])
            if cnv:
                d['cnv_id'] = cnv['cnv_id']
                d['cnv_points'] = cnv['points']
                d['cnv_total_points'] = cnv['total_points']
    else:
        details = []

    return {
        'all_time': {
            'total':                at_total,
            'used':                 at_used,
            'unused':               at_unused,
            'usage_rate':           at_usage_rate,
            'used_pct':             round(at_used / at_total * 100, 2) if at_total else 0,
            'total_amount':         float(at_amount),
            'total_coupon_amount':  float(at_coupon_amount),
            'unique_invoice_amount': float(at_unique_amount),
            'duplicate_invoice_count': _dup_at,
        },
        'period': {
            'total':                pd_total,
            'used':                 pd_used,
            'unused':               pd_unused,
            'usage_rate':           pd_usage_rate,
            'used_pct':             round(pd_used / pd_total * 100, 2) if pd_total else 0,
            'total_amount':         float(pd_amount),
            'total_coupon_amount':  float(pd_coupon_amount),
            'unique_invoice_amount': float(pd_unique_amount),
            'duplicate_invoice_count': _dup_pd,
        },
        'details': details,
    }
