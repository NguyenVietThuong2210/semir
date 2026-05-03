"""
App/cnv/service.py — CNV business logic service layer.

Contains all heavy computation for CNV/POS comparison analytics.
Views and tab_functions import from here — never the other way around.
"""
import logging
from datetime import datetime, timedelta, date as _date

from django.db.models import Count, Q as _Q
from django.utils import timezone

from App.models import Customer as POSCustomer
from App.cnv.models import CNVCustomer
from App.analytics.customer_utils import build_inv_bucket_map_from_db, _norm_vid, classify_new_inv

logger = logging.getLogger("App.cnv")


# ── Date parsing ───────────────────────────────────────────────────────────────

def parse_cnv_period_filter(start_date, end_date):
    """Parse 'YYYY-MM-DD' strings → (period_filter dict, has_filter bool).

    Returns ({start, end} with timezone-aware datetimes, True) on success,
    or ({}, False) when dates are missing/invalid.
    """
    if start_date and end_date:
        try:
            start = datetime.strptime(start_date, "%Y-%m-%d")
            end = datetime.strptime(end_date, "%Y-%m-%d").replace(
                hour=23, minute=59, second=59, microsecond=999999
            )
            return {
                "start": timezone.make_aware(start),
                "end": timezone.make_aware(end),
            }, True
        except ValueError:
            pass
    return {}, False


# ── Phone-set helpers ──────────────────────────────────────────────────────────

def get_cnv_phone_sets():
    """Return (pos_phones_all, cnv_phones_all) Python sets for O(1) membership checks.

    These are all-time, unfiltered sets — used by _compute_cnv_breakdown.
    Cached for 10 minutes; customer data changes rarely during a session.
    """
    from django.core.cache import cache as _djc
    _key = "cnv_phone_sets"
    hit = _djc.get(_key)
    if hit is not None:
        return hit
    pos_phones_all = set(
        POSCustomer.objects
        .filter(vip_id__isnull=False, phone__isnull=False)
        .exclude(vip_id=0).exclude(phone="")
        .values_list("phone", flat=True)
    )
    cnv_phones_all = set(
        CNVCustomer.objects.filter(phone__isnull=False).exclude(phone="")
        .values_list("phone", flat=True)
    )
    result = (pos_phones_all, cnv_phones_all)
    _djc.set(_key, result, timeout=600)
    return result


def get_cnv_customer_kpis(period_filter, has_filter, pos_phones_all, cnv_phones_all):
    """Compute CNV customer analytics KPI counts.

    Used by both the web customer_analytics view and the mobile CustomerAnalyticsView API.
    Returns a dict; callers map keys to their own response format.

    All-time keys: total_pos, total_cnv, both, pos_only_all, cnv_only_all
    Period keys (zeroed when has_filter=False): new_pos, new_cnv, pos_only_period,
        cnv_only_period, new_pos_inv, new_pos_no_inv, synced_period, active_period
    """
    from App.models import SalesTransaction as _ST
    from django.db.models import Q as _DQ

    total_pos = len(pos_phones_all)
    total_cnv = len(cnv_phones_all)
    both = len(pos_phones_all & cnv_phones_all)
    pos_only_all = total_pos - both
    cnv_only_all = total_cnv - both

    new_pos = new_cnv = 0
    pos_only_period = cnv_only_period = 0
    new_pos_inv = new_pos_no_inv = 0

    if has_filter:
        pos_all = (
            POSCustomer.objects.filter(vip_id__isnull=False, phone__isnull=False)
            .exclude(vip_id=0).exclude(phone='')
        )
        cnv_all = CNVCustomer.objects.filter(phone__isnull=False).exclude(phone='')
        _cnv_phone_qs = cnv_all.values('phone')
        _pos_phone_qs = pos_all.values('phone')

        pos_period = pos_all.filter(
            registration_date__gte=period_filter['start'],
            registration_date__lte=period_filter['end'],
        )
        new_pos = pos_period.count()
        cnv_period = cnv_all.filter(
            cnv_created_at__gte=period_filter['start'],
            cnv_created_at__lte=period_filter['end'],
        )
        new_cnv = cnv_period.count()
        pos_only_period = pos_period.exclude(phone__in=_cnv_phone_qs).count()
        cnv_only_period = cnv_period.exclude(phone__in=_pos_phone_qs).count()

        _inv_qs = (
            _ST.objects
            .filter(
                sales_date__gte=period_filter['start'].date(),
                sales_date__lte=period_filter['end'].date(),
            )
            .exclude(vip_id__isnull=True).exclude(vip_id='').exclude(vip_id='0')
        )
        _pks_wi_qs = _inv_qs.filter(customer__isnull=False).values('customer_id')
        _vids_wi_qs = _inv_qs.values('vip_id')
        _inv_phones = set(
            POSCustomer.objects
            .filter(_DQ(id__in=_pks_wi_qs) | _DQ(vip_id__in=_vids_wi_qs))
            .exclude(phone__isnull=True).exclude(phone='')
            .values_list('phone', flat=True)
        )
        _pos_period_phones = set(pos_period.values_list('phone', flat=True))
        new_pos_inv = len(_pos_period_phones & _inv_phones)
        new_pos_no_inv = new_pos - new_pos_inv

    # synced_period = new POS customers also in CNV (from POS side)
    synced_period = new_pos - pos_only_period
    # active_period = all unique new customers across both systems
    active_period = pos_only_period + cnv_only_period + synced_period

    return {
        'total_pos':        total_pos,
        'total_cnv':        total_cnv,
        'both':             both,
        'pos_only_all':     pos_only_all,
        'cnv_only_all':     cnv_only_all,
        'new_pos':          new_pos,
        'new_cnv':          new_cnv,
        'pos_only_period':  pos_only_period,
        'cnv_only_period':  cnv_only_period,
        'new_pos_inv':      new_pos_inv,
        'new_pos_no_inv':   new_pos_no_inv,
        'synced_period':    synced_period,
        'active_period':    active_period,
    }


