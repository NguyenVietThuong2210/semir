"""
CNV Views
Handles CNV Loyalty integration pages
"""

import logging
import threading

from django.conf import settings
from django.db.models import Count
from django.http import HttpResponse, JsonResponse
from django.shortcuts import render
from App.permissions import requires_perm
from django.views.decorators.http import require_POST
from datetime import datetime, timedelta, date as _date
from django.utils import timezone

from App.models import Customer as POSCustomer
from App.cnv.models import CNVCustomer, CNVOrder, CNVSyncLog
from App.cnv.service import (
    parse_cnv_period_filter,
    get_cnv_customer_kpis,
    get_cnv_phone_sets,
    get_cnv_comparison_data,
)

logger = logging.getLogger("App.cnv")


@requires_perm("cnv.sync")
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




@requires_perm("cnv.view")
def customer_analytics(request):
    """
    Compare POS System vs CNV Loyalty customers.
    Lazy loading: initial page only computes bd_season (first BD tab) + summary counts.
    Other tabs load via AJAX on first click.
    """
    from App.analytics.tab_functions import get_customer_tab
    from App.views.view_utils import filter_params_str

    start_date = request.GET.get("start_date", "")
    end_date   = request.GET.get("end_date", "")

    logger.info(
        "customer_analytics: from=%s to=%s user=%s",
        start_date or "all", end_date or "all", request.user,
        extra={"step": "cnv_comparison"},
    )

    period_filter, has_filter = parse_cnv_period_filter(start_date, end_date)
    period_label = f"{start_date} to {end_date}" if has_filter else "All Time"

    pos_phones_all, cnv_phones_all = get_cnv_phone_sets()
    kpis = get_cnv_customer_kpis(period_filter, has_filter, pos_phones_all, cnv_phones_all)

    # First BD tab (bd_season) — server-rendered; other tabs load lazily
    bd_season_data = get_customer_tab('bd_season', start_date, end_date)
    lazy_params = filter_params_str(start_date=start_date, end_date=end_date)

    context = {
        "has_filter":             has_filter,
        "period_label":           period_label,
        "total_pos":              kpis['total_pos'],
        "total_cnv":              kpis['total_cnv'],
        "pos_only_all_count":     kpis['pos_only_all'],
        "cnv_only_all_count":     kpis['cnv_only_all'],
        "new_pos_count":          kpis['new_pos'],
        "new_pos_inv_count":      kpis['new_pos_inv'],
        "new_pos_no_inv_count":   kpis['new_pos_no_inv'],
        "new_cnv_count":          kpis['new_cnv'],
        "pos_only_period_count":  kpis['pos_only_period'],
        "cnv_only_period_count":  kpis['cnv_only_period'],
        "breakdown": {"season": bd_season_data["by_season"]},
        "lazy_params":  lazy_params,
        "start_date":   start_date,
        "end_date":     end_date,
        "quick_btns":   [("Last 7 Days", 7), ("Last 30 Days", 30), ("Last 90 Days", 90)],
    }
    return render(request, "cnv/customer_analytics.html", context)


@requires_perm("cnv.view")
def customer_tab(request, tab: str):
    """
    AJAX endpoint: returns a rendered HTML fragment for one Customer Analytics tab.
    Called by lazy_tabs_js.html on first tab click.
    """
    from django.http import HttpResponseBadRequest
    from App.analytics.tab_functions import get_customer_tab, CUSTOMER_TABS

    if not request.headers.get('X-Requested-With') == 'XMLHttpRequest':
        return HttpResponseBadRequest("AJAX only")
    if tab not in CUSTOMER_TABS:
        return HttpResponseBadRequest(f"Invalid tab: {tab!r}")

    start_date = request.GET.get("start_date", "")
    end_date   = request.GET.get("end_date", "")

    logger.info(
        "customer_tab: tab=%s from=%s to=%s user=%s",
        tab, start_date or "all", end_date or "all", request.user,
        extra={"step": "customer_tab"},
    )

    data = get_customer_tab(tab, start_date=start_date, end_date=end_date)
    ctx = {
        **data,
        "start_date": start_date,
        "end_date":   end_date,
    }
    return render(request, f"cnv/tabs/{tab}.html", ctx)


@requires_perm("cnv.export")
def export_customer_analytics(request):
    """Export POS vs CNV comparison to Excel.
    If ?tab=<points|zalo|pos_cnv|breakdown> is given, exports only that tab's sheets.
    Otherwise exports the full workbook.
    """
    from App.models import Customer
    from App.analytics.excel_export import (
        export_customer_analytics_to_excel,
        export_cnv_tab_to_excel,
        _CNV_TAB_SHEETS,
    )

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
    d, _ = get_cnv_comparison_data(start_date, end_date)
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
            zalo_mini_app_inactive_list=d["zalo_mini_app_inactive_list"],
            zalo_oa_list=d["zalo_oa_list"],
            zalo_stats=zalo_stats_export,
        )
        filename = f"customer_analytics_{period}_{ts}.xlsx"

    logger.info("export_customer_analytics: file=%s user=%s", filename, request.user,
                extra={"step": "export_customer_analytics"})
    response = HttpResponse(
        content_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
    )
    response["Content-Disposition"] = f'attachment; filename="{filename}"'
    wb.save(response)
    return response


