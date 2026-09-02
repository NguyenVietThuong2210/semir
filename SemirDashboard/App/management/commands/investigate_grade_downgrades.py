"""
App/management/commands/investigate_grade_downgrades.py

READ-ONLY investigation script. Writes nothing to the database — no
.save()/.create()/.update()/.delete() calls anywhere in this file. Safe to
run directly against PROD.

Context (2026-09-02): the PO observed on PROD (/membership/?from_batch=3&to_
batch=4, real Jan-2026 -> Feb-2026 auto-snapshots) that a large number of
customers show a REAL recorded downgrade between the two batches. This is
notable because App/analytics/calculations.py's GRADE_DOWNGRADE_MIN_ANNUAL_
PURCHASES thresholds are documented as "informational only, not enforced" by
this app -- vip_grade always comes from the external POS system via the
uploaded file, never computed/written by this Django app. So a real
downgrade appearing between two consecutive snapshots means the EXTERNAL POS
system itself changed the customer's grade -- this command investigates
whether that external change correlates with a drop in computed spend
(the same locked GRADE_UPGRADE_THRESHOLDS this app already uses elsewhere),
which would suggest the external system evaluates roughly the same way this
app already assumes.

TWO spend windows are computed and reported side by side, deliberately:
  - "calendar-YTD" — Jan 1 of the snapshot's year through the snapshot date
    (compute_annual_spend_map()'s exact existing formula).
  - "rolling-365d" — the 365 days immediately BEFORE the snapshot date.
A batch pair like Jan-1-2026 -> Feb-1-2026 straddles a calendar-year
boundary right at the FROM side: calendar-YTD spend as of Jan 1 is ~0 for
almost everyone (it's the very first day of the year), which would make the
calendar-YTD comparison look like "everyone's spend dropped to zero" without
actually explaining anything about why they held their PRE-Jan-1 grade in
the first place. The rolling-365d window doesn't have this artifact (it
looks back a full year regardless of where the snapshot falls in the
calendar), so it's the more informative comparison for snapshot pairs taken
near a Jan-1 boundary specifically. Both are reported so the reader isn't
stuck guessing which one applies.

Prior local-only validation this session (dev fixture data, NOT this PROD
data) found the calendar-year-to-date crossing formula agrees with real
recorded grades ~97.6% of the time on backfilled Nov/Dec-2025 data, on a
batch pair NOT straddling a Jan-1 boundary. This command is deliberately
built to be run on the REAL PROD dataset instead, since local dev data does
not reflect PROD's actual customer/sales history.

Usage (on PROD):
    docker compose exec web python manage.py investigate_grade_downgrades --from-batch 3 --to-batch 4

Output is aggregate statistics + a small sample of vip_id/amounts only --
no customer name or phone number is read or printed anywhere in this file,
to minimize PII exposure when the output is copy-pasted back for review.
"""
from collections import defaultdict
from datetime import timedelta
from decimal import Decimal

from django.core.management.base import BaseCommand, CommandError
from django.db.models import Sum

from App.analytics.calculations import GRADE_UPGRADE_THRESHOLDS
from App.analytics.membership import compute_annual_spend_map, get_grade_changes


def _rolling_spend_map(as_of_date):
    """dict[vip_id] -> Decimal spend in the 365 days ending at as_of_date
    (inclusive). Mirrors compute_annual_spend_map()'s query shape/footguns
    (.order_by() before .values()/.annotate() to clear Meta.ordering) but
    with a rolling window instead of a calendar-year one."""
    from App.models import SalesTransaction

    window_start = as_of_date - timedelta(days=365)
    rows = (
        SalesTransaction.objects
        .filter(sales_date__gte=window_start, sales_date__lte=as_of_date)
        .exclude(vip_id__isnull=True).exclude(vip_id='').exclude(vip_id='0')
        .order_by()
        .values('vip_id')
        .annotate(spend=Sum('settlement_amount'))
    )
    return {r['vip_id']: (r['spend'] or Decimal('0')) for r in rows}


