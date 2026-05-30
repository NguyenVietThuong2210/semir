"""App/views/upload.py — Data upload views (background thread processing)."""
import logging
import threading

_ALLOWED_UPLOAD_EXTENSIONS = {"csv", "xls", "xlsx"}


def _validate_upload_ext(f) -> str | None:
    """Return error message if file extension is not allowed, else None."""
    ext = f.name.rsplit(".", 1)[-1].lower() if "." in f.name else ""
    if ext not in _ALLOWED_UPLOAD_EXTENSIONS:
        return f"File type '.{ext}' is not allowed. Only CSV and Excel files are accepted."
    return None

from django.contrib import messages
from django.db.models import Count, Max, Min
from django.http import JsonResponse
from django.shortcuts import redirect, render

from App.forms import CustomerUploadForm, InventoryUploadForm, SaleDetailUploadForm, SalesUploadForm, UsedPointsUploadForm
from App.models import Customer, InventorySnapshot, SaleDetail, SalesTransaction
from App.permissions import requires_perm
from App.services import (
    process_coupon_file,
    process_customer_file,
    process_inventory_file,
    process_sale_detail_file,
    process_sales_file,
    process_used_points_file,
)
from App.upload_jobs import NamedBytesIO, _now_iso, create_job, get_recent_jobs, is_type_running, make_progress_fn, update_job

logger = logging.getLogger(__name__)


# ── Background thread runner ──────────────────────────────────────────────────

def _run_upload(job_id, fn, file_bytes, filename, on_done_fn=None):
    """Execute upload service function in a background thread."""
    from django.db import connection
    update_job(job_id, status="running")
    try:
        f = NamedBytesIO(file_bytes, filename)
        result = fn(f, progress_fn=make_progress_fn(job_id))
        if on_done_fn:
            on_done_fn()
        update_job(
            job_id,
            status="done",
            finished_at=_now_iso(),
            result=result,
        )
        logger.info("Job %s done: %s", job_id, result, extra={"step": "upload_job"})
    except Exception as exc:
        update_job(
            job_id,
            status="error",
            finished_at=_now_iso(),
            error=str(exc),
        )
        logger.exception("Job %s failed", job_id, extra={"step": "upload_job"})
    finally:
        connection.close()  # release DB connection held by this thread


def _start_thread(job_id, fn, file_bytes, filename, on_done_fn=None):
    t = threading.Thread(
        target=_run_upload,
        args=(job_id, fn, file_bytes, filename, on_done_fn),
        daemon=True,
    )
    t.start()


# ── Upload views ──────────────────────────────────────────────────────────────

@requires_perm("data.upload")
def upload_customers(request):
    if request.method == "POST":
        form = CustomerUploadForm(request.POST, request.FILES)
        if form.is_valid():
            if is_type_running("customers"):
                messages.warning(request, "A customer upload is already in progress. Please wait for it to finish.")
                return redirect("upload_customers")
            f = request.FILES["file"]
            err = _validate_upload_ext(f)
            if err:
                messages.error(request, err)
                return redirect("upload_customers")
            file_bytes = f.read()
            job_id = create_job("customers", f.name)
            logger.info("upload_customers queued job=%s file=%s user=%s", job_id, f.name, request.user, extra={"step": "upload_customers"})
            _start_thread(job_id, process_customer_file, file_bytes, f.name, None)
            messages.info(request, f"Upload started — tracking job {job_id[:8]}…")
            return redirect("upload_customers")
        else:
            messages.error(request, "Invalid form submission.")

    date_stats = Customer.objects.aggregate(
        min_date=Min("registration_date"),
        max_date=Max("registration_date"),
        total_count=Count("id"),
    )
    return render(
        request,
        "upload/customers.html",
        {
            "form": CustomerUploadForm(),
            "used_points_form": UsedPointsUploadForm(),
            "date_stats": date_stats,
        },
    )


@requires_perm("data.upload")
def upload_used_points(request):
    if request.method == "POST":
        form = UsedPointsUploadForm(request.POST, request.FILES)
        if form.is_valid():
            if is_type_running("used_points"):
                messages.warning(request, "A used-points upload is already in progress. Please wait.")
                return redirect("upload_customers")
            f = request.FILES["file"]
            err = _validate_upload_ext(f)
            if err:
                messages.error(request, err)
                return redirect("upload_customers")
            file_bytes = f.read()
            job_id = create_job("used_points", f.name)
            logger.info("upload_used_points queued job=%s file=%s user=%s", job_id, f.name, request.user, extra={"step": "upload_used_points"})
            _start_thread(job_id, process_used_points_file, file_bytes, f.name)
            messages.info(request, f"Upload started — tracking job {job_id[:8]}…")
        else:
            messages.error(request, "Invalid form submission.")
    return redirect("upload_customers")


