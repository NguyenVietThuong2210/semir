"""
App/analytics/membership.py

Read/aggregation helpers for the Customer Membership snapshot feature.
Business rule constants (grade thresholds, next_tier_info) live in
calculations.py (pure, no DB access) — this module does the DB queries that
feed them. Used by both the snapshot-writing service
(App/services/membership_snapshot.py) and the Membership page views
(App/views/membership.py).
"""
from datetime import date
from decimal import Decimal

from django.db.models import Count, Q, Sum

from App.analytics.calculations import next_tier_info
from App.analytics.customer_utils import GRADE_ORDER, _norm_vid, resolve_grade

# "No Grade" customers (blank/missing vip_grade on import) are excluded from
# the grade breakdown/comparison/trend views — PO feedback 2026-08-14: not an
# actionable tier, just noise in the KPI view. Individual "No Grade" customers
# still appear in the per-customer tier table (they have a real upgrade path
# to Silver via next_tier_info()) — only the grade-level summary excludes them.
DISPLAY_GRADES = [g for g in GRADE_ORDER if g != 'No Grade']


def compute_annual_spend_map(as_of_date):
    """
    ONE grouped query — not per-customer. Returns
    dict[normalized_vip_id] -> {'annual_spend': Decimal, 'annual_purchase_count': int}
    for the calendar year containing as_of_date, Jan 1 through as_of_date inclusive.

    `.order_by()` before `.values()/.annotate()` clears SalesTransaction's
    Meta.ordering — otherwise it leaks into the GROUP BY (see CLAUDE.md
    Database Notes).
    """
    from App.models import SalesTransaction

    year_start = as_of_date.replace(month=1, day=1)
    rows = (
        SalesTransaction.objects
        .filter(sales_date__gte=year_start, sales_date__lte=as_of_date)
        .exclude(vip_id__isnull=True).exclude(vip_id='').exclude(vip_id='0')
        .order_by()
        .values('vip_id')
        .annotate(spend=Sum('settlement_amount'), cnt=Count('invoice_number', distinct=True))
    )
    result = {}
    for r in rows:
        vid = _norm_vid(r['vip_id'])
        result[vid] = {
            'annual_spend': r['spend'] or Decimal('0'),
            'annual_purchase_count': r['cnt'],
        }
    return result


def list_batches():
    from App.models.membership import MembershipSnapshotBatch
    return list(MembershipSnapshotBatch.objects.all())  # Meta.ordering = -snapshot_date,-created_at


def get_snapshot_registration_stores():
    """
    Distinct registration_store values that actually appear across ANY
    MembershipSnapshot row (not scoped to a single batch). Added 2026-08-31,
    PO feedback: the "by Registration Store" comparison drill-down and the
    trend chart's store filter both work with SNAPSHOT data, not live
    Customer data — reusing the live-Customer-sourced `registration_stores`
    dropdown (App/views/shop_detail.py::_get_dropdown_options(), correct only
    for the live-data "Customer Tier Progress" section) silently offered
    store names that don't exist in older snapshots (or vice versa — a store
    renamed since an old snapshot was taken), producing an all-zero result
    that looked like a bug but was really "this store, under this exact
    name, has no rows in this particular batch."

    Deliberately NOT scoped to the currently-selected From/To batch pair —
    querying across all batches means every offered option corresponds to a
    real store that existed at some point, and a 0 for a specific batch pair
    is then genuine information (the store didn't have this name yet, or any
    members, at that snapshot date) rather than a picklist/data mismatch.
    """
    from App.models.membership import MembershipSnapshot

    return sorted(
        MembershipSnapshot.objects
        .exclude(registration_store__isnull=True).exclude(registration_store='')
        .values_list('registration_store', flat=True)
        .order_by().distinct()
    )


def get_grade_breakdown(batch_id, store=None):
    """dict[grade] -> count for each DISPLAY_GRADES key (0 if absent). Excludes
    'No Grade' — see DISPLAY_GRADES docstring.

    `store` (added 2026-08-31, PO feedback: per-store comparison) optionally
    scopes the count to one registration_store — exact match, since callers
    pass a value picked from the `registration_stores` <select> (populated by
    shop_detail.py's _get_dropdown_options()), not free-text. Pass the literal
    string '(No Store)' to match blank/missing registration_store rows —
    mirrors the bucketing convention in get_grade_breakdown_by_store().
    """
    from App.models.membership import MembershipSnapshot

    counts = {g: 0 for g in DISPLAY_GRADES}
    if not batch_id:
        return counts
    qs = MembershipSnapshot.objects.filter(batch_id=batch_id, grade__in=DISPLAY_GRADES)
    if store:
        if store == '(No Store)':
            qs = qs.filter(Q(registration_store__isnull=True) | Q(registration_store=''))
        else:
            qs = qs.filter(registration_store=store)
    rows = qs.order_by().values('grade').annotate(cnt=Count('id'))
    for r in rows:
        counts[r['grade']] = counts.get(r['grade'], 0) + r['cnt']
    return counts


