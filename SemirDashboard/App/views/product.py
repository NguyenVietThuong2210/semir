"""App/views/product.py — Product Analytics page (SaleDetail-based)."""
import logging

from django.shortcuts import render, redirect
from django.contrib import messages
from django.http import HttpResponse

from App.permissions import requires_perm
from App.analytics.product_analytics import get_product_tab, PRODUCT_TABS
from App.views.view_utils import parse_date, filter_params_str

logger = logging.getLogger(__name__)

QUICK_BTNS = [
    ("Last 7 Days", 7),
    ("Last 30 Days", 30),
    ("Last 90 Days", 90),
    ("Last Year", 365),
]
YEAR_BTNS = [2024, 2025, 2026]


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

    data = get_product_tab('season', date_from=date_from, date_to=date_to, shop_group=shop_group or None)
    if not data:
        messages.info(request, "No sale detail data found. Please upload sale detail data first.")
        return redirect("upload_sales")

    lazy_params = filter_params_str(start_date=start_date, end_date=end_date, shop_group=shop_group)

    return render(request, "product/dashboard.html", {
        "overview":    data.get("overview", {}),
        "by_season":   data.get("by_season", []),
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

    from App.views.view_utils import parse_date_silent
    date_from = parse_date_silent(start_date)
    date_to   = parse_date_silent(end_date)

    data = get_product_tab(tab, date_from=date_from, date_to=date_to, shop_group=shop_group or None)
    ctx = {"data": data, "start_date": start_date, "end_date": end_date,
           "shop_group": shop_group, "currency": "VND"}
    # Season tab uses `by_season` + `overview` directly (same template for server-side and AJAX)
    if tab == 'season' and data:
        ctx['by_season'] = data.get('by_season', [])
        ctx['overview']  = data.get('overview', {})
    return render(request, f"product/tabs/{tab}.html", ctx)
