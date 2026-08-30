"""App/views/membership.py — Customer Membership KPI snapshot page."""
import logging

from django.contrib import messages
from django.http import HttpResponse
from django.shortcuts import redirect, render

from App.analytics.membership import (
    compare_batches,
    get_all_batch_grade_series,
    get_customer_tier_table,
    list_batches,
)
from App.forms import MembershipBackfillForm
from App.permissions import requires_perm, user_has_perm
from App.upload_jobs import acquire_type_lock, create_job, is_type_running
from App.views.shop_detail import _ajax_perm_check
from App.views.upload import _pre_upload_checks, _start_thread

logger = logging.getLogger(__name__)


def _default_batch_ids(batches):
    """Default From/To selection: the two most recent batches (or the single
    batch if only one exists)."""
    if not batches:
        return None, None
    if len(batches) == 1:
        return None, batches[0].id
    # batches is ordered -snapshot_date,-created_at (newest first)
    return batches[1].id, batches[0].id


@requires_perm("membership.view")
def membership_dashboard(request):
    batches = list_batches()
    default_from, default_to = _default_batch_ids(batches)

    def _parse_id(raw, default):
        if not raw:
            return default
        try:
            return int(raw)
        except (TypeError, ValueError):
            return default

    from_batch = _parse_id(request.GET.get("from_batch"), default_from)
    to_batch = _parse_id(request.GET.get("to_batch"), default_to)

    comparison = compare_batches(from_batch, to_batch)
    chart_series = get_all_batch_grade_series()

    return render(
        request,
        "membership.html",
        {
            "batches": batches,
            "from_batch": from_batch,
            "to_batch": to_batch,
            "comparison": comparison,
            "chart_series": chart_series,
            "backfill_form": MembershipBackfillForm(),
            "can_import": user_has_perm(request.user, "membership.import"),
        },
    )


def membership_table_partial(request):
    err = _ajax_perm_check(request, "membership.view")
    if err:
        return err

    def _parse_id(raw):
        try:
            return int(raw)
        except (TypeError, ValueError):
            return None

    batch_id = _parse_id(request.GET.get("batch"))
    if not batch_id:
        batches = list_batches()
        batch_id = batches[0].id if batches else None  # newest first (Meta.ordering)
    grade_filter = request.GET.get("grade") or None
    shop_filter = request.GET.get("shop") or None
    sort = request.GET.get("sort") or "amount_to_next_tier"

    if not batch_id:
        return HttpResponse('<div class="alert alert-warning m-0">No snapshot selected.</div>')

    rows, total_count = get_customer_tier_table(batch_id, grade_filter=grade_filter, shop_filter=shop_filter, sort=sort)
    return render(request, "membership/_table_partial.html", {"rows": rows, "total_count": total_count})


@requires_perm("membership.import")
def membership_backfill_import(request):
    if request.method != "POST":
        return redirect("membership_dashboard")

    form = MembershipBackfillForm(request.POST, request.FILES)
    if not form.is_valid():
        messages.error(request, "Invalid form submission.")
        return redirect("membership_dashboard")

    if is_type_running("membership_backfill"):
        messages.warning(request, "A backfill import is already in progress. Please wait for it to finish.")
        return redirect("membership_dashboard")

    f = request.FILES["file"]
    pre = _pre_upload_checks(request, f, "customers")
    if pre is None:
        return redirect("membership_dashboard")
    file_bytes, file_hash, df = pre

    if not acquire_type_lock("membership_backfill"):
        messages.warning(request, "A backfill import is already in progress. Please wait.")
        return redirect("membership_dashboard")

    job_id = create_job("membership_backfill", f.name, file_hash=file_hash)
    logger.info(
        "membership_backfill_import queued job=%s file=%s user=%s",
        job_id, f.name, request.user, extra={"step": "membership_backfill"},
    )

    from functools import partial

    from App.services.membership_snapshot import create_backfill_snapshot

    fn = partial(
        create_backfill_snapshot,
        snapshot_date=form.cleaned_data["snapshot_date"],
        uploaded_by=request.user if request.user.is_authenticated else None,
        note=form.cleaned_data.get("note", ""),
    )
    _start_thread(job_id, fn, file_bytes, f.name, None, df)
    messages.info(request, f"Backfill snapshot import started — tracking job {job_id[:8]}…")
    return redirect("membership_dashboard")
