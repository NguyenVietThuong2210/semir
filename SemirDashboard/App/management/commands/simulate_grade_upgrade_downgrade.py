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
Customer.vip_grade).

PO's own worked example, which this simulation must reproduce exactly:
  - Registers 2025-01-01 (starts at Member, no grade-change date yet).
  - On 2025-06-06 a purchase pushes calendar-YTD spend past the Silver
    threshold -> upgraded to Silver on 2025-06-06 exactly (not "sometime in
    June", not "end of June" -- the literal transaction date).
    last_grade_change_date is now 2025-06-06.
  - Exactly one year later, 2026-06-06 (the ANNIVERSARY of the last grade
    change, not a fixed calendar checkpoint like month-end), the system
    checks: how many purchases did they make in the trailing 365 days
    (2025-06-06 -> 2026-06-06)? If below Silver's minimum (2), downgrade to
    Member on 2026-06-06 exactly. last_grade_change_date is now 2026-06-06,
    and a NEW anniversary check is scheduled for 2027-06-06.
  - No purchases since -> grade stays Member through today.

Algorithm (per customer, exact-date event simulation — NOT a fixed monthly
checkpoint, which was this command's earlier, less precise draft):
  1. Build this customer's transactions sorted by date. Also build their
     DISTINCT-invoice date list (one entry per invoice_number, at that
     invoice's earliest line-item date) for the trailing-365-day PURCHASE
     COUNT check — "annual_purchase_count" is distinct invoices everywhere
     else in this codebase (see compute_annual_spend_map's
     Count('invoice_number', distinct=True)), so this matches that
     convention rather than counting raw SalesTransaction rows.
  2. Walk a merged event timeline of (a) each transaction date and (b) each
     "anniversary check" date, which is generated on the fly as
     last_grade_change_date + 365 days, recurring every time a check occurs
     (whether or not it results in a downgrade) — i.e. once a customer has
     ever changed grade, they get re-evaluated every 365 days from that
     point forward, indefinitely, matching the locked rule's literal
     wording ("within 1 year of the customer's last grade-change date").
  3. On a transaction event: add settlement_amount to a running
     calendar-year-to-date total (reset every Jan 1). If the YTD total now
     implies a HIGHER grade than the customer's current simulated grade,
     upgrade immediately (can skip tiers in one step — the locked rule has
     no "must pass through each tier" language), set
     last_grade_change_date to this exact transaction date, and (re)schedule
     the next anniversary check 365 days later.
  4. On an anniversary-check event (only relevant once current_grade is
     above Member): count DISTINCT invoices in the 365 days immediately
     before this exact check date. If below
     GRADE_DOWNGRADE_MIN_ANNUAL_PURCHASES for the CURRENT simulated grade,
     downgrade exactly one tier, set last_grade_change_date to this exact
     check date, and schedule the next anniversary 365 days later
     (regardless of whether a downgrade happened this time — matches the PO
     example's implicit expectation that a customer keeps getting
     re-evaluated annually even after failing a prior check, until they
     reach Member, at which point no further checks apply since Member has
     no minimum-purchase floor to fall below).

Usage (on PROD):
    docker compose exec web python manage.py simulate_grade_upgrade_downgrade
    docker compose exec web python manage.py simulate_grade_upgrade_downgrade --as-of 2026-08-31
    docker compose exec web python manage.py simulate_grade_upgrade_downgrade --vip-id 1460606   # trace one customer's full event log

Output is aggregate statistics + a small sample of vip_id/dates/amounts only
— no customer name or phone number is read or printed anywhere in this file.
"""
import bisect
from collections import defaultdict
from datetime import date, timedelta
from decimal import Decimal

from django.core.management.base import BaseCommand

from App.analytics.calculations import GRADE_UPGRADE_THRESHOLDS, GRADE_DOWNGRADE_MIN_ANNUAL_PURCHASES
from App.analytics.customer_utils import resolve_grade

GRADE_RANK = {'Member': 0, 'Silver': 1, 'Gold': 2, 'Diamond': 3}
RANK_TO_GRADE = {v: k for k, v in GRADE_RANK.items()}
ONE_YEAR = timedelta(days=365)


def _grade_for_spend(spend):
    if spend >= GRADE_UPGRADE_THRESHOLDS['Diamond']:
        return 'Diamond'
    if spend >= GRADE_UPGRADE_THRESHOLDS['Gold']:
        return 'Gold'
    if spend >= GRADE_UPGRADE_THRESHOLDS['Silver']:
        return 'Silver'
    return 'Member'


def simulate_one_customer(txns, invoice_dates, as_of_date, trace=None):
    """
    txns: list of (date, Decimal amount), sorted by date.
    invoice_dates: sorted list of dates, one per DISTINCT invoice_number
        (earliest line-item date for that invoice), used only for the
        trailing-365-day purchase-count check via bisect.
    as_of_date: simulate through this date, inclusive.
    trace: optional list -- if given, every event is appended as a string
        for debugging a single customer's full history (--vip-id flag).

    Returns (final_grade, last_grade_change_date or None).
    """
    current_grade = 'Member'
    last_change_date = None
    next_anniversary = None
    ytd_year = None
    ytd_spend = Decimal('0')

    def purchases_in_trailing_365(end_date):
        start = end_date - ONE_YEAR
        lo = bisect.bisect_right(invoice_dates, start)  # strictly after start
        hi = bisect.bisect_right(invoice_dates, end_date)  # up to and including end_date
        return hi - lo

    def process_anniversary(check_date):
        nonlocal current_grade, last_change_date, next_anniversary
        if current_grade != 'Member':
            cnt = purchases_in_trailing_365(check_date)
            min_req = GRADE_DOWNGRADE_MIN_ANNUAL_PURCHASES.get(current_grade)
            if min_req is not None and cnt < min_req:
                old = current_grade
                current_grade = RANK_TO_GRADE[GRADE_RANK[current_grade] - 1]
                last_change_date = check_date
                if trace is not None:
                    trace.append(f"{check_date}: ANNIVERSARY CHECK -- trailing 365d purchases={cnt} < min={min_req} -> DOWNGRADE {old} -> {current_grade}")
            elif trace is not None:
                trace.append(f"{check_date}: ANNIVERSARY CHECK -- trailing 365d purchases={cnt} >= min={min_req} -> no change ({current_grade})")
        # Schedule the next check 365 days after THIS check_date -- not
        # last_change_date. When no downgrade happens, last_change_date is
        # left untouched (correct: the grade didn't change), but that means
        # `last_change_date + ONE_YEAR` would recompute to the exact same
        # value that produced this call, so the caller's while loop would
        # re-process the identical check_date forever (infinite loop) for
        # any customer who passes 2+ consecutive annual checks. Anchoring
        # on check_date guarantees forward progress every call. Once the
        # customer is back at Member (either entered that way or was just
        # downgraded to it), there is no floor to fall below, so no further
        # checks are scheduled at all -- matches the module docstring.
        next_anniversary = None if current_grade == 'Member' else check_date + ONE_YEAR

    txn_idx = 0
    n = len(txns)
    while txn_idx < n and txns[txn_idx][0] <= as_of_date:
        txn_date, amount = txns[txn_idx]

        # Process any anniversary checks on or before this transaction's date.
        # Using <= (not strict <) so a check landing on the EXACT SAME date as
        # a transaction is evaluated first, rather than being silently
        # overwritten/skipped if that transaction goes on to trigger an
        # upgrade (upgrade assigns next_anniversary = txn_date + ONE_YEAR
        # unconditionally, which would otherwise erase a same-day pending
        # check before it's ever run). process_anniversary always advances
        # next_anniversary strictly forward (or sets it None), so this loop
        # terminates.
        while next_anniversary is not None and next_anniversary <= txn_date and next_anniversary <= as_of_date:
            process_anniversary(next_anniversary)

        year = txn_date.year
        if ytd_year != year:
            ytd_year = year
            ytd_spend = Decimal('0')
        ytd_spend += amount
        implied = _grade_for_spend(ytd_spend)
        if GRADE_RANK[implied] > GRADE_RANK[current_grade]:
            old = current_grade
            current_grade = implied
            last_change_date = txn_date
            next_anniversary = txn_date + ONE_YEAR
            if trace is not None:
                trace.append(f"{txn_date}: TXN +{amount} (YTD={ytd_spend}) -> UPGRADE {old} -> {current_grade}")
        elif trace is not None:
            trace.append(f"{txn_date}: TXN +{amount} (YTD={ytd_spend}), no change ({current_grade})")
        txn_idx += 1

    # Drain remaining anniversary checks up to as_of_date.
    while next_anniversary is not None and next_anniversary <= as_of_date:
        process_anniversary(next_anniversary)

    return current_grade, last_change_date


class Command(BaseCommand):
    help = "READ-ONLY: exact-date per-customer simulation of grade upgrade/downgrade from first purchase to today, vs live Customer.vip_grade"

    def add_arguments(self, parser):
        parser.add_argument("--as-of", type=str, default=None, help="Simulate through this date (YYYY-MM-DD). Default: today.")
        parser.add_argument("--sample-size", type=int, default=15)
        parser.add_argument("--vip-id", type=str, default=None, help="Print the full event trace for just this one vip_id and exit (no aggregate stats).")

    def handle(self, *args, **options):
        from App.models import Customer, SalesTransaction

        as_of = date.fromisoformat(options["as_of"]) if options["as_of"] else date.today()

        self.stdout.write("=" * 70)
        self.stdout.write("simulate_grade_upgrade_downgrade — READ ONLY, no writes")
        self.stdout.write(f"Simulating through: {as_of}")
        self.stdout.write("=" * 70)

        self.stdout.write("\nLoading SalesTransaction rows (this may take a moment)...")
        txns_by_vip = defaultdict(list)
        invoices_by_vip = defaultdict(dict)  # vip_id -> {invoice_number: earliest_date}
        qs = (
            SalesTransaction.objects
            .exclude(vip_id__isnull=True).exclude(vip_id='').exclude(vip_id='0')
            .order_by('vip_id', 'sales_date')
            .values_list('vip_id', 'sales_date', 'settlement_amount', 'invoice_number')
        )
        row_count = 0
        for vip_id, sales_date, amount, invoice_number in qs.iterator():
            txns_by_vip[vip_id].append((sales_date, amount or Decimal('0')))
            inv_map = invoices_by_vip[vip_id]
            if invoice_number not in inv_map or sales_date < inv_map[invoice_number]:
                inv_map[invoice_number] = sales_date
            row_count += 1
        self.stdout.write(f"  {row_count} rows loaded, covering {len(txns_by_vip)} distinct vip_ids")

        if options["vip_id"]:
            vid = options["vip_id"]
            txns = sorted(txns_by_vip.get(vid, []), key=lambda t: t[0])
            invoice_dates = sorted(invoices_by_vip.get(vid, {}).values())
            trace = []
            final_grade, last_change = simulate_one_customer(txns, invoice_dates, as_of, trace=trace)
            self.stdout.write(f"\n=== Full event trace for vip_id={vid} ===")
            for line in trace:
                self.stdout.write(f"  {line}")
            self.stdout.write(f"\nFinal simulated grade: {final_grade}")
            self.stdout.write(f"Last grade-change date: {last_change}")
            try:
                real_raw = Customer.objects.get(vip_id=vid).vip_grade
                self.stdout.write(f"Real live grade: {resolve_grade(vid, real_raw)} (raw: {real_raw!r})")
            except Customer.DoesNotExist:
                self.stdout.write("(vip_id not found in live Customer table)")
            return

        self.stdout.write("\nRunning per-customer simulation...")
        sim_grade = {}
        sim_last_change = {}
        processed = 0
        for vid, txns in txns_by_vip.items():
            txns.sort(key=lambda t: t[0])
            invoice_dates = sorted(invoices_by_vip[vid].values())
            grade, last_change = simulate_one_customer(txns, invoice_dates, as_of)
            sim_grade[vid] = grade
            sim_last_change[vid] = last_change
            processed += 1
            if processed % 10000 == 0:
                self.stdout.write(f"  ...simulated {processed}/{len(txns_by_vip)} customers")

        self.stdout.write(f"Simulation complete for {len(sim_grade)} customers with transaction history.")

        self.stdout.write("\nComparing against live Customer.vip_grade...")
        live_rows = Customer.objects.exclude(vip_id='0').values_list('vip_id', 'vip_grade')
        agree = disagree = checked = 0
        confusion = defaultdict(int)
        sample_agree, sample_disagree = [], []

        for vip_id, raw_grade in live_rows:
            real_grade = resolve_grade(vip_id, raw_grade)
            if real_grade not in GRADE_RANK:
                continue
            simulated = sim_grade.get(vip_id, 'Member')
            checked += 1
            confusion[(real_grade, simulated)] += 1
            if simulated == real_grade:
                agree += 1
                if len(sample_agree) < options["sample_size"]:
                    sample_agree.append((vip_id, real_grade, sim_last_change.get(vip_id)))
            else:
                disagree += 1
                if len(sample_disagree) < options["sample_size"]:
                    sample_disagree.append((vip_id, real_grade, simulated, sim_last_change.get(vip_id)))

        self.stdout.write("\n" + "=" * 70)
        self.stdout.write("RESULTS")
        self.stdout.write("=" * 70)
        self.stdout.write(f"Checked {checked} live customers with a real Member/Silver/Gold/Diamond grade")
        self.stdout.write(f"Agree:    {agree} ({100*agree/checked:.1f}%)")
        self.stdout.write(f"Disagree: {disagree} ({100*disagree/checked:.1f}%)")

        self.stdout.write("\nConfusion matrix (real -> simulated): count")
        for (real, sim), c in sorted(confusion.items(), key=lambda x: -x[1]):
            self.stdout.write(f"  {real:8s} -> {sim:8s} : {c}")

        self.stdout.write(f"\nSample AGREEING, with simulated last-grade-change date (up to {options['sample_size']}):")
        for vid, grade, last_change in sample_agree:
            self.stdout.write(f"  {vid}: grade={grade} last_change={last_change}")

        self.stdout.write(f"\nSample DISAGREEING (up to {options['sample_size']}):")
        for vid, real, sim, last_change in sample_disagree:
            self.stdout.write(f"  {vid}: real={real} simulated={sim} simulated_last_change={last_change}")

        self.stdout.write("\nDONE (read-only, nothing was written to the database)")
