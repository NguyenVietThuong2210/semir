"""
App/management/commands/simulate_grade_upgrade_downgrade.py

READ-ONLY simulation. Writes nothing to the database — no
.save()/.create()/.update()/.delete() calls anywhere in this file. Safe to
run directly against PROD.

Context (2026-09-02, PO): a single point-in-time spend-vs-grade check isn't
a real test of the upgrade/downgrade FORMULA — the real test is: run a full
chronological simulation of grade changes from the earliest available
SalesTransaction data through to TODAY, applying the locked upgrade rule and
a hypothesized downgrade rule at every step, and see whether the FINAL
simulated grade matches each customer's CURRENT REAL grade in the live
Customer table. PO explicitly said to ignore MembershipSnapshotBatch
entirely for this check -- compare only against Customer.vip_grade (live).

Algorithm (monthly-stepped simulation, one pass per calendar month from the
earliest SalesTransaction month through the current month):
  1. UPGRADE pass — for every vip_id, compute calendar-year-to-date spend as
     of this month's last day (same locked GRADE_UPGRADE_THRESHOLDS formula
     App/analytics/calculations.py already defines: Silver >= 6,000,000 /
     Gold >= 12,000,000 / Diamond >= 20,000,000). If that implies a HIGHER
     grade than the customer's current simulated grade, upgrade immediately
     (can skip tiers in one step, e.g. Member straight to Gold on a single
     large purchase -- matches the locked rule's plain reading, no "must
     pass through Silver first" language exists anywhere in the locked
     rules).
  2. DOWNGRADE pass — for every vip_id currently above Member in the
     simulation, count DISTINCT invoices in the trailing 365 days ending at
     this month's last day. If below GRADE_DOWNGRADE_MIN_ANNUAL_PURCHASES
     for their CURRENT simulated grade, downgrade exactly one tier.
     This is a simplification of the locked rule's literal wording ("within
     1 year of the customer's LAST GRADE-CHANGE date" -- a per-customer
     rolling anniversary) down to "check everyone on a fixed monthly
     cadence, using a trailing-365-day window ending at that checkpoint"
     -- chosen because (a) it matches the OBSERVED monthly auto-snapshot
     cadence in this system, and (b) checking monthly is frequent enough
     relative to a 365-day window that the two approaches should rarely
     diverge in their end state. If PROD results show this doesn't match
     well, the per-customer-anniversary version is the natural next
     refinement to try.
  3. A customer never seen before (no prior simulated grade) starts at
     'Member' the first month they appear with any transaction -- the
     UPGRADE pass in that same month-step then immediately raises them if
     their spend already qualifies. No downgrade check applies to a
     customer's very first appearance.

At the end, the simulated grade for every vip_id is compared against
Customer.vip_grade (run through the exact same resolve_grade() normalization
App/services/membership_snapshot.py already uses for consistency), and an
agreement rate + confusion matrix + samples are printed.

Usage (on PROD):
    docker compose exec web python manage.py simulate_grade_upgrade_downgrade
    docker compose exec web python manage.py simulate_grade_upgrade_downgrade --as-of 2026-08-31

Output is aggregate statistics + a small sample of vip_id/amounts only --
no customer name or phone number is read or printed anywhere in this file.
"""
from collections import defaultdict
from datetime import date, timedelta
from decimal import Decimal

from dateutil.relativedelta import relativedelta
from django.core.management.base import BaseCommand
from django.db.models import Count, Sum

from App.analytics.calculations import GRADE_UPGRADE_THRESHOLDS, GRADE_DOWNGRADE_MIN_ANNUAL_PURCHASES
from App.analytics.customer_utils import GRADE_ORDER, resolve_grade

GRADE_RANK = {g: i for i, g in enumerate(['Member', 'Silver', 'Gold', 'Diamond'])}
RANK_TO_GRADE = {i: g for g, i in GRADE_RANK.items()}


def _grade_for_spend(spend):
    if spend >= GRADE_UPGRADE_THRESHOLDS['Diamond']:
        return 'Diamond'
    if spend >= GRADE_UPGRADE_THRESHOLDS['Gold']:
        return 'Gold'
    if spend >= GRADE_UPGRADE_THRESHOLDS['Silver']:
        return 'Silver'
    return 'Member'


def _month_ends(start_date, end_date):
    """Yield the last calendar day of every month from start_date's month
    through end_date's month (inclusive), e.g. 2025-01-31, 2025-02-28, ..."""
    cur = date(start_date.year, start_date.month, 1)
    while cur <= end_date:
        next_month = cur + relativedelta(months=1)
        month_end = next_month - timedelta(days=1)
        yield min(month_end, end_date)
        cur = next_month