def get_grade_breakdown_by_store(batch_id):
    """
    List of {'store', 'counts': [count_per_DISPLAY_GRADES_in_order], 'total'}
    rows, one per distinct registration_store present in the batch, sorted by
    store name. Blank/missing registration_store rows are bucketed under
    '(No Store)' rather than dropped — the dropdown that feeds the page's
    store *filter* excludes blanks (App/views/shop_detail.py
    _get_dropdown_options), but this breakdown must still account for every
    row in the batch, so a customer with no registration_store on file still
    shows up here.

    `counts` is a plain list (not a dict) so the template can zip it against
    the `grades` list positionally — Django templates can't do `dict[var]`
    lookups with a loop variable as the key without a custom filter.
    """
    from App.models.membership import MembershipSnapshot

    if not batch_id:
        return []
    rows = (
        MembershipSnapshot.objects.filter(batch_id=batch_id, grade__in=DISPLAY_GRADES)
        .order_by()
        .values('registration_store', 'grade')
        .annotate(cnt=Count('id'))
    )
    by_store = {}
    for r in rows:
        store = r['registration_store'] or '(No Store)'
        counts = by_store.setdefault(store, {g: 0 for g in DISPLAY_GRADES})
        counts[r['grade']] += r['cnt']
    out = []
    for store in sorted(by_store.keys()):
        counts = by_store[store]
        out.append({
            'store': store,
            'counts': [counts[g] for g in DISPLAY_GRADES],
            'total': sum(counts.values()),
        })
    return out


def compare_batches(from_batch_id, to_batch_id, store=None):
    """Per-grade {from_count, to_count, delta, delta_pct}, ordered by GRADE_ORDER.
    `store` (added 2026-08-31) optionally scopes both sides to one
    registration_store — see get_grade_breakdown() docstring."""
    frm = get_grade_breakdown(from_batch_id, store=store)
    to = get_grade_breakdown(to_batch_id, store=store)
    out = []
    for g in sorted(DISPLAY_GRADES, key=GRADE_ORDER.get):
        f, t = frm.get(g, 0), to.get(g, 0)
        delta = t - f
        out.append({
            'grade': g,
            'from_count': f,
            'to_count': t,
            'delta': delta,
            'delta_pct': round(delta / f * 100, 1) if f else None,
        })
    return out


def get_all_batch_grade_series(store=None):
    """
    For the Chart.js line chart across ALL snapshots (not just the 2 selected
    on the compare view). Returns a chronological list:
    [{'batch_id', 'snapshot_date', 'source', 'counts': {grade: count}}]

    `store` (added 2026-08-31, PO feedback: chart needs a store filter)
    optionally scopes every batch's counts to one registration_store — one
    filtered query per batch (bounded by batch count, not store count), not
    routed through get_grade_breakdown_by_store() which would compute every
    store's breakdown per batch just to keep one.
    """
    batches = sorted(list_batches(), key=lambda b: (b.snapshot_date, b.created_at))
    return [
        {
            'batch_id': b.id,
            'snapshot_date': b.snapshot_date.isoformat(),
            'source': b.source,
            'counts': get_grade_breakdown(b.id, store=store),
        }
        for b in batches
    ]


