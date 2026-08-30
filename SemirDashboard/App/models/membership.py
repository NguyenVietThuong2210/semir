from django.conf import settings
from django.db import models


class MembershipSnapshotBatch(models.Model):
    """One row per snapshot event. `snapshot_date` is the as-of date used for
    the annual-spend calendar-year window (Jan 1 of snapshot_date.year through
    snapshot_date inclusive)."""

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

    class Meta:
        indexes = [
            models.Index(fields=["source", "snapshot_date"]),
        ]
        ordering = ["-snapshot_date", "-created_at"]

    def __str__(self):
        return f"{self.snapshot_date} ({self.source}) — {self.row_count} rows"


class MembershipSnapshot(models.Model):
    """One row per customer per batch. Lean, denormalized — a reporting table,
    not a hot path.

    `grade_changed_at` is always NULL today: no source data (Customer model,
    imported customer files) contains a date of last grade change anywhere.
    PO decision (confirmed 2026-08-14): leave it blank rather than synthesize
    a proxy date; backfill later if a real source becomes available.
    """

    batch = models.ForeignKey(
        MembershipSnapshotBatch, on_delete=models.CASCADE, related_name="snapshots"
    )
    vip_id = models.CharField(max_length=1000)
    phone = models.CharField(max_length=1000, blank=True)
    name = models.CharField(max_length=1000, blank=True)
    grade = models.CharField(max_length=20)
    registration_date = models.DateField(null=True, blank=True)
    registration_store = models.CharField(max_length=1000, blank=True)
    annual_spend = models.DecimalField(max_digits=14, decimal_places=2, default=0)
    annual_purchase_count = models.IntegerField(default=0)
    points = models.IntegerField(default=0)
    grade_changed_at = models.DateField(null=True, blank=True)

    class Meta:
        unique_together = ("batch", "vip_id", "phone")
        indexes = [
            models.Index(fields=["batch", "grade"]),
            models.Index(fields=["vip_id"]),
            models.Index(fields=["batch", "registration_store"]),
        ]

    def __str__(self):
        return f"{self.vip_id} @ batch {self.batch_id} = {self.grade}"