# ── Registration breakdown (BD tabs) ──────────────────────────────────────────

def _fetch_bd_raw(period_filter):
    """
    Fetch all DB data needed for compute_cnv_breakdown.
    Cached per period_filter for 5 minutes — shared across ALL tab requests with
    the same period, so tabs 2-N pay only the fast Python accumulation cost.

    Returns (pos_list, cnv_list, zalo_list, phone_to_store, _phone_to_inv,
             _inv_vid_map, _inv_pk_map, _pop_lo, _pop_hi)
    """
    from django.core.cache import cache as _djc
    from django.db.models import Min, Max

    _period_key = f"{period_filter.get('start', '')}:{period_filter.get('end', '')}"
    _key = f"bd_raw:{_period_key}"
    hit = _djc.get(_key)
    if hit is not None:
        return hit

    # Effective date range
    if period_filter:
        reg_lo = period_filter["start"].date()
        reg_hi = period_filter["end"].date()
        cnv_lo = period_filter["start"]
        cnv_hi = period_filter["end"]
    else:
        _bounds = (
            POSCustomer.objects
            .filter(vip_id__isnull=False, phone__isnull=False,
                    registration_date__isnull=False)
            .exclude(vip_id=0).exclude(phone="")
            .aggregate(lo=Min("registration_date"), hi=Max("registration_date"))
        )
        reg_lo = _bounds["lo"]
        reg_hi = _bounds["hi"]
        _cnv_bounds = (
            CNVCustomer.objects
            .filter(phone__isnull=False, cnv_created_at__isnull=False)
            .exclude(phone="")
            .aggregate(lo=Min("cnv_created_at"), hi=Max("cnv_created_at"))
        )
        cnv_lo = _cnv_bounds["lo"]
        cnv_hi = _cnv_bounds["hi"]

    # POS customers in period (deduplicated by vip_id)
    pos_qs = (
        POSCustomer.objects
        .filter(registration_date__isnull=False)
        .values("id", "vip_id", "phone", "registration_date", "registration_store")
    )
    if reg_lo and reg_hi:
        pos_qs = pos_qs.filter(registration_date__gte=reg_lo, registration_date__lte=reg_hi)
    _seen_keys = set()
    pos_list = []
    for _c in pos_qs:
        _vid = _norm_vid(str(_c["vip_id"] or ""))
        _k = _vid if (_vid and _vid != "0") else f"__pk{_c['id']}"
        if _k not in _seen_keys:
            _seen_keys.add(_k)
            pos_list.append(_c)

    # CNV customers in period
    cnv_qs = (
        CNVCustomer.objects.filter(phone__isnull=False).exclude(phone="")
        .values("phone", "cnv_created_at", "zalo_app_id", "zalo_oa_id")
    )
    if cnv_lo and cnv_hi:
        cnv_qs = cnv_qs.filter(cnv_created_at__gte=cnv_lo, cnv_created_at__lte=cnv_hi)
    cnv_list = list(cnv_qs)

    # Zalo registrations in period (pre-fetched so accumulation loop is pure Python)
    zalo_qs = (
        CNVCustomer.objects.filter(phone__isnull=False).exclude(phone="")
        .filter(zalo_app_id__isnull=False).exclude(zalo_app_id="")
        .filter(zalo_app_created_at__isnull=False)
    )
    if cnv_lo and cnv_hi:
        zalo_qs = zalo_qs.filter(zalo_app_created_at__gte=cnv_lo, zalo_app_created_at__lte=cnv_hi)
    zalo_list = list(zalo_qs.values("phone", "zalo_app_created_at", "zalo_oa_id"))

    # All-time POS customers — phone_to_store + inv lookup maps
    _all_pos_rows = list(
        POSCustomer.objects.filter(vip_id__isnull=False, phone__isnull=False)
        .exclude(vip_id=0).exclude(phone="")
        .values("id", "vip_id", "phone", "registration_store")
    )
    phone_to_store = {
        r["phone"]: r["registration_store"]
        for r in _all_pos_rows
        if r["registration_store"]
    }
    _inv_vid_map = {}
    _inv_pk_map = {}
    _phone_to_inv = {}
    if reg_lo and reg_hi:
        _inv_vid_map, _inv_pk_map = build_inv_bucket_map_from_db(reg_lo, reg_hi)
        for _row in _all_pos_rows:
            _ii = _inv_vid_map.get(_norm_vid(str(_row['vip_id']))) or _inv_pk_map.get(_row['id'])
            if _ii:
                _phone_to_inv[_row['phone']] = _ii

    # Week date bounds (union of POS + CNV date ranges)
    _pop_lo = reg_lo if isinstance(reg_lo, _date) else (reg_lo.date() if reg_lo else None)
    _pop_hi = reg_hi if isinstance(reg_hi, _date) else (reg_hi.date() if reg_hi else None)
    _cnv_lo_d = cnv_lo.date() if cnv_lo and hasattr(cnv_lo, 'date') else cnv_lo
    _cnv_hi_d = cnv_hi.date() if cnv_hi and hasattr(cnv_hi, 'date') else cnv_hi
    if _cnv_lo_d:
        _pop_lo = min(_pop_lo, _cnv_lo_d) if _pop_lo else _cnv_lo_d
    if _cnv_hi_d:
        _pop_hi = max(_pop_hi, _cnv_hi_d) if _pop_hi else _cnv_hi_d

    result = (pos_list, cnv_list, zalo_list, phone_to_store, _phone_to_inv,
              _inv_vid_map, _inv_pk_map, _pop_lo, _pop_hi)
    _djc.set(_key, result, timeout=300)
    return result


