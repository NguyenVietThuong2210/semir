"""
App/analytics/grade_simulation.py

Shared, read-only grade-upgrade/downgrade simulation logic. Extracted
2026-09-02 from App/management/commands/simulate_grade_upgrade_downgrade.py
so multiple call sites (the original diagnostic command, the snapshot
temporal-precision validation command, and any future production feature)
all run the EXACT same validated algorithm instead of re-deriving it.

This module contains no I/O beyond the one shared SalesTransaction loading
query -- it never writes to the database.

Context: the goal is to reconstruct the upgrade/downgrade DATE the external
POS system doesn't expose, using only SalesTransaction + Customer data and
the already-LOCKED grade rules (App/analytics/calculations.py). Validated
against real PROD Customer.vip_grade at 98.5% agreement (86,797/88,093,
2026-09-02); an A/B test confirmed the LOCKED calendar-year upgrade window
beats a rolling-365-day alternative on real PROD data (net -1172 agreements
if switched), so 'calendar' remains the production rule -- 'rolling' exists
here only as a diagnostic option for future A/B checks.

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

Algorithm (per customer, exact-date event simulation):
  1. Build this customer's transactions sorted by date. Also build their
     DISTINCT-invoice date list (one entry per invoice_number, at that
     invoice's earliest line-item date) for the trailing-365-day PURCHASE
     COUNT check -- "annual_purchase_count" is distinct invoices everywhere
     else in this codebase (see compute_annual_spend_map's
     Count('invoice_number', distinct=True)), so this matches that
     convention rather than counting raw SalesTransaction rows.
  2. Walk a merged event timeline of (a) each transaction date and (b) each
     "anniversary check" date, generated on the fly as
     last_grade_change_date + 365 days, recurring every time a check occurs
     (whether or not it results in a downgrade) -- i.e. once a customer has
     ever changed grade, they get re-evaluated every 365 days from that
     point forward, indefinitely, matching the locked rule's literal
     wording ("within 1 year of the customer's last grade-change date").
  3. On a transaction event: add settlement_amount to a running
     calendar-year-to-date total (reset every Jan 1). If the YTD total now
     implies a HIGHER grade than the customer's current simulated grade,
     upgrade immediately (can skip tiers in one step -- the locked rule has
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
     (regardless of whether a downgrade happened this time -- matches the PO
     example's implicit expectation that a customer keeps getting
     re-evaluated annually even after failing a prior check, until they
     reach Member, at which point no further checks apply since Member has
     no minimum-purchase floor to fall below).
"""
import bisect
from collections import defaultdict
from datetime import timedelta
from decimal import Decimal

from App.analytics.calculations import GRADE_UPGRADE_THRESHOLDS, GRADE_DOWNGRADE_MIN_ANNUAL_PURCHASES

GRADE_RANK = {'Member': 0, 'Silver': 1, 'Gold': 2, 'Diamond': 3}
RANK_TO_GRADE = {v: k for k, v in GRADE_RANK.items()}
ONE_YEAR = timedelta(days=365)


def count_invoices_in_trailing_window(invoice_dates, end_date):
    """invoice_dates: sorted list of dates (one per distinct invoice_number).
    Returns count of entries in [end_date - 365 days, end_date], inclusive of
    both ends -- same window convention as the downgrade-anniversary check
    inside simulate_one_customer (A/B-validated 2026-09-02, see that
    function's purchases_in_trailing_365 docstring for the evidence)."""
    start = end_date - ONE_YEAR
    lo = bisect.bisect_left(invoice_dates, start)
    hi = bisect.bisect_right(invoice_dates, end_date)
    return hi - lo


def _grade_for_spend(spend):
    if spend >= GRADE_UPGRADE_THRESHOLDS['Diamond']:
        return 'Diamond'
    if spend >= GRADE_UPGRADE_THRESHOLDS['Gold']:
        return 'Gold'
    if spend >= GRADE_UPGRADE_THRESHOLDS['Silver']:
        return 'Silver'
    return 'Member'