class Command(BaseCommand):
    help = "READ-ONLY: investigate whether real downgrades between two batches correlate with a computed spend drop"

    def add_arguments(self, parser):
        parser.add_argument("--from-batch", type=int, required=True, help="From MembershipSnapshotBatch id")
        parser.add_argument("--to-batch", type=int, required=True, help="To MembershipSnapshotBatch id")
        parser.add_argument("--sample-size", type=int, default=15, help="How many sample rows to print per bucket")

    def handle(self, *args, **options):
        from App.models.membership import MembershipSnapshotBatch

        from_id, to_id = options["from_batch"], options["to_batch"]
        sample_size = options["sample_size"]

        try:
            from_batch = MembershipSnapshotBatch.objects.get(pk=from_id)
            to_batch = MembershipSnapshotBatch.objects.get(pk=to_id)
        except MembershipSnapshotBatch.DoesNotExist as e:
            raise CommandError(str(e))

        self.stdout.write("=" * 70)
        self.stdout.write("investigate_grade_downgrades — READ ONLY, no writes")
        self.stdout.write(
            f"From batch {from_batch.id}: {from_batch.snapshot_date} ({from_batch.source}, {from_batch.row_count} rows)"
        )
        self.stdout.write(
            f"To batch   {to_batch.id}: {to_batch.snapshot_date} ({to_batch.source}, {to_batch.row_count} rows)"
        )
        self.stdout.write("=" * 70)

        rows, total_count = get_grade_changes(from_id, to_id, direction="downgrade", limit=None)
        self.stdout.write(f"\nReal recorded downgrades between these two batches: {total_count}")
        if not total_count:
            self.stdout.write("Nothing to investigate.")
            return

        by_transition = {}
        for r in rows:
            key = f"{r['from_grade']} -> {r['to_grade']}"
            by_transition[key] = by_transition.get(key, 0) + 1
        self.stdout.write("\nBreakdown by transition type:")
        for key, count in sorted(by_transition.items(), key=lambda x: -x[1]):
            self.stdout.write(f"  {key}: {count}")

        self.stdout.write("\nComputing spend windows (this may take a moment)...")
        cal_from = compute_annual_spend_map(from_batch.snapshot_date)
        cal_to = compute_annual_spend_map(to_batch.snapshot_date)
        roll_from = _rolling_spend_map(from_batch.snapshot_date)
        roll_to = _rolling_spend_map(to_batch.snapshot_date)

        def _bucket_by_delta(get_from, get_to):
            buckets = defaultdict(list)
            for r in rows:
                vid = r["vip_id"]
                f, t = get_from(vid), get_to(vid)
                rec = {**r, "from_spend": f, "to_spend": t}
                if f == 0 and t == 0:
                    buckets["no_data"].append(rec)
                elif t == 0 and f > 0:
                    buckets["dropped_to_zero"].append(rec)
                elif t < f:
                    buckets["dropped_partial"].append(rec)
                else:
                    buckets["flat_or_up"].append(rec)
            return buckets

        cal_buckets = _bucket_by_delta(
            lambda v: cal_from.get(v, {}).get("annual_spend", Decimal("0")),
            lambda v: cal_to.get(v, {}).get("annual_spend", Decimal("0")),
        )
        roll_buckets = _bucket_by_delta(
            lambda v: roll_from.get(v, Decimal("0")),
            lambda v: roll_to.get(v, Decimal("0")),
        )

        n = total_count
        for title, buckets in [
            ("CALENDAR-YEAR-TO-DATE (Jan 1 -> snapshot date, each batch's own year)", cal_buckets),
            ("ROLLING 365 DAYS (ending at snapshot date)", roll_buckets),
        ]:
            self.stdout.write("\n" + "=" * 70)
            self.stdout.write(f"RESULTS — {title}")
            self.stdout.write("=" * 70)
            dz, dp, fu, nd = (
                buckets["dropped_to_zero"], buckets["dropped_partial"],
                buckets["flat_or_up"], buckets["no_data"],
            )
            self.stdout.write(f"Spend dropped to ZERO (stopped buying entirely): {len(dz)}/{n} ({100*len(dz)/n:.1f}%)")
            self.stdout.write(f"Spend dropped but still buying something:        {len(dp)}/{n} ({100*len(dp)/n:.1f}%)")
            self.stdout.write(f"Spend FLAT or INCREASED despite the downgrade:   {len(fu)}/{n} ({100*len(fu)/n:.1f}%)  <-- most interesting bucket")
            self.stdout.write(f"No SalesTransaction data at all in either window:{len(nd)}/{n} ({100*len(nd)/n:.1f}%)")

            for label, bucket in [
                ("SPEND FLAT OR INCREASED (unexplained by spend)", fu),
                ("SPEND DROPPED (still buying)", dp),
            ]:
                self.stdout.write(f"\n  Sample: {label}, up to {sample_size}:")
                for rec in bucket[:sample_size]:
                    self.stdout.write(
                        f"    {rec['vip_id']}: real {rec['from_grade']}->{rec['to_grade']}"
                        f" | spend {rec['from_spend']} -> {rec['to_spend']}"
                    )

        self.stdout.write("\nDONE (read-only, nothing was written to the database)")