def compute_cnv_breakdown(period_filter, pos_phones_all, cnv_phones_all, dims=None, store_filter=None):
    """
    Compute registration breakdown tables: by season / month / week / shop
    and the cross-tab variants (season×shop, month×shop, week×shop).

    period_filter: {"start": aware_datetime, "end": aware_datetime} or {}
    pos_phones_all / cnv_phones_all: all-time phone sets (for POS-only / CNV-only check).
    dims: accepted but ignored — always computes all dims and caches the full result.
    store_filter: if given, only process entries whose registration_store == store_filter.

    Full result is cached for 5 minutes per (period_filter, store_filter).
    """
    from django.core.cache import cache as _djc
    _period_key = f"{period_filter.get('start', '')}:{period_filter.get('end', '')}"
    _store_key = store_filter or ""
    _bd_cache_key = f"cnv_breakdown:{_period_key}:{_store_key}"
    _bd_hit = _djc.get(_bd_cache_key)
    if _bd_hit is not None:
        return _bd_hit

    _want = frozenset({
        'season', 'month', 'week', 'shop',
        'season_shop', 'month_shop', 'week_shop',
    })
    from App.analytics.season_utils import (
        get_session_key, session_sort_key,
        get_month_key, month_sort_key,
        get_week_info, week_sort_key,
    )

    # DB fetch — fast on cache hit (same period_filter across all BD tabs)
    (pos_list, cnv_list, zalo_list, phone_to_store, _phone_to_inv,
     _inv_vid_map, _inv_pk_map, _pop_lo, _pop_hi) = _fetch_bd_raw(period_filter)

    def _empty():
        return {"new_pos": 0, "new_pos_only": 0, "new_pos_inv": 0, "new_pos_no_inv": 0,
                "new_cnv": 0, "new_cnv_only": 0, "new_cnv_inv": 0, "new_cnv_no_inv": 0,
                "zalo_app": 0, "zalo_oa": 0}

    season_data, month_data, shop_data = {}, {}, {}
    season_shop_data, month_shop_data = {}, {}
    week_data      = {}
    week_shop_data = {}

    if ('week' in _want or 'week_shop' in _want) and _pop_lo and _pop_hi:
        _cur = _pop_lo
        _seen_w = set()
        while _cur <= _pop_hi:
            _ws, _wl = get_week_info(_cur)
            if _ws not in _seen_w:
                _seen_w.add(_ws)
                week_data[_ws] = (_wl, _empty())
            _cur += timedelta(days=7)
        _ws, _wl = get_week_info(_pop_hi)
        if _ws not in _seen_w:
            week_data[_ws] = (_wl, _empty())

    # ── POS pass ──────────────────────────────────────────────────────────────
    _shop_keys = set()
    for c in pos_list:
        reg_date = c["registration_date"]
        if not reg_date:
            continue
        phone = c["phone"] or ""
        store = (c["registration_store"] or "").strip() or "Unknown"
        if store_filter and store != store_filter:
            continue
        is_pos_only = (not phone) or (phone not in cnv_phones_all)

        c_pk  = c.get("id")
        c_vid = _norm_vid(c.get("vip_id") or "")
        _inv  = _inv_vid_map.get(c_vid) or _inv_pk_map.get(c_pk) or {}

        s_key          = get_session_key(reg_date)
        m_key          = get_month_key(reg_date)
        w_sort, w_lbl  = get_week_info(reg_date)

        chk = classify_new_inv(_inv, reg_sk=s_key, reg_mk=m_key, reg_wk=w_sort)

        _shop_keys.add(store)

        if 'season' in _want:
            r = season_data.setdefault(s_key, _empty())
            r["new_pos"] += 1
            if is_pos_only: r["new_pos_only"] += 1
            if chk["season"]: r["new_pos_inv"] += 1
            else: r["new_pos_no_inv"] += 1

        if 'month' in _want:
            r = month_data.setdefault(m_key, _empty())
            r["new_pos"] += 1
            if is_pos_only: r["new_pos_only"] += 1
            if chk["month"]: r["new_pos_inv"] += 1
            else: r["new_pos_no_inv"] += 1

        if 'shop' in _want:
            r = shop_data.setdefault(store, _empty())
            r["new_pos"] += 1
            if is_pos_only: r["new_pos_only"] += 1
            if chk["any"]: r["new_pos_inv"] += 1
            else: r["new_pos_no_inv"] += 1

        if 'season_shop' in _want:
            r = season_shop_data.setdefault((s_key, store), _empty())
            r["new_pos"] += 1
            if is_pos_only: r["new_pos_only"] += 1
            if chk["season"]: r["new_pos_inv"] += 1
            else: r["new_pos_no_inv"] += 1

        if 'month_shop' in _want:
            r = month_shop_data.setdefault((m_key, store), _empty())
            r["new_pos"] += 1
            if is_pos_only: r["new_pos_only"] += 1
            if chk["month"]: r["new_pos_inv"] += 1
            else: r["new_pos_no_inv"] += 1

        if 'week' in _want or 'week_shop' in _want:
            if w_sort not in week_data:
                week_data[w_sort] = (w_lbl, _empty())
            r = week_data[w_sort][1]
            r["new_pos"] += 1
            if is_pos_only: r["new_pos_only"] += 1
            if chk["week"]: r["new_pos_inv"] += 1
            else: r["new_pos_no_inv"] += 1

        if 'week_shop' in _want:
            ws_key = (w_sort, store)
            if ws_key not in week_shop_data:
                week_shop_data[ws_key] = (w_lbl, _empty())
            r = week_shop_data[ws_key][1]
            r["new_pos"] += 1
            if is_pos_only: r["new_pos_only"] += 1
            if chk["week"]: r["new_pos_inv"] += 1
            else: r["new_pos_no_inv"] += 1

    # ── CNV pass ──────────────────────────────────────────────────────────────
    for c in cnv_list:
        dt    = c["cnv_created_at"]
        phone = c["phone"] or ""
        if not dt or not phone:
            continue
        reg_date    = dt.date() if hasattr(dt, "date") else dt
        is_cnv_only = phone not in pos_phones_all
        store       = phone_to_store.get(phone)
        if store_filter and store != store_filter:
            continue

        s_key         = get_session_key(reg_date)
        m_key         = get_month_key(reg_date)
        w_sort, w_lbl = get_week_info(reg_date)

        chk_cnv = classify_new_inv(_phone_to_inv.get(phone, {}),
                                   reg_sk=s_key, reg_mk=m_key, reg_wk=w_sort)

        if 'season' in _want:
            r = season_data.setdefault(s_key, _empty())
            r["new_cnv"] += 1
            if is_cnv_only: r["new_cnv_only"] += 1
            if chk_cnv["season"]: r["new_cnv_inv"] += 1
            else: r["new_cnv_no_inv"] += 1

        if 'month' in _want:
            r = month_data.setdefault(m_key, _empty())
            r["new_cnv"] += 1
            if is_cnv_only: r["new_cnv_only"] += 1
            if chk_cnv["month"]: r["new_cnv_inv"] += 1
            else: r["new_cnv_no_inv"] += 1

        if 'week' in _want or 'week_shop' in _want:
            if w_sort not in week_data:
                week_data[w_sort] = (w_lbl, _empty())
            wr = week_data[w_sort][1]
            wr["new_cnv"] += 1
            if is_cnv_only: wr["new_cnv_only"] += 1
            if chk_cnv["week"]: wr["new_cnv_inv"] += 1
            else: wr["new_cnv_no_inv"] += 1

        if store:
            _shop_keys.add(store)

            if 'shop' in _want:
                r = shop_data.setdefault(store, _empty())
                r["new_cnv"] += 1
                if is_cnv_only: r["new_cnv_only"] += 1
                if chk_cnv["any"]: r["new_cnv_inv"] += 1
                else: r["new_cnv_no_inv"] += 1

            if 'season_shop' in _want:
                r = season_shop_data.setdefault((s_key, store), _empty())
                r["new_cnv"] += 1
                if is_cnv_only: r["new_cnv_only"] += 1
                if chk_cnv["season"]: r["new_cnv_inv"] += 1
                else: r["new_cnv_no_inv"] += 1

            if 'month_shop' in _want:
                r = month_shop_data.setdefault((m_key, store), _empty())
                r["new_cnv"] += 1
                if is_cnv_only: r["new_cnv_only"] += 1
                if chk_cnv["month"]: r["new_cnv_inv"] += 1
                else: r["new_cnv_no_inv"] += 1

            if 'week_shop' in _want:
                ws_key = (w_sort, store)
                if ws_key not in week_shop_data:
                    week_shop_data[ws_key] = (w_lbl, _empty())
                wr2 = week_shop_data[ws_key][1]
                wr2["new_cnv"] += 1
                if is_cnv_only: wr2["new_cnv_only"] += 1
                if chk_cnv["week"]: wr2["new_cnv_inv"] += 1
                else: wr2["new_cnv_no_inv"] += 1

    # ── Zalo pass (uses pre-fetched zalo_list — no DB query here) ────────────
    for z in zalo_list:
        phone = z["phone"] or ""
        dt    = z["zalo_app_created_at"]
        if not dt or not phone:
            continue
        reg_date = dt.date() if hasattr(dt, "date") else dt
        has_oa   = bool(z["zalo_oa_id"])
        store    = phone_to_store.get(phone)
        if store_filter and store != store_filter:
            continue

        s_key         = get_session_key(reg_date)
        m_key         = get_month_key(reg_date)
        w_sort, w_lbl = get_week_info(reg_date)

        if 'season' in _want:
            r = season_data.setdefault(s_key, _empty())
            r["zalo_app"] += 1
            if has_oa:
                r["zalo_oa"] += 1

        if 'month' in _want:
            r = month_data.setdefault(m_key, _empty())
            r["zalo_app"] += 1
            if has_oa:
                r["zalo_oa"] += 1

        if 'week' in _want or 'week_shop' in _want:
            if w_sort not in week_data:
                week_data[w_sort] = (w_lbl, _empty())
            wr = week_data[w_sort][1]
            wr["zalo_app"] += 1
            if has_oa:
                wr["zalo_oa"] += 1

        if store:
            _shop_keys.add(store)

            if 'shop' in _want:
                r = shop_data.setdefault(store, _empty())
                r["zalo_app"] += 1
                if has_oa:
                    r["zalo_oa"] += 1

            if 'season_shop' in _want:
                r = season_shop_data.setdefault((s_key, store), _empty())
                r["zalo_app"] += 1
                if has_oa:
                    r["zalo_oa"] += 1

            if 'month_shop' in _want:
                r = month_shop_data.setdefault((m_key, store), _empty())
                r["zalo_app"] += 1
                if has_oa:
                    r["zalo_oa"] += 1

            if 'week_shop' in _want:
                ws_key = (w_sort, store)
                if ws_key not in week_shop_data:
                    week_shop_data[ws_key] = (w_lbl, _empty())
                wr2 = week_shop_data[ws_key][1]
                wr2["zalo_app"] += 1
                if has_oa:
                    wr2["zalo_oa"] += 1

    # Ensure every (week, shop) pair exists in week_shop_data
    if 'week_shop' in _want:
        _all_wk_keys = set(week_data.keys())
        _all_sh_keys = set(shop_data.keys()) if 'shop' in _want else _shop_keys
        for _wk in _all_wk_keys:
            _wl = week_data[_wk][0]
            for _sh in _all_sh_keys:
                _ws_key = (_wk, _sh)
                if _ws_key not in week_shop_data:
                    week_shop_data[_ws_key] = (_wl, _empty())

    # ── Finalise ──────────────────────────────────────────────────────────────
    def _pct(a, b):
        return round(a / b * 100, 1) if b else 0.0

    def _flat_rows(data, sort_fn):
        rows = []
        for k in sorted(data.keys(), key=sort_fn):
            v = data[k]
            rows.append({"label": k, **v,
                         "zalo_app_pct": _pct(v["zalo_app"], v["new_cnv"]),
                         "zalo_oa_pct":  _pct(v["zalo_oa"],  v["new_cnv"])})
        return rows

    def _week_rows(wdict):
        rows = []
        for k in sorted(wdict.keys(), key=week_sort_key):
            lbl, v = wdict[k]
            rows.append({"label": lbl, **v,
                         "zalo_app_pct": _pct(v["zalo_app"], v["new_cnv"]),
                         "zalo_oa_pct":  _pct(v["zalo_oa"],  v["new_cnv"])})
        return rows

    def _cross_rows(data, time_sort_fn):
        rows = []
        for (t, sh) in sorted(data.keys(), key=lambda x: (time_sort_fn(x[0]), x[1])):
            v = data[(t, sh)]
            rows.append({"label": t, "shop": sh, **v,
                         "zalo_app_pct": _pct(v["zalo_app"], v["new_cnv"]),
                         "zalo_oa_pct":  _pct(v["zalo_oa"],  v["new_cnv"])})
        return rows

    def _week_cross_rows(wdict):
        rows = []
        for (w_sort, sh) in sorted(wdict.keys(), key=lambda x: (week_sort_key(x[0]), x[1])):
            lbl, v = wdict[(w_sort, sh)]
            rows.append({"label": lbl, "shop": sh, **v,
                         "zalo_app_pct": _pct(v["zalo_app"], v["new_cnv"]),
                         "zalo_oa_pct":  _pct(v["zalo_oa"],  v["new_cnv"])})
        return rows

    def _shop_cross_rows(cross_data, time_sort_fn):
        shop_dict = {}
        for (t, sh), v in cross_data.items():
            shop_dict.setdefault(sh, []).append({"label": t, **v,
                                                  "zalo_app_pct": _pct(v["zalo_app"], v["new_cnv"]),
                                                  "zalo_oa_pct":  _pct(v["zalo_oa"],  v["new_cnv"])})
        result = []
        for sh in sorted(shop_dict.keys()):
            rows = sorted(shop_dict[sh], key=lambda x: time_sort_fn(x["label"]))
            result.append({"shop": sh, "rows": rows})
        return result

    def _shop_week_cross_rows(wdict):
        shop_dict = {}
        for (w_sort, sh), (lbl, v) in wdict.items():
            shop_dict.setdefault(sh, []).append({"label": lbl, "week_sort": w_sort, **v,
                                                  "zalo_app_pct": _pct(v["zalo_app"], v["new_cnv"]),
                                                  "zalo_oa_pct":  _pct(v["zalo_oa"],  v["new_cnv"])})
        result = []
        for sh in sorted(shop_dict.keys()):
            rows = sorted(shop_dict[sh], key=lambda x: week_sort_key(x["week_sort"]))
            result.append({"shop": sh, "rows": rows})
        return result

    _r_shop_season = _shop_cross_rows(season_shop_data, session_sort_key) if 'season_shop' in _want else []
    _r_shop_month  = _shop_cross_rows(month_shop_data,  month_sort_key)  if 'month_shop'  in _want else []
    _r_shop_week   = _shop_week_cross_rows(week_shop_data)               if 'week_shop'   in _want else []

    if 'shop' in _want:
        _shop_sum_map = {r["label"]: r for r in _flat_rows(shop_data, lambda x: x)}
        _ss_map = {sg["shop"]: sg["rows"] for sg in _r_shop_season}
        _sm_map = {sg["shop"]: sg["rows"] for sg in _r_shop_month}
        _sw_map = {sg["shop"]: sg["rows"] for sg in _r_shop_week}
        _all_shops = sorted(set(_shop_sum_map) | set(_ss_map) | set(_sm_map) | set(_sw_map))
        shop_detail = [
            {
                "shop":      sh,
                "summary":   _shop_sum_map.get(sh),
                "by_season": _ss_map.get(sh, []),
                "by_month":  _sm_map.get(sh, []),
                "by_week":   _sw_map.get(sh, []),
            }
            for sh in _all_shops
        ]
    else:
        shop_detail = []

    _bd_result = {
        "season":      _flat_rows(season_data, session_sort_key),
        "month":       _flat_rows(month_data,  month_sort_key),
        "week":        _week_rows(week_data),
        "shop":        _flat_rows(shop_data,   lambda x: x),
        "season_shop": _cross_rows(season_shop_data, session_sort_key),
        "month_shop":  _cross_rows(month_shop_data,  month_sort_key),
        "week_shop":   _week_cross_rows(week_shop_data),
        "shop_season": _r_shop_season,
        "shop_month":  _r_shop_month,
        "shop_week":   _r_shop_week,
        "shop_detail": shop_detail,
    }
    _djc.set(_bd_cache_key, _bd_result, timeout=300)
    return _bd_result


