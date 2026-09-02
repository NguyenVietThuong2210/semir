"""
App/services/grade_progress_calc.py

Full-DB recompute service backing the "Customer Tier Progress" grade-change
date feature (Membership page). Runs the validated per-customer, exact-date
simulation (App/analytics/grade_simulation.py::simulate_one_customer(),
already A/B-validated at 98.5% live-grade agreement, 90.5% exact-day match
against real PROD snapshots) for every live customer, compares the
simulation's FINAL grade to that customer's REAL live grade (via
customer_utils.resolve_grade — the same normalization every other
grade-analytics view uses), and persists one CustomerGradeProgress row per
vip_id so App/analytics/membership.py::get_live_customer_tier_table() can
display last_grade_change_date without re-running the simulation (which
loads the ENTIRE SalesTransaction table) on every page load.

This is a full recompute every run, not incremental — existing
CustomerGradeProgress rows are deleted and bulk-created fresh (batch_size
1000, matching the project's Customer.bulk_update convention). Triggered
manually via App/views/membership.py::compute_grade_progress(), tracked as
an upload_jobs.py job of type "grade_progress_calc".

Excludes vip_id='0' ("buyer without info") — same convention as every other
grade-analytics function in this codebase (compute_annual_spend_map,
simulate_grade_upgrade_downgrade.py, etc.).
"""
import logging
from collections import defaultdict
from datetime import date

from django.db import transaction

from App.analytics.customer_utils import _norm_vid, resolve_grade
from App.analytics.grade_simulation import load_customer_transactions, simulate_one_customer

logger = logging.getLogger(__name__)

_PROGRESS_EVERY = 2000


def compute_all_grade_progress(file=None, progress_fn=None, df=None, as_of_date=None):
    """
    file/df: accepted but ignored. This function computes purely from
    existing DB data (SalesTransaction + Customer) — there is no uploaded
    file. The signature keeps it callable as fn(file_or_none, progress_fn=...,
    df=...), exactly how App/views/upload.py::_run_upload() invokes every
    job function (`result = fn(f, progress_fn=..., df=df)`), so the existing
    generic _start_thread()/_run_upload() job-runner plumbing can launch this
    the same way as every upload job, with no bespoke thread-launch path in
    the view.

    progress_fn(processed, total), if given, is called every _PROGRESS_EVERY
    customers (and once more on the final customer) — same callback shape as
    App/upload_jobs.py::make_progress_fn().

    Returns a summary dict: {'total': int, 'ok': int, 'mismatch': int,
    'no_data': int}.
    """
    from App.models import Customer
    from App.models.membership import CustomerGradeProgress

    as_of = as_of_date or date.today()
    logger.info("compute_all_grade_progress starting as_of=%s", as_of, extra={"step": "grade_progress_calc"})

    txns_by_vip, invoices_by_vip, _invoice_log_by_vip = load_customer_transactions()

    # Normalize the SalesTransaction-side vip_id keys before joining against
    # Customer.vip_id (2026-09-02 code review finding): SalesTransaction.vip_id
    # and Customer.vip_id can differ in raw format for the same real customer
    # (whitespace, "12345.0" vs "12345") -- every OTHER grade-analytics
    # function in this module (compute_annual_spend_map, get_live_customer_
    # tier_table) already normalizes both sides via customer_utils._norm_vid()
    # for exactly this reason. Without it, a customer still affected by that
    # historical format drift would silently land in status='no_data' despite
    # having real transaction history. Normalized here at the call site
    # (rather than inside load_customer_transactions() itself) so the two
    # diagnostic commands that also call load_customer_transactions() --
    # simulate_grade_upgrade_downgrade.py and
    # validate_grade_dates_against_snapshots.py, whose 98.5%/90.5% validation
    # results were already reported to the PO using the raw join -- are left
    # unchanged; only this production code path gets the fix.
    txns_by_vip_norm = defaultdict(list)
    for vid, txns in txns_by_vip.items():
        txns_by_vip_norm[_norm_vid(vid)].extend(txns)
    invoices_by_vip_norm = defaultdict(dict)
    for vid, inv_map in invoices_by_vip.items():
        invoices_by_vip_norm[_norm_vid(vid)].update(inv_map)

    # Dedupe live customers by vip_id — Customer is unique on (vip_id, phone),
    # not vip_id alone (a vip_id can legitimately have >1 row, e.g. a
    # duplicate/blank-phone record — see simulate_grade_upgrade_downgrade.py's
    # _dump_customer docstring), but CustomerGradeProgress.vip_id is unique.
    # Keep the lowest-id row per vip_id, matching the
    # `.filter(vip_id=vid).order_by('id').first()` convention used elsewhere
    # in this codebase for the same ambiguity.
    live_grade_by_vip = {}
    for vip_id, raw_grade in (
        Customer.objects.exclude(vip_id='0').order_by('id').values_list('vip_id', 'vip_grade')
    ):
        if vip_id not in live_grade_by_vip:
            live_grade_by_vip[vip_id] = raw_grade

    total = len(live_grade_by_vip)
    summary = {'total': total, 'ok': 0, 'mismatch': 0, 'no_data': 0}
    to_create = []
    processed = 0

    for vip_id, raw_grade in live_grade_by_vip.items():
        real_grade = resolve_grade(vip_id, raw_grade)
        norm_vid = _norm_vid(vip_id)
        txns = txns_by_vip_norm.get(norm_vid)

        if not txns:
            summary['no_data'] += 1
            to_create.append(CustomerGradeProgress(
                vip_id=vip_id,
                last_grade_change_date=None,
                change_direction='',
                next_check_date=None,
                simulated_grade='',
                status='no_data',
                as_of_date=as_of,
            ))
        else:
            txns_sorted = sorted(txns, key=lambda t: t[0])
            invoice_dates = sorted(invoices_by_vip_norm.get(norm_vid, {}).values())
            simulated_grade, last_change_date, direction, next_check_date = simulate_one_customer(
                txns_sorted, invoice_dates, as_of, upgrade_window='calendar',
            )
            status = 'ok' if simulated_grade == real_grade else 'mismatch'
            summary[status] += 1
            to_create.append(CustomerGradeProgress(
                vip_id=vip_id,
                last_grade_change_date=last_change_date,
                change_direction=direction or '',
                next_check_date=next_check_date,
                simulated_grade=simulated_grade,
                status=status,
                as_of_date=as_of,
            ))

        processed += 1
        if progress_fn and (processed % _PROGRESS_EVERY == 0 or processed == total):
            progress_fn(processed, total)

    # Wrapped in a transaction (2026-09-02 code review finding): without
    # this, the delete and bulk_create are two independent autocommitted
    # statements on Postgres. If bulk_create throws partway through ~75k
    # rows (constraint violation, DB timeout, connection drop), the delete
    # has already committed -- CustomerGradeProgress is left PERMANENTLY
    # EMPTY (every customer reads back as 'not_computed') until someone
    # notices and reruns the job. Atomic makes it all-or-nothing: either the
    # full new dataset lands, or none of it does and the previous run's data
    # (stale but present) is left untouched.
    with transaction.atomic():
        CustomerGradeProgress.objects.all().delete()
        CustomerGradeProgress.objects.bulk_create(to_create, batch_size=1000)

    logger.info(
        "compute_all_grade_progress done: total=%s ok=%s mismatch=%s no_data=%s",
        summary['total'], summary['ok'], summary['mismatch'], summary['no_data'],
        extra={"step": "grade_progress_calc"},
    )
    return summary
