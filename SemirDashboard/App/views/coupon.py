"""App/views/coupon.py — Coupon analytics views."""
import json
import logging
import threading
from datetime import datetime

from django.shortcuts import render, redirect
from django.contrib import messages
from django.http import HttpResponse
from django.core.cache import cache

from App.permissions import requires_perm
from App.analytics.coupon_analytics import (
    calculate_coupon_analytics,
    export_coupon_to_excel,
    export_coupon_tab_to_excel,
    _COUPON_TAB_SHEETS,
)
from App.models import CouponCampaign

logger = logging.getLogger(__name__)

_COUPON_TTL = 600  # 10 minutes
_cpn_ver_lock = threading.Lock()
_cpn_ver = 0
_cpn_trend_ver = 0


def _coupon_cache_key(date_from, date_to, prefix, shop_group):
    return f"cpn_data:{_cpn_ver}:{date_from}:{date_to}:{prefix}:{shop_group}"


def _coupon_trend_cache_key(date_from, date_to, shop_group, prefix):
    return f"cpn_trend:{_cpn_trend_ver}:{date_from}:{date_to}:{shop_group}:{prefix}"


def _invalidate_coupon_cache():
    global _cpn_ver, _cpn_trend_ver
    with _cpn_ver_lock:
        _cpn_ver += 1
        _cpn_trend_ver += 1
    logger.info("coupon cache invalidated (in-process ver->%d, trend_ver->%d)", _cpn_ver, _cpn_trend_ver)


def _get_coupon_data(date_from, date_to, prefix, shop_group):
    """Return full coupon analytics dict from cache or compute it."""
    cache_key = _coupon_cache_key(date_from, date_to, prefix, shop_group)
    data = cache.get(cache_key)
    if data is not None:
        logger.info("coupon cache HIT (%s)", cache_key)
        return data, cache_key

    data = calculate_coupon_analytics(
        date_from=date_from,
        date_to=date_to,
        coupon_id_prefix=prefix or None,
        shop_group=shop_group or None,
    )
    cache.set(cache_key, data, _COUPON_TTL)
    logger.info("coupon cache MISS — computed & cached (%s)", cache_key)
    return data, cache_key


def _parse_date(val, label, request):
    """Parse date string to date object."""
    if not val:
        return None
    try:
        return datetime.strptime(val, "%Y-%m-%d").date()
    except ValueError:
        messages.warning(request, f"Invalid {label} format")
        return None


@requires_perm("page_coupons")
def coupon_dashboard(request):
    """
    Coupon analytics dashboard.
    Supports date range filtering, coupon ID prefix search, and shop group filtering.
    """
    start_date = request.GET.get("start_date", "")
    end_date = request.GET.get("end_date", "")
    coupon_id_prefix = request.GET.get("coupon_id_prefix", "").strip()
    shop_group = request.GET.get("shop_group", "").strip()

    date_from = _parse_date(start_date, "start date", request)
    date_to = _parse_date(end_date, "end date", request)

    logger.info(
        "coupon_dashboard: from=%s to=%s prefix=%s shop_group=%s user=%s",
        date_from,
        date_to,
        coupon_id_prefix,
        shop_group,
        request.user,
    )

    data, _ = _get_coupon_data(date_from, date_to, coupon_id_prefix, shop_group)

    _campaigns = list(CouponCampaign.objects.values("id", "name", "prefix"))
    for _c in _campaigns:
        _c["prefix_list"] = [p.strip() for p in (_c["prefix"] or "").split(",") if p.strip()]

    return render(
        request,
        "coupon/dashboard.html",
        {
            "all_time": data["all_time"],
            "period": data["period"],
            "by_shop": data["by_shop"],
            "details": data["details"],
            "duplicate_invoices": data["duplicate_invoices"],
            "start_date": start_date,
            "end_date": end_date,
            "coupon_id_prefix": coupon_id_prefix,
            "shop_group": shop_group,
            "quick_btns": [("Last 7 Days", 7), ("Last 30 Days", 30), ("Last 90 Days", 90), ("Last Year", 365)],
            "campaigns_json": json.dumps(_campaigns),
        },
    )


