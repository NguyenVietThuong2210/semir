"""App/views/analytics.py — Sales analytics views."""
import json
import logging
from datetime import datetime

from django.shortcuts import render, redirect
from django.contrib import messages
from django.http import HttpResponse, HttpResponseBadRequest

from App.permissions import requires_perm
from App.analytics.core import calculate_return_rate_analytics
from App.analytics.tab_functions import get_sales_tab, SALES_TABS
from App.analytics.excel_export import export_analytics_to_excel, export_tab_to_excel, _TAB_SHEETS, export_sales_chart_to_excel
from App.views.view_utils import parse_date, filter_params_str

logger = logging.getLogger(__name__)

QUICK_BTNS = [
    ("Last 7 Days", 7),
    ("Last 30 Days", 30),
    ("Last 90 Days", 90),
    ("Last Year", 365),
]

YEAR_BTNS = [2024, 2025, 2026]




@requires_perm("sales.view")
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

    date_from = parse_date(start_date, "start date", request)
    date_to = parse_date(end_date, "end date", request)

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

    # Lazy loading: only compute grade tab (first tab) + overview on initial page load
    data = get_sales_tab('grade', date_from=date_from, date_to=date_to, shop_group=shop_group or None)
    if not data:
        messages.info(request, "No sales data. Please upload sales data first.")
        return redirect("upload_sales")

    lazy_params = filter_params_str(start_date=start_date, end_date=end_date, shop_group=shop_group)
    ctx = {
        "date_range": data["date_range"],
        "session_label": data.get("session_label"),
        "overview": data["overview"],
        "grade_stats": data["by_grade"],
        "customer_details": data.get("customer_details", []),
        "total_detail_count": data.get("total_detail_count", 0),
        "buyer_without_info_stats": data.get("buyer_without_info_stats", {}),
        # Lazy tab params
        "lazy_params": lazy_params,
        "start_date": start_date,
        "end_date": end_date,
        "shop_group": shop_group,
        "currency": "VND",
        "quick_btns": QUICK_BTNS,
        "year_btns": YEAR_BTNS,
    }
    return render(request, "analytics/dashboard.html", ctx)


@requires_perm("sales.view")
def analytics_tab(request, tab: str):
    """
    AJAX endpoint: returns a rendered HTML fragment for one Sales Analytics tab.
    Called by lazy_tabs_js.html on first tab click.
    """
    if not request.headers.get('X-Requested-With') == 'XMLHttpRequest':
        return HttpResponseBadRequest("AJAX only")
    if tab not in SALES_TABS or tab == 'grade':
        return HttpResponseBadRequest(f"Invalid tab: {tab!r}")

    start_date = request.GET.get("start_date", "")
    end_date   = request.GET.get("end_date", "")
    shop_group = request.GET.get("shop_group", "")

    date_from = parse_date(start_date, "start date", request)
    date_to   = parse_date(end_date,   "end date",   request)

    logger.info(
        "analytics_tab: tab=%s from=%s to=%s shop_group=%s user=%s",
        tab, date_from, date_to, shop_group, request.user,
    )

    data = get_sales_tab(tab, date_from=date_from, date_to=date_to, shop_group=shop_group or None)
    if not data:
        return render(request, "analytics/tabs/_empty.html", {})

    ctx = {
        **data,
        "start_date": start_date,
        "end_date":   end_date,
        "shop_group": shop_group,
        "currency": "VND",
    }
    return render(request, f"analytics/tabs/{tab}.html", ctx)


@requires_perm("sales.chart")
def analytics_chart(request):
    """Overview chart page — donut summaries + interactive shop trend line chart."""
    start_date = request.GET.get("start_date", "")
    end_date = request.GET.get("end_date", "")
    shop_group = request.GET.get("shop_group", "")

    date_from = parse_date(start_date, "start date", request)
    date_to = parse_date(end_date, "end date", request)

    if date_from and date_to and date_from > date_to:
        messages.error(request, "Start date must be before end date")
        date_from = date_to = None

    logger.info(
        "analytics_chart: from=%s to=%s shop_group=%s user=%s",
        date_from, date_to, shop_group, request.user,
        extra={"step": "analytics_chart"},
    )
    data = calculate_return_rate_analytics(
        date_from=date_from, date_to=date_to,
        shop_group=shop_group or None, chart_only=True,
    )
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


