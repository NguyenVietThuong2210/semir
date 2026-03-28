"""
CNV Views
Handles CNV Loyalty integration pages
"""

import logging
import threading

from django.conf import settings
from django.core.cache import cache
from django.http import HttpResponse, JsonResponse
from django.shortcuts import render
from App.permissions import requires_perm
from django.views.decorators.http import require_POST
from datetime import datetime
from django.utils import timezone

from App.models import Customer as POSCustomer
from App.cnv.models import CNVCustomer, CNVOrder, CNVSyncLog
from App.analytics.customer_utils import get_inv_lookups_for_period, build_inv_bucket_map_from_db, _norm_vid

logger = logging.getLogger("App.cnv")

_CNV_VER_KEY = "cnv_cmp_ver"
_CNV_TTL = 300  # 5 minutes (syncs happen more frequently)


def _cnv_cache_key(start_date, end_date):
    v = cache.get(_CNV_VER_KEY, 0)
    return f"cnv_cmp:{v}:{start_date}:{end_date}"


def _invalidate_cnv_cache():
    v = cache.get(_CNV_VER_KEY, 0)
    cache.set(_CNV_VER_KEY, v + 1, 86400 * 30)
    logger.info("CNV comparison cache invalidated (ver→%d)", v + 1)


@requires_perm("page_cnv_sync")
def sync_status(request):
    """
    CNV Sync Status Dashboard
    Shows latest sync logs and statistics
    """
    # Get latest sync logs
    latest_customer_sync = (
        CNVSyncLog.objects.filter(sync_type="customers")
        .order_by("-completed_at")
        .first()
    )

    latest_order_sync = (
        CNVSyncLog.objects.filter(sync_type="orders").order_by("-completed_at").first()
    )

    # Get statistics
    total_customers = CNVCustomer.objects.count()
    total_orders = CNVOrder.objects.count()

    # Recent sync history (last 10)
    recent_syncs = CNVSyncLog.objects.order_by("-started_at")[:10]

    # Running-state flags (check DB)
    customers_running = CNVSyncLog.objects.filter(
        sync_type="customers", status="running"
    ).exists()
    orders_running = CNVSyncLog.objects.filter(
        sync_type="orders", status="running"
    ).exists()
    zalo_running = CNVSyncLog.objects.filter(
        sync_type="zalo_sync", status="running"
    ).exists()
    latest_zalo_sync = (
        CNVSyncLog.objects.filter(sync_type="zalo_sync")
        .order_by("-completed_at")
        .first()
    )

    context = {
        "latest_customer_sync": latest_customer_sync,
        "latest_order_sync": latest_order_sync,
        "latest_zalo_sync": latest_zalo_sync,
        "total_customers": total_customers,
        "total_orders": total_orders,
        "recent_syncs": recent_syncs,
        "customers_running": customers_running,
        "orders_running": orders_running,
        "zalo_running": zalo_running,
    }

    return render(request, "cnv/sync_status.html", context)


