"""App/views/inventory.py — Global Inventory Analytics page."""
import csv
import io
import logging

from django.shortcuts import render, redirect
from django.contrib import messages
from django.http import HttpResponse

from App.permissions import requires_perm
from App.analytics.inventory_functions import get_inventory_overview

logger = logging.getLogger(__name__)

SHOP_GROUPS = [
    ("",        "All Shops"),
    ("semir",   "Semir"),
    ("bala",    "Bala Bala"),
    ("others",  "Others"),
]


@requires_perm("inventory.view")
def inventory_dashboard(request):
    shop_group = request.GET.get("shop_group", "")

    data = get_inventory_overview(shop_group=shop_group or None)

    if not data:
        messages.info(request, "No inventory data found. Please upload an inventory file first.")
        return redirect("upload_inventory")

    return render(request, "inventory/dashboard.html", {
        "data":        data,
        "for_sale":    data.get("for_sale", {}),
        "gifts":       data.get("gifts", {}),
        "dead_year":   data.get("dead_year_threshold"),
        "shop_group":  shop_group,
        "shop_groups": SHOP_GROUPS,
    })


@requires_perm("inventory.view")
def export_inventory_dead_stock(request):
    """Download dead stock SKUs as CSV."""
    shop_group = request.GET.get("shop_group", "")
    data = get_inventory_overview(shop_group=shop_group or None)
    dead_top = (data.get("for_sale") or {}).get("dead", {}).get("top", [])

    buf = io.StringIO()
    writer = csv.writer(buf)
    writer.writerow(["Shop", "Product Code", "Product Name", "Brand",
                     "Year", "Season", "Tag Price", "Qty", "Value (VND)"])
    for row in dead_top:
        writer.writerow([
            row.get("shop_name", ""),
            row.get("product_code", ""),
            row.get("product_name", ""),
            row.get("brand", ""),
            row.get("year", ""),
            row.get("season", ""),
            row.get("tag_price", ""),
            row.get("qty", 0),
            row.get("value", 0),
        ])

    response = HttpResponse(buf.getvalue(), content_type="text/csv; charset=utf-8")
    fname = f"dead_stock_{shop_group or 'all'}.csv"
    response["Content-Disposition"] = f'attachment; filename="{fname}"'
    return response