@requires_perm("download_coupons")
def export_coupons(request):
    """Export coupon analytics to Excel.
    If ?tab=<name> is provided, exports only that tab (Summary + tab sheet).
    Otherwise exports the full workbook.
    """
    start_date = request.GET.get("start_date", "")
    end_date = request.GET.get("end_date", "")
    coupon_id_prefix = request.GET.get("coupon_id_prefix", "").strip()
    shop_group = request.GET.get("shop_group", "").strip()
    tab = request.GET.get("tab", "").strip()

    date_from = _parse_date(start_date, "start date", request)
    date_to = _parse_date(end_date, "end date", request)

    logger.info(
        "export_coupons: from=%s to=%s prefix=%s shop_group=%s tab=%s user=%s",
        date_from, date_to, coupon_id_prefix, shop_group, tab or "full", request.user,
        extra={"step": "export_coupons"},
    )
    data, _ = _get_coupon_data(date_from, date_to, coupon_id_prefix, shop_group)

    ts = datetime.now().strftime('%H%M%S')
    period = f"{date_from}_{date_to}" if date_from and date_to else datetime.now().strftime('%Y%m%d')

    if tab and tab in _COUPON_TAB_SHEETS:
        _, tab_title = _COUPON_TAB_SHEETS[tab]
        wb = export_coupon_tab_to_excel(tab, data, date_from=date_from, date_to=date_to,
                                        coupon_id_prefix=coupon_id_prefix, shop_group=shop_group)
        tab_slug = tab_title.replace(" ", "_").replace("-", "").replace("/", "")
        fn = f"coupon_{tab_slug}_{period}_{ts}.xlsx"
    else:
        wb = export_coupon_to_excel(data, date_from=date_from, date_to=date_to,
                                    coupon_id_prefix=coupon_id_prefix, shop_group=shop_group)
        fn = f"coupon_{period}_{ts}.xlsx"

    resp = HttpResponse(
        content_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
    )
    resp["Content-Disposition"] = f'attachment; filename="{fn}"'
    wb.save(resp)
    return resp


@requires_perm("page_coupon_chart")
def coupon_chart(request):
    """Coupon analytics chart page — overview pies + shop/campaign trend lines."""
    from App.analytics.coupon_analytics import calculate_coupon_trend_data

    start_date = request.GET.get("start_date", "")
    end_date = request.GET.get("end_date", "")
    coupon_id_prefix = request.GET.get("coupon_id_prefix", "").strip()
    shop_group = request.GET.get("shop_group", "").strip()

    date_from = _parse_date(start_date, "start date", request)
    date_to = _parse_date(end_date, "end date", request)

    # Overview pies reuse the cached coupon data
    data, _ = _get_coupon_data(date_from, date_to, coupon_id_prefix, shop_group)

    # Trend data (shop×time, campaign×time) — separate cache
    trend_cache_key = _coupon_trend_cache_key(date_from, date_to, shop_group, coupon_id_prefix)
    trend_data = cache.get(trend_cache_key)
    if trend_data is None:
        trend_data = calculate_coupon_trend_data(date_from, date_to, shop_group, coupon_id_prefix)
        cache.set(trend_cache_key, trend_data, _COUPON_TTL)
        logger.info("coupon trend cache MISS (%s)", trend_cache_key)
    else:
        logger.info("coupon trend cache HIT (%s)", trend_cache_key)

    campaigns = list(CouponCampaign.objects.values("id", "name", "prefix"))

    return render(
        request,
        "coupon/chart.html",
        {
            "all_time": data["all_time"],
            "period": data["period"],
            "all_time_json": json.dumps(data["all_time"]),
            "period_json": json.dumps(data["period"]),
            "trend_data_json": json.dumps(trend_data),
            "campaigns_json": json.dumps(campaigns),
            "start_date": start_date,
            "end_date": end_date,
            "coupon_id_prefix": coupon_id_prefix,
            "shop_group": shop_group,
            "quick_btns": [("Last 7 Days", 7), ("Last 30 Days", 30), ("Last 90 Days", 90), ("Last Year", 365)],
            "year_btns": [2024, 2025, 2026],
        },
    )


