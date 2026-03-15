"""
views.py - Customer Analytics Application

Version: 3.1
- Added database statistics with date ranges to upload pages
- Shows min/max dates and total counts for better UX
"""

import json
import logging
from django.shortcuts import render, redirect
from django.contrib import messages
from django.http import HttpResponse
from django.db.models import Min, Max, Count
from django.core.cache import cache
from datetime import datetime
from App.permissions import requires_perm, user_has_perm

_ANALYTICS_VER_KEY = "analytics_data_ver"
_ANALYTICS_TTL = 600  # 10 minutes

_COUPON_VER_KEY = "coupon_data_ver"
_COUPON_TTL = 600  # 10 minutes


# ── Cache key builders ────────────────────────────────────────────────────────


def _analytics_cache_key(date_from, date_to, shop_group):
    v = cache.get(_ANALYTICS_VER_KEY, 0)
    return f"anl_data:{v}:{date_from}:{date_to}:{shop_group}"


def _coupon_cache_key(date_from, date_to, prefix, shop_group):
    v = cache.get(_COUPON_VER_KEY, 0)
    return f"cpn_data:{v}:{date_from}:{date_to}:{prefix}:{shop_group}"


# ── Invalidators ──────────────────────────────────────────────────────────────


def _invalidate_analytics_cache():
    v = cache.get(_ANALYTICS_VER_KEY, 0)
    cache.set(_ANALYTICS_VER_KEY, v + 1, 86400 * 30)
    logger.info("analytics cache invalidated (ver→%d)", v + 1)


def _invalidate_coupon_cache():
    v = cache.get(_COUPON_VER_KEY, 0)
    cache.set(_COUPON_VER_KEY, v + 1, 86400 * 30)
    tv = cache.get("cpn_trend_ver", 0)
    cache.set("cpn_trend_ver", tv + 1, 86400 * 30)
    logger.info("coupon cache invalidated (ver→%d, trend_ver→%d)", v + 1, tv + 1)


# ── Data helpers (cache get-or-compute) ───────────────────────────────────────


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


from App.analytics.core import calculate_return_rate_analytics
from App.analytics.coupon_analytics import (
    calculate_coupon_analytics,
    export_coupon_to_excel,
)
from App.analytics.excel_export import export_analytics_to_excel
from .forms import CustomerUploadForm, SalesUploadForm, UsedPointsUploadForm
from .utils import process_customer_file, process_sales_file, process_used_points_file
from .models import Customer, SalesTransaction, Coupon
from .models_cnv import CNVCustomer

logger = logging.getLogger("customer_analytics")

QUICK_BTNS = [
    ("Last 7 Days", 7),
    ("Last 30 Days", 30),
    ("Last 90 Days", 90),
    ("Last Year", 365),
]

YEAR_BTNS = [2024, 2025, 2026]


def _parse_date(val, label, request):
    """Parse date string to date object."""
    if not val:
        return None
    try:
        return datetime.strptime(val, "%Y-%m-%d").date()
    except ValueError:
        messages.warning(request, f"Invalid {label} format")
        return None


def home(request):
    """Home page view."""
    return render(request, "home.html")


@requires_perm("page_upload")
def upload_customers(request):
    """
    Upload customer data from Excel/CSV file.
    Now includes database statistics showing date ranges.
    """
    if request.method == "POST":
        form = CustomerUploadForm(request.POST, request.FILES)
        used_points_form = UsedPointsUploadForm()
        if form.is_valid():
            f = request.FILES["file"]
            logger.info("upload_customers: %s user=%s", f.name, request.user)
            try:
                result = process_customer_file(f)
                _invalidate_analytics_cache()
                messages.success(
                    request,
                    f"Processed {result['total_processed']} customers – "
                    f"Created: {result['created']}, Updated: {result['updated']}",
                )
                for err in result.get("errors", [])[:5]:
                    messages.warning(request, err)
                return redirect("upload_customers")
            except Exception as e:
                logger.exception("upload_customers error")
                messages.error(request, f"Error: {e}")
    else:
        form = CustomerUploadForm()
        used_points_form = UsedPointsUploadForm()

    # Get database statistics with date ranges
    date_stats = Customer.objects.aggregate(
        min_date=Min("registration_date"),
        max_date=Max("registration_date"),
        total_count=Count("id"),
    )

    return render(
        request,
        "upload_customers.html",
        {"form": form, "used_points_form": used_points_form, "date_stats": date_stats},
    )


