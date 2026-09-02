"""
App/management/commands/validate_grade_dates_against_snapshots.py

READ-ONLY validation. Writes nothing to the database — no
.save()/.create()/.update()/.delete() calls anywhere in this file. Safe to
run directly against PROD.

Context (2026-09-02, PO): the grade-change-date simulation
(App/analytics/grade_simulation.py, see that module's docstring for the full
algorithm) was already validated against TODAY's live Customer.vip_grade at
98.5% agreement. That's an "endpoint only" test — it proves the formula
predicts the right FINAL grade, but says nothing about whether it gets the
DATE of a change right, or even whether it agrees with the real system at
any point OTHER than today.

PROD has two real MembershipSnapshotBatch rows exactly one day apart
(batch_id=3 @ 2026-08-30, batch_id=4 @ 2026-08-31 — see
/membership/?from_batch=3&to_batch=4 on the live site). For every customer
with a REAL recorded grade change between these two exact snapshot dates,
this command checks THREE things independently:
  1. endpoint_from_match: does the simulation, run with as_of=from_batch's
     snapshot_date, reproduce the FROM grade recorded in that snapshot?
  2. endpoint_to_match: does the simulation, run with as_of=to_batch's
     snapshot_date, reproduce the TO grade recorded in that snapshot?
  3. timing_match: does the simulation's own last_grade_change_date (as of
     the to_batch run) fall strictly inside the (from_date, to_date] window
     -- i.e. does the simulation ALSO think a change happened in this exact
     1-day window, not just eventually converge to the right grade for some
     unrelated reason?

This is a stronger test than the today-only endpoint check because it pins
the formula down in TIME, not just final state. Reuses the existing,
already-tested App.analytics.membership.get_grade_changes() -- the same
function that powers the /membership/ comparison page -- for the real
recorded transitions, so this command never re-derives batch-diff logic.

Usage (on PROD):
    docker compose exec web python manage.py validate_grade_dates_against_snapshots --from-batch 3 --to-batch 4

Output is aggregate statistics plus, for any mismatch, a full raw invoice
log + simulator trace dump (same style as simulate_grade_upgrade_downgrade.py)
so a failure can be root-caused from real data. Only vip_id/dates/grades/
invoice_number/amounts are ever read or printed -- no customer name or phone
number (get_grade_changes() returns name/phone for its own UI use; this
command deliberately never reads those keys off its result rows).
"""
from django.core.management.base import BaseCommand, CommandError

from App.analytics.grade_simulation import load_customer_transactions, simulate_one_customer


