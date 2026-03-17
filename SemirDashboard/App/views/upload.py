"""App/views/upload.py — Data upload views."""
import logging
from django.shortcuts import render, redirect
from django.contrib import messages
from django.db.models import Min, Max, Count

from App.permissions import requires_perm
from App.forms import CustomerUploadForm, SalesUploadForm, UsedPointsUploadForm
from App.services import process_customer_file, process_sales_file, process_used_points_file
from App.models import Customer, SalesTransaction

logger = logging.getLogger("customer_analytics")


def _invalidate_analytics_cache():
    from django.core.cache import cache
    from App.views.analytics import _ANALYTICS_VER_KEY
    v = cache.get(_ANALYTICS_VER_KEY, 0)
    cache.set(_ANALYTICS_VER_KEY, v + 1, 86400 * 30)
    logger.info("analytics cache invalidated (ver→%d)", v + 1)


def _invalidate_coupon_cache():
    from django.core.cache import cache
    from App.views.coupon import _COUPON_VER_KEY
    v = cache.get(_COUPON_VER_KEY, 0)
    cache.set(_COUPON_VER_KEY, v + 1, 86400 * 30)
    tv = cache.get("cpn_trend_ver", 0)
    cache.set("cpn_trend_ver", tv + 1, 86400 * 30)
    logger.info("coupon cache invalidated (ver→%d, trend_ver→%d)", v + 1, tv + 1)


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
        "upload/customers.html",
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
        request, "upload/sales.html", {"form": form, "date_stats": date_stats}
    )


@requires_perm("page_upload")
def upload_coupons(request):
    """Upload coupon data from Excel/CSV file."""
    if request.method == "POST" and request.FILES.get("file"):
        f = request.FILES["file"]
        logger.info("upload_coupons: %s user=%s", f.name, request.user)
        try:
            from App.services import process_coupon_file

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
    return render(request, "upload/coupons.html")