@requires_perm("page_upload")
def upload_used_points(request):
    """Upload used_points and used_points_note for existing POS customers."""
    if request.method == "POST":
        form = UsedPointsUploadForm(request.POST, request.FILES)
        if form.is_valid():
            f = request.FILES["file"]
            logger.info("upload_used_points: %s user=%s", f.name, request.user)
            try:
                result = process_used_points_file(f)
                messages.success(
                    request,
                    f"Processed {result['total_processed']} rows — "
                    f"Updated: {result['updated']}, Skipped: {result['skipped']}",
                )
                for err in result.get("errors", [])[:5]:
                    messages.warning(request, err)
                return redirect("upload_customers")
            except Exception as e:
                logger.exception("upload_used_points error")
                messages.error(request, f"Error: {e}")
    else:
        form = UsedPointsUploadForm()

    return redirect("upload_customers")


@requires_perm("page_upload")
def upload_sales(request):
    """
    Upload sales transaction data from Excel/CSV file.
    Now includes database statistics showing date ranges.
    """
    if request.method == "POST":
        form = SalesUploadForm(request.POST, request.FILES)
        if form.is_valid():
            f = request.FILES["file"]
            logger.info("upload_sales: %s user=%s", f.name, request.user)
            try:
                result = process_sales_file(f)
                _invalidate_analytics_cache()
                messages.success(
                    request,
                    f"Imported {result['created']} new transactions. "
                    f"Updated (overwritten) {result['updated']} existing.",
                )
                for err in result.get("errors", [])[:5]:
                    messages.warning(request, err)
                return redirect("analytics_dashboard")
            except Exception as e:
                logger.exception("upload_sales error")
                messages.error(request, f"Error: {e}")
    else:
        form = SalesUploadForm()

    # Get database statistics with date ranges
    date_stats = SalesTransaction.objects.aggregate(
        min_date=Min("sales_date"), max_date=Max("sales_date"), total_count=Count("id")
    )

    return render(
        request, "upload_sales.html", {"form": form, "date_stats": date_stats}
    )


@requires_perm("page_upload")
def upload_coupons(request):
    """Upload coupon data from Excel/CSV file."""
    if request.method == "POST" and request.FILES.get("file"):
        f = request.FILES["file"]
        logger.info("upload_coupons: %s user=%s", f.name, request.user)
        try:
            from .utils import process_coupon_file

            result = process_coupon_file(f)
            _invalidate_coupon_cache()
            messages.success(
                request,
                f"Coupon import complete – Created: {result['created']}, "
                f"Updated (overwritten): {result['updated']}, Errors: {result['errors']}",
            )
        except Exception as e:
            logger.exception("upload_coupons error")
            messages.error(request, f"Error: {e}")
        return redirect("upload_coupons")
    return render(request, "upload_coupons.html")


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
    return render(request, "analytics_dashboard.html", ctx)


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
        "analytics_chart.html",
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
    """Export analytics data to Excel file."""
    start_date = request.GET.get("start_date", "")
    end_date = request.GET.get("end_date", "")
    shop_group = request.GET.get("shop_group", "")  # New: include shop_group in export

    date_from = _parse_date(start_date, "start date", request)
    date_to = _parse_date(end_date, "end date", request)

    data, _ = _get_analytics_data(date_from, date_to, shop_group)
    if not data:
        messages.error(request, "No data to export")
        return redirect("analytics_dashboard")

    # Pass filter info to export
    wb = export_analytics_to_excel(
        data, date_from=date_from, date_to=date_to, shop_group=shop_group
    )

    fn = (
        f"return_visit_rate_{date_from}_{date_to}_{datetime.now().strftime('%H%M%S')}.xlsx"
        if date_from and date_to
        else f"return_visit_rate_{datetime.now().strftime('%Y%m%d_%H%M%S')}.xlsx"
    )
    resp = HttpResponse(
        content_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
    )
    resp["Content-Disposition"] = f'attachment; filename="{fn}"'
    wb.save(resp)
    return resp


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

    from .models import CouponCampaign as _CC
    _campaigns = list(_CC.objects.values("id", "name", "prefix"))
    for _c in _campaigns:
        _c["prefix_list"] = [p.strip() for p in (_c["prefix"] or "").split(",") if p.strip()]

    return render(
        request,
        "coupon_dashboard.html",
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
            "quick_btns": QUICK_BTNS,
            "campaigns_json": json.dumps(_campaigns),
        },
    )