def get_customer_tier_table(batch_id, grade_filter=None, shop_filter=None, sort='amount_to_next_tier', limit=500):
    """
    Snapshot-scoped per-customer tier table. Not called by any view as of
    2026-08-31 — the "Customer Tier Progress" UI section was moved to
    get_live_customer_tier_table() (PO feedback: that section reads live
    Customer data, unrelated to any snapshot). Kept as the historical/
    per-snapshot counterpart (e.g. for a future "what did this look like at
    snapshot X" query or export) and still covered by GetCustomerTierTableTest.

    Per-customer rows for the batch, with next_tier + amount_to_next_tier
    computed via calculations.next_tier_info(). Sorted ascending by amount
    remaining by default (customers closest to their next tier first).

    Returns (rows, total_count). `limit` caps the returned row list (default
    500) — a batch can hold tens of thousands of customers, and rendering
    them all into one AJAX response/DOM would be a real browser-freezing
    payload (unfiltered, this table is a reporting/triage list, not a full
    export — use the grade/shop filters or a future Excel export for the
    complete set). `total_count` lets the UI show "showing top N of TOTAL".
    Pass limit=None for the full unfiltered set (e.g. for Excel export).
    """
    from App.models.membership import MembershipSnapshot

    qs = MembershipSnapshot.objects.filter(batch_id=batch_id)
    if grade_filter:
        qs = qs.filter(grade=grade_filter)
    if shop_filter:
        # Exact match (changed 2026-08-31, independent review finding): the
        # membership.html store filter is now a <select> of exact DB values
        # (registration_stores/snapshot_stores), not free text — icontains
        # would silently pull in rows from any OTHER store whose name
        # contains the selected one as a substring (e.g. "AEON MALL" also
        # matching "AEON MALL - Tan Phu"). Matches the exact-match convention
        # already used by get_grade_breakdown()/compare_batches() for `store`.
        qs = qs.filter(registration_store=shop_filter)
    total_count = qs.count()
    rows = list(qs.values(
        'vip_id', 'phone', 'name', 'grade', 'annual_spend',
        'annual_purchase_count', 'points', 'registration_store',
    ))
    for r in rows:
        r['next_grade'], r['amount_to_next_tier'] = next_tier_info(r['grade'], r['annual_spend'])
    if sort == 'amount_to_next_tier':
        rows.sort(key=lambda r: (r['next_grade'] is None, r['amount_to_next_tier']))
    elif sort == 'annual_spend_desc':
        rows.sort(key=lambda r: r['annual_spend'], reverse=True)
    if limit is not None:
        rows = rows[:limit]
    return rows, total_count


def get_live_customer_tier_table(grade_filter=None, shop_filter=None, sort='amount_to_next_tier', limit=500, as_of_date=None):
    """
    Live counterpart to get_customer_tier_table() — reads directly from the
    Customer table, not MembershipSnapshot. PO feedback 2026-08-31: "Customer
    Tier Progress" should reflect current customer data, not a snapshot —
    it has nothing to do with any snapshot batch, so it must work even if
    zero snapshots have ever been taken (e.g. right after this feature is
    deployed, before the next customer upload triggers the first auto-snapshot).

    Applies the exact same grade-resolution convention as
    App/services/membership_snapshot.py::_build_rows() — both call the
    shared customer_utils.resolve_grade() — so these numbers match what the
    next auto-snapshot would record.

    `shop_filter` is an exact match against `registration_store` — the
    membership.html store filter is a <select> of exact DB values
    (registration_stores/snapshot_stores), not free text.

    Same (rows, total_count) / limit=500 contract as get_customer_tier_table().
    """
    from App.models import Customer

    as_of_date = as_of_date or date.today()
    qs = Customer.objects.all()
    if shop_filter:
        qs = qs.filter(registration_store=shop_filter)
    customer_dicts = qs.values('vip_id', 'phone', 'name', 'vip_grade', 'points', 'registration_store')

    spend_map = compute_annual_spend_map(as_of_date)
    zero = {'annual_spend': Decimal('0'), 'annual_purchase_count': 0}

    rows = []
    for c in customer_dicts:
        grade = resolve_grade(c['vip_id'], c['vip_grade'])
        if grade_filter and grade != grade_filter:
            continue
        agg = spend_map.get(_norm_vid(c['vip_id']), zero)
        next_grade, amount_to_next_tier = next_tier_info(grade, agg['annual_spend'])
        rows.append({
            'vip_id': c['vip_id'],
            'phone': c['phone'],
            'name': c['name'],
            'grade': grade,
            'annual_spend': agg['annual_spend'],
            'annual_purchase_count': agg['annual_purchase_count'],
            'points': c['points'],
            'registration_store': c['registration_store'],
            'next_grade': next_grade,
            'amount_to_next_tier': amount_to_next_tier,
        })
    total_count = len(rows)
    if sort == 'amount_to_next_tier':
        rows.sort(key=lambda r: (r['next_grade'] is None, r['amount_to_next_tier']))
    elif sort == 'annual_spend_desc':
        rows.sort(key=lambda r: r['annual_spend'], reverse=True)
    if limit is not None:
        rows = rows[:limit]
    return rows, total_count