@requires_perm("cnv.sync")
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
    except json.JSONDecodeError:
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


@requires_perm("cnv.sync")
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
    except json.JSONDecodeError:
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


@requires_perm("cnv.sync")
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
    except json.JSONDecodeError:
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


# ══════════════════════════════════════════════════════════════════════════════
#  CUSTOMER ANALYTICS CHARTS
# ══════════════════════════════════════════════════════════════════════════════

_CUST_CHART_TTL = 300   # 5-min cache for full chart result
_CUST_OV_TTL   = 600   # 10-min cache for all-time overview counts (rarely change)

_CUST_OV_CACHE_KEY = "cust_chart_overview_counts"


def _cust_chart_cache_key(start_date: str, end_date: str) -> str:
    return f"cust_chart:{start_date}:{end_date}"


def compute_customer_chart_data(start_date: str = "", end_date: str = "") -> dict:
    """
    Compute all chart data for Customer Analytics Charts page.

    Uses the SAME underlying service calls as the customer analytics page:
      - compute_cnv_breakdown() via _fetch_bd_raw() → same cache, same numbers
      - get_cnv_phone_sets()                        → shared all-time phone sets

    This guarantees chart data ≡ table data for every metric.

    Performance improvements over v1:
      1. Overview counts cached separately for 10 min (all-time, rarely change).
      2. Shop dims merged into the same compute_cnv_breakdown call → single _fetch_bd_raw.
      3. Full chart result still cached 5 min per (start_date, end_date).
      4. YOY breakdown ({} period) shares _fetch_bd_raw cache with other all-time calls.
    """
    from django.core.cache import cache as _djc
    from App.cnv.service import (
        parse_cnv_period_filter,
        get_cnv_phone_sets,
        compute_cnv_breakdown,
    )

    _cache_key = _cust_chart_cache_key(start_date, end_date)
    hit = _djc.get(_cache_key)
    if hit is not None:
        return hit

    period_filter, _ = parse_cnv_period_filter(start_date, end_date)
    pos_phones_all, cnv_phones_all = get_cnv_phone_sets()

    # ── Overview counts: cached separately (all-time, 10 min TTL) ────────────
    ov = _djc.get(_CUST_OV_CACHE_KEY)
    if ov is None:
        ov = {
            "total_cnv":   CNVCustomer.objects.count(),
            "total_pos":   POSCustomer.objects.filter(
                               vip_id__isnull=False).exclude(vip_id=0).count(),
            "active_zalo": CNVCustomer.objects.filter(
                               zalo_app_id__isnull=False).exclude(zalo_app_id="").count(),
            "follow_oa":   CNVCustomer.objects.filter(
                               zalo_oa_id__isnull=False).exclude(zalo_oa_id="").count(),
        }
        _djc.set(_CUST_OV_CACHE_KEY, ov, timeout=_CUST_OV_TTL)

    pos_only_count = len(pos_phones_all - cnv_phones_all)
    cnv_only_count = len(cnv_phones_all - pos_phones_all)

    # ── Breakdown (filtered period) — includes shop dims in one pass ──────────
    # Adding shop dims costs only Python accumulation (same _fetch_bd_raw DB hit).
    _DIMS_PERIOD = frozenset({'season', 'month', 'week',
                              'shop', 'season_shop', 'month_shop', 'week_shop'})
    bd = compute_cnv_breakdown(period_filter, pos_phones_all, cnv_phones_all, dims=_DIMS_PERIOD)

    # ── All-time breakdown for YOY (shares _fetch_bd_raw("") cache) ──────────
    _DIMS_ALL = frozenset({'season', 'month', 'week'})
    bd_all = compute_cnv_breakdown({}, pos_phones_all, cnv_phones_all, dims=_DIMS_ALL)

    # ── Serialisers ───────────────────────────────────────────────────────────
    def _ser_row(row, time_key, time_val):
        return {
            time_key:       time_val,
            "new_pos_inv":  row["new_pos_inv"],
            "new_pos_no_inv": row["new_pos_no_inv"],
            "new_pos":      row["new_pos"],
            "new_pos_only": row["new_pos_only"],
            "new_cnv":      row["new_cnv"],
            "new_cnv_only": row["new_cnv_only"],
            "zalo_app":     row["zalo_app"],
            "zalo_app_pct": row["zalo_app_pct"],
            "zalo_oa":      row["zalo_oa"],
            "zalo_oa_pct":  row["zalo_oa_pct"],
        }

    def _ser_season(rows):
        return [_ser_row(r, "label", r["label"]) for r in rows]

    def _ser_month(rows):
        return [_ser_row(r, "month", r["label"]) for r in rows]

    def _ser_week(rows):
        return [_ser_row(r, "week", r["label"]) for r in rows]

    # ── Per-shop series: {shop_name: {season, month, week}} ──────────────────
    # shop_season / shop_month / shop_week from compute_cnv_breakdown:
    #   [{"shop": "Shop A", "rows": [{"label": "M2-4 2025", "new_pos": 5, ...}]}, ...]
    def _shop_series(shop_list_key, ser_fn):
        out = {}
        for sh_entry in bd.get(shop_list_key, []):
            out[sh_entry["shop"]] = ser_fn(sh_entry["rows"])
        return out

    shop_season_map = _shop_series("shop_season", _ser_season)
    shop_month_map  = _shop_series("shop_month",  _ser_month)
    shop_week_map   = _shop_series("shop_week",   _ser_week)

    all_shops = sorted(
        set(shop_season_map) | set(shop_month_map) | set(shop_week_map)
    )

    shop_stats = {
        shop: {
            "season": shop_season_map.get(shop, []),
            "month":  shop_month_map.get(shop, []),
            "week":   shop_week_map.get(shop, []),
        }
        for shop in all_shops
    }

    result = {
        "overview": {
            **ov,
            "cnv_only": cnv_only_count,
            "pos_only": pos_only_count,
        },
        # Filtered period series (trend line + period totals bar)
        "season_stats": _ser_season(bd["season"]),
        "month_stats":  _ser_month(bd["month"]),
        "week_stats":   _ser_week(bd["week"]),
        # All-time series (YOY chart)
        "all_season_stats": _ser_season(bd_all["season"]),
        "all_month_stats":  _ser_month(bd_all["month"]),
        "all_week_stats":   _ser_week(bd_all["week"]),
        # Per-shop data (Period Totals shop selector)
        "shops":      all_shops,
        "shop_stats": shop_stats,
    }

    _djc.set(_cache_key, result, timeout=_CUST_CHART_TTL)
    return result