def _compute_cnv_breakdown(period_filter, pos_phones_all, cnv_phones_all):
    """
    Compute registration breakdown tables: by season / month / week / shop
    and the cross-tab variants (season×shop, month×shop, week×shop).

    period_filter: {"start": aware_datetime, "end": aware_datetime} or {}
    pos_phones_all / cnv_phones_all: all-time phone sets (for POS-only / CNV-only check).
    """
    from App.analytics.season_utils import (
        get_session_key, session_sort_key,
        get_month_key, month_sort_key,
        get_week_info, week_sort_key,
    )

    # POS customers (date-filtered)
    pos_qs = (
        POSCustomer.objects.filter(vip_id__isnull=False, phone__isnull=False)
        .exclude(vip_id=0).exclude(phone="")
        .values("id", "vip_id", "phone", "registration_date", "registration_store")
    )
    if period_filter:
        pos_qs = pos_qs.filter(
            registration_date__gte=period_filter["start"].date(),
            registration_date__lte=period_filter["end"].date(),
        )
    pos_list = list(pos_qs)

    # CNV customers (date-filtered)
    cnv_qs = (
        CNVCustomer.objects.filter(phone__isnull=False).exclude(phone="")
        .values("phone", "cnv_created_at", "zalo_app_id", "zalo_oa_id")
    )
    if period_filter:
        cnv_qs = cnv_qs.filter(
            cnv_created_at__gte=period_filter["start"],
            cnv_created_at__lte=period_filter["end"],
        )
    cnv_list = list(cnv_qs)

    # phone → registration_store (all-time) for CNV shop attribution
    phone_to_store = dict(
        POSCustomer.objects.filter(vip_id__isnull=False, phone__isnull=False)
        .exclude(vip_id=0).exclude(phone="")
        .exclude(registration_store__isnull=True).exclude(registration_store="")
        .values_list("phone", "registration_store")
    )

    def _empty():
        return {"new_pos": 0, "new_pos_only": 0, "new_pos_inv": 0, "new_pos_no_inv": 0,
                "new_cnv": 0, "new_cnv_only": 0, "new_cnv_inv": 0, "new_cnv_no_inv": 0,
                "zalo_app": 0, "zalo_oa": 0}

    # Per-bucket invoice maps: vid_map[normalized_vip_id] and pk_map[customer_pk]
    # Each entry: {sessions, months, years, weeks, shops, session_shops, ...}
    # Used for per-bucket is_pos_inv checks (not full-period).
    _inv_vid_map = {}
    _inv_pk_map = {}
    pos_phones_with_inv = set()  # kept for CNV pass (phone-based)
    if period_filter:
        from django.db.models import Q
        _inv_vid_map, _inv_pk_map = build_inv_bucket_map_from_db(
            period_filter["start"].date(), period_filter["end"].date()
        )
        # phone → inv presence: any customer whose vid or pk has ANY invoice in period
        _pks_any = set(_inv_pk_map.keys())
        _vids_any = set(_inv_vid_map.keys())
        pos_phones_with_inv = set(
            POSCustomer.objects
            .filter(Q(id__in=_pks_any) | Q(vip_id__in=_vids_any))
            .exclude(phone__isnull=True).exclude(phone='')
            .values_list('phone', flat=True)
        )

    season_data, month_data, shop_data = {}, {}, {}
    season_shop_data, month_shop_data = {}, {}
    week_data       = {}   # sort_key → (label, row)
    week_shop_data  = {}   # (sort_key, shop) → (label, row)

    # ── POS pass ──────────────────────────────────────────────────────────────
    for c in pos_list:
        reg_date = c["registration_date"]
        phone    = c["phone"] or ""
        store    = (c["registration_store"] or "").strip() or "Unknown"
        if not reg_date or not phone:
            continue
        is_pos_only = phone not in cnv_phones_all

        # Per-bucket invoice presence (user's formula: inv must be in same bucket as reg)
        c_pk  = c.get("id")
        c_vid = _norm_vid(c.get("vip_id") or "")
        _inv  = _inv_vid_map.get(c_vid) or _inv_pk_map.get(c_pk) or {}

        s_key          = get_session_key(reg_date)
        m_key          = get_month_key(reg_date)
        w_sort, w_lbl  = get_week_info(reg_date)

        is_inv_season = s_key in _inv.get("sessions", set())
        is_inv_month  = m_key in _inv.get("months", set())
        is_inv_week   = w_sort in _inv.get("weeks", set())
        is_inv_shop   = store in _inv.get("shops", set())
        is_inv_ss     = (s_key, store) in _inv.get("session_shops", set())
        is_inv_ms     = (m_key, store) in _inv.get("month_shops", set())
        is_inv_ws     = (w_sort, store) in _inv.get("week_shops", set())

        # season_data
        r = season_data.setdefault(s_key, _empty())
        r["new_pos"] += 1
        if is_pos_only: r["new_pos_only"] += 1
        if is_inv_season: r["new_pos_inv"] += 1
        else: r["new_pos_no_inv"] += 1

        # month_data
        r = month_data.setdefault(m_key, _empty())
        r["new_pos"] += 1
        if is_pos_only: r["new_pos_only"] += 1
        if is_inv_month: r["new_pos_inv"] += 1
        else: r["new_pos_no_inv"] += 1

        # shop_data
        r = shop_data.setdefault(store, _empty())
        r["new_pos"] += 1
        if is_pos_only: r["new_pos_only"] += 1
        if is_inv_shop: r["new_pos_inv"] += 1
        else: r["new_pos_no_inv"] += 1

        # season_shop_data
        r = season_shop_data.setdefault((s_key, store), _empty())
        r["new_pos"] += 1
        if is_pos_only: r["new_pos_only"] += 1
        if is_inv_ss: r["new_pos_inv"] += 1
        else: r["new_pos_no_inv"] += 1

        # month_shop_data
        r = month_shop_data.setdefault((m_key, store), _empty())
        r["new_pos"] += 1
        if is_pos_only: r["new_pos_only"] += 1
        if is_inv_ms: r["new_pos_inv"] += 1
        else: r["new_pos_no_inv"] += 1

        # week_data
        if w_sort not in week_data:
            week_data[w_sort] = (w_lbl, _empty())
        r = week_data[w_sort][1]
        r["new_pos"] += 1
        if is_pos_only: r["new_pos_only"] += 1
        if is_inv_week: r["new_pos_inv"] += 1
        else: r["new_pos_no_inv"] += 1

        # week_shop_data
        ws_key = (w_sort, store)
        if ws_key not in week_shop_data:
            week_shop_data[ws_key] = (w_lbl, _empty())
        r = week_shop_data[ws_key][1]
        r["new_pos"] += 1
        if is_pos_only: r["new_pos_only"] += 1
        if is_inv_ws: r["new_pos_inv"] += 1
        else: r["new_pos_no_inv"] += 1

    # ── CNV pass ──────────────────────────────────────────────────────────────
    for c in cnv_list:
        dt    = c["cnv_created_at"]
        phone = c["phone"] or ""
        if not dt or not phone:
            continue
        reg_date   = dt.date() if hasattr(dt, "date") else dt
        is_cnv_only = phone not in pos_phones_all
        is_cnv_inv  = phone in pos_phones_with_inv
        store      = phone_to_store.get(phone)  # None if not linked to POS

        s_key         = get_session_key(reg_date)
        m_key         = get_month_key(reg_date)
        w_sort, w_lbl = get_week_info(reg_date)

        # Flat (all-shops) buckets
        for bucket, key in [(season_data, s_key), (month_data, m_key)]:
            r = bucket.setdefault(key, _empty())
            r["new_cnv"] += 1
            if is_cnv_only:
                r["new_cnv_only"] += 1
            if is_cnv_inv:
                r["new_cnv_inv"] += 1
            else:
                r["new_cnv_no_inv"] += 1

        if w_sort not in week_data:
            week_data[w_sort] = (w_lbl, _empty())
        wr = week_data[w_sort][1]
        wr["new_cnv"] += 1
        if is_cnv_only:
            wr["new_cnv_only"] += 1
        if is_cnv_inv:
            wr["new_cnv_inv"] += 1
        else:
            wr["new_cnv_no_inv"] += 1

        # Shop-linked buckets (only if CNV customer is linked to a POS shop)
        if store:
            for bucket, key in [(shop_data, store),
                                 (season_shop_data, (s_key, store)),
                                 (month_shop_data, (m_key, store))]:
                r = bucket.setdefault(key, _empty())
                r["new_cnv"] += 1
                if is_cnv_only:
                    r["new_cnv_only"] += 1
                if is_cnv_inv:
                    r["new_cnv_inv"] += 1
                else:
                    r["new_cnv_no_inv"] += 1

            ws_key = (w_sort, store)
            if ws_key not in week_shop_data:
                week_shop_data[ws_key] = (w_lbl, _empty())
            wr2 = week_shop_data[ws_key][1]
            wr2["new_cnv"] += 1
            if is_cnv_only:
                wr2["new_cnv_only"] += 1
            if is_cnv_inv:
                wr2["new_cnv_inv"] += 1
            else:
                wr2["new_cnv_no_inv"] += 1

    # ── Zalo pass (grouped by zalo_app_created_at) ────────────────────────────
    zalo_qs = (
        CNVCustomer.objects.filter(phone__isnull=False).exclude(phone="")
        .filter(zalo_app_id__isnull=False).exclude(zalo_app_id="")
        .filter(zalo_app_created_at__isnull=False)
    )
    if period_filter:
        zalo_qs = zalo_qs.filter(
            zalo_app_created_at__gte=period_filter["start"],
            zalo_app_created_at__lte=period_filter["end"],
        )
    for z in zalo_qs.values("phone", "zalo_app_created_at", "zalo_oa_id"):
        phone = z["phone"] or ""
        dt    = z["zalo_app_created_at"]
        if not dt or not phone:
            continue
        reg_date = dt.date() if hasattr(dt, "date") else dt
        has_oa   = bool(z["zalo_oa_id"])
        store    = phone_to_store.get(phone)

        s_key         = get_session_key(reg_date)
        m_key         = get_month_key(reg_date)
        w_sort, w_lbl = get_week_info(reg_date)

        for bucket, key in [(season_data, s_key), (month_data, m_key)]:
            r = bucket.setdefault(key, _empty())
            r["zalo_app"] += 1
            if has_oa:
                r["zalo_oa"] += 1

        if store:
            r = shop_data.setdefault(store, _empty())
            r["zalo_app"] += 1
            if has_oa:
                r["zalo_oa"] += 1

        if w_sort not in week_data:
            week_data[w_sort] = (w_lbl, _empty())
        wr = week_data[w_sort][1]
        wr["zalo_app"] += 1
        if has_oa:
            wr["zalo_oa"] += 1

        if store:
            for bucket, key in [(season_shop_data, (s_key, store)),
                                 (month_shop_data,  (m_key, store))]:
                r = bucket.setdefault(key, _empty())
                r["zalo_app"] += 1
                if has_oa:
                    r["zalo_oa"] += 1

            ws_key = (w_sort, store)
            if ws_key not in week_shop_data:
                week_shop_data[ws_key] = (w_lbl, _empty())
            wr2 = week_shop_data[ws_key][1]
            wr2["zalo_app"] += 1
            if has_oa:
                wr2["zalo_oa"] += 1

    # ── Finalise: add pct, convert to sorted row lists ────────────────────────
    def _pct(a, b):
        return round(a / b * 100, 1) if b else 0.0

    def _flat_rows(data, sort_fn):
        rows = []
        for k, v in sorted(data.items(), key=lambda x: sort_fn(x[0])):
            rows.append({"label": k, **v,
                         "zalo_app_pct": _pct(v["zalo_app"], v["new_cnv"]),
                         "zalo_oa_pct":  _pct(v["zalo_oa"],  v["new_cnv"])})
        return rows

    def _week_rows(wdict):
        rows = []
        for k, (lbl, v) in sorted(wdict.items(), key=lambda x: week_sort_key(x[0])):
            rows.append({"label": lbl, **v,
                         "zalo_app_pct": _pct(v["zalo_app"], v["new_cnv"]),
                         "zalo_oa_pct":  _pct(v["zalo_oa"],  v["new_cnv"])})
        return rows

    def _cross_rows(data, time_sort_fn):
        rows = []
        for (t, sh), v in sorted(data.items(),
                                  key=lambda x: (time_sort_fn(x[0][0]), x[0][1])):
            rows.append({"label": t, "shop": sh, **v,
                         "zalo_app_pct": _pct(v["zalo_app"], v["new_cnv"]),
                         "zalo_oa_pct":  _pct(v["zalo_oa"],  v["new_cnv"])})
        return rows

    def _week_cross_rows(wdict):
        rows = []
        for (w_sort, sh), (lbl, v) in sorted(wdict.items(),
                                              key=lambda x: (week_sort_key(x[0][0]), x[0][1])):
            rows.append({"label": lbl, "shop": sh, **v,
                         "zalo_app_pct": _pct(v["zalo_app"], v["new_cnv"]),
                         "zalo_oa_pct":  _pct(v["zalo_oa"],  v["new_cnv"])})
        return rows

    def _shop_cross_rows(cross_data, time_sort_fn):
        """Group flat cross-data by shop → sorted list of {shop, rows}."""
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
        """Group flat week×shop data by shop → sorted list of {shop, rows}."""
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

    # Compute per-shop grouped once (reused in shop_detail + return dict)
    _r_shop_season = _shop_cross_rows(season_shop_data, session_sort_key)
    _r_shop_month  = _shop_cross_rows(month_shop_data,  month_sort_key)
    _r_shop_week   = _shop_week_cross_rows(week_shop_data)

    # Combined per-shop detail for Sales-style "By Shop" card layout
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

    return {
        "season":       _flat_rows(season_data, session_sort_key),
        "month":        _flat_rows(month_data,  month_sort_key),
        "week":         _week_rows(week_data),
        "shop":         _flat_rows(shop_data,   lambda x: x),
        "season_shop":  _cross_rows(season_shop_data, session_sort_key),
        "month_shop":   _cross_rows(month_shop_data,  month_sort_key),
        "week_shop":    _week_cross_rows(week_shop_data),
        "shop_season":  _r_shop_season,
        "shop_month":   _r_shop_month,
        "shop_week":    _r_shop_week,
        "shop_detail":  shop_detail,
    }


