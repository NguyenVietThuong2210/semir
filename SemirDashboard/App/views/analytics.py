"""App/views/analytics.py — Sales analytics views."""
import json
import logging
import threading
from datetime import datetime

from django.shortcuts import render, redirect
from django.contrib import messages
from django.http import HttpResponse
from django.core.cache import cache

from App.permissions import requires_perm
from App.analytics.core import calculate_return_rate_analytics
from App.analytics.excel_export import export_analytics_to_excel, export_tab_to_excel, _TAB_SHEETS

logger = logging.getLogger(__name__)

_ANALYTICS_TTL = 600  # 10 minutes
# In-process version counter — incremented on invalidation, zero cache calls.
# No startup timestamp: cache in Redis survives restarts and stays warm.
# Invalidation on upload (counter increment) is the only bust mechanism needed.
_anl_ver_lock = threading.Lock()
_anl_ver = 0

QUICK_BTNS = [
    ("Last 7 Days", 7),
    ("Last 30 Days", 30),
    ("Last 90 Days", 90),
    ("Last Year", 365),
]

YEAR_BTNS = [2024, 2025, 2026]


def _analytics_cache_key(date_from, date_to, shop_group):
    return f"anl_data:{_anl_ver}:{date_from}:{date_to}:{shop_group}"


def _invalidate_analytics_cache():
    global _anl_ver
    with _anl_ver_lock:
        _anl_ver += 1
    logger.info("analytics cache invalidated (in-process ver->%d)", _anl_ver)


def _get_analytics_data(date_from, date_to, shop_group):
    """Return full analytics data dict from cache or compute it.

    customer_purchases dict has model instances stripped (set to None)
    before storing — safe for pickle/Redis.
    Returns None if no data exists.
    """
    cache_key = _analytics_cache_key(date_from, date_to, shop_group)
    data = cache.get(cache_key)
    if data is not None:
        logger.info("analytics cache HIT (%s)", cache_key)
        return data, cache_key

    data = calculate_return_rate_analytics(
        date_from=date_from,
        date_to=date_to,
        shop_group=shop_group or None,
    )
    if not data:
        return None, cache_key

    # Strip Django model instances from customer_purchases so it can be pickled
    if "customer_purchases" in data:
        data["customer_purchases"] = {
            vid: [{**p, "customer": None} for p in purchases]
            for vid, purchases in data["customer_purchases"].items()
        }
    cache.set(cache_key, data, _ANALYTICS_TTL)
    logger.info("analytics cache MISS — computed & cached (%s)", cache_key)
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


@requires_perm("page_analytics")
def analytics_dashboard(request):
    """
    Main analytics dashboard showing return visit rate statistics.
    Supports date range filtering and shop group filtering via query parameters.
    """
    start_date = request.GET.get("start_date", "")
    end_date = request.GET.get("end_date", "")
    shop_group = request.GET.get(
        "shop_group", ""
    )  # New: Bala Group, Semir Group, Others Group

    date_from = _parse_date(start_date, "start date", request)
    date_to = _parse_date(end_date, "end date", request)

    if date_from and date_to and date_from > date_to:
        messages.error(request, "Start date must be before end date")
        date_from = date_to = None

    logger.info(
        "analytics_dashboard: from=%s to=%s shop_group=%s user=%s",
        date_from,
        date_to,
        shop_group,
        request.user,
    )

    data, _ = _get_analytics_data(date_from, date_to, shop_group)
    if not data:
        messages.info(request, "No sales data. Please upload sales data first.")
        return redirect("upload_sales")

    ctx = {
        "date_range": data["date_range"],
        "session_label": data.get("session_label"),
        "overview": data["overview"],
        "grade_stats": data["by_grade"],
        "session_stats": data["by_session"],
        "month_stats": data["by_month"],
        "week_stats": data["by_week"],
        "shop_stats": data["by_shop"],
        "by_shop": data["by_shop"],
        "customer_details": data["customer_details"][:100],
        "total_detail_count": len(data["customer_details"]),
        "buyer_without_info_stats": data.get("buyer_without_info_stats", {}),
    }
    ctx.update(
        {
            "start_date": start_date,
            "end_date": end_date,
            "shop_group": shop_group,
            "currency": "VND",
            "quick_btns": QUICK_BTNS,
            "year_btns": YEAR_BTNS,
        }
    )
    return render(request, "analytics/dashboard.html", ctx)