class Command(BaseCommand):
    help = "READ-ONLY: cross-validate the grade simulation's DATE precision against two real MembershipSnapshotBatch rows"

    def add_arguments(self, parser):
        parser.add_argument("--from-batch", type=int, required=True, help="From MembershipSnapshotBatch id")
        parser.add_argument("--to-batch", type=int, required=True, help="To MembershipSnapshotBatch id")
        parser.add_argument("--sample-size", type=int, default=10, help="How many full invoice-log+trace dumps to print per mismatch category.")

    def handle(self, *args, **options):
        from App.analytics.membership import get_grade_changes
        from App.models.membership import MembershipSnapshotBatch

        from_id, to_id = options["from_batch"], options["to_batch"]
        sample_size = options["sample_size"]

        try:
            from_batch = MembershipSnapshotBatch.objects.get(pk=from_id)
            to_batch = MembershipSnapshotBatch.objects.get(pk=to_id)
        except MembershipSnapshotBatch.DoesNotExist as e:
            raise CommandError(str(e))

        from_date, to_date = from_batch.snapshot_date, to_batch.snapshot_date

        self.stdout.write("=" * 70)
        self.stdout.write("validate_grade_dates_against_snapshots — READ ONLY, no writes")
        self.stdout.write(f"From batch {from_batch.id}: {from_date} ({from_batch.source}, {from_batch.row_count} rows)")
        self.stdout.write(f"To batch   {to_batch.id}: {to_date} ({to_batch.source}, {to_batch.row_count} rows)")
        self.stdout.write("=" * 70)

        self.stdout.write("\nLoading real recorded grade changes between these two batches...")
        real_changes, total_count = get_grade_changes(from_id, to_id, limit=None)
        self.stdout.write(f"  {total_count} real recorded grade changes")
        if not total_count:
            self.stdout.write("Nothing to validate.")
            return

        self.stdout.write("\nLoading SalesTransaction rows (this may take a moment)...")
        txns_by_vip, invoices_by_vip, invoice_log_by_vip = load_customer_transactions()
        self.stdout.write(f"  covering {len(txns_by_vip)} distinct vip_ids")

        def _sim(vid, as_of_date, trace=None):
            txns = sorted(txns_by_vip.get(vid, []), key=lambda t: t[0])
            invoice_dates = sorted(invoices_by_vip.get(vid, {}).values())
            return simulate_one_customer(txns, invoice_dates, as_of_date, trace=trace, upgrade_window='calendar')

        def _dump_customer(vid):
            rows = sorted(invoice_log_by_vip.get(vid, []), key=lambda r: r[0])
            self.stdout.write(f"  raw invoices ({len(rows)} line items):")
            for d, inv_no, amt in rows:
                self.stdout.write(f"    {d}  invoice={inv_no!r}  amount={amt}")
            trace = []
            final_grade, last_change = _sim(vid, to_date, trace=trace)
            self.stdout.write(f"  simulator trace (as_of={to_date}):")
            for line in trace:
                self.stdout.write(f"    {line}")
            self.stdout.write(f"  final simulated grade={final_grade}  last_grade_change={last_change}")

        self.stdout.write("\nRunning simulation at both snapshot dates for each real transition...")
        endpoint_from_ok = endpoint_to_ok = timing_ok = full_match = 0
        samples = {"full_match": [], "endpoint_only": [], "no_match": []}
        for row in real_changes:
            vid = row["vip_id"]
            real_from, real_to = row["from_grade"], row["to_grade"]

            sim_from_grade, _ = _sim(vid, from_date)
            sim_to_grade, sim_to_last_change = _sim(vid, to_date)

            from_ok = sim_from_grade == real_from
            to_ok = sim_to_grade == real_to
            time_ok = sim_to_last_change is not None and from_date < sim_to_last_change <= to_date

            if from_ok:
                endpoint_from_ok += 1
            if to_ok:
                endpoint_to_ok += 1
            if time_ok:
                timing_ok += 1

            if from_ok and to_ok and time_ok:
                full_match += 1
                bucket = "full_match"
            elif from_ok and to_ok:
                bucket = "endpoint_only"
            else:
                bucket = "no_match"
            if len(samples[bucket]) < sample_size:
                samples[bucket].append((vid, real_from, real_to, sim_from_grade, sim_to_grade, sim_to_last_change))

        self.stdout.write("\n" + "=" * 70)
        self.stdout.write("RESULTS")
        self.stdout.write("=" * 70)
        self.stdout.write(f"Real recorded transitions checked: {total_count}")
        self.stdout.write(f"endpoint_from_match (sim as_of {from_date} == real from_grade): {endpoint_from_ok} ({100*endpoint_from_ok/total_count:.1f}%)")
        self.stdout.write(f"endpoint_to_match   (sim as_of {to_date} == real to_grade):     {endpoint_to_ok} ({100*endpoint_to_ok/total_count:.1f}%)")
        self.stdout.write(f"timing_match (sim's own last_grade_change falls in ({from_date}, {to_date}]): {timing_ok} ({100*timing_ok/total_count:.1f}%)")
        self.stdout.write(f"FULL match (all three): {full_match} ({100*full_match/total_count:.1f}%)")

        for label, key in [
            ("FULL MATCH (endpoints + timing all agree)", "full_match"),
            ("ENDPOINTS MATCH but timing does not (right final grades, formula thinks the change happened at a different time)", "endpoint_only"),
            ("NO MATCH (at least one endpoint is wrong)", "no_match"),
        ]:
            rows = samples[key]
            if not rows:
                continue
            self.stdout.write(f"\n--- Sample: {label} (up to {sample_size}) ---")
            for vid, real_from, real_to, sim_from, sim_to, sim_last_change in rows:
                self.stdout.write(
                    f"  {vid}: real {real_from}->{real_to} | simulated {sim_from}->{sim_to} | "
                    f"simulated_last_change={sim_last_change}"
                )

        if samples["no_match"]:
            self.stdout.write("\n" + "=" * 70)
            self.stdout.write(f"DETAILED INVOICE LOG for up to {sample_size} NO-MATCH sample customer(s)")
            self.stdout.write("(raw transaction rows + simulator trace -- root-cause evidence, not a guess)")
            self.stdout.write("=" * 70)
            for vid, real_from, real_to, sim_from, sim_to, sim_last_change in samples["no_match"]:
                self.stdout.write(f"\nvip_id={vid}  real {real_from}->{real_to}  simulated {sim_from}->{sim_to}")
                _dump_customer(vid)

        self.stdout.write("\nDONE (read-only, nothing was written to the database)")