def _get_cnv_comparison_data(start_date, end_date):
    """Compute or retrieve cached CNV comparison data.

    Returns a dict with all counts, mismatch lists, and Zalo stats.
    All values are plain Python dicts/lists — safe to pickle for Redis.
    """
    cache_key = _cnv_cache_key(start_date, end_date)
    cached = cache.get(cache_key)
    if cached is not None:
        logger.info("CNV comparison cache HIT (%s)", cache_key)
        return cached, cache_key

    from django.db.models import Subquery

    period_filter = {}
    has_filter = False
    if start_date and end_date:
        try:
            start = datetime.strptime(start_date, "%Y-%m-%d")
            end = datetime.strptime(end_date, "%Y-%m-%d")
            period_filter = {
                "start": timezone.make_aware(start),
                "end": timezone.make_aware(end),
            }
            has_filter = True
        except ValueError:
            pass

    pos_all = (
        POSCustomer.objects.filter(vip_id__isnull=False, phone__isnull=False)
        .exclude(vip_id=0)
        .exclude(phone="")
    )
    cnv_all = CNVCustomer.objects.filter(phone__isnull=False).exclude(phone="")

    total_pos_all = (
        POSCustomer.objects.filter(vip_id__isnull=False).exclude(vip_id=0).count()
    )
    total_cnv_all = CNVCustomer.objects.count()

    pos_phones_all = set(pos_all.values_list("phone", flat=True))
    cnv_phones_all = set(cnv_all.values_list("phone", flat=True))
    pos_only_phones_all = pos_phones_all - cnv_phones_all
    cnv_only_phones_all = cnv_phones_all - pos_phones_all

    pos_only_all = list(
        pos_all.exclude(phone__in=Subquery(cnv_all.values("phone")))
        .values(
            "vip_id",
            "phone",
            "name",
            "vip_grade",
            "email",
            "registration_date",
            "points",
        )
        .order_by("-registration_date")
    )

    cnv_only_all = list(
        cnv_all.exclude(phone__in=Subquery(pos_all.values("phone")))
        .values(
            "cnv_id",
            "phone",
            "last_name",
            "first_name",
            "level_name",
            "email",
            "cnv_created_at",
            "points",
            "total_points",
            "used_points",
        )
        .order_by("-cnv_created_at")
    )

    pos_only_period = []
    cnv_only_period = []
    new_pos_count = new_cnv_count = pos_only_period_count = cnv_only_period_count = 0
    new_pos_inv_count = new_pos_no_inv_count = 0

    if period_filter:
        pos_period = pos_all.filter(
            registration_date__gte=period_filter["start"],
            registration_date__lte=period_filter["end"],
        )
        new_pos_count = pos_period.count()
        _pos_period_phones = set(pos_period.values_list('phone', flat=True))
        from django.db.models import Q as _Q
        _pks_wi, _vids_wi = get_inv_lookups_for_period(
            period_filter["start"].date(), period_filter["end"].date()
        )
        _inv_phones = set(
            POSCustomer.objects
            .filter(_Q(id__in=_pks_wi) | _Q(vip_id__in=_vids_wi))
            .exclude(phone__isnull=True).exclude(phone='')
            .values_list('phone', flat=True)
        )
        new_pos_inv_count = len(_pos_period_phones & _inv_phones)
        new_pos_no_inv_count = new_pos_count - new_pos_inv_count
        cnv_period = cnv_all.filter(
            cnv_created_at__gte=period_filter["start"],
            cnv_created_at__lte=period_filter["end"],
        )
        new_cnv_count = cnv_period.count()

        pos_only_period_qs = pos_period.exclude(
            phone__in=Subquery(cnv_all.values("phone"))
        )
        pos_only_period_count = pos_only_period_qs.count()
        pos_only_period = list(
            pos_only_period_qs.values(
                "vip_id",
                "phone",
                "name",
                "vip_grade",
                "email",
                "registration_date",
                "points",
            ).order_by("-registration_date")
        )

        cnv_only_period_qs = cnv_period.exclude(
            phone__in=Subquery(pos_all.values("phone"))
        )
        cnv_only_period_count = cnv_only_period_qs.count()
        cnv_only_period = list(
            cnv_only_period_qs.values(
                "cnv_id",
                "phone",
                "last_name",
                "first_name",
                "level_name",
                "email",
                "cnv_created_at",
                "points",
                "total_points",
                "used_points",
            ).order_by("-cnv_created_at")
        )

    # Points mismatch — single Python join
    pos_map = {
        c["phone"]: c
        for c in pos_all.filter(phone__in=Subquery(cnv_all.values("phone"))).values(
            "vip_id", "phone", "name", "vip_grade", "points", "used_points"
        )
    }
    cnv_map = {
        c["phone"]: c
        for c in cnv_all.filter(phone__in=Subquery(pos_all.values("phone"))).values(
            "cnv_id",
            "phone",
            "last_name",
            "first_name",
            "level_name",
            "points",
            "total_points",
            "used_points",
        )
    }

    points_mismatch = []
    total_points_mismatch = []
    for phone, pos_c in pos_map.items():
        cnv_c = cnv_map.get(phone)
        if not cnv_c:
            continue
        pos_pts = int(pos_c.get("points") or 0)
        pos_used = int(pos_c.get("used_points") or 0)
        pos_net = pos_pts - pos_used
        cnv_pts = int(cnv_c.get("points") or 0)
        cnv_total = int(float(cnv_c.get("total_points") or 0))
        base = {
            "phone": phone,
            "pos_vip_id": pos_c["vip_id"],
            "pos_name": pos_c["name"],
            "pos_grade": pos_c["vip_grade"],
            "pos_points": pos_pts,
            "pos_used_points": pos_used,
            "pos_net_points": pos_net,
            "cnv_id": cnv_c["cnv_id"],
            "cnv_name": f"{cnv_c.get('last_name') or ''} {cnv_c.get('first_name') or ''}".strip(),
            "cnv_level": cnv_c["level_name"],
            "cnv_points": cnv_pts,
            "cnv_total_points": cnv_c.get("total_points") or 0,
            "cnv_used_points": cnv_c.get("used_points") or 0,
        }
        if pos_net != cnv_pts:
            points_mismatch.append({**base, "diff": cnv_pts - pos_net})
        if pos_net != cnv_total:
            total_points_mismatch.append({**base, "diff": cnv_total - pos_net})

    points_mismatch.sort(key=lambda x: abs(x["diff"]), reverse=True)
    total_points_mismatch.sort(key=lambda x: abs(x["diff"]), reverse=True)

    # CNV used points
    cnv_used_qs = (
        cnv_all.filter(used_points__gt=0)
        .values(
            "cnv_id",
            "phone",
            "last_name",
            "first_name",
            "level_name",
            "email",
            "cnv_created_at",
            "points",
            "total_points",
            "used_points",
        )
        .order_by("-used_points")
    )
    cnv_used_points_count = cnv_all.filter(used_points__gt=0).count()
    _used_phones = [r["phone"] for r in cnv_used_qs if r["phone"]]
    _pos_phones_set = set(
        pos_all.filter(phone__in=_used_phones).values_list("phone", flat=True)
    )
    cnv_used_points_list = [
        {**r, "in_pos": r["phone"] in _pos_phones_set} for r in cnv_used_qs
    ]

    # Zalo stats
    zalo_app_qs = CNVCustomer.objects.filter(zalo_app_id__isnull=False).exclude(
        zalo_app_id=""
    )
    zalo_oa_qs = CNVCustomer.objects.filter(zalo_oa_id__isnull=False).exclude(
        zalo_oa_id=""
    )
    zalo_app_all_count = zalo_app_qs.count()
    zalo_oa_all_count = zalo_oa_qs.count()
    zalo_app_all_pct = (
        round(zalo_app_all_count / total_cnv_all * 100, 1) if total_cnv_all else 0
    )
    zalo_oa_all_pct = (
        round(zalo_oa_all_count / total_cnv_all * 100, 1) if total_cnv_all else 0
    )

    zalo_app_period_count = zalo_oa_period_count = 0
    zalo_app_period_pct = zalo_oa_period_pct = 0
    if period_filter:
        _pqs = CNVCustomer.objects.filter(
            zalo_app_created_at__gte=period_filter["start"],
            zalo_app_created_at__lte=period_filter["end"],
        )
        zalo_app_period_count = (
            _pqs.filter(zalo_app_id__isnull=False).exclude(zalo_app_id="").count()
        )
        zalo_oa_period_count = (
            _pqs.filter(zalo_oa_id__isnull=False).exclude(zalo_oa_id="").count()
        )
        zalo_app_period_pct = (
            round(zalo_app_period_count / total_cnv_all * 100, 1)
            if total_cnv_all
            else 0
        )
        zalo_oa_period_pct = (
            round(zalo_oa_period_count / total_cnv_all * 100, 1) if total_cnv_all else 0
        )

    _zf = {
        "cnv_id",
        "phone",
        "last_name",
        "first_name",
        "level_name",
        "email",
        "cnv_created_at",
        "points",
        "zalo_app_id",
        "zalo_oa_id",
        "zalo_app_created_at",
    }
    zalo_app_list = list(
        zalo_app_qs.order_by("-zalo_app_created_at").values(*_zf)
    )
    zalo_oa_list = list(zalo_oa_qs.order_by("-zalo_app_created_at").values(*_zf))
    _all_z_phones = {r["phone"] for r in zalo_app_list + zalo_oa_list if r["phone"]}
    _pos_z_phones = (
        set(pos_all.filter(phone__in=_all_z_phones).values_list("phone", flat=True))
        if _all_z_phones
        else set()
    )
    for r in zalo_app_list:
        r["in_pos"] = r["phone"] in _pos_z_phones
    for r in zalo_oa_list:
        r["in_pos"] = r["phone"] in _pos_z_phones

    result = {
        "has_filter": has_filter,
        "period_label": f"{start_date} to {end_date}" if has_filter else "All Time",
        "total_pos": total_pos_all,
        "total_cnv": total_cnv_all,
        "pos_only_all_count": len(pos_only_phones_all),
        "cnv_only_all_count": len(cnv_only_phones_all),
        "new_pos_count": new_pos_count,
        "new_pos_inv_count": new_pos_inv_count,
        "new_pos_no_inv_count": new_pos_no_inv_count,
        "new_cnv_count": new_cnv_count,
        "pos_only_period_count": pos_only_period_count,
        "cnv_only_period_count": cnv_only_period_count,
        "pos_only_all": pos_only_all,
        "cnv_only_all": cnv_only_all,
        "pos_only_period": pos_only_period,
        "cnv_only_period": cnv_only_period,
        "points_mismatch": points_mismatch,
        "points_mismatch_count": len(points_mismatch),
        "total_points_mismatch": total_points_mismatch,
        "total_points_mismatch_count": len(total_points_mismatch),
        "cnv_used_points_list": cnv_used_points_list,
        "cnv_used_points_count": cnv_used_points_count,
        "zalo_app_all_count": zalo_app_all_count,
        "zalo_oa_all_count": zalo_oa_all_count,
        "zalo_app_all_pct": zalo_app_all_pct,
        "zalo_oa_all_pct": zalo_oa_all_pct,
        "zalo_app_period_count": zalo_app_period_count,
        "zalo_oa_period_count": zalo_oa_period_count,
        "zalo_app_period_pct": zalo_app_period_pct,
        "zalo_oa_period_pct": zalo_oa_period_pct,
        "zalo_mini_app_list": zalo_app_list,
        "zalo_oa_list": zalo_oa_list,
        "breakdown": _compute_cnv_breakdown(period_filter, pos_phones_all, cnv_phones_all),
    }
    cache.set(cache_key, result, _CNV_TTL)
    logger.info("CNV comparison cache MISS — computed & cached (%s)", cache_key)
    return result, cache_key