class Command(BaseCommand):
    help = "READ-ONLY: simulate grade upgrade/downgrade month-by-month from earliest sales data to today, compare to live Customer.vip_grade"

    def add_arguments(self, parser):
        parser.add_argument("--as-of", type=str, default=None, help="Simulate through this date (YYYY-MM-DD). Default: today.")
        parser.add_argument("--sample-size", type=int, default=15)

    def handle(self, *args, **options):
        from App.models import Customer, SalesTransaction

        as_of = date.fromisoformat(options["as_of"]) if options["as_of"] else date.today()

        earliest = SalesTransaction.objects.order_by('sales_date').values_list('sales_date', flat=True).first()
        latest = SalesTransaction.objects.order_by('-sales_date').values_list('sales_date', flat=True).first()
        if not earliest:
            self.stdout.write("No SalesTransaction rows found -- nothing to simulate.")
            return

        self.stdout.write("=" * 70)
        self.stdout.write("simulate_grade_upgrade_downgrade — READ ONLY, no writes")
        self.stdout.write(f"SalesTransaction date range: {earliest} -> {latest}")
        self.stdout.write(f"Simulating month-by-month through: {as_of}")
        self.stdout.write("=" * 70)

        sim_grade = {}  # vip_id -> current simulated grade (str)
        checkpoints = list(_month_ends(earliest, as_of))
        self.stdout.write(f"\n{len(checkpoints)} monthly checkpoints to process...")

        for i, checkpoint in enumerate(checkpoints):
            year_start = checkpoint.replace(month=1, day=1)
            window_start = checkpoint - timedelta(days=365)

            # --- UPGRADE pass: calendar-YTD spend as of this checkpoint ---
            ytd_rows = (
                SalesTransaction.objects
                .filter(sales_date__gte=year_start, sales_date__lte=checkpoint)
                .exclude(vip_id__isnull=True).exclude(vip_id='').exclude(vip_id='0')
                .order_by()
                .values('vip_id')
                .annotate(spend=Sum('settlement_amount'))
            )
            for r in ytd_rows:
                vid = r['vip_id']
                implied = _grade_for_spend(r['spend'] or Decimal('0'))
                current = sim_grade.get(vid, 'Member')
                if GRADE_RANK[implied] > GRADE_RANK[current]:
                    sim_grade[vid] = implied

            # --- DOWNGRADE pass: rolling 365-day purchase count as of this checkpoint ---
            above_member = [vid for vid, g in sim_grade.items() if g != 'Member']
            if above_member:
                roll_rows = (
                    SalesTransaction.objects
                    .filter(sales_date__gte=window_start, sales_date__lte=checkpoint, vip_id__in=above_member)
                    .order_by()
                    .values('vip_id')
                    .annotate(cnt=Count('invoice_number', distinct=True))
                )
                purchase_count = {r['vip_id']: r['cnt'] for r in roll_rows}
                for vid in above_member:
                    current = sim_grade[vid]
                    min_required = GRADE_DOWNGRADE_MIN_ANNUAL_PURCHASES.get(current)
                    if min_required is not None and purchase_count.get(vid, 0) < min_required:
                        sim_grade[vid] = RANK_TO_GRADE[GRADE_RANK[current] - 1]

            if (i + 1) % 6 == 0 or i == len(checkpoints) - 1:
                self.stdout.write(f"  ...processed {i+1}/{len(checkpoints)} checkpoints (through {checkpoint})")

        self.stdout.write(f"\nSimulation complete. {len(sim_grade)} distinct vip_ids have a simulated grade.")

        # --- Compare final simulated grade against live Customer.vip_grade ---
        self.stdout.write("\nComparing against live Customer.vip_grade...")
        live_rows = Customer.objects.exclude(vip_id='0').values_list('vip_id', 'vip_grade')
        agree = 0
        disagree = 0
        checked = 0
        confusion = defaultdict(int)
        sample_agree = []
        sample_disagree = []

        for vip_id, raw_grade in live_rows:
            real_grade = resolve_grade(vip_id, raw_grade)
            if real_grade not in GRADE_RANK:
                continue  # 'No Grade' or unrecognized -- not part of this formula's scope
            simulated = sim_grade.get(vip_id, 'Member')
            checked += 1
            confusion[(real_grade, simulated)] += 1
            if simulated == real_grade:
                agree += 1
                if len(sample_agree) < options["sample_size"]:
                    sample_agree.append((vip_id, real_grade))
            else:
                disagree += 1
                if len(sample_disagree) < options["sample_size"]:
                    sample_disagree.append((vip_id, real_grade, simulated))

        self.stdout.write("\n" + "=" * 70)
        self.stdout.write("RESULTS")
        self.stdout.write("=" * 70)
        self.stdout.write(f"Checked {checked} live customers with a real Member/Silver/Gold/Diamond grade")
        self.stdout.write(f"Agree:    {agree} ({100*agree/checked:.1f}%)")
        self.stdout.write(f"Disagree: {disagree} ({100*disagree/checked:.1f}%)")

        self.stdout.write("\nConfusion matrix (real -> simulated): count")
        for (real, sim), c in sorted(confusion.items(), key=lambda x: -x[1]):
            self.stdout.write(f"  {real:8s} -> {sim:8s} : {c}")

        self.stdout.write(f"\nSample AGREEING (up to {options['sample_size']}):")
        for vid, grade in sample_agree:
            self.stdout.write(f"  {vid}: grade={grade}")

        self.stdout.write(f"\nSample DISAGREEING (up to {options['sample_size']}):")
        for vid, real, sim in sample_disagree:
            self.stdout.write(f"  {vid}: real={real} simulated={sim}")

        self.stdout.write("\nDONE (read-only, nothing was written to the database)")
