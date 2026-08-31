"""App/views/membership.py — Customer Membership KPI snapshot page."""
import logging

from django.contrib import messages
from django.http import HttpResponse, JsonResponse
from django.shortcuts import redirect, render

from App.analytics.membership import (
    DISPLAY_GRADES,
    compare_batches,
    get_all_batch_grade_series,
    get_grade_breakdown_by_store,
    get_live_customer_tier_table,
    get_snapshot_registration_stores,
    list_batches,
)
from App.forms import MembershipBackfillForm
from App.permissions import requires_perm, user_has_perm
from App.upload_jobs import acquire_type_lock, create_job, is_type_running
from App.views.shop_detail import _ajax_perm_check, _get_dropdown_options
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
    # Two DIFFERENT store lists, on purpose (PO feedback 2026-08-31): the
    # live Customer table for the LIVE-data "Customer Tier Progress" section,
    # vs. whatever actually appears in snapshot data for the two
    # snapshot-scoped sections below. Conflating them silently offered store
    # names absent from a given snapshot batch, producing a misleading
    # all-zero result.
    _, registration_stores, _, _, _, _ = _get_dropdown_options()
    snapshot_stores = get_snapshot_registration_stores()

    return render(
        request,
        "membership.html",
        {
            "batches": batches,
            "from_batch": from_batch,
            "to_batch": to_batch,
            "comparison": comparison,
            "chart_series": chart_series,
            "registration_stores": registration_stores,
            "snapshot_stores": snapshot_stores,
            "backfill_form": MembershipBackfillForm(),
            "can_import": user_has_perm(request.user, "membership.import"),
            "can_delete": user_has_perm(request.user, "membership.delete"),
        },
    )


def membership_table_partial(request):
    """Customer Tier Progress — reads the LIVE Customer table, not a snapshot
    (PO feedback 2026-08-31: "không liên quan gì đến snapshot"/has nothing to
    do with snapshot). Works even if zero snapshot batches exist yet."""
    err = _ajax_perm_check(request, "membership.view")
    if err:
        return err

    grade_filter = request.GET.get("grade") or None
    shop_filter = request.GET.get("shop") or None
    sort = request.GET.get("sort") or "amount_to_next_tier"

    rows, total_count = get_live_customer_tier_table(grade_filter=grade_filter, shop_filter=shop_filter, sort=sort)
    return render(request, "membership/_table_partial.html", {"rows": rows, "total_count": total_count})


def membership_store_breakdown_partial(request):
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

    if not batch_id:
        return HttpResponse('<div class="alert alert-warning m-0">No snapshot selected.</div>')

    store = request.GET.get("store") or None
    if store:
        # Drill-down: one store's Grade/From/To/Diff/%Change, reusing the
        # exact table markup as Section 2's overall comparison (PO feedback
        # 2026-08-31: "want comparison here too") — added 2026-08-31.
        from_batch_id = _parse_id(request.GET.get("from_batch"))
        comparison = compare_batches(from_batch_id, batch_id, store=store)
        return render(request, "membership/_store_grade_comparison_partial.html", {
            "comparison": comparison, "from_batch": from_batch_id, "store": store,
        })

    rows = get_grade_breakdown_by_store(batch_id)
    return render(request, "membership/_store_breakdown_partial.html", {"rows": rows, "grades": DISPLAY_GRADES})


def membership_trend_partial(request):
    """JSON (not HTML) — the trend chart is built entirely client-side by
    Chart.js from a JSON array, so an HTML fragment would be the wrong shape.
    Added 2026-08-31, PO feedback: chart needs a store filter. Bounded by
    batch count, not store count — see get_all_batch_grade_series() docstring."""
    err = _ajax_perm_check(request, "membership.view")
    if err:
        return err
    store = request.GET.get("store") or None
    return JsonResponse({"series": get_all_batch_grade_series(store=store)})


@requires_perm("membership.delete")
def membership_delete_batch(request, batch_id):
    if request.method != "POST":
        return redirect("membership_dashboard")

    from App.models.membership import MembershipSnapshotBatch

    try:
        batch = MembershipSnapshotBatch.objects.get(pk=batch_id)
    except MembershipSnapshotBatch.DoesNotExist:
        messages.error(request, "Snapshot not found.")
        return redirect("membership_dashboard")

    snapshot_date, source_display, row_count = batch.snapshot_date, batch.get_source_display(), batch.row_count
    batch.delete()  # cascades to MembershipSnapshot rows (on_delete=CASCADE)
    logger.info(
        "membership_delete_batch batch=%s date=%s source=%s rows=%s user=%s",
        batch_id, snapshot_date, source_display, row_count, request.user, extra={"step": "membership_snapshot"},
    )
    messages.info(request, f"Deleted snapshot {snapshot_date} ({source_display}, {row_count} rows).")
    return redirect("membership_dashboard")


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