@requires_perm("download_coupons")
def export_coupons(request):
    """Export coupon analytics to Excel file with shop group filter support."""
    start_date = request.GET.get("start_date", "")
    end_date = request.GET.get("end_date", "")
    coupon_id_prefix = request.GET.get("coupon_id_prefix", "").strip()
    shop_group = request.GET.get("shop_group", "").strip()

    date_from = _parse_date(start_date, "start date", request)
    date_to = _parse_date(end_date, "end date", request)

    data, _ = _get_coupon_data(date_from, date_to, coupon_id_prefix, shop_group)

    wb = export_coupon_to_excel(
        data,
        date_from=date_from,
        date_to=date_to,
        coupon_id_prefix=coupon_id_prefix,
        shop_group=shop_group,
    )

    fn = (
        f"coupon_{date_from}_{date_to}_{datetime.now().strftime('%H%M%S')}.xlsx"
        if date_from and date_to
        else f"coupon_{datetime.now().strftime('%Y%m%d_%H%M%S')}.xlsx"
    )
    resp = HttpResponse(
        content_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
    )
    resp["Content-Disposition"] = f'attachment; filename="{fn}"'
    wb.save(resp)
    return resp


@requires_perm("page_formulas")
def formulas_page(request):
    """Display formulas and definitions used in analytics."""
    return render(request, "formulas.html")


# ── Coupon Campaign CRUD ──────────────────────────────────────────────────────


@requires_perm("manage_campaigns")
def manage_campaigns(request):
    """
    AJAX + page endpoint for CouponCampaign CRUD.
    GET  → JSON list of all campaigns.
    POST → action=create|update|delete.
    """
    import json
    from django.http import JsonResponse
    from .models import CouponCampaign

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
            _invalidate_coupon_cache()
            return JsonResponse({"ok": True})

        if action == "delete":
            pk = body.get("id")
            if not pk:
                return JsonResponse({"error": "id required"}, status=400)
            deleted, _ = CouponCampaign.objects.filter(pk=pk).delete()
            if not deleted:
                return JsonResponse({"error": "Campaign not found"}, status=404)
            _invalidate_coupon_cache()
            return JsonResponse({"ok": True})

        return JsonResponse({"error": "Unknown action"}, status=400)

    return JsonResponse({"error": "Method not allowed"}, status=405)


# ── Coupon Analytics Chart ────────────────────────────────────────────────────


@requires_perm("page_coupon_chart")
def coupon_chart(request):
    """Coupon analytics chart page — overview pies + shop/campaign trend lines."""
    from .analytics.coupon_analytics import calculate_coupon_trend_data
    from .models import CouponCampaign

    start_date = request.GET.get("start_date", "")
    end_date = request.GET.get("end_date", "")
    coupon_id_prefix = request.GET.get("coupon_id_prefix", "").strip()
    shop_group = request.GET.get("shop_group", "").strip()

    date_from = _parse_date(start_date, "start date", request)
    date_to = _parse_date(end_date, "end date", request)

    # Overview pies reuse the cached coupon data
    data, _ = _get_coupon_data(date_from, date_to, coupon_id_prefix, shop_group)

    # Trend data (shop×time, campaign×time) — separate cache
    _trend_ver_key = "cpn_trend_ver"
    _trend_ttl = 600
    trend_v = cache.get(_trend_ver_key, 0)
    trend_cache_key = f"cpn_trend:{trend_v}:{date_from}:{date_to}:{shop_group}:{coupon_id_prefix}"
    trend_data = cache.get(trend_cache_key)
    if trend_data is None:
        trend_data = calculate_coupon_trend_data(date_from, date_to, shop_group, coupon_id_prefix)
        cache.set(trend_cache_key, trend_data, _trend_ttl)
        logger.info("coupon trend cache MISS (%s)", trend_cache_key)
    else:
        logger.info("coupon trend cache HIT (%s)", trend_cache_key)

    campaigns = list(CouponCampaign.objects.values("id", "name", "prefix"))

    return render(
        request,
        "coupon_chart.html",
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
            "quick_btns": QUICK_BTNS,
            "year_btns": YEAR_BTNS,
        },
    )