@requires_perm("page_cnv_comparison")
def customer_analytics(request):
    """Compare POS System vs CNV Loyalty customers — served from cache."""
    start_date = request.GET.get("start_date", "")
    end_date = request.GET.get("end_date", "")

    logger.info(
        "customer_analytics: from=%s to=%s user=%s",
        start_date or "all", end_date or "all", request.user,
        extra={"step": "cnv_comparison"},
    )
    d, _ = _get_cnv_comparison_data(start_date, end_date)

    context = {
        **d,
        "start_date": start_date,
        "end_date": end_date,
        # UI display limits — download uses full data from cache
        "points_mismatch":       d["points_mismatch"][:100],
        "total_points_mismatch": d["total_points_mismatch"][:100],
        "cnv_used_points_list":  d["cnv_used_points_list"][:200],
        "zalo_mini_app_list":    d["zalo_mini_app_list"][:100],
        "zalo_oa_list":          d["zalo_oa_list"][:100],
        "pos_only_all":          d["pos_only_all"][:50],
        "cnv_only_all":          d["cnv_only_all"][:50],
        "pos_only_period":       d["pos_only_period"][:50],
        "cnv_only_period":       d["cnv_only_period"][:50],
        "quick_btns": [("Last 7 Days", 7), ("Last 30 Days", 30), ("Last 90 Days", 90)],
        # breakdown display limits (full data goes to Excel)
        "breakdown": {
            # Season lists reversed so newest season appears first
            "season":       list(reversed(d["breakdown"]["season"])),
            "month":        d["breakdown"]["month"],
            "week":         d["breakdown"]["week"][:200],
            "shop":         d["breakdown"]["shop"],
            "season_shop":  list(reversed(d["breakdown"]["season_shop"][:500])),
            "month_shop":   d["breakdown"]["month_shop"][:500],
            "week_shop":    d["breakdown"]["week_shop"][:500],
            "shop_season":  d["breakdown"]["shop_season"],
            "shop_month":   d["breakdown"]["shop_month"],
            "shop_week":    d["breakdown"]["shop_week"],
            "shop_detail":  [
                {**sd, "by_season": list(reversed(sd["by_season"]))}
                for sd in d["breakdown"]["shop_detail"]
            ],
        },
    }
    return render(request, "cnv/customer_analytics.html", context)