@requires_perm("manage_campaigns")
def manage_campaigns(request):
    """
    AJAX + page endpoint for CouponCampaign CRUD.
    GET  → JSON list of all campaigns.
    POST → action=create|update|delete.
    """
    import json
    from django.http import JsonResponse
    from App.models import CouponCampaign

    if request.method == "GET":
        campaigns = list(
            CouponCampaign.objects.values(
                "id", "name", "prefix", "detail", "created_at"
            )
        )
        for c in campaigns:
            if c["created_at"]:
                c["created_at"] = c["created_at"].strftime("%Y-%m-%d")
            # Expose individual prefixes as a list for frontend display
            c["prefix_list"] = [p.strip() for p in (c["prefix"] or "").split(",") if p.strip()]
        return JsonResponse({"campaigns": campaigns})

    if request.method == "POST":
        try:
            body = json.loads(request.body)
        except Exception:
            return JsonResponse({"error": "Invalid JSON"}, status=400)

        action = body.get("action")

        def _clean_prefix(raw):
            """Normalise comma-separated prefixes: strip whitespace, upper-case each, deduplicate."""
            parts = [p.strip().upper() for p in (raw or "").split(",") if p.strip()]
            return ",".join(dict.fromkeys(parts))  # deduplicate, keep order

        if action == "create":
            name = (body.get("name") or "").strip()
            prefix = _clean_prefix(body.get("prefix"))
            detail = (body.get("detail") or "").strip()
            if not name or not prefix:
                return JsonResponse(
                    {"error": "Name and at least one prefix are required"}, status=400
                )
            if CouponCampaign.objects.filter(name=name).exists():
                return JsonResponse(
                    {"error": f"Campaign '{name}' already exists"}, status=400
                )
            c = CouponCampaign.objects.create(
                name=name, prefix=prefix, detail=detail or None
            )
            logger.info("campaign_create: name=%s prefix=%s by=%s", name, prefix, request.user, extra={"step": "manage_campaigns"})
            _invalidate_coupon_cache()
            return JsonResponse(
                {"ok": True, "id": c.pk, "name": c.name, "prefix": c.prefix}
            )

        if action == "update":
            pk = body.get("id")
            name = (body.get("name") or "").strip()
            prefix = _clean_prefix(body.get("prefix"))
            detail = (body.get("detail") or "").strip()
            if not pk or not name or not prefix:
                return JsonResponse(
                    {"error": "id, name and prefix are required"}, status=400
                )
            try:
                c = CouponCampaign.objects.get(pk=pk)
            except CouponCampaign.DoesNotExist:
                return JsonResponse({"error": "Campaign not found"}, status=404)
            if CouponCampaign.objects.filter(name=name).exclude(pk=pk).exists():
                return JsonResponse(
                    {"error": f"Name '{name}' already in use"}, status=400
                )
            c.name = name
            c.prefix = prefix
            c.detail = detail or None
            c.save()
            logger.info("campaign_update: id=%s name=%s prefix=%s by=%s", pk, name, prefix, request.user, extra={"step": "manage_campaigns"})
            _invalidate_coupon_cache()
            return JsonResponse({"ok": True})

        if action == "delete":
            pk = body.get("id")
            if not pk:
                return JsonResponse({"error": "id required"}, status=400)
            deleted, _ = CouponCampaign.objects.filter(pk=pk).delete()
            if not deleted:
                return JsonResponse({"error": "Campaign not found"}, status=404)
            logger.info("campaign_delete: id=%s by=%s", pk, request.user, extra={"step": "manage_campaigns"})
            _invalidate_coupon_cache()
            return JsonResponse({"ok": True})

        return JsonResponse({"error": "Unknown action"}, status=400)

    return JsonResponse({"error": "Method not allowed"}, status=405)
