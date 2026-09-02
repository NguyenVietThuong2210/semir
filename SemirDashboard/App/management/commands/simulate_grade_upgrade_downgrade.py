"""
App/management/commands/simulate_grade_upgrade_downgrade.py

READ-ONLY simulation. Writes nothing to the database — no
.save()/.create()/.update()/.delete() calls anywhere in this file. Safe to
run directly against PROD.

Context (2026-09-02, PO): the goal is to reconstruct the upgrade/downgrade
DATE the external POS system doesn't expose, using only SalesTransaction +
Customer data and the already-LOCKED grade rules. The real test of whether
the reconstruction is trustworthy: run a full chronological, PER-CUSTOMER,
EXACT-DATE simulation from that customer's first transaction through today,
and check whether the FINAL simulated grade matches their CURRENT REAL grade
in the live Customer table (MembershipSnapshotBatch is intentionally not
used anywhere in this file, per PO instruction — compare only against
Customer.vip_grade). For a snapshot-based temporal-precision cross-check
instead, see validate_grade_dates_against_snapshots.py.

The simulation algorithm itself (PO's worked example, event-timeline
description, upgrade/downgrade mechanics) now lives in
App/analytics/grade_simulation.py — read that module's docstring for the
full algorithm. This command is a thin CLI wrapper: load all transactions,
run the shared simulate_one_customer() per customer, compare to live
Customer.vip_grade, and report aggregate/diagnostic statistics.

Usage (on PROD):
    docker compose exec web python manage.py simulate_grade_upgrade_downgrade
    docker compose exec web python manage.py simulate_grade_upgrade_downgrade --as-of 2026-08-31
    docker compose exec web python manage.py simulate_grade_upgrade_downgrade --vip-id 1460606   # trace one customer's full event log
    docker compose exec web python manage.py simulate_grade_upgrade_downgrade --samples-per-bucket 5

Output is aggregate statistics for the LOCKED calendar-year upgrade rule, a
side-by-side A/B comparison against a diagnostic-only rolling-365-day upgrade
variant (added 2026-09-02 after real PROD data showed customers whose spend
straddles a Jan-1 boundary never crossing a calendar-year threshold despite
having an elevated real grade -- see UPGRADE-WINDOW A/B section), a
recency-bucketed breakdown of calendar-rule disagreements, and — per bucket —
a handful of sample customers dumped with their FULL raw invoice log (date,
invoice_number, settlement_amount) plus both simulators' event traces, so a
disagreement can be root-caused from actual transaction data instead of
guessed from a bucket label alone. The rolling variant is diagnostic evidence
only -- it does not change the locked rule anywhere else in the app unless
the PO explicitly approves switching it. Only vip_id/dates/invoice_number/
amounts are ever read or printed anywhere in this file — no customer name or
phone number.
"""
from collections import defaultdict
from datetime import date

from django.core.management.base import BaseCommand

from App.analytics.customer_utils import resolve_grade
from App.analytics.grade_simulation import GRADE_RANK, simulate_one_customer

# Note: the simulation algorithm itself (simulate_one_customer, GRADE_RANK,
# etc.) was extracted 2026-09-02 into App/analytics/grade_simulation.py so
# this command and App/management/commands/validate_grade_dates_against_snapshots.py
# both run the exact same validated logic. See that module's docstring for
# the full algorithm description and the PO's worked example.