@requires_perm("download_cnv")
def export_customer_analytics(request):
    """Export POS vs CNV comparison to Excel.
    If ?tab=<points|zalo|pos_cnv|breakdown> is given, exports only that tab's sheets.
    Otherwise exports the full workbook.
    """
    from App.models import Customer
    from App.analytics.excel_export import export_customer_analytics_to_excel, export_cnv_tab_to_excel, _CNV_TAB_SHEETS

    start_date = request.GET.get("start_date", "")
    end_date = request.GET.get("end_date", "")
    tab = request.GET.get("tab", "").strip()

    date_from = date_to = None
    try:
        if start_date:
            date_from = datetime.strptime(start_date, "%Y-%m-%d").date()
        if end_date:
            date_to = datetime.strptime(end_date, "%Y-%m-%d").date()
    except ValueError:
        pass

    logger.info(
        "export_customer_analytics: from=%s to=%s tab=%s user=%s",
        date_from, date_to, tab or "full", request.user,
        extra={"step": "export_customer_analytics"},
    )
    d, _ = _get_cnv_comparison_data(start_date, end_date)
    ts = datetime.now().strftime('%H%M%S')
    period = f"{date_from}_{date_to}" if date_from and date_to else datetime.now().strftime('%Y%m%d')

    if tab and tab in _CNV_TAB_SHEETS:
        wb = export_cnv_tab_to_excel(tab, d, date_from=date_from, date_to=date_to)
        filename = f"customer_analytics_{tab}_{period}_{ts}.xlsx"
    else:
        cnv_used_points_export = list(
            CNVCustomer.objects.filter(used_points__gt=0).order_by("-used_points")
        )
        zalo_stats_export = {k: d[k] for k in (
            "zalo_app_all_count", "zalo_oa_all_count", "zalo_app_all_pct", "zalo_oa_all_pct",
            "zalo_app_period_count", "zalo_oa_period_count", "zalo_app_period_pct", "zalo_oa_period_pct",
        )}
        wb = export_customer_analytics_to_excel(
            Customer.objects.all(), CNVCustomer.objects.all(), date_from, date_to,
            points_mismatch=d["points_mismatch"],
            total_points_mismatch=d["total_points_mismatch"],
            cnv_used_points=cnv_used_points_export,
            zalo_mini_app_list=d["zalo_mini_app_list"],
            zalo_oa_list=d["zalo_oa_list"],
            zalo_stats=zalo_stats_export,
        )
        filename = f"customer_analytics_{period}_{ts}.xlsx"

    response = HttpResponse(
        content_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
    )
    response["Content-Disposition"] = f'attachment; filename="{filename}"'
    wb.save(response)
    return response


