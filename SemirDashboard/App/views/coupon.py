"""App/views/coupon.py — Coupon analytics views."""
import json
import logging
from datetime import datetime

from django.shortcuts import render, redirect
from django.contrib import messages
from django.http import HttpResponse, HttpResponseBadRequest

from App.permissions import requires_perm
from App.analytics.coupon_analytics import (
    calculate_coupon_analytics,
    get_coupon_summary,
    calculate_coupon_trend_data,
    export_coupon_to_excel,
    export_coupon_tab_to_excel,
    _COUPON_TAB_SHEETS,
)
from App.analytics.excel_export import export_coupon_chart_to_excel
from App.analytics.tab_functions import get_coupon_tab, COUPON_TABS
from App.models import CouponCampaign
from App.views.view_utils import parse_date, filter_params_str

logger = logging.getLogger(__name__)


def _get_campaigns_with_prefix_list(extra_fields=()):
    """Return all CouponCampaign rows with a computed prefix_list field."""
    fields = ("id", "name", "prefix") + tuple(extra_fields)
    campaigns = list(CouponCampaign.objects.values(*fields))
    for c in campaigns:
        c["prefix_list"] = [p.strip() for p in (c["prefix"] or "").split(",") if p.strip()]
    return campaigns


@requires_perm("coupons.view")
def coupon_dashboard(request):
    """
    Coupon analytics dashboard.
    Supports date range filtering, coupon ID prefix search, and shop group filtering.
    """
    start_date = request.GET.get("start_date", "")
    end_date = request.GET.get("end_date", "")
    coupon_id_prefix = request.GET.get("coupon_id_prefix", "").strip()
    shop_group = request.GET.get("shop_group", "").strip()

    date_from = parse_date(start_date, "start date", request)
    date_to = parse_date(end_date, "end date", request)

    logger.info(
        "coupon_dashboard: from=%s to=%s prefix=%s shop_group=%s user=%s",
        date_from,
        date_to,
        coupon_id_prefix,
        shop_group,
        request.user,
    )

    # Lazy loading: only compute shop tab (first tab) on initial page load
    data = get_coupon_tab('shop', date_from=date_from, date_to=date_to,
                          coupon_id_prefix=coupon_id_prefix or None,
                          shop_group=shop_group or None)

    _campaigns = _get_campaigns_with_prefix_list()

    # Build lazy params for tab AJAX URLs
    _lazy_parts = []
    if start_date:    _lazy_parts.append(f'start_date={start_date}')
    if end_date:      _lazy_parts.append(f'end_date={end_date}')
    if coupon_id_prefix: _lazy_parts.append(f'coupon_id_prefix={coupon_id_prefix}')
    if shop_group:    _lazy_parts.append(f'shop_group={shop_group}')
    lazy_params = '&'.join(_lazy_parts)

    return render(
        request,
        "coupon/dashboard.html",
        {
            "all_time": data["all_time"],
            "period": data["period"],
            "by_shop": data["by_shop"],
            "lazy_params": lazy_params,
            "start_date": start_date,
            "end_date": end_date,
            "coupon_id_prefix": coupon_id_prefix,
            "shop_group": shop_group,
            "quick_btns": [("Last 7 Days", 7), ("Last 30 Days", 30), ("Last 90 Days", 90), ("Last Year", 365)],
            "campaigns_json": _campaigns,
        },
    )


@requires_perm("coupons.view")
def coupon_tab(request, tab: str):
    """
    AJAX endpoint: returns a rendered HTML fragment for one Coupon Analytics tab.
    Called by lazy_tabs_js.html on first tab click.
    """
    if not request.headers.get('X-Requested-With') == 'XMLHttpRequest':
        return HttpResponseBadRequest("AJAX only")
    if tab not in COUPON_TABS or tab == 'shop':
        return HttpResponseBadRequest(f"Invalid tab: {tab!r}")

    start_date       = request.GET.get("start_date", "")
    end_date         = request.GET.get("end_date", "")
    coupon_id_prefix = request.GET.get("coupon_id_prefix", "").strip()
    shop_group       = request.GET.get("shop_group", "").strip()

    date_from = parse_date(start_date, "start date", request)
    date_to   = parse_date(end_date,   "end date",   request)

    logger.info(
        "coupon_tab: tab=%s from=%s to=%s prefix=%s shop_group=%s user=%s",
        tab, date_from, date_to, coupon_id_prefix, shop_group, request.user,
    )

    data = get_coupon_tab(tab, date_from=date_from, date_to=date_to,
                          coupon_id_prefix=coupon_id_prefix or None,
                          shop_group=shop_group or None)

    ctx = {
        **data,
        "start_date": start_date,
        "end_date":   end_date,
        "coupon_id_prefix": coupon_id_prefix,
        "shop_group": shop_group,
    }
    return render(request, f"coupon/tabs/{tab}.html", ctx)


@requires_perm("coupons.export")
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

    date_from = parse_date(start_date, "start date", request)
    date_to = parse_date(end_date, "end date", request)

    logger.info(
        "export_coupons: from=%s to=%s prefix=%s shop_group=%s tab=%s user=%s",
        date_from, date_to, coupon_id_prefix, shop_group, tab or "full", request.user,
        extra={"step": "export_coupons"},
    )
    data = calculate_coupon_analytics(
        date_from=date_from, date_to=date_to,
        coupon_id_prefix=coupon_id_prefix or None, shop_group=shop_group or None,
    )
    if not data:
        logger.warning("export_coupons: no data, from=%s to=%s prefix=%s user=%s",
                       date_from, date_to, coupon_id_prefix, request.user, extra={"step": "export_coupons"})
        messages.error(request, "No data to export")
        return redirect("coupon_dashboard")

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

    logger.info("export_coupons: file=%s user=%s", fn, request.user, extra={"step": "export_coupons"})
    resp = HttpResponse(
        content_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
    )
    resp["Content-Disposition"] = f'attachment; filename="{fn}"'
    wb.save(resp)
    return resp


