"""
App/analytics/customer_tabs.py
Customer analytics tabs (CNV): get_customer_tab (bd_* + ca_*).
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
from .sales_tabs import _group_flat_by_period

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
    'bd_week_allshops':   frozenset({'week_shop'}),
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
        return {'period_season': _group_flat_by_period(bd['season_shop'])}
    if tab == 'bd_month_allshops':
        return {'period_month': _group_flat_by_period(bd['month_shop'])}
    if tab == 'bd_week_allshops':
        return {'period_week': _group_flat_by_period(bd['week_shop'])}
    raise ValueError(f"Unknown BD tab: {tab!r}")


def _customer_ca_points(start_date: str, end_date: str) -> dict:
    """
    Lean function for ca_points tab.
    Fetches:
      - CNV customers with used_points > 0 (+ in_pos flag)
      - Points mismatch tables (moved here from ca_pos_cnv for logical grouping)

    Performance: reuses the same POS/CNV querysets for both used_points in_pos check
    and mismatch computation, avoiding duplicate broad phone-set queries.
    """
    from App.cnv.models import CNVCustomer
    from App.models import Customer as _POS

    pos_all = (
        _POS.objects.filter(vip_id__isnull=False, phone__isnull=False)
        .exclude(vip_id=0).exclude(phone='')
    )
    cnv_all = CNVCustomer.objects.filter(phone__isnull=False).exclude(phone='')

    # Reuse cached phone sets (5-min TTL) instead of fetching 74k POS rows again
    pos_phones_all, _ = _get_cnv_phone_sets()

    # CNV used-points list
    _raw = list(
        CNVCustomer.objects.filter(used_points__gt=0)
        .values(
            'cnv_id', 'phone', 'last_name', 'first_name', 'level_name',
            'email', 'cnv_created_at', 'points', 'total_points', 'used_points',
        )
        # 'cnv_id' tie-breaker: used_points is not unique, so ties would
        # otherwise sort arbitrarily on Postgres (no guaranteed order absent
        # a fully-deterministic key — discovered 2026-08-30 switching dev to
        # Postgres, where a snapshot test picked a different tied row across
        # two otherwise-identical runs).
        .order_by('-used_points', 'cnv_id')
    )
    cnv_used_points_list = [
        {**r, 'in_pos': bool(r['phone']) and r['phone'] in pos_phones_all}
        for r in _raw
    ]

    # Mismatch computation: only phones present in BOTH systems
    _cnv_phone_qs = cnv_all.values('phone')
    _pos_phone_qs = pos_all.values('phone')
    _pos_map = {
        c['phone']: c
        for c in pos_all.filter(phone__in=_cnv_phone_qs)
        .values('vip_id', 'phone', 'name', 'vip_grade', 'points', 'used_points')
        .order_by('vip_id')
    }
    _cnv_map = {
        c['phone']: c
        for c in cnv_all.filter(phone__in=_pos_phone_qs)
        .values(
            'cnv_id', 'phone', 'last_name', 'first_name', 'level_name',
            'points', 'total_points', 'used_points',
        )
        .order_by('cnv_id')
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
            'phone':            phone,
            'pos_vip_id':       pos_c['vip_id'],
            'pos_name':         pos_c['name'],
            'pos_grade':        pos_c['vip_grade'],
            'pos_points':       pos_pts,
            'pos_used_points':  pos_used,
            'pos_net_points':   pos_net,
            'cnv_id':           cnv_c['cnv_id'],
            'cnv_name':         f"{cnv_c.get('last_name') or ''} {cnv_c.get('first_name') or ''}".strip(),
            'cnv_level':        cnv_c['level_name'],
            'cnv_points':       cnv_pts,
            'cnv_used_points':  int(cnv_c.get('used_points') or 0),
            'cnv_total_points': cnv_total,
        }
        if pos_net != cnv_pts:
            points_mismatch.append({**base, 'diff': cnv_pts - pos_net})
        if pos_net != cnv_total:
            total_points_mismatch.append({**base, 'diff': cnv_total - pos_net})
    # 'phone' tie-breaker: multiple customers can share the same abs(diff);
    # Python's sort is stable so ties otherwise fall back to _pos_map's
    # iteration order — now deterministic via .order_by() above, but this
    # key makes the guarantee explicit at the point it's actually needed.
    points_mismatch.sort(key=lambda x: (abs(x['diff']), x['phone']), reverse=True)
    total_points_mismatch.sort(key=lambda x: (abs(x['diff']), x['phone']), reverse=True)

    return {
        'cnv_used_points_count':       len(cnv_used_points_list),
        'cnv_used_points_list':        cnv_used_points_list,
        'points_mismatch':             points_mismatch,
        'points_mismatch_count':       len(points_mismatch),
        'total_points_mismatch':       total_points_mismatch,
        'total_points_mismatch_count': len(total_points_mismatch),
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

    # Fetch both zalo lists (indexed queries on zalo_app_id / zalo_oa_id)
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

    # 'cnv_id' tiebreaker: timestamps have many ties — without it the order of
    # tied rows is DB-plan-dependent, which made the ca_zalo snapshot flaky.
    zalo_mini_app_list = list(zalo_app_qs.order_by('-zalo_app_created_at', 'cnv_id').values(*_zf))
    # A-06: OA list sorts by CNV creation date — OA-only customers have no
    # zalo_app_created_at and would otherwise always sink to the bottom.
    zalo_oa_list       = list(zalo_oa_qs.order_by('-cnv_created_at', 'cnv_id').values(*_zf))

    # One targeted POS lookup via DB subquery — avoids loading all 74k POS rows
    # via get_cnv_phone_sets() and avoids SQLite "too many variables" for large IN lists.
    from App.models import Customer as _POSCustomer
    _active_zalo_phone_qs = (
        CNVCustomer.objects
        .filter(_Q(zalo_app_id__isnull=False) & ~_Q(zalo_app_id='')
                | _Q(zalo_oa_id__isnull=False) & ~_Q(zalo_oa_id=''))
        .values('phone')
    )
    _pos_zalo_rows = {
        row['phone']: row['registration_store']
        for row in _POSCustomer.objects
        .filter(phone__in=_active_zalo_phone_qs, vip_id__isnull=False)
        .exclude(vip_id=0).exclude(phone='')
        .values('phone', 'registration_store')
        if row['phone']
    }
    for r in zalo_mini_app_list:
        r['in_pos'] = r['phone'] in _pos_zalo_rows
        r['registration_store'] = _pos_zalo_rows.get(r['phone'], '') if r['in_pos'] else ''
    for r in zalo_oa_list:
        r['in_pos'] = r['phone'] in _pos_zalo_rows
        r['registration_store'] = _pos_zalo_rows.get(r['phone'], '') if r['in_pos'] else ''

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
    Fetches: pos_only / cnv_only lists (all-time + period).
    Points mismatch tables have moved to ca_points tab (_customer_ca_points).
    Does NOT compute: breakdown, zalo, used_points, points_mismatch.
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

    # All-time pos_only + cnv_only lists. Tie-breaker (vip_id / cnv_id) added
    # for the same reason as _customer_ca_points' used_points sort: neither
    # registration_date nor cnv_created_at is unique, so without a
    # fully-deterministic key Postgres can order tied rows differently
    # between runs (SQLite happened to look stable by accident).
    pos_only_all = list(
        pos_all.exclude(phone__in=_cnv_phone_qs)
        .values('vip_id', 'phone', 'name', 'vip_grade', 'email', 'registration_date', 'points')
        .order_by('-registration_date', 'vip_id')
    )
    cnv_only_all = list(
        cnv_all.exclude(phone__in=_pos_phone_qs)
        .values(
            'cnv_id', 'phone', 'last_name', 'first_name', 'level_name',
            'email', 'cnv_created_at', 'points', 'total_points', 'used_points',
        )
        .order_by('-cnv_created_at', 'cnv_id')
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
    }


# ── Shop Detail page helpers ──────────────────────────────────────────────────

