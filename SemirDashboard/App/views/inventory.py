"""App/views/inventory.py — Global Inventory Analytics page."""
import csv
import io
import logging

from django.shortcuts import render, redirect
from django.contrib import messages
from django.http import HttpResponse

from App.permissions import requires_perm
from App.analytics.inventory_functions import get_inventory_overview, get_product_prefix_detail
from App.models import InventorySnapshot

logger = logging.getLogger(__name__)

SHOP_GROUPS = [
    ("",        "All Shops"),
    ("semir",   "Semir"),
    ("bala",    "Bala Bala"),
    ("others",  "Others"),
]


def _get_filter_options():
    """Return distinct years and seasons available in the inventory, for dropdowns."""
    years = list(
        InventorySnapshot.objects
        .order_by('-year').values_list('year', flat=True).distinct()
        .exclude(year__isnull=True)
    )
    seasons = list(
        InventorySnapshot.objects
        .order_by('season').values_list('season', flat=True).distinct()
        .exclude(season='')
    )
    return years, seasons


@requires_perm("inventory.view")
def inventory_dashboard(request):
    shop_group     = request.GET.get("shop_group", "")
    year_str       = request.GET.get("year", "")
    season         = request.GET.get("season", "")
    product_prefix = request.GET.get("product_prefix", "").strip()

    year = int(year_str) if year_str.isdigit() else None

    data = get_inventory_overview(
        shop_group=shop_group or None,
        year=year,
        season=season or None,
    )

    if not data:
        messages.info(request, "No inventory data found. Please upload an inventory file first.")
        return redirect("upload_inventory")

    prefix_data = {}
    if product_prefix:
        prefix_data = get_product_prefix_detail(
            prefix=product_prefix,
            shop_group=shop_group or None,
            year=year,
            season=season or None,
        )

    years_available, seasons_available = _get_filter_options()

    return render(request, "inventory/dashboard.html", {
        "data":               data,
        "for_sale":           data.get("for_sale", {}),
        "gifts":              data.get("gifts", {}),
        "dead_year":          data.get("dead_year_threshold"),
        "shop_group":         shop_group,
        "shop_groups":        SHOP_GROUPS,
        "year_filter":        year,
        "season_filter":      season,
        "years_available":    years_available,
        "seasons_available":  seasons_available,
        "product_prefix":     product_prefix,
        "prefix_data":        prefix_data,
    })


@requires_perm("inventory.export")
def export_inventory_dead_stock(request):
    """Download dead stock SKUs as CSV."""
    shop_group = request.GET.get("shop_group", "")
    year_str   = request.GET.get("year", "")
    season     = request.GET.get("season", "")
    year = int(year_str) if year_str.isdigit() else None

    data = get_inventory_overview(
        shop_group=shop_group or None,
        year=year,
        season=season or None,
    )
    dead_top = (data.get("for_sale") or {}).get("dead", {}).get("top", [])

    buf = io.StringIO()
    writer = csv.writer(buf)
    writer.writerow([
        "Shop", "Product Code", "Product Name", "Product Name VN",
        "Color", "Size", "Category L1", "Category L2", "Category L3", "Gender",
        "Brand", "Year", "Season", "Tag Price", "Qty", "Value (VND)",
    ])
    for row in dead_top:
        writer.writerow([
            row.get("shop_name", ""),
            row.get("product_code", ""),
            row.get("product_name", ""),
            row.get("product_name_vn", ""),
            row.get("color", ""),
            row.get("size", ""),
            row.get("category_l1", ""),
            row.get("category_l2", ""),
            row.get("category_l3", ""),
            row.get("gender", ""),
            row.get("brand", ""),
            row.get("year", ""),
            row.get("season", ""),
            row.get("tag_price", ""),
            row.get("qty", 0),
            row.get("value", 0),
        ])

    response = HttpResponse(buf.getvalue(), content_type="text/csv; charset=utf-8-sig")
    fname = f"dead_stock_{shop_group or 'all'}.csv"
    response["Content-Disposition"] = f'attachment; filename="{fname}"'
    return response
