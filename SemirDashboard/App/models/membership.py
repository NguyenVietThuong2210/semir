from django.conf import settings
from django.db import models


class MembershipSnapshotBatch(models.Model):
    """One row per snapshot event. `snapshot_date` is the as-of date used for
    the annual-spend calendar-year window (Jan 1 of snapshot_date.year through
    snapshot_date inclusive).

    Redesigned 2026-09-01 (PO request, storage/performance): used to be a
    header row with a `MembershipSnapshot` child row PER CUSTOMER (100k
    customers = 100k child rows per batch). Measured on real data: 267
    bytes/row, and a query touching ALL batches (the trend chart) degraded to
    a full Sequential Scan once total rows got large — extrapolated ~60s to
    load the trend chart after 5 years of daily snapshots at 100k customers,
    even after fixing an N+1 query pattern. Replaced with two JSON fields
    directly on this model — see their docstrings below. `MembershipSnapshot`
    (the old per-customer child model) no longer exists; see migration 0024
    for the one-time lossless conversion of pre-existing rows.
    """

    SOURCE_CHOICES = [
        ("auto", "Automatic"),
        ("manual_import", "Manual Backfill Import"),
    ]

    snapshot_date = models.DateField(db_index=True)
    source = models.CharField(max_length=20, choices=SOURCE_CHOICES, db_index=True)
    created_at = models.DateTimeField(auto_now_add=True)
    uploaded_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="membership_batches",
    )
    source_filename = models.CharField(max_length=255, blank=True)
    note = models.TextField(blank=True)
    row_count = models.IntegerField(default=0)

    grade_counts = models.JSONField(default=dict, blank=True, help_text=(
        "Small (a few KB). {'overall': {grade: count}, 'by_store': "
        "{store: {grade: count}}}. Keyed by all 5 grades including 'No "
        "Grade'. Read by every list/chart view (get_grade_breakdown, "
        "get_grade_breakdown_by_store, get_all_batch_grade_series) via "
        "`.values('grade_counts')` — deliberately never joined with a read "
        "of grade_members, so the trend chart's one-query-per-page-load "
        "stays a few KB regardless of batch count or customer count."
    ))
    grade_members = models.JSONField(default=dict, blank=True, help_text=(
        "Large (~1-2MB at 100k customers). Same shape as grade_counts but "
        "lists of vip_id instead of counts: {'overall': {grade: [vip_id, "
        "...]}, 'by_store': {store: {grade: [vip_id, ...]}}}. Read ONLY by "
        "get_grade_changes() (the grade-change diff feature), always exactly "
        "2 batches at a time — never read for the trend chart/breakdown/"
        "comparison views, which use grade_counts instead."
    ))

    class Meta:
        indexes = [
            models.Index(fields=["source", "snapshot_date"]),
        ]
        ordering = ["-snapshot_date", "-created_at"]

    def __str__(self):
        return f"{self.snapshot_date} ({self.source}) — {self.row_count} rows"


class CustomerGradeProgress(models.Model):
    """
    One row per vip_id — the last-computed result of the full-DB grade
    upgrade/downgrade DATE simulation (App/analytics/grade_simulation.py),
    persisted so App/analytics/membership.py::get_live_customer_tier_table()
    can display it without re-running the simulation on every page load (the
    simulation loads ALL of SalesTransaction — expensive; the "Customer Tier
    Progress" table page-loads by design, see that function's docstring).

    Written ONLY by App/services/grade_progress_calc.py::compute_all_grade_progress()
    (full recompute, deletes+bulk_creates every run — no incremental update).
    Triggered manually via App/views/membership.py::compute_grade_progress()
    (permission membership.compute), tracked as an upload_jobs.py job of type
    "grade_progress_calc" — same async-job pattern as every other long-running
    computation in this codebase (see App/views/upload.py::_start_thread).

    status distinguishes WHY last_grade_change_date may or may not be
    trustworthy for a given customer:
      - 'ok': the simulation's final grade matches the customer's REAL live
        grade (Customer.vip_grade via resolve_grade()) — last_grade_change_date
        is shown to the user.
      - 'mismatch': this vip_id has transaction history but the simulation's
        final grade does NOT match the real live grade — the formula's answer
        is not trustworthy for this customer, so the UI layer
        (get_live_customer_tier_table()) hides last_grade_change_date/
        change_direction even though a value is stored here (kept for
        debugging, e.g. via the Django admin or a future diagnostic command).
      - 'no_data': this vip_id has zero SalesTransaction rows — there is
        nothing to simulate from.
    """
    vip_id = models.CharField(max_length=1000, unique=True, db_index=True)
    last_grade_change_date = models.DateField(null=True, blank=True)
    change_direction = models.CharField(
        max_length=10,
        choices=[("upgrade", "Upgrade"), ("downgrade", "Downgrade")],
        blank=True,
    )
    next_check_date = models.DateField(
        null=True, blank=True,
        help_text=(
            "The customer's NEXT scheduled downgrade anniversary check date "
            "(App/analytics/grade_simulation.py's simulate_one_customer() 4th "
            "return value, next_check_date). NULL when current_grade is "
            "Member/No Grade (no downgrade floor to check). NOT simply "
            "last_grade_change_date + 365 days -- a customer who has passed "
            "one or more prior annual checks without an actual grade change "
            "has next_check_date further out than that, since the check "
            "recurs every 365 days from the LAST CHECK, not the last change. "
            "Used to compute 'purchases needed to avoid downgrade' against "
            "the customer's TRUE upcoming check window, and shown directly "
            "in the Customer Tier Progress table as the expected downgrade "
            "review date."
        ),
    )
    simulated_grade = models.CharField(max_length=20, blank=True)
    status = models.CharField(
        max_length=20,
        choices=[("ok", "OK"), ("mismatch", "Formula Mismatch"), ("no_data", "No Transaction Data")],
        db_index=True,
    )
    computed_at = models.DateTimeField(auto_now=True)
    as_of_date = models.DateField()

    class Meta:
        indexes = [
            models.Index(fields=["status"]),
        ]

    def __str__(self):
        return f"{self.vip_id}: {self.status} ({self.simulated_grade})"
