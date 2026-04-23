from functools import wraps
from django.contrib.auth.decorators import login_required
from django.shortcuts import redirect
from django.contrib import messages

PERMISSION_DEFS = [
    ("sales.view",          "View Sales Analytics",             "Sales Analytics"),
    ("sales.chart",         "View Sales Chart",                 "Sales Analytics"),
    ("sales.export",        "Export Sales Analytics (Excel)",   "Sales Analytics"),
    ("sales.export_chart",  "Export Sales Chart (Excel)",       "Sales Analytics"),
    ("coupons.view",        "View Coupon Dashboard",            "Coupons"),
    ("coupons.chart",       "View Coupon Chart",                "Coupons"),
    ("coupons.export",      "Export Coupons (Excel)",           "Coupons"),
    ("coupons.export_chart","Export Coupon Chart (Excel)",      "Coupons"),
    ("coupons.manage",      "Manage Coupon Campaigns",          "Coupons"),
    ("cnv.view",            "View Customer Analytics (CNV)",    "CNV / Customer Analytics"),
    ("cnv.chart",           "View Customer Chart (CNV)",        "CNV / Customer Analytics"),
    ("cnv.sync",            "View CNV Sync Status",             "CNV / Customer Analytics"),
    ("cnv.export",          "Export Customer Analytics (Excel)","CNV / Customer Analytics"),
    ("cnv.export_chart",    "Export Customer Chart (Excel)",    "CNV / Customer Analytics"),
    ("customers.detail",    "View Customer Detail",             "Customers"),
    ("shops.view",          "View Shop Detail",                 "Shop Detail"),
    ("shops.export",        "Export Shop Detail (Excel)",       "Shop Detail"),
    ("data.upload",         "Upload Data",                      "Data Management"),
    ("data.formulas",       "View Formulas",                    "Data Management"),
    ("admin.users",         "Manage Users",                     "Admin"),
]

ALL_PERMISSIONS = [p[0] for p in PERMISSION_DEFS]
ADMIN_PERMISSIONS = ALL_PERMISSIONS
VIEWER_PERMISSIONS = [
    "sales.view",
]


def user_has_perm(user, codename):
    if not user.is_authenticated:
        return False
    if user.is_superuser:
        return True
    try:
        profile = user.profile
        if profile.role:
            return codename in (profile.role.permissions or [])
    except Exception:
        pass
    return False


def requires_perm(codename):
    def decorator(view_func):
        @login_required
        @wraps(view_func)
        def wrapper(request, *args, **kwargs):
            if not user_has_perm(request.user, codename):
                messages.error(
                    request, "You do not have permission to access this page."
                )
                return redirect("home")
            return view_func(request, *args, **kwargs)

        return wrapper

    return decorator