@requires_perm("page_cnv_sync")
def sync_cnv_points(request):
    """
    AJAX endpoint: sync points for a list of CNV customer IDs.
    POST body JSON: { "cnv_ids": [123, 456, ...] }
    Returns JSON: { "results": [ {cnv_id, status, points, total_points, used_points, level_name}, ... ] }
    """
    import json
    from django.http import JsonResponse
    from decimal import Decimal
    from App.cnv.api_client import CNVAPIClient

    if request.method != "POST":
        return JsonResponse({"error": "POST required"}, status=405)

    try:
        body = json.loads(request.body)
        cnv_ids = body.get("cnv_ids", [])
    except Exception:
        return JsonResponse({"error": "Invalid JSON"}, status=400)

    if not cnv_ids:
        return JsonResponse({"error": "No cnv_ids provided"}, status=400)

    client = CNVAPIClient(settings.CNV_USERNAME, settings.CNV_PASSWORD)
    results = []

    logger.info("sync_cnv_points: syncing %d ids by=%s", len(cnv_ids), request.user, extra={"step": "cnv_points_sync"})
    for cnv_id in cnv_ids:
        try:
            response = client.get_customer_membership(int(cnv_id))
            if response and "membership" in response:
                m = response["membership"]
                points = Decimal(str(m.get("points", 0)))
                total_pts = Decimal(str(m.get("total_points", 0)))
                used_pts = Decimal(str(m.get("used_points", 0)))
                level_name = m.get("level_name")

                CNVCustomer.objects.filter(cnv_id=cnv_id).update(
                    points=points,
                    total_points=total_pts,
                    used_points=used_pts,
                    level_name=level_name,
                )
                results.append(
                    {
                        "cnv_id": cnv_id,
                        "status": "ok",
                        "points": float(points),
                        "total_points": float(total_pts),
                        "used_points": float(used_pts),
                        "level_name": level_name,
                    }
                )
            else:
                logger.warning("sync_cnv_points: no membership data for cnv_id=%s", cnv_id, extra={"step": "cnv_points_sync"})
                results.append({"cnv_id": cnv_id, "status": "no_data"})
        except Exception as e:
            logger.error("sync_cnv_points: cnv_id=%s error=%s", cnv_id, e, extra={"step": "cnv_points_sync"})
            results.append({"cnv_id": cnv_id, "status": "error", "error": str(e)})

    ok = sum(1 for r in results if r["status"] == "ok")
    logger.info("sync_cnv_points: done ok=%d no_data=%d error=%d", ok, len(results) - ok, sum(1 for r in results if r["status"] == "error"), extra={"step": "cnv_points_sync"})
    return JsonResponse({"results": results})