@requires_perm("data.upload")
def upload_sales(request):
    if request.method == "POST":
        form = SalesUploadForm(request.POST, request.FILES)
        if form.is_valid():
            if is_type_running("sales"):
                messages.warning(request, "A sales upload is already in progress. Please wait.")
                return redirect("upload_sales")
            f = request.FILES["file"]
            err = _validate_upload_ext(f)
            if err:
                messages.error(request, err)
                return redirect("upload_sales")
            file_bytes = f.read()
            job_id = create_job("sales", f.name)
            logger.info("upload_sales queued job=%s file=%s user=%s", job_id, f.name, request.user, extra={"step": "upload_sales"})
            _start_thread(job_id, process_sales_file, file_bytes, f.name, None)
            messages.info(request, f"Upload started — tracking job {job_id[:8]}…")
            return redirect("upload_sales")
        else:
            messages.error(request, "Invalid form submission.")

    date_stats = SalesTransaction.objects.aggregate(
        min_date=Min("sales_date"), max_date=Max("sales_date"), total_count=Count("id")
    )
    detail_stats = SaleDetail.objects.aggregate(
        min_date=Min("sales_date"), max_date=Max("sales_date"), total_count=Count("id"),
    )
    return render(request, "upload/sales.html", {
        "form": SalesUploadForm(),
        "date_stats": date_stats,
        "detail_form": SaleDetailUploadForm(),
        "detail_stats": detail_stats,
    })


@requires_perm("data.upload")
def upload_coupons(request):
    if request.method == "POST" and request.FILES.get("file"):
        if is_type_running("coupons"):
            messages.warning(request, "A coupon upload is already in progress. Please wait.")
            return redirect("upload_coupons")
        f = request.FILES["file"]
        err = _validate_upload_ext(f)
        if err:
            messages.error(request, err)
            return redirect("upload_coupons")
        file_bytes = f.read()
        job_id = create_job("coupons", f.name)
        logger.info("upload_coupons queued job=%s file=%s user=%s", job_id, f.name, request.user, extra={"step": "upload_coupons"})
        _start_thread(job_id, process_coupon_file, file_bytes, f.name, None)
        messages.info(request, f"Upload started — tracking job {job_id[:8]}…")
        return redirect("upload_coupons")
    return render(request, "upload/coupons.html")


@requires_perm("data.upload")
def upload_inventory(request):
    if request.method == "POST":
        form = InventoryUploadForm(request.POST, request.FILES)
        if form.is_valid():
            if is_type_running("inventory"):
                messages.warning(request, "An inventory upload is already in progress. Please wait.")
                return redirect("upload_inventory")
            f = request.FILES["file"]
            err = _validate_upload_ext(f)
            if err:
                messages.error(request, err)
                return redirect("upload_inventory")
            file_bytes = f.read()
            job_id = create_job("inventory", f.name)
            logger.info("upload_inventory queued job=%s file=%s user=%s", job_id, f.name, request.user,
                        extra={"step": "upload_inventory"})
            def _inv_done():
                from django.core.cache import cache
                from App.analytics.inventory_functions import bump_inventory_version
                cache.delete("shop_detail_dropdowns")
                bump_inventory_version()
            _start_thread(job_id, process_inventory_file, file_bytes, f.name, _inv_done)
            messages.info(request, f"Inventory upload started — tracking job {job_id[:8]}…")
            return redirect("upload_inventory")
        else:
            messages.error(request, "Invalid form submission.")

    from django.db.models import Sum
    stats = InventorySnapshot.objects.aggregate(
        total_rows=Count('id'),
        total_qty=Sum('inventory_qty'),
        total_value=Sum('tag_amount'),
    )
    latest = InventorySnapshot.objects.order_by('-uploaded_at').values('uploaded_at', 'shop_name').first()
    return render(request, "upload/inventory.html", {
        "form": InventoryUploadForm(),
        "stats": stats,
        "latest": latest,
    })


@requires_perm("data.upload")
def upload_sale_detail(request):
    if request.method == "POST":
        form = SaleDetailUploadForm(request.POST, request.FILES)
        if form.is_valid():
            if is_type_running("sale_detail"):
                messages.warning(request, "A sale detail upload is already in progress. Please wait.")
                return redirect("upload_sales")
            f = request.FILES["file"]
            err = _validate_upload_ext(f)
            if err:
                messages.error(request, err)
                return redirect("upload_sales")
            file_bytes = f.read()
            job_id = create_job("sale_detail", f.name)
            logger.info("upload_sale_detail queued job=%s file=%s user=%s", job_id, f.name, request.user,
                        extra={"step": "upload_sale_detail"})
            def _sd_done():
                from App.analytics.product_analytics import bump_product_version
                bump_product_version()
            _start_thread(job_id, process_sale_detail_file, file_bytes, f.name, _sd_done)
            messages.info(request, f"Sale detail upload started — tracking job {job_id[:8]}…")
        else:
            messages.error(request, "Invalid form submission.")
    return redirect("upload_sales")


# ── Status API endpoints ──────────────────────────────────────────────────────

@requires_perm("data.upload")
def upload_job_status(request, job_id):
    """Return JSON status for a single job."""
    from App.upload_jobs import get_job
    job = get_job(job_id)
    if not job:
        return JsonResponse({"error": "Job not found"}, status=404)
    return JsonResponse(job)


@requires_perm("data.upload")
def upload_jobs_list(request):
    """Return JSON list of recent upload jobs."""
    jobs = get_recent_jobs(limit=30)
    return JsonResponse({"jobs": jobs})