@requires_perm("sales.export")
def export_analytics(request):
    """Export analytics data to Excel file.
    If ?tab=<name> is provided, exports only that tab (Overview + tab sheet(s)).
    Otherwise exports the full workbook.
    """
    start_date = request.GET.get("start_date", "")
    end_date = request.GET.get("end_date", "")
    shop_group = request.GET.get("shop_group", "")
    tab = request.GET.get("tab", "").strip()

    date_from = parse_date(start_date, "start date", request)
    date_to = parse_date(end_date, "end date", request)

    logger.info(
        "export_analytics: from=%s to=%s shop_group=%s tab=%s user=%s",
        date_from, date_to, shop_group, tab or "full", request.user,
        extra={"step": "export_analytics"},
    )
    data = calculate_return_rate_analytics(date_from=date_from, date_to=date_to, shop_group=shop_group or None)
    if not data:
        logger.warning("export_analytics: no data returned, from=%s to=%s shop_group=%s user=%s",
                       date_from, date_to, shop_group, request.user, extra={"step": "export_analytics"})
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

    logger.info("export_analytics: file=%s user=%s", fn, request.user, extra={"step": "export_analytics"})
    resp = HttpResponse(
        content_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
    )
    resp["Content-Disposition"] = f'attachment; filename="{fn}"'
    wb.save(resp)
    return resp


@requires_perm("sales.export_chart")
def export_sales_chart_excel(request):
    """Export Sales Analytics Chart data to Excel workbook matching current UI state."""
    start_date = request.GET.get("start_date", "")
    end_date = request.GET.get("end_date", "")
    shop_group = request.GET.get("shop_group", "").strip()

    # Chart section params (set by JS reading UI state)
    def _shops(key):
        return [s for s in request.GET.get(key, "").split(",") if s.strip()]

    trend_xaxis  = request.GET.get("trend_xaxis", "month")
    trend_metric = request.GET.get("trend_metric", "return_rate")
    trend_shops  = _shops("trend_shops")
    bar_xaxis    = request.GET.get("bar_xaxis", "month")
    bar_metric   = request.GET.get("bar_metric", "total_customers")
    bar_shops    = _shops("bar_shops")
    yoy_xaxis    = request.GET.get("yoy_xaxis", "month")
    yoy_metric   = request.GET.get("yoy_metric", "total_customers")
    yoy_shops    = _shops("yoy_shops")

    date_from = parse_date(start_date, "start date", request)
    date_to = parse_date(end_date, "end date", request)

    logger.info(
        "export_sales_chart_excel: from=%s to=%s shop_group=%s user=%s",
        date_from, date_to, shop_group, request.user,
    )

    data = calculate_return_rate_analytics(
        date_from=date_from, date_to=date_to,
        shop_group=shop_group or None,
    )
    if not data:
        messages.error(request, "No data to export")
        return redirect("analytics_chart")

    wb = export_sales_chart_to_excel(
        data, date_from=date_from, date_to=date_to, shop_group=shop_group or None,
        trend_xaxis=trend_xaxis, trend_metric=trend_metric, trend_shops=trend_shops,
        bar_xaxis=bar_xaxis, bar_metric=bar_metric, bar_shops=bar_shops,
        yoy_xaxis=yoy_xaxis, yoy_metric=yoy_metric, yoy_shops=yoy_shops,
    )

    ts = datetime.now().strftime('%H%M%S')
    period = f"{date_from}_{date_to}" if date_from and date_to else datetime.now().strftime('%Y%m%d')
    fn = f"sales_chart_{period}_{ts}.xlsx"

    resp = HttpResponse(
        content_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
    )
    resp["Content-Disposition"] = f'attachment; filename="{fn}"'
    wb.save(resp)
    return resp