# ============================================================================
# MANUAL SYNC TRIGGERS
# ============================================================================


@requires_perm("page_cnv_sync")
@require_POST
def trigger_sync(request):
    """
    AJAX: Trigger manual sync for customers or orders.
    Checks CNVSyncLog for running jobs before starting.
    """
    import json

    try:
        body = json.loads(request.body)
        sync_type = body.get("sync_type")  # 'customers' or 'orders'
    except Exception:
        return JsonResponse({"error": "Invalid JSON"}, status=400)

    if sync_type not in ("customers", "orders"):
        return JsonResponse({"error": "Invalid sync_type"}, status=400)

    logger.info("trigger_sync: type=%s user=%s", sync_type, request.user, extra={"step": "cnv_sync"})

    # Clear orphaned "running" logs before checking (in case of previous crash/restart)
    from datetime import timedelta
    from App.cnv.scheduler import _STALE_SYNC_HOURS
    stale_threshold = timezone.now() - timedelta(hours=_STALE_SYNC_HOURS)
    stale_count = CNVSyncLog.objects.filter(
        sync_type=sync_type,
        status="running",
        started_at__lt=stale_threshold,
    ).update(
        status="failed",
        error_message=f"Auto-failed: stuck for > {_STALE_SYNC_HOURS}h (orphaned after restart)",
        completed_at=timezone.now(),
    )
    if stale_count:
        logger.warning("trigger_sync: cleared %d stale %s sync log(s)", stale_count, sync_type, extra={"step": "cnv_sync"})

    # Check if already running (scheduler functions also check, but check here first
    # to give a fast response to the user)
    if CNVSyncLog.objects.filter(sync_type=sync_type, status="running").exists():
        return JsonResponse(
            {
                "status": "skipped",
                "message": f"A {sync_type} sync is already running. Please wait for it to complete.",
            }
        )

    def _run():
        from django.db import connection
        from App.cnv.scheduler import sync_cnv_customers_only, sync_cnv_orders_only
        try:
            # Re-check inside the thread — APScheduler may have fired in the gap
            # between the HTTP check above and this thread starting
            if CNVSyncLog.objects.filter(sync_type=sync_type, status="running").exists():
                logger.warning("trigger_sync: %s already running (race guard), aborting", sync_type, extra={"step": "cnv_sync"})
                return
            if sync_type == "customers":
                sync_cnv_customers_only()
            else:
                sync_cnv_orders_only()
        finally:
            connection.close()  # always release DB connection held by this thread

    t = threading.Thread(target=_run, daemon=True)
    t.start()

    return JsonResponse(
        {
            "status": "started",
            "message": f"{sync_type.capitalize()} sync started in background.",
        }
    )


