"""
CNV Views
Handles CNV Loyalty integration pages
"""

import json
import logging
import threading

from django.conf import settings
from django.core.cache import cache
from django.http import Http404, HttpResponse, JsonResponse
from django.shortcuts import render
from django.db.models import Count, Q
from django.db.models.functions import ExtractYear, ExtractMonth, ExtractWeek
from App.permissions import requires_perm
from django.views.decorators.http import require_POST
from datetime import datetime
from django.utils import timezone

from App.models import Customer as POSCustomer
from App.models_cnv import CNVCustomer, CNVOrder, CNVSyncLog

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

    if period_filter:
        pos_period = pos_all.filter(
            registration_date__gte=period_filter["start"],
            registration_date__lte=period_filter["end"],
        )
        new_pos_count = pos_period.count()
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
    }
    cache.set(cache_key, result, _CNV_TTL)
    logger.info("CNV comparison cache MISS — computed & cached (%s)", cache_key)
    return result, cache_key


@requires_perm("page_cnv_comparison")
def customer_comparison(request):
    """Compare POS System vs CNV Loyalty customers — served from cache."""
    start_date = request.GET.get("start_date", "")
    end_date = request.GET.get("end_date", "")

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
    }
    return render(request, "cnv/customer_comparison.html", context)


@requires_perm("download_cnv")
def export_customer_comparison(request):
    """Export POS vs CNV comparison to Excel.
    If ?tab=<points|zalo|pos_cnv> is given, exports only that tab's sheets.
    Otherwise exports the full workbook.
    """
    from App.models import Customer
    from App.analytics.excel_export import export_customer_comparison_to_excel, export_cnv_tab_to_excel, _CNV_TAB_SHEETS

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
        wb = export_customer_comparison_to_excel(
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
                results.append({"cnv_id": cnv_id, "status": "no_data"})
        except Exception as e:
            results.append({"cnv_id": cnv_id, "status": "error", "error": str(e)})

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

    # Check if already running
    if CNVSyncLog.objects.filter(sync_type=sync_type, status="running").exists():
        return JsonResponse(
            {
                "status": "skipped",
                "message": f"A {sync_type} sync is already running. Please wait for it to complete.",
            }
        )

    def _run():
        from App.cnv.scheduler import sync_cnv_customers_only, sync_cnv_orders_only

        if sync_type == "customers":
            sync_cnv_customers_only()
        else:
            sync_cnv_orders_only()

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

    # In-memory guard
    if is_zalo_sync_running():
        return JsonResponse(
            {
                "status": "skipped",
                "message": "Zalo sync is already running. Please wait.",
            }
        )

    # DB guard
    if CNVSyncLog.objects.filter(sync_type="zalo_sync", status="running").exists():
        return JsonResponse(
            {
                "status": "skipped",
                "message": "Zalo sync is already running (see sync log). Please wait.",
            }
        )

    total = CNVCustomer.objects.count()
    t = threading.Thread(target=run_zalo_sync, args=(cookie,), daemon=True)
    t.start()

    return JsonResponse(
        {
            "status": "started",
            "message": f"Zalo sync started for {total:,} customers. This may take a while.",
            "total": total,
        }
    )


# ═══════════════════════════════════════════════════════════════
#  CUSTOMER ANALYTICS CHARTS
# ═══════════════════════════════════════════════════════════════

_CUST_CHART_VER_KEY = "cust_chart_ver"
_CUST_CHART_TTL = 300


def _cust_chart_cache_key(start_date, end_date):
    v = cache.get(_CUST_CHART_VER_KEY, 0)
    return f"cust_chart:{v}:{start_date}:{end_date}"


def _compute_customer_chart_data(date_from=None, date_to=None):
    """Compute all data needed for Customer Analytics Charts page.

    Uses the same base querysets as _get_cnv_comparison_data so that
    all four metrics are calculated identically between both pages.
    """
    # ── Base querysets (mirrors _get_cnv_comparison_data) ───────
    # POS: exclude vip_id=0 (non-VIP), require phone
    pos_base = (
        POSCustomer.objects.filter(vip_id__isnull=False, phone__isnull=False)
        .exclude(vip_id=0).exclude(phone="")
    )
    # CNV: require phone (needed for POS↔CNV matching)
    cnv_base = CNVCustomer.objects.filter(phone__isnull=False).exclude(phone="")
    # Zalo: exclude empty-string IDs (as in customer_comparison)
    zalo_app_base = (
        CNVCustomer.objects.filter(zalo_app_id__isnull=False, zalo_app_created_at__isnull=False)
        .exclude(zalo_app_id="")
    )
    zalo_oa_base = (
        CNVCustomer.objects.filter(zalo_oa_id__isnull=False, zalo_app_created_at__isnull=False)
        .exclude(zalo_oa_id="")
    )

    # ── All-time overview (no date filter) ──────────────────────
    total_cnv     = CNVCustomer.objects.count()
    total_pos     = POSCustomer.objects.filter(vip_id__isnull=False).exclude(vip_id=0).count()
    active_zalo_t = CNVCustomer.objects.filter(zalo_app_id__isnull=False).exclude(zalo_app_id="").count()
    follow_oa_t   = CNVCustomer.objects.filter(zalo_oa_id__isnull=False).exclude(zalo_oa_id="").count()

    # POS ↔ CNV overlap — set-difference (mirrors customer_comparison)
    pos_phones = set(pos_base.values_list("phone", flat=True))
    cnv_phones = set(cnv_base.values_list("phone", flat=True))
    cnv_only_count = len(cnv_phones - pos_phones)
    pos_only_count = len(pos_phones - cnv_phones)

    # ── Inner helper: build week / month / season / year series ─
    def _build_series(df=None, dt=None):
        qs_pos  = pos_base
        qs_cnv  = cnv_base
        qs_zalo = zalo_app_base
        qs_oa   = zalo_oa_base
        if df:
            qs_pos  = qs_pos.filter(registration_date__gte=df)
            qs_cnv  = qs_cnv.filter(cnv_created_at__date__gte=df)
            qs_zalo = qs_zalo.filter(zalo_app_created_at__date__gte=df)
            qs_oa   = qs_oa.filter(zalo_app_created_at__date__gte=df)
        if dt:
            qs_pos  = qs_pos.filter(registration_date__lte=dt)
            qs_cnv  = qs_cnv.filter(cnv_created_at__date__lte=dt)
            qs_zalo = qs_zalo.filter(zalo_app_created_at__date__lte=dt)
            qs_oa   = qs_oa.filter(zalo_app_created_at__date__lte=dt)

        def _grp_month(qs, field):
            return {
                f"{d['y']:04d}-{d['m']:02d}": d["cnt"]
                for d in qs.annotate(y=ExtractYear(field), m=ExtractMonth(field))
                           .values("y", "m").annotate(cnt=Count("id")).order_by("y", "m")
                if d["y"] and d["m"]
            }

        def _grp_week(qs, field):
            return {
                f"{d['y']:04d}-W{d['w']:02d}": d["cnt"]
                for d in qs.annotate(y=ExtractYear(field), w=ExtractWeek(field))
                           .values("y", "w").annotate(cnt=Count("id")).order_by("y", "w")
                if d["y"] and d["w"]
            }

        def _grp_year(qs, field):
            return {
                str(d["y"]): d["cnt"]
                for d in qs.annotate(y=ExtractYear(field))
                           .values("y").annotate(cnt=Count("id")).order_by("y")
                if d["y"]
            }

        # Month
        pm = _grp_month(qs_pos,  "registration_date")
        nm = _grp_month(qs_cnv,  "cnv_created_at")
        zm = _grp_month(qs_zalo, "zalo_app_created_at")
        om = _grp_month(qs_oa,   "zalo_app_created_at")
        all_months = sorted(set(pm) | set(nm) | set(zm) | set(om))
        month_stats = [
            {"month": m, "new_pos_users": pm.get(m, 0), "new_cnv_users": nm.get(m, 0),
             "active_zalo": zm.get(m, 0), "follow_oa": om.get(m, 0)}
            for m in all_months
        ]

        # Season: SS = Jan-Jun, AW = Jul-Dec
        season_data = {}
        for ms in month_stats:
            y, mo = ms["month"].split("-")
            s = f"{'SS' if int(mo) <= 6 else 'AW'}{y}"
            if s not in season_data:
                season_data[s] = {"season": s, "new_pos_users": 0, "new_cnv_users": 0,
                                  "active_zalo": 0, "follow_oa": 0}
            for k in ("new_pos_users", "new_cnv_users", "active_zalo", "follow_oa"):
                season_data[s][k] += ms[k]
        season_stats = [season_data[s] for s in sorted(season_data)]

        # Week
        pw = _grp_week(qs_pos,  "registration_date")
        nw = _grp_week(qs_cnv,  "cnv_created_at")
        zw = _grp_week(qs_zalo, "zalo_app_created_at")
        ow = _grp_week(qs_oa,   "zalo_app_created_at")
        all_weeks = sorted(set(pw) | set(nw) | set(zw) | set(ow))
        week_stats = [
            {"week": w, "new_pos_users": pw.get(w, 0), "new_cnv_users": nw.get(w, 0),
             "active_zalo": zw.get(w, 0), "follow_oa": ow.get(w, 0)}
            for w in all_weeks
        ]

        # Year
        py_ = _grp_year(qs_pos,  "registration_date")
        ny_ = _grp_year(qs_cnv,  "cnv_created_at")
        zy_ = _grp_year(qs_zalo, "zalo_app_created_at")
        oy_ = _grp_year(qs_oa,   "zalo_app_created_at")
        all_years = sorted(set(py_) | set(ny_) | set(zy_) | set(oy_))
        year_stats = [
            {"year": y, "new_pos_users": py_.get(y, 0), "new_cnv_users": ny_.get(y, 0),
             "active_zalo": zy_.get(y, 0), "follow_oa": oy_.get(y, 0)}
            for y in all_years
        ]

        return month_stats, season_stats, week_stats, year_stats

    month_stats,     season_stats,     week_stats,     year_stats     = _build_series(date_from, date_to)
    all_month_stats, all_season_stats, all_week_stats, all_year_stats = _build_series()  # all-time for YOY

    return {
        "overview": {
            "total_cnv":   total_cnv,
            "active_zalo": active_zalo_t,
            "follow_oa":   follow_oa_t,
            "cnv_only":    cnv_only_count,
            "pos_only":    pos_only_count,
            "total_pos":   total_pos,
        },
        "month_stats":      month_stats,
        "season_stats":     season_stats,
        "week_stats":       week_stats,
        "year_stats":       year_stats,
        "all_month_stats":  all_month_stats,
        "all_season_stats": all_season_stats,
        "all_week_stats":   all_week_stats,
        "all_year_stats":   all_year_stats,
    }


@requires_perm("page_customer_chart")
def customer_chart(request):
    """Customer Analytics Charts — donut overview + bar chart + YOY comparison."""
    if not getattr(settings, "SHOW_CUSTOMER_CHART", False):
        raise Http404
    start_date = request.GET.get("start_date", "")
    end_date   = request.GET.get("end_date", "")

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
        date_from = date_to = None
        start_date = end_date = ""

    cache_key = _cust_chart_cache_key(start_date, end_date)
    data = cache.get(cache_key)
    if data is None:
        data = _compute_customer_chart_data(date_from, date_to)
        cache.set(cache_key, data, _CUST_CHART_TTL)

    now_year = datetime.now().year
    return render(
        request,
        "cnv/customer_chart.html",
        {
            "overview":         data["overview"],
            "chart_data_json":  json.dumps(data),
            "start_date":       start_date,
            "end_date":         end_date,
            "quick_btns":       [("Last 7 Days", 7), ("Last 30 Days", 30), ("Last 90 Days", 90)],
            "year_btns":        [now_year - i for i in range(4)],
        },
    )
