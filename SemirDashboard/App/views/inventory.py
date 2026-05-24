"""App/views/inventory.py — Global Inventory Analytics page."""
import logging

from django.shortcuts import render, redirect
from django.contrib import messages

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