@requires_perm("coupons.chart")
def coupon_chart(request):
    """Coupon analytics chart page — overview pies + shop/campaign trend lines."""
    from App.analytics.coupon_analytics import calculate_coupon_trend_data

    start_date = request.GET.get("start_date", "")
    end_date = request.GET.get("end_date", "")
    coupon_id_prefix = request.GET.get("coupon_id_prefix", "").strip()
    shop_group = request.GET.get("shop_group", "").strip()

    date_from = parse_date(start_date, "start date", request)
    date_to = parse_date(end_date, "end date", request)

    data = get_coupon_summary(
        date_from=date_from, date_to=date_to,
        coupon_id_prefix=coupon_id_prefix or None,
        shop_group=shop_group or None,
    )

    # Trend data (shop×time, campaign×time)
    trend_data = calculate_coupon_trend_data(date_from, date_to, shop_group, coupon_id_prefix)

    campaigns = _get_campaigns_with_prefix_list()

    return render(
        request,
        "coupon/chart.html",
        {
            "all_time": data["all_time"],
            "period": data["period"],
            "all_time_json": data["all_time"],
            "period_json": data["period"],
            "trend_data_json": trend_data,
            "campaigns_json": campaigns,
            "start_date": start_date,
            "end_date": end_date,
            "coupon_id_prefix": coupon_id_prefix,
            "shop_group": shop_group,
            "quick_btns": [("Last 7 Days", 7), ("Last 30 Days", 30), ("Last 90 Days", 90), ("Last Year", 365)],
            "year_btns": [2024, 2025, 2026],
        },
    )


@requires_perm("coupons.manage")
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
        campaigns = _get_campaigns_with_prefix_list(extra_fields=("detail", "created_at"))
        for c in campaigns:
            if c["created_at"]:
                c["created_at"] = c["created_at"].strftime("%Y-%m-%d")
        return JsonResponse({"campaigns": campaigns})

    if request.method == "POST":
        try:
            body = json.loads(request.body)
        except json.JSONDecodeError:
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

            return JsonResponse({"ok": True})

        if action == "delete":
            pk = body.get("id")
            if not pk:
                return JsonResponse({"error": "id required"}, status=400)
            deleted, _ = CouponCampaign.objects.filter(pk=pk).delete()
            if not deleted:
                return JsonResponse({"error": "Campaign not found"}, status=404)
            logger.info("campaign_delete: id=%s by=%s", pk, request.user, extra={"step": "manage_campaigns"})

            return JsonResponse({"ok": True})

        return JsonResponse({"error": "Unknown action"}, status=400)

    return JsonResponse({"error": "Method not allowed"}, status=405)


@requires_perm("coupons.export_chart")
def export_coupon_chart_excel(request):
    """Export Coupon Analytics Chart data to Excel workbook matching current UI state."""
    start_date = request.GET.get("start_date", "")
    end_date = request.GET.get("end_date", "")
    coupon_id_prefix = request.GET.get("coupon_id_prefix", "").strip()
    shop_group = request.GET.get("shop_group", "").strip()

    date_from = parse_date(start_date, "start date", request)
    date_to = parse_date(end_date, "end date", request)

    logger.info(
        "export_coupon_chart_excel: from=%s to=%s prefix=%s shop_group=%s user=%s",
        date_from, date_to, coupon_id_prefix, shop_group, request.user,
    )

    def _shops(key):
        return [s for s in request.GET.get(key, "").split(",") if s.strip()]

    shop_xaxis    = request.GET.get("shop_xaxis", "month")
    shop_metric   = request.GET.get("shop_metric", "used")
    shop_shops    = _shops("shop_shops")
    camp_xaxis    = request.GET.get("camp_xaxis", "month")
    camp_metric   = request.GET.get("camp_metric", "used")
    camp_campaigns = _shops("camp_campaigns")

    summary = get_coupon_summary(
        date_from=date_from, date_to=date_to,
        coupon_id_prefix=coupon_id_prefix or None,
        shop_group=shop_group or None,
    )
    trend = calculate_coupon_trend_data(date_from, date_to, shop_group or None, coupon_id_prefix or None)

    wb = export_coupon_chart_to_excel(
        summary, trend,
        date_from=date_from, date_to=date_to,
        coupon_id_prefix=coupon_id_prefix or None,
        shop_group=shop_group or None,
        shop_xaxis=shop_xaxis, shop_metric=shop_metric, shop_shops=shop_shops,
        camp_xaxis=camp_xaxis, camp_metric=camp_metric, camp_campaigns=camp_campaigns,
    )

    ts = datetime.now().strftime('%H%M%S')
    period = f"{date_from}_{date_to}" if date_from and date_to else datetime.now().strftime('%Y%m%d')
    fn = f"coupon_chart_{period}_{ts}.xlsx"

    resp = HttpResponse(
        content_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
    )
    resp["Content-Disposition"] = f'attachment; filename="{fn}"'
    wb.save(resp)
    return resp
