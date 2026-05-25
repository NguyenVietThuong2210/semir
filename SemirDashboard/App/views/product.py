"""App/views/product.py — Sales & Product Analytics page (SaleDetail-based)."""
import logging
from datetime import datetime

from django.shortcuts import render, redirect
from django.contrib import messages
from django.http import HttpResponse

from App.permissions import requires_perm
from App.analytics.product_analytics import get_product_tab, PRODUCT_TABS
from App.views.view_utils import parse_date, parse_date_silent, filter_params_str

logger = logging.getLogger(__name__)

QUICK_BTNS = [
    ("Last 7 Days", 7),
    ("Last 30 Days", 30),
    ("Last 90 Days", 90),
    ("Last Year", 365),
]
YEAR_BTNS = [2024, 2025, 2026]

# Initial tab loaded server-side on page load (avoids a 2nd AJAX call)
_INITIAL_TAB = 'month'


@requires_perm("products.view")
def product_dashboard(request):
    start_date = request.GET.get("start_date", "")
    end_date   = request.GET.get("end_date", "")
    shop_group = request.GET.get("shop_group", "")

    date_from = parse_date(start_date, "start date", request)
    date_to   = parse_date(end_date,   "end date",   request)

    if date_from and date_to and date_from > date_to:
        messages.error(request, "Start date must be before end date.")
        date_from = date_to = None

    data = get_product_tab(_INITIAL_TAB, date_from=date_from, date_to=date_to,
                           shop_group=shop_group or None)
    if not data:
        messages.info(request, "No sale detail data found. Please upload sale detail data first.")
        return redirect("upload_sales")

    lazy_params = filter_params_str(start_date=start_date, end_date=end_date, shop_group=shop_group)

    return render(request, "product/dashboard.html", {
        "overview":    data.get("overview", {}),
        "initial_tab": _INITIAL_TAB,
        "initial_data": data,
        "start_date":  start_date,
        "end_date":    end_date,
        "shop_group":  shop_group,
        "lazy_params": lazy_params,
        "quick_btns":  QUICK_BTNS,
        "year_btns":   YEAR_BTNS,
        "currency":    "VND",
    })


@requires_perm("products.view")
def product_tab(request, tab):
    """Lazy-load AJAX tab for product analytics."""
    if tab not in PRODUCT_TABS:
        return HttpResponse('<div class="alert alert-danger">Unknown tab.</div>', status=400)

    start_date = request.GET.get("start_date", "")
    end_date   = request.GET.get("end_date", "")
    shop_group = request.GET.get("shop_group", "")

    date_from = parse_date_silent(start_date)
    date_to   = parse_date_silent(end_date)

    shop_name = request.GET.get("shop_name", "").strip() or None
    data = get_product_tab(tab, date_from=date_from, date_to=date_to,
                           shop_group=shop_group or None, shop_name=shop_name)
    ctx = {
        "data": data,
        "overview": data.get("overview", {}) if data else {},
        "start_date": start_date,
        "end_date": end_date,
        "shop_group": shop_group,
        "shop_name": shop_name,
        "currency": "VND",
    }
    return render(request, f"product/tabs/{tab}.html", ctx)


_EXPORT_TABS = ('month', 'year', 'week', 'sales_season', 'product_season', 'vip_grade', 'brand', 'category', 'shop', 'product')


@requires_perm("products.export")
def export_product_analytics(request):
    """Export product analytics data to Excel.

    ?tab=<name> exports a single tab sheet.
    No ?tab exports all tabs in one workbook.
    """
    from App.analytics.excel_export import export_product_analytics_to_excel

    start_date = request.GET.get("start_date", "")
    end_date   = request.GET.get("end_date", "")
    shop_group = request.GET.get("shop_group", "")
    tab_param  = request.GET.get("tab", "").strip()

    date_from = parse_date_silent(start_date)
    date_to   = parse_date_silent(end_date)

    export_tabs = [tab_param] if tab_param in _EXPORT_TABS else list(_EXPORT_TABS)

    tabs_data = {}
    for tab in export_tabs:
        d = get_product_tab(tab, date_from=date_from, date_to=date_to,
                            shop_group=shop_group or None)
        if d:
            tabs_data[tab] = d

    if not tabs_data:
        messages.error(request, "No data to export.")
        return redirect("product_dashboard")

    wb = export_product_analytics_to_excel(
        tabs_data, date_from=date_from, date_to=date_to, shop_group=shop_group
    )
    ts = datetime.now().strftime('%H%M%S')
    period = f"{date_from}_{date_to}" if date_from and date_to else datetime.now().strftime('%Y%m%d')
    tab_suffix = f"_{tab_param}" if tab_param in _EXPORT_TABS else ""
    fn = f"product_analytics{tab_suffix}_{period}_{ts}.xlsx"

    response = HttpResponse(
        content_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
    )
    response["Content-Disposition"] = f'attachment; filename="{fn}"'
    wb.save(response)
    return response
