"""App/views/upload.py — Data upload views (background thread processing)."""
import logging
import threading

from django.contrib import messages
from django.db.models import Count, Max, Min
from django.http import JsonResponse
from django.shortcuts import redirect, render

from App.forms import CustomerUploadForm, SalesUploadForm, UsedPointsUploadForm
from App.models import Customer, SalesTransaction
from App.permissions import requires_perm
from App.services import (
    process_coupon_file,
    process_customer_file,
    process_sales_file,
    process_used_points_file,
)
from App.upload_jobs import NamedBytesIO, _now_iso, create_job, get_recent_jobs, is_type_running, make_progress_fn, update_job

logger = logging.getLogger(__name__)


# ── Cache helpers ─────────────────────────────────────────────────────────────

def _invalidate_analytics_cache():
    from App.views.analytics import _invalidate_analytics_cache as _do
    _do()


def _invalidate_coupon_cache():
    from App.views.coupon import _invalidate_coupon_cache as _do
    _do()


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

@requires_perm("page_upload")
def upload_customers(request):
    if request.method == "POST":
        form = CustomerUploadForm(request.POST, request.FILES)
        if form.is_valid():
            if is_type_running("customers"):
                messages.warning(request, "A customer upload is already in progress. Please wait for it to finish.")
                return redirect("upload_customers")
            f = request.FILES["file"]
            file_bytes = f.read()
            job_id = create_job("customers", f.name)
            logger.info("upload_customers queued job=%s file=%s user=%s", job_id, f.name, request.user, extra={"step": "upload_customers"})
            _start_thread(job_id, process_customer_file, file_bytes, f.name, _invalidate_analytics_cache)
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


@requires_perm("page_upload")
def upload_used_points(request):
    if request.method == "POST":
        form = UsedPointsUploadForm(request.POST, request.FILES)
        if form.is_valid():
            if is_type_running("used_points"):
                messages.warning(request, "A used-points upload is already in progress. Please wait.")
                return redirect("upload_customers")
            f = request.FILES["file"]
            file_bytes = f.read()
            job_id = create_job("used_points", f.name)
            logger.info("upload_used_points queued job=%s file=%s user=%s", job_id, f.name, request.user, extra={"step": "upload_used_points"})
            _start_thread(job_id, process_used_points_file, file_bytes, f.name)
            messages.info(request, f"Upload started — tracking job {job_id[:8]}…")
        else:
            messages.error(request, "Invalid form submission.")
    return redirect("upload_customers")


@requires_perm("page_upload")
def upload_sales(request):
    if request.method == "POST":
        form = SalesUploadForm(request.POST, request.FILES)
        if form.is_valid():
            if is_type_running("sales"):
                messages.warning(request, "A sales upload is already in progress. Please wait.")
                return redirect("upload_sales")
            f = request.FILES["file"]
            file_bytes = f.read()
            job_id = create_job("sales", f.name)
            logger.info("upload_sales queued job=%s file=%s user=%s", job_id, f.name, request.user, extra={"step": "upload_sales"})
            _start_thread(job_id, process_sales_file, file_bytes, f.name, _invalidate_analytics_cache)
            messages.info(request, f"Upload started — tracking job {job_id[:8]}…")
            return redirect("upload_sales")
        else:
            messages.error(request, "Invalid form submission.")

    date_stats = SalesTransaction.objects.aggregate(
        min_date=Min("sales_date"), max_date=Max("sales_date"), total_count=Count("id")
    )
    return render(request, "upload/sales.html", {"form": SalesUploadForm(), "date_stats": date_stats})


@requires_perm("page_upload")
def upload_coupons(request):
    if request.method == "POST" and request.FILES.get("file"):
        if is_type_running("coupons"):
            messages.warning(request, "A coupon upload is already in progress. Please wait.")
            return redirect("upload_coupons")
        f = request.FILES["file"]
        file_bytes = f.read()
        job_id = create_job("coupons", f.name)
        logger.info("upload_coupons queued job=%s file=%s user=%s", job_id, f.name, request.user, extra={"step": "upload_coupons"})
        _start_thread(job_id, process_coupon_file, file_bytes, f.name, _invalidate_coupon_cache)
        messages.info(request, f"Upload started — tracking job {job_id[:8]}…")
        return redirect("upload_coupons")
    return render(request, "upload/coupons.html")


# ── Status API endpoints ──────────────────────────────────────────────────────

@requires_perm("page_upload")
def upload_job_status(request, job_id):
    """Return JSON status for a single job."""
    from App.upload_jobs import get_job
    job = get_job(job_id)
    if not job:
        return JsonResponse({"error": "Job not found"}, status=404)
    return JsonResponse(job)


@requires_perm("page_upload")
def upload_jobs_list(request):
    """Return JSON list of recent upload jobs."""
    jobs = get_recent_jobs(limit=30)
    return JsonResponse({"jobs": jobs})