@requires_perm("page_cnv_sync")
@require_POST
def trigger_zalo_sync(request):
    """
    AJAX: Start Zalo sync for all CNV customers.
    Accepts cookie in POST body.
    """
    import json
    from App.cnv.zalo_sync import run_zalo_sync, is_zalo_sync_running

    try:
        body = json.loads(request.body)
        cookie = body.get("cookie", "").strip()
    except Exception:
        return JsonResponse({"error": "Invalid JSON"}, status=400)

    if not cookie:
        return JsonResponse({"error": "Cookie is required"}, status=400)

    logger.info("trigger_zalo_sync: user=%s", request.user, extra={"step": "zalo_sync"})

    # Clear orphaned "running" Zalo logs before checking
    from datetime import timedelta
    from App.cnv.zalo_sync import _STALE_ZALO_HOURS
    stale_threshold = timezone.now() - timedelta(hours=_STALE_ZALO_HOURS)
    stale_count = CNVSyncLog.objects.filter(
        sync_type="zalo_sync",
        status="running",
        started_at__lt=stale_threshold,
    ).update(
        status="failed",
        error_message=f"Auto-failed: stuck for > {_STALE_ZALO_HOURS}h (orphaned after restart)",
        completed_at=timezone.now(),
    )
    if stale_count:
        logger.warning("trigger_zalo_sync: cleared %d stale log(s)", stale_count, extra={"step": "zalo_sync"})

    # In-memory guard (same-process fast path)
    if is_zalo_sync_running():
        return JsonResponse(
            {
                "status": "skipped",
                "message": "Zalo sync is already running. Please wait.",
            }
        )

    # DB guard (authoritative cross-worker check)
    if CNVSyncLog.objects.filter(sync_type="zalo_sync", status="running").exists():
        return JsonResponse(
            {
                "status": "skipped",
                "message": "Zalo sync is already running (see sync log). Please wait.",
            }
        )

    total = CNVCustomer.objects.count()
    logger.info("trigger_zalo_sync: starting for total=%d customers", total, extra={"step": "zalo_sync"})
    t = threading.Thread(target=run_zalo_sync, args=(cookie,), daemon=True)
    t.start()

    return JsonResponse(
        {
            "status": "started",
            "message": f"Zalo sync started for {total:,} customers. This may take a while.",
            "total": total,
        }
    )