def load_customer_transactions():
    """
    One query over the whole SalesTransaction table (excluding blank/null/'0'
    vip_id, matching the app-wide convention -- see App/analytics/membership.py).
    Returns three dicts, all keyed by vip_id:
      - txns_by_vip: vip_id -> [(date, Decimal amount), ...] (unsorted -- sort
        before passing to simulate_one_customer)
      - invoices_by_vip: vip_id -> {invoice_number: earliest_date}
      - invoice_log_by_vip: vip_id -> [(date, invoice_number, amount), ...],
        raw rows for diagnostic dumps.
    """
    from App.models import SalesTransaction

    txns_by_vip = defaultdict(list)
    invoices_by_vip = defaultdict(dict)
    invoice_log_by_vip = defaultdict(list)
    qs = (
        SalesTransaction.objects
        .exclude(vip_id__isnull=True).exclude(vip_id='').exclude(vip_id='0')
        .order_by('vip_id', 'sales_date')
        .values_list('vip_id', 'sales_date', 'settlement_amount', 'invoice_number')
    )
    for vip_id, sales_date, amount, invoice_number in qs.iterator():
        amt = amount or Decimal('0')
        txns_by_vip[vip_id].append((sales_date, amt))
        invoice_log_by_vip[vip_id].append((sales_date, invoice_number, amt))
        inv_map = invoices_by_vip[vip_id]
        if invoice_number not in inv_map or sales_date < inv_map[invoice_number]:
            inv_map[invoice_number] = sales_date
    return txns_by_vip, invoices_by_vip, invoice_log_by_vip


def simulate_one_customer(txns, invoice_dates, as_of_date, trace=None, upgrade_window='calendar'):
    """
    txns: list of (date, Decimal amount), sorted by date.
    invoice_dates: sorted list of dates, one per DISTINCT invoice_number
        (earliest line-item date for that invoice), used only for the
        trailing-365-day purchase-count check via bisect.
    as_of_date: simulate through this date, inclusive.
    trace: optional list -- if given, every event is appended as a string
        for debugging a single customer's full history.
    upgrade_window: 'calendar' (LOCKED rule, App/analytics/calculations.py --
        spend resets every Jan 1, only the current calendar year counts) or
        'rolling' (diagnostic-only alternate: cumulative spend in the
        trailing 365 days ending at each transaction, never reset by the
        calendar).

    Returns (final_grade, last_grade_change_date or None, last_change_direction
    or None, next_check_date or None). last_change_direction is 'upgrade' or
    'downgrade', reflecting whichever event (txn-driven upgrade or
    anniversary-check downgrade) most recently set last_grade_change_date --
    None if the customer never changed grade during the simulation.
    next_check_date is the date of this customer's NEXT scheduled downgrade
    anniversary check (None if current_grade == 'Member', since Member has no
    downgrade floor to check). Added 2026-09-02 so a "purchases needed to
    avoid downgrade" UI figure can be computed against the customer's TRUE
    upcoming check window `[next_check_date - 365, next_check_date]`, not a
    naive "365 days ending today" window -- those differ whenever a customer
    has passed one or more prior annual checks without last_grade_change_date
    advancing (last_grade_change_date only moves on an actual grade change,
    while next_check_date keeps advancing 365 days on every check, pass or
    fail -- see process_anniversary below), so next_check_date can NOT be
    reconstructed as last_grade_change_date + 365 after multiple passing
    checks and must be returned explicitly.
    """
    current_grade = 'Member'
    last_change_date = None
    last_change_direction = None
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
        # with ZERO change to the PO's locked worked example.
        return count_invoices_in_trailing_window(invoice_dates, end_date)

    def process_anniversary(check_date):
        nonlocal current_grade, last_change_date, last_change_direction, next_anniversary
        if current_grade != 'Member':
            cnt = purchases_in_trailing_365(check_date)
            min_req = GRADE_DOWNGRADE_MIN_ANNUAL_PURCHASES.get(current_grade)
            if min_req is not None and cnt < min_req:
                old = current_grade
                current_grade = RANK_TO_GRADE[GRADE_RANK[current_grade] - 1]
                last_change_date = check_date
                last_change_direction = 'downgrade'
                if trace is not None:
                    trace.append(f"{check_date}: ANNIVERSARY CHECK -- trailing 365d purchases={cnt} < min={min_req} -> DOWNGRADE {old} -> {current_grade}")
            elif trace is not None:
                trace.append(f"{check_date}: ANNIVERSARY CHECK -- trailing 365d purchases={cnt} >= min={min_req} -> no change ({current_grade})")
        # Schedule the next check 365 days after THIS check_date -- not
        # last_change_date, to guarantee forward progress even across
        # multiple consecutive passing checks (see module history / git log
        # for the infinite-loop bug this specifically fixes). Once the
        # customer is back at Member, no further checks are scheduled.
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
            last_change_direction = 'upgrade'
            next_anniversary = txn_date + ONE_YEAR
            if trace is not None:
                trace.append(f"{txn_date}: TXN +{amount} ({spend_label}) -> UPGRADE {old} -> {current_grade}")
        elif trace is not None:
            trace.append(f"{txn_date}: TXN +{amount} ({spend_label}), no change ({current_grade})")
        txn_idx += 1

    # Drain remaining anniversary checks up to as_of_date.
    while next_anniversary is not None and next_anniversary <= as_of_date:
        process_anniversary(next_anniversary)

    return current_grade, last_change_date, last_change_direction, next_anniversary