@requires_perm("page_customer_detail")
def customer_detail(request):
    """
    Customer Detail Analytics - Search and view individual customer info.
    Searches by VIP ID or Phone Number.
    Shows customer info, CNV sync status, and invoice history.
    """
    search_vip_id = request.GET.get("vip_id", "").strip()
    search_phone = request.GET.get("phone", "").strip()

    customer = None
    invoices = []
    stats = {}
    is_synced_to_cnv = False
    cnv_customer = None
    search_attempted = bool(search_vip_id or search_phone)

    if search_vip_id or search_phone:
        logger.info(
            "customer_detail: vip_id=%s phone=%s user=%s",
            search_vip_id,
            search_phone,
            request.user,
        )

        # Search customer
        if search_vip_id:
            try:
                customer = Customer.objects.get(vip_id=search_vip_id)
            except Customer.DoesNotExist:
                logger.warning("Customer not found: vip_id=%s", search_vip_id)
        elif search_phone:
            try:
                customer = Customer.objects.get(phone=search_phone)
            except Customer.DoesNotExist:
                logger.warning("Customer not found: phone=%s", search_phone)
            except Customer.MultipleObjectsReturned:
                # If multiple customers with same phone, get first one
                customer = Customer.objects.filter(phone=search_phone).first()
                logger.warning(
                    "Multiple customers found with phone=%s, using first", search_phone
                )

        if customer:
            # Check CNV sync status (use 'phone' field not 'phone_no')
            if customer.phone:
                cnv_customer = CNVCustomer.objects.filter(phone=customer.phone).first()
                print(
                    f"{cnv_customer.total_points} - {cnv_customer.used_points} - {cnv_customer.points}"
                )
                is_synced_to_cnv = True if cnv_customer is not None else False

            # Get all invoices for this customer
            invoices = (
                SalesTransaction.objects.filter(vip_id=customer.vip_id)
                .select_related()
                .order_by("-sales_date")
            )

            # Add coupon info to each invoice
            invoices_with_coupons = []
            for inv in invoices:
                invoice_data = {
                    "invoice_no": inv.invoice_number,
                    "sales_day": inv.sales_date,
                    "shop_name": inv.shop_name,
                    "amount": inv.settlement_amount,
                    "season": inv.bu,
                    "coupon_id": None,
                    "face_value_display": None,
                    "coupon_amount": None,
                }

                # Check if this invoice has a coupon
                coupon = Coupon.objects.filter(
                    docket_number=inv.invoice_number, using_date__isnull=False
                ).first()

                if coupon:
                    invoice_data["coupon_id"] = coupon.coupon_id
                    # Display face value
                    from App.analytics.coupon_analytics import (
                        format_face_value,
                        calc_coupon_amount,
                    )

                    invoice_data["face_value_display"] = format_face_value(
                        coupon.face_value
                    )
                    invoice_data["coupon_amount"] = calc_coupon_amount(
                        coupon.face_value, inv.settlement_amount
                    )

                invoices_with_coupons.append(invoice_data)

            invoices = invoices_with_coupons

            # Calculate statistics
            from decimal import Decimal
            from django.db.models import Sum, Max, Count

            invoice_stats = SalesTransaction.objects.filter(
                vip_id=customer.vip_id
            ).aggregate(
                total=Count("id"),
                total_amount=Sum("settlement_amount"),
                last_date=Max("sales_date"),
            )

            stats = {
                "total_purchases": invoice_stats["total"] or 0,
                "total_amount": invoice_stats["total_amount"] or Decimal(0),
                "last_purchase_date": invoice_stats["last_date"],
            }

    return render(
        request,
        "customer_detail.html",
        {
            "customer": customer,
            "invoices": invoices,
            "stats": stats,
            "is_synced_to_cnv": is_synced_to_cnv,
            "cnv_customer": cnv_customer,
            "search_vip_id": search_vip_id,
            "search_phone": search_phone,
            "search_attempted": search_attempted,
        },
    )