@requires_perm("cnv.chart")
def customer_chart(request):
    """Customer Analytics Charts — donut overview + trend lines + bar + YOY comparison."""
    import json

    start_date = request.GET.get("start_date", "")
    end_date   = request.GET.get("end_date", "")

    # Validate / normalise dates
    date_from = date_to = None
    try:
        if start_date:
            date_from = datetime.strptime(start_date, "%Y-%m-%d").date()
    except ValueError:
        start_date = ""
    try:
        if end_date:
            date_to = datetime.strptime(end_date, "%Y-%m-%d").date()
    except ValueError:
        end_date = ""
    if date_from and date_to and date_from > date_to:
        start_date = end_date = ""

    logger.info(
        "customer_chart: from=%s to=%s user=%s",
        start_date or "all", end_date or "all", request.user,
        extra={"step": "customer_chart"},
    )

    data = compute_customer_chart_data(start_date, end_date)
    now_year = datetime.now().year

    return render(
        request,
        "cnv/customer_chart.html",
        {
            "overview":        data["overview"],
            "chart_data_json": data,
            "chart_shops":     data["shops"],   # sorted list for template checklist
            "start_date":      start_date,
            "end_date":        end_date,
            "quick_btns":      [("Last 7 Days", 7), ("Last 30 Days", 30), ("Last 90 Days", 90)],
            "year_btns":       [now_year - i for i in range(4)],
        },
    )




@requires_perm("cnv.export_chart")
def export_customer_chart_excel(request):
    """Export Customer Analytics Chart data to Excel workbook matching current UI state."""
    from App.analytics.excel_export import export_customer_chart_to_excel
    from django.http import HttpResponse
    from django.shortcuts import redirect

    start_date = request.GET.get("start_date", "")
    end_date = request.GET.get("end_date", "")

    def _shops(key):
        return [s for s in request.GET.get(key, "").split(",") if s.strip()]

    trend_xaxis  = request.GET.get("trend_xaxis", "month")
    trend_metric = request.GET.get("trend_metric", "new_pos")
    trend_shops  = _shops("trend_shops")
    bar_xaxis    = request.GET.get("bar_xaxis", "month")
    bar_metric   = request.GET.get("bar_metric", "new_pos")
    bar_shops    = _shops("bar_shops")
    yoy_xaxis    = request.GET.get("yoy_xaxis", "month")
    yoy_metric   = request.GET.get("yoy_metric", "new_pos")

    logger.info(
        "export_customer_chart_excel: from=%s to=%s user=%s",
        start_date or "all", end_date or "all", request.user,
        extra={"step": "export_customer_chart_excel"},
    )

    data = compute_customer_chart_data(start_date, end_date)

    wb = export_customer_chart_to_excel(
        data, start_date=start_date, end_date=end_date,
        trend_xaxis=trend_xaxis, trend_metric=trend_metric, trend_shops=trend_shops,
        bar_xaxis=bar_xaxis, bar_metric=bar_metric, bar_shops=bar_shops,
        yoy_xaxis=yoy_xaxis, yoy_metric=yoy_metric,
    )

    ts = datetime.now().strftime('%H%M%S')
    period = f"{start_date}_{end_date}" if start_date and end_date else datetime.now().strftime('%Y%m%d')
    fn = f"customer_chart_{period}_{ts}.xlsx"

    resp = HttpResponse(
        content_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
    )
    resp["Content-Disposition"] = f'attachment; filename="{fn}"'
    wb.save(resp)
    return resp