# ── Full comparison (used by export + tests) ──────────────────────────────────

def compute_cnv_comparison(start_date, end_date):
    """Compute all CNV comparison data — used by export and tests.

    This is the full computation including all lists (pos_only, cnv_only,
    points_mismatch, zalo lists, breakdown). For tab-level lazy loading
    use get_customer_tab() instead.
    Result is cached for 5 minutes per (start_date, end_date).
    """
    from django.core.cache import cache as _djc
    _cache_key = f"cnv_comparison:{start_date}:{end_date}"
    _cached = _djc.get(_cache_key)
    if _cached is not None:
        return _cached

    period_filter, has_filter = parse_cnv_period_filter(start_date, end_date)

    pos_all = (
        POSCustomer.objects.filter(vip_id__isnull=False, phone__isnull=False)
        .exclude(vip_id=0).exclude(phone="")
    )
    cnv_all = CNVCustomer.objects.filter(phone__isnull=False).exclude(phone="")

    total_pos_all = POSCustomer.objects.filter(vip_id__isnull=False).exclude(vip_id=0).count()
    total_cnv_all = CNVCustomer.objects.count()

    # Bulk fetch all rows in 2 queries, then use Python set ops — avoids slow SQL anti-joins
    _POS_FIELDS = ("vip_id", "phone", "name", "vip_grade", "email",
                   "registration_date", "points", "used_points")
    _CNV_FIELDS = ("cnv_id", "phone", "last_name", "first_name", "level_name",
                   "email", "cnv_created_at", "points", "total_points", "used_points")
    _all_pos_rows = list(pos_all.values(*_POS_FIELDS).order_by())
    _all_cnv_rows = list(cnv_all.values(*_CNV_FIELDS).order_by())

    pos_phones_all = {r["phone"] for r in _all_pos_rows}
    cnv_phones_all = {r["phone"] for r in _all_cnv_rows}
    _pos_only_phones = pos_phones_all - cnv_phones_all
    _cnv_only_phones = cnv_phones_all - pos_phones_all
    _shared_phones   = pos_phones_all & cnv_phones_all

    pos_only_all = sorted(
        [r for r in _all_pos_rows if r["phone"] in _pos_only_phones],
        key=lambda r: r["registration_date"] or _date.min, reverse=True,
    )
    cnv_only_all = sorted(
        [r for r in _all_cnv_rows if r["phone"] in _cnv_only_phones],
        key=lambda r: r["cnv_created_at"] or datetime.min, reverse=True,
    )
    pos_map = {r["phone"]: r for r in _all_pos_rows if r["phone"] in _shared_phones}
    cnv_map = {r["phone"]: r for r in _all_cnv_rows if r["phone"] in _shared_phones}

    pos_only_period = []
    cnv_only_period = []
    new_pos_count = new_cnv_count = pos_only_period_count = cnv_only_period_count = 0
    new_pos_inv_count = new_pos_no_inv_count = 0

    if has_filter:
        pos_period = pos_all.filter(
            registration_date__gte=period_filter["start"],
            registration_date__lte=period_filter["end"],
        )
        new_pos_count = pos_period.count()
        _pos_period_phones = set(pos_period.values_list("phone", flat=True))

        from App.models import SalesTransaction as _ST
        _inv_qs = (
            _ST.objects
            .filter(
                sales_date__gte=period_filter["start"].date(),
                sales_date__lte=period_filter["end"].date(),
            )
            .exclude(vip_id__isnull=True).exclude(vip_id="").exclude(vip_id="0")
        )
        _pks_wi_qs  = _inv_qs.filter(customer__isnull=False).values("customer_id")
        _vids_wi_qs = _inv_qs.values("vip_id")
        _inv_phones = set(
            POSCustomer.objects
            .filter(_Q(id__in=_pks_wi_qs) | _Q(vip_id__in=_vids_wi_qs))
            .exclude(phone__isnull=True).exclude(phone="")
            .values_list("phone", flat=True)
        )
        new_pos_inv_count    = len(_pos_period_phones & _inv_phones)
        new_pos_no_inv_count = new_pos_count - new_pos_inv_count

        cnv_period = cnv_all.filter(
            cnv_created_at__gte=period_filter["start"],
            cnv_created_at__lte=period_filter["end"],
        )
        new_cnv_count = cnv_period.count()

        # Python set ops — avoids anti-join subqueries
        _period_pos_rows = list(
            pos_period.values("vip_id", "phone", "name", "vip_grade",
                              "email", "registration_date", "points").order_by()
        )
        pos_only_period = sorted(
            [r for r in _period_pos_rows if r["phone"] not in cnv_phones_all],
            key=lambda r: r["registration_date"] or _date.min, reverse=True,
        )
        pos_only_period_count = len(pos_only_period)

        _period_cnv_rows = list(
            cnv_period.values("cnv_id", "phone", "last_name", "first_name",
                              "level_name", "email", "cnv_created_at",
                              "points", "total_points", "used_points").order_by()
        )
        cnv_only_period = sorted(
            [r for r in _period_cnv_rows if r["phone"] not in pos_phones_all],
            key=lambda r: r["cnv_created_at"] or datetime.min, reverse=True,
        )
        cnv_only_period_count = len(cnv_only_period)

    points_mismatch = []
    total_points_mismatch = []
    for phone, pos_c in pos_map.items():
        cnv_c = cnv_map.get(phone)
        if not cnv_c:
            continue
        pos_pts  = int(pos_c.get("points") or 0)
        pos_used = int(pos_c.get("used_points") or 0)
        pos_net  = pos_pts - pos_used
        cnv_pts  = int(cnv_c.get("points") or 0)
        cnv_total = int(float(cnv_c.get("total_points") or 0))
        base = {
            "phone":           phone,
            "pos_vip_id":      pos_c["vip_id"],
            "pos_name":        pos_c["name"],
            "pos_grade":       pos_c["vip_grade"],
            "pos_points":      pos_pts,
            "pos_used_points": pos_used,
            "pos_net_points":  pos_net,
            "cnv_id":          cnv_c["cnv_id"],
            "cnv_name":        f"{cnv_c.get('last_name') or ''} {cnv_c.get('first_name') or ''}".strip(),
            "cnv_level":       cnv_c["level_name"],
            "cnv_points":      cnv_pts,
            "cnv_total_points": cnv_c.get("total_points") or 0,
            "cnv_used_points":  cnv_c.get("used_points") or 0,
        }
        if pos_net != cnv_pts:
            points_mismatch.append({**base, "diff": cnv_pts - pos_net})
        if pos_net != cnv_total:
            total_points_mismatch.append({**base, "diff": cnv_total - pos_net})
    points_mismatch.sort(key=lambda x: abs(x["diff"]), reverse=True)
    total_points_mismatch.sort(key=lambda x: abs(x["diff"]), reverse=True)

    _cnv_used_raw = list(
        cnv_all.filter(used_points__gt=0)
        .values("cnv_id", "phone", "last_name", "first_name", "level_name",
                "email", "cnv_created_at", "points", "total_points", "used_points")
        .order_by("-used_points")
    )
    cnv_used_points_count = len(_cnv_used_raw)
    cnv_used_points_list = [
        {**r, "in_pos": bool(r["phone"]) and r["phone"] in pos_phones_all}
        for r in _cnv_used_raw
    ]

    _zalo_all_counts = CNVCustomer.objects.aggregate(
        app=Count("id", filter=_Q(zalo_app_id__isnull=False) & ~_Q(zalo_app_id="")),
        oa=Count("id",  filter=_Q(zalo_oa_id__isnull=False)  & ~_Q(zalo_oa_id="")),
    )
    zalo_app_all_count = _zalo_all_counts["app"]
    zalo_oa_all_count  = _zalo_all_counts["oa"]
    zalo_app_all_pct = round(zalo_app_all_count / total_cnv_all * 100, 1) if total_cnv_all else 0
    zalo_oa_all_pct  = round(zalo_oa_all_count  / total_cnv_all * 100, 1) if total_cnv_all else 0

    zalo_app_period_count = zalo_oa_period_count = 0
    zalo_app_period_pct   = zalo_oa_period_pct   = 0
    if has_filter:
        _pqs = CNVCustomer.objects.filter(
            zalo_app_created_at__gte=period_filter["start"],
            zalo_app_created_at__lte=period_filter["end"],
        )
        _pz = _pqs.aggregate(
            app=Count("id", filter=_Q(zalo_app_id__isnull=False) & ~_Q(zalo_app_id="")),
            oa=Count("id",  filter=_Q(zalo_oa_id__isnull=False)  & ~_Q(zalo_oa_id="")),
        )
        zalo_app_period_count = _pz["app"]
        zalo_oa_period_count  = _pz["oa"]
        zalo_app_period_pct = round(zalo_app_period_count / total_cnv_all * 100, 1) if total_cnv_all else 0
        zalo_oa_period_pct  = round(zalo_oa_period_count  / total_cnv_all * 100, 1) if total_cnv_all else 0

    _zf = ("cnv_id", "phone", "last_name", "first_name", "level_name",
           "email", "cnv_created_at", "points", "zalo_app_id", "zalo_oa_id", "zalo_app_created_at")
    zalo_app_qs = CNVCustomer.objects.filter(zalo_app_id__isnull=False).exclude(zalo_app_id="")
    zalo_oa_qs  = CNVCustomer.objects.filter(zalo_oa_id__isnull=False).exclude(zalo_oa_id="")
    zalo_app_list = list(zalo_app_qs.order_by("-zalo_app_created_at").values(*_zf))
    zalo_oa_list  = list(zalo_oa_qs.order_by("-zalo_app_created_at").values(*_zf))
    _all_z_phones = {r["phone"] for r in zalo_app_list + zalo_oa_list if r["phone"]}
    _pos_z_phones = _all_z_phones & pos_phones_all
    for r in zalo_app_list:
        r["in_pos"] = r["phone"] in _pos_z_phones
    for r in zalo_oa_list:
        r["in_pos"] = r["phone"] in _pos_z_phones

    result = {
        "has_filter":                has_filter,
        "period_label":              f"{start_date} to {end_date}" if has_filter else "All Time",
        "total_pos":                 total_pos_all,
        "total_cnv":                 total_cnv_all,
        "pos_only_all_count":        len(pos_only_all),
        "cnv_only_all_count":        len(cnv_only_all),
        "new_pos_count":             new_pos_count,
        "new_pos_inv_count":         new_pos_inv_count,
        "new_pos_no_inv_count":      new_pos_no_inv_count,
        "new_cnv_count":             new_cnv_count,
        "pos_only_period_count":     pos_only_period_count,
        "cnv_only_period_count":     cnv_only_period_count,
        "pos_only_all":              pos_only_all,
        "cnv_only_all":              cnv_only_all,
        "pos_only_period":           pos_only_period,
        "cnv_only_period":           cnv_only_period,
        "points_mismatch":           points_mismatch,
        "points_mismatch_count":     len(points_mismatch),
        "total_points_mismatch":     total_points_mismatch,
        "total_points_mismatch_count": len(total_points_mismatch),
        "cnv_used_points_list":      cnv_used_points_list,
        "cnv_used_points_count":     cnv_used_points_count,
        "zalo_app_all_count":        zalo_app_all_count,
        "zalo_oa_all_count":         zalo_oa_all_count,
        "zalo_app_all_pct":          zalo_app_all_pct,
        "zalo_oa_all_pct":           zalo_oa_all_pct,
        "zalo_app_period_count":     zalo_app_period_count,
        "zalo_oa_period_count":      zalo_oa_period_count,
        "zalo_app_period_pct":       zalo_app_period_pct,
        "zalo_oa_period_pct":        zalo_oa_period_pct,
        "zalo_mini_app_list":        zalo_app_list,
        "zalo_oa_list":              zalo_oa_list,
        "breakdown": compute_cnv_breakdown(period_filter, pos_phones_all, cnv_phones_all),
    }
    _djc.set(_cache_key, result, timeout=300)
    return result


def get_cnv_comparison_data(start_date, end_date):
    """Wrapper returning (data, None) — used by export view."""
    return compute_cnv_comparison(start_date, end_date), None
