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
