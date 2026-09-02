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
     above Member): count DISTINCT invoices in the 365 days ending at this
     check date, INCLUSIVE of the day exactly 365 days before it (so a
     customer's very first anniversary counts the purchase that earned them
     the tier in the first place -- see purchases_in_trailing_365's comment
     for the A/B evidence behind this). If below
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


def simulate_one_customer(txns, invoice_dates, as_of_date, trace=None, upgrade_window='calendar'):
    """
    txns: list of (date, Decimal amount), sorted by date.
    invoice_dates: sorted list of dates, one per DISTINCT invoice_number
        (earliest line-item date for that invoice), used only for the
        trailing-365-day purchase-count check via bisect.
    as_of_date: simulate through this date, inclusive.
    trace: optional list -- if given, every event is appended as a string
        for debugging a single customer's full history (--vip-id flag).
    upgrade_window: 'calendar' (LOCKED rule, App/analytics/calculations.py --
        spend resets every Jan 1, only the current calendar year counts) or
        'rolling' (diagnostic-only alternate: cumulative spend in the
        trailing 365 days ending at each transaction, never reset by the
        calendar). Added 2026-09-02 after real PROD data showed customers
        whose spend is split across a Jan-1 boundary (e.g. registered
        mid-year) never cross a calendar-year threshold even though their
        real grade is elevated -- see 'no simulated change' bucket in the
        recency analysis. 'rolling' exists to A/B-test that hypothesis
        against the locked 'calendar' rule on the SAME data in the SAME
        run; it does not change what's actually enforced anywhere else in
        the app, and the locked rule remains 'calendar' unless the PO
        explicitly approves switching it after seeing the A/B numbers.

    Returns (final_grade, last_grade_change_date or None).
    """
    current_grade = 'Member'
    last_change_date = None
    next_anniversary = None
    ytd_year = None
    ytd_spend = Decimal('0')

    # For upgrade_window='rolling' only: prefix sums over txns (already
    # sorted by date) so the trailing-365-day cumulative spend ending at any
    # given transaction can be computed in O(log n) via bisect, mirroring
    # purchases_in_trailing_365's inclusive-start convention for consistency.
    txn_dates = [t[0] for t in txns]
    txn_prefix = [Decimal('0')] * (len(txns) + 1)
    for i, (_, amt) in enumerate(txns):
        txn_prefix[i + 1] = txn_prefix[i] + amt

    def rolling_spend_ending_at(idx):
        end_date = txn_dates[idx]
        start = end_date - ONE_YEAR
        lo = bisect.bisect_left(txn_dates, start)
        return txn_prefix[idx + 1] - txn_prefix[lo]

    def purchases_in_trailing_365(end_date):
        # Window is [start, end_date] -- INCLUSIVE of the start boundary. This
        # matters specifically for a customer's first anniversary check right
        # after an upgrade: last_grade_change_date becomes both the window's
        # start AND the date of the purchase that earned the tier, so an
        # exclusive-start window would strip that customer's own qualifying
        # purchase out of their first-year retention count. Decided by A/B
        # test on real local data (2026-09-02): switching exclusive->inclusive
        # start dropped simulation/live disagreement from 1727 to 1496 (-13.4%)
        # with ZERO change to the PO's locked worked example (that example's
        # single purchase now counts as 1 in the trailing window instead of 0,
        # but 1 is still < Silver's min-2 threshold, so the downgrade outcome
        # is identical either way).
        start = end_date - ONE_YEAR
        lo = bisect.bisect_left(invoice_dates, start)
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

        if upgrade_window == 'rolling':
            spend_for_check = rolling_spend_ending_at(txn_idx)
            spend_label = f"trailing365={spend_for_check}"
        else:
            year = txn_date.year
            if ytd_year != year:
                ytd_year = year
                ytd_spend = Decimal('0')
            ytd_spend += amount
            spend_for_check = ytd_spend
            spend_label = f"YTD={ytd_spend}"
        implied = _grade_for_spend(spend_for_check)
        if GRADE_RANK[implied] > GRADE_RANK[current_grade]:
            old = current_grade
            current_grade = implied
            last_change_date = txn_date
            next_anniversary = txn_date + ONE_YEAR
            if trace is not None:
                trace.append(f"{txn_date}: TXN +{amount} ({spend_label}) -> UPGRADE {old} -> {current_grade}")
        elif trace is not None:
            trace.append(f"{txn_date}: TXN +{amount} ({spend_label}), no change ({current_grade})")
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
        parser.add_argument("--samples-per-bucket", type=int, default=3, help="How many customers' full invoice log + trace to dump per recency bucket.")

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
        invoice_log_by_vip = defaultdict(list)  # vip_id -> [(date, invoice_number, amount)], raw rows for diagnostics
        qs = (
            SalesTransaction.objects
            .exclude(vip_id__isnull=True).exclude(vip_id='').exclude(vip_id='0')
            .order_by('vip_id', 'sales_date')
            .values_list('vip_id', 'sales_date', 'settlement_amount', 'invoice_number')
        )
        row_count = 0
        for vip_id, sales_date, amount, invoice_number in qs.iterator():
            amt = amount or Decimal('0')
            txns_by_vip[vip_id].append((sales_date, amt))
            invoice_log_by_vip[vip_id].append((sales_date, invoice_number, amt))
            inv_map = invoices_by_vip[vip_id]
            if invoice_number not in inv_map or sales_date < inv_map[invoice_number]:
                inv_map[invoice_number] = sales_date
            row_count += 1
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
                final_grade, last_change = simulate_one_customer(txns, invoice_dates, as_of, trace=trace, upgrade_window=window)
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
            grade, last_change = simulate_one_customer(txns, invoice_dates, as_of, upgrade_window='calendar')
            sim_grade[vid] = grade
            sim_last_change[vid] = last_change
            grade_roll, _ = simulate_one_customer(txns, invoice_dates, as_of, upgrade_window='rolling')
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