@requires_perm("page_chart")
def analytics_chart(request):
    """Overview chart page — donut summaries + interactive shop trend line chart."""
    start_date = request.GET.get("start_date", "")
    end_date = request.GET.get("end_date", "")
    shop_group = request.GET.get("shop_group", "")

    date_from = _parse_date(start_date, "start date", request)
    date_to = _parse_date(end_date, "end date", request)

    if date_from and date_to and date_from > date_to:
        messages.error(request, "Start date must be before end date")
        date_from = date_to = None

    logger.info(
        "analytics_chart: from=%s to=%s shop_group=%s user=%s",
        date_from, date_to, shop_group, request.user,
        extra={"step": "analytics_chart"},
    )
    data, _ = _get_analytics_data(date_from, date_to, shop_group)
    if not data:
        messages.info(request, "No sales data. Please upload sales data first.")
        return redirect("upload_sales")

    # Build compact JSON payload for Chart.js
    chart_data = {
        "overview": data["overview"],
        "session_stats": data["by_session"],
        "month_stats": data["by_month"],
        "year_stats": data["by_year"],
        "week_stats": data["by_week"],
        "shop_stats": [
            {
                "shop_name": s["shop_name"],
                "by_session": s["by_session"],
                "by_month": s["by_month"],
                "by_year": s["by_year"],
                "by_week": s["by_week"],
            }
            for s in data["by_shop"]
        ],
    }

    return render(
        request,
        "analytics/chart.html",
        {
            "date_range": data["date_range"],
            "session_label": data.get("session_label"),
            "overview": data["overview"],
            "shop_stats": data["by_shop"],
            "chart_data_json": json.dumps(chart_data),
            "start_date": start_date,
            "end_date": end_date,
            "shop_group": shop_group,
            "quick_btns": QUICK_BTNS,
            "year_btns": YEAR_BTNS,
        },
    )


@requires_perm("download_analytics")
def export_analytics(request):
    """Export analytics data to Excel file.
    If ?tab=<name> is provided, exports only that tab (Overview + tab sheet(s)).
    Otherwise exports the full workbook.
    """
    start_date = request.GET.get("start_date", "")
    end_date = request.GET.get("end_date", "")
    shop_group = request.GET.get("shop_group", "")
    tab = request.GET.get("tab", "").strip()

    date_from = _parse_date(start_date, "start date", request)
    date_to = _parse_date(end_date, "end date", request)

    logger.info(
        "export_analytics: from=%s to=%s shop_group=%s tab=%s user=%s",
        date_from, date_to, shop_group, tab or "full", request.user,
        extra={"step": "export_analytics"},
    )
    data, _ = _get_analytics_data(date_from, date_to, shop_group)
    if not data:
        messages.error(request, "No data to export")
        return redirect("analytics_dashboard")

    ts = datetime.now().strftime('%H%M%S')
    period = f"{date_from}_{date_to}" if date_from and date_to else datetime.now().strftime('%Y%m%d')

    if tab and tab in _TAB_SHEETS:
        _, tab_title = _TAB_SHEETS[tab]
        wb = export_tab_to_excel(tab, data, date_from=date_from, date_to=date_to, shop_group=shop_group)
        tab_slug = tab_title.replace(" ", "_").replace("-", "").replace("/", "")
        fn = f"analytics_{tab_slug}_{period}_{ts}.xlsx"
    else:
        wb = export_analytics_to_excel(data, date_from=date_from, date_to=date_to, shop_group=shop_group)
        fn = f"return_visit_rate_{period}_{ts}.xlsx"

    resp = HttpResponse(
        content_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
    )
    resp["Content-Disposition"] = f'attachment; filename="{fn}"'
    wb.save(resp)
    return resp