class Command(BaseCommand):
    help = "READ-ONLY: exact-date per-customer simulation of grade upgrade/downgrade from first purchase to today, vs live Customer.vip_grade"

    def add_arguments(self, parser):
        parser.add_argument("--as-of", type=str, default=None, help="Simulate through this date (YYYY-MM-DD). Default: today.")
        parser.add_argument("--sample-size", type=int, default=15)
        parser.add_argument("--vip-id", type=str, default=None, help="Print the full event trace for just this one vip_id and exit (no aggregate stats).")
        parser.add_argument("--samples-per-bucket", type=int, default=3, help="How many customers' full invoice log + trace to dump per recency bucket.")

    def handle(self, *args, **options):
        from App.analytics.grade_simulation import load_customer_transactions
        from App.models import Customer

        as_of = date.fromisoformat(options["as_of"]) if options["as_of"] else date.today()

        self.stdout.write("=" * 70)
        self.stdout.write("simulate_grade_upgrade_downgrade — READ ONLY, no writes")
        self.stdout.write(f"Simulating through: {as_of}")
        self.stdout.write("=" * 70)

        self.stdout.write("\nLoading SalesTransaction rows (this may take a moment)...")
        txns_by_vip, invoices_by_vip, invoice_log_by_vip = load_customer_transactions()
        row_count = sum(len(v) for v in txns_by_vip.values())
        self.stdout.write(f"  {row_count} rows loaded, covering {len(txns_by_vip)} distinct vip_ids")

        def _dump_customer(vid, real_grade=None):
            """Print registration_date + full raw invoice log + simulator trace (both
            upgrade_window variants, for direct comparison) for one vip_id.
            Customer is unique on (vip_id, phone), not vip_id alone (App/models/pos.py) -- a vip_id
            can legitimately have >1 row (e.g. a duplicate/blank-phone record), so this uses
            .filter().first() rather than .get() to avoid crashing mid-run on MultipleObjectsReturned."""
            cust = Customer.objects.filter(vip_id=vid).order_by('id').first()
            reg_date = cust.registration_date if cust else None
            self.stdout.write(f"  registration_date={reg_date}")
            rows = sorted(invoice_log_by_vip.get(vid, []), key=lambda r: r[0])
            self.stdout.write(f"  raw invoices ({len(rows)} line items):")
            for d, inv_no, amt in rows:
                self.stdout.write(f"    {d}  invoice={inv_no!r}  amount={amt}")
            txns = sorted(txns_by_vip.get(vid, []), key=lambda t: t[0])
            invoice_dates = sorted(invoices_by_vip.get(vid, {}).values())
            for label, window in [("CALENDAR-YEAR (locked rule)", "calendar"), ("ROLLING-365-DAY (diagnostic A/B)", "rolling")]:
                trace = []
                final_grade, last_change, _direction, _next_check = simulate_one_customer(txns, invoice_dates, as_of, trace=trace, upgrade_window=window)
                self.stdout.write(f"  --- {label} ---")
                for line in trace:
                    self.stdout.write(f"    {line}")
                self.stdout.write(f"  final simulated grade={final_grade}  last_grade_change={last_change}")
            if real_grade is not None:
                self.stdout.write(f"  real live grade={real_grade}")

        if options["vip_id"]:
            vid = options["vip_id"]
            cust = Customer.objects.filter(vip_id=vid).order_by('id').first()
            if cust:
                real_grade = f"{resolve_grade(vid, cust.vip_grade)} (raw: {cust.vip_grade!r})"
            else:
                real_grade = "(vip_id not found in live Customer table)"
            self.stdout.write(f"\n=== vip_id={vid} ===")
            _dump_customer(vid, real_grade=real_grade)
            return

        self.stdout.write("\nRunning per-customer simulation (calendar-year + rolling-365-day, for A/B comparison)...")
        sim_grade = {}
        sim_last_change = {}
        sim_grade_roll = {}
        processed = 0
        for vid, txns in txns_by_vip.items():
            txns.sort(key=lambda t: t[0])
            invoice_dates = sorted(invoices_by_vip[vid].values())
            grade, last_change, _direction, _next_check = simulate_one_customer(txns, invoice_dates, as_of, upgrade_window='calendar')
            sim_grade[vid] = grade
            sim_last_change[vid] = last_change
            grade_roll, _, _direction_roll, _next_check_roll = simulate_one_customer(txns, invoice_dates, as_of, upgrade_window='rolling')
            sim_grade_roll[vid] = grade_roll
            processed += 1
            if processed % 10000 == 0:
                self.stdout.write(f"  ...simulated {processed}/{len(txns_by_vip)} customers")

        self.stdout.write(f"Simulation complete for {len(sim_grade)} customers with transaction history.")

        self.stdout.write("\nComparing against live Customer.vip_grade...")
        live_rows = Customer.objects.exclude(vip_id='0').values_list('vip_id', 'vip_grade')
        agree = disagree = checked = 0
        confusion = defaultdict(int)
        sample_agree, sample_disagree = [], []

        # Recency-of-disagreement analysis (2026-09-02 follow-up): if most
        # disagreements have a simulated_last_change very close to as_of,
        # that's evidence of a REPORTING LAG between when the real POS
        # system actually changes a grade and when that change shows up in
        # the uploaded Customer file this app reads -- rather than the
        # downgrade/upgrade RULE itself being wrong. Bucketed alongside the
        # main agree/disagree pass (one query, not two) by how many days ago
        # each disagreement's simulated_last_change was, relative to as_of.
        recency_buckets = {
            "0-30 days ago": 0, "31-60 days ago": 0, "61-90 days ago": 0,
            "91-180 days ago": 0, "181-365 days ago": 0, "over 365 days ago": 0,
            "no simulated change (never upgraded in simulation)": 0,
        }
        bucket_samples = defaultdict(list)  # bucket label -> [(vip_id, real_grade, simulated)], capped
        samples_per_bucket = options["samples_per_bucket"]
        lower_count = higher_count = 0  # simulated < real vs simulated > real, by rank

        # Rolling-window (diagnostic) A/B tally, computed alongside the primary
        # calendar-year pass so both come from the exact same customer set in
        # one run. swing_to_agree = disagreed under calendar but agrees under
        # rolling (evidence FOR switching); swing_to_disagree = the reverse
        # (evidence AGAINST). Net negative swing_to_disagree with a large
        # positive swing_to_agree is the signal the PO asked to test for.
        roll_agree = roll_disagree = 0
        roll_confusion = defaultdict(int)
        swing_to_agree = swing_to_disagree = 0

        def _recency_bucket(last_change):
            if last_change is None:
                return "no simulated change (never upgraded in simulation)"
            days_ago = (as_of - last_change).days
            if days_ago <= 30:
                return "0-30 days ago"
            if days_ago <= 60:
                return "31-60 days ago"
            if days_ago <= 90:
                return "61-90 days ago"
            if days_ago <= 180:
                return "91-180 days ago"
            if days_ago <= 365:
                return "181-365 days ago"
            return "over 365 days ago"

        for vip_id, raw_grade in live_rows:
            real_grade = resolve_grade(vip_id, raw_grade)
            if real_grade not in GRADE_RANK:
                continue
            simulated = sim_grade.get(vip_id, 'Member')
            checked += 1
            confusion[(real_grade, simulated)] += 1
            calendar_agrees = simulated == real_grade
            if calendar_agrees:
                agree += 1
                if len(sample_agree) < options["sample_size"]:
                    sample_agree.append((vip_id, real_grade, sim_last_change.get(vip_id)))
            else:
                disagree += 1
                if len(sample_disagree) < options["sample_size"]:
                    sample_disagree.append((vip_id, real_grade, simulated, sim_last_change.get(vip_id)))

                last_change = sim_last_change.get(vip_id)
                bucket = _recency_bucket(last_change)
                recency_buckets[bucket] += 1
                if len(bucket_samples[bucket]) < samples_per_bucket:
                    bucket_samples[bucket].append((vip_id, real_grade, simulated))
                if GRADE_RANK[simulated] < GRADE_RANK[real_grade]:
                    lower_count += 1
                else:
                    higher_count += 1

            simulated_roll = sim_grade_roll.get(vip_id, 'Member')
            roll_confusion[(real_grade, simulated_roll)] += 1
            rolling_agrees = simulated_roll == real_grade
            if rolling_agrees:
                roll_agree += 1
            else:
                roll_disagree += 1
            if calendar_agrees and not rolling_agrees:
                swing_to_disagree += 1
            elif not calendar_agrees and rolling_agrees:
                swing_to_agree += 1

        self.stdout.write("\n" + "=" * 70)
        self.stdout.write("RESULTS")
        self.stdout.write("=" * 70)
        self.stdout.write(f"Checked {checked} live customers with a real Member/Silver/Gold/Diamond grade")
        self.stdout.write(f"Agree:    {agree} ({100*agree/checked:.1f}%)")
        self.stdout.write(f"Disagree: {disagree} ({100*disagree/checked:.1f}%)")

        self.stdout.write("\nConfusion matrix (real -> simulated): count")
        for (real, sim), c in sorted(confusion.items(), key=lambda x: -x[1]):
            self.stdout.write(f"  {real:8s} -> {sim:8s} : {c}")

        self.stdout.write("\n" + "=" * 70)
        self.stdout.write("UPGRADE-WINDOW A/B: calendar-year (LOCKED rule) vs rolling-365-day (diagnostic)")
        self.stdout.write("=" * 70)
        self.stdout.write(
            "Both computed from the exact same customers in this same run. This does NOT change "
            "what's enforced anywhere else in the app -- it's evidence only, to inform whether the "
            "PO wants to reconsider the locked calendar-year rule."
        )
        self.stdout.write(f"Calendar-year : agree={agree} ({100*agree/checked:.1f}%)  disagree={disagree} ({100*disagree/checked:.1f}%)")
        self.stdout.write(f"Rolling-365d  : agree={roll_agree} ({100*roll_agree/checked:.1f}%)  disagree={roll_disagree} ({100*roll_disagree/checked:.1f}%)")
        self.stdout.write(f"\nSwing FOR rolling (disagreed under calendar, agrees under rolling):    {swing_to_agree}")
        self.stdout.write(f"Swing AGAINST rolling (agreed under calendar, disagrees under rolling): {swing_to_disagree}")
        self.stdout.write(f"Net change if switched to rolling: {swing_to_agree - swing_to_disagree:+d} agreements")
        self.stdout.write("\nRolling-365d confusion matrix (real -> simulated): count")
        for (real, sim), c in sorted(roll_confusion.items(), key=lambda x: -x[1]):
            self.stdout.write(f"  {real:8s} -> {sim:8s} : {c}")

        self.stdout.write("\n" + "=" * 70)
        self.stdout.write("DISAGREEMENT RECENCY ANALYSIS (all disagreements, not just the sample; calendar-year rule)")
        self.stdout.write("=" * 70)
        if disagree == 0:
            self.stdout.write("No disagreements -- nothing to analyze.")
        else:
            self.stdout.write(f"Direction: simulated LOWER than real (simulation downgraded ahead of real system): {lower_count} ({100*lower_count/disagree:.1f}% of disagreements)")
            self.stdout.write(f"Direction: simulated HIGHER than real (simulation upgraded ahead of real system):  {higher_count} ({100*higher_count/disagree:.1f}% of disagreements)")
            self.stdout.write("\nHow long ago was the simulated grade change that caused each disagreement:")
            for label, count in recency_buckets.items():
                self.stdout.write(f"  {label}: {count} ({100*count/disagree:.1f}% of disagreements)")
            self.stdout.write(
                "\nIf '0-30 days ago' + '31-60 days ago' dominate, that supports a REPORTING-LAG "
                "explanation (the real system just hasn't caught up to a recent change yet) rather "
                "than the downgrade/upgrade RULE itself being miscalibrated."
            )

        self.stdout.write(f"\nSample AGREEING, with simulated last-grade-change date (up to {options['sample_size']}):")
        for vid, grade, last_change in sample_agree:
            self.stdout.write(f"  {vid}: grade={grade} last_change={last_change}")

        self.stdout.write(f"\nSample DISAGREEING (up to {options['sample_size']}):")
        for vid, real, sim, last_change in sample_disagree:
            self.stdout.write(f"  {vid}: real={real} simulated={sim} simulated_last_change={last_change}")

        if disagree > 0:
            self.stdout.write("\n" + "=" * 70)
            self.stdout.write(f"DETAILED INVOICE LOG for up to {samples_per_bucket} sample customer(s) per recency bucket")
            self.stdout.write("(raw transaction rows + simulator trace -- root-cause evidence, not a guess)")
            self.stdout.write("=" * 70)
            for bucket, samples in bucket_samples.items():
                if not samples:
                    continue
                self.stdout.write(f"\n--- Bucket: {bucket} ({recency_buckets[bucket]} total in this bucket) ---")
                for vid, real_grade, simulated in samples:
                    self.stdout.write(f"\nvip_id={vid}  real={real_grade}  simulated={simulated}")
                    _dump_customer(vid)

        self.stdout.write("\nDONE (read-only, nothing was written to the database)")
