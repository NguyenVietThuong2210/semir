"""
App/analytics/membership.py

Read/aggregation helpers for the Customer Membership snapshot feature.
Business rule constants (grade thresholds, next_tier_info) live in
calculations.py (pure, no DB access) — this module does the DB queries that
feed them. Used by both the snapshot-writing service
(App/services/membership_snapshot.py) and the Membership page views
(App/views/membership.py).

Redesigned 2026-09-01: MembershipSnapshotBatch stores per-batch grade
breakdowns as two JSON fields (grade_counts, grade_members) instead of one
DB row per customer — see App/models/membership.py docstring for the full
rationale. Every function below reads ONLY grade_counts (small, a few KB)
EXCEPT get_grade_changes()/_members_bucket() which read grade_members (large,
~1-2MB at 100k customers) — never mix the two in the same query, and never
read grade_members for more than 2 batches at once (see their docstrings).
"""
from datetime import date
from decimal import Decimal

from django.db.models import Count, Sum

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
    Sorted list of every distinct registration_store that appears across ANY
    batch's grade_counts['by_store'] keys — one query, reads only the small
    grade_counts field for every batch. Excludes the literal '(No Store)'
    bucket to match the blank-exclusion convention used by the live-Customer
    dropdown (App/views/shop_detail.py::_get_dropdown_options()).

    Deliberately NOT scoped to the currently-selected From/To batch pair —
    every offered option corresponds to a real store that existed at some
    point, so a 0 for a specific batch pair is genuine information (the store
    didn't have this name yet, or any members, at that snapshot date) rather
    than a picklist/data mismatch. (PO feedback 2026-08-31 — the by-Store and
    trend-chart store filters must NOT reuse the live-Customer-sourced
    `registration_stores` list, since a store's name can differ between live
    data and an older snapshot.)
    """
    from App.models.membership import MembershipSnapshotBatch

    stores = set()
    for grade_counts in MembershipSnapshotBatch.objects.values_list('grade_counts', flat=True):
        stores.update(grade_counts.get('by_store', {}).keys())
    stores.discard('(No Store)')
    return sorted(stores)


def _store_grade_counts_map(batch_id):
    """Internal helper. dict[store] -> {grade: count} for DISPLAY_GRADES, for
    ONE batch — reads only grade_counts (small field)."""
    from App.models.membership import MembershipSnapshotBatch

    if not batch_id:
        return {}
    try:
        grade_counts = MembershipSnapshotBatch.objects.values_list('grade_counts', flat=True).get(pk=batch_id)
    except MembershipSnapshotBatch.DoesNotExist:
        return {}
    by_store = grade_counts.get('by_store', {})
    return {store: {g: counts.get(g, 0) for g in DISPLAY_GRADES} for store, counts in by_store.items()}


def get_grade_breakdown(batch_id, store=None):
    """dict[grade] -> count for each DISPLAY_GRADES key (0 if absent). Excludes
    'No Grade' — see DISPLAY_GRADES docstring.

    `store` optionally scopes the count to one registration_store — exact
    match, since callers pass a value picked from a <select> populated by
    get_snapshot_registration_stores(), not free-text. Pass the literal
    string '(No Store)' to match blank/missing registration_store rows.
    """
    from App.models.membership import MembershipSnapshotBatch

    zero = {g: 0 for g in DISPLAY_GRADES}
    if not batch_id:
        return zero
    try:
        grade_counts = MembershipSnapshotBatch.objects.values_list('grade_counts', flat=True).get(pk=batch_id)
    except MembershipSnapshotBatch.DoesNotExist:
        return zero
    bucket = grade_counts.get('by_store', {}).get(store, {}) if store else grade_counts.get('overall', {})
    return {g: bucket.get(g, 0) for g in DISPLAY_GRADES}


def get_grade_breakdown_by_store(batch_id):
    """
    List of {'store', 'counts': [count_per_DISPLAY_GRADES_in_order], 'total'}
    for ONE batch, sorted by store name. Building block reused by
    get_grade_breakdown_by_store_comparison() (zips two calls' results into
    from/to pairs) — also usable standalone.
    """
    store_map = _store_grade_counts_map(batch_id)
    out = []
    for store in sorted(store_map.keys()):
        counts = store_map[store]
        counts_list = [counts[g] for g in DISPLAY_GRADES]
        total = sum(counts_list)
        if total == 0:
            # A store whose only members are 'No Grade' has nothing in
            # DISPLAY_GRADES — matches the old SQL behavior (grade__in=
            # DISPLAY_GRADES filtered before grouping, so such a store never
            # appeared in the grouped results at all).
            continue
        out.append({'store': store, 'counts': counts_list, 'total': total})
    return out


def get_grade_breakdown_by_store_comparison(from_batch_id, to_batch_id):
    """
    List of {'store', 'counts': [{'grade','from','to'}, ...], 'total_from',
    'total_to'} for the union of stores present in either batch, sorted by
    store name. Powers the "Members per Grade — by Registration Store"
    matrix's From/To columns (PO feedback 2026-09-01) — replaced the old
    single-store drill-down comparison mode, now redundant since this matrix
    already shows from/to per store and get_grade_changes() shows the actual
    individual customers who moved.
    """
    from_map = _store_grade_counts_map(from_batch_id)
    to_map = _store_grade_counts_map(to_batch_id)
    zero = {g: 0 for g in DISPLAY_GRADES}
    stores = sorted(set(from_map) | set(to_map))
    out = []
    for store in stores:
        f = from_map.get(store, zero)
        t = to_map.get(store, zero)
        total_from, total_to = sum(f.values()), sum(t.values())
        if total_from == 0 and total_to == 0:
            # A store whose only members are 'No Grade' on both sides has
            # nothing in DISPLAY_GRADES on either side — matches
            # get_grade_breakdown_by_store()'s exclusion (see its comment).
            continue
        counts = [{'grade': g, 'from': f[g], 'to': t[g]} for g in DISPLAY_GRADES]
        out.append({
            'store': store,
            'counts': counts,
            'total_from': total_from,
            'total_to': total_to,
        })
    return out


def compare_batches(from_batch_id, to_batch_id, store=None):
    """Per-grade {from_count, to_count, delta, delta_pct}, ordered by GRADE_ORDER.
    `store` optionally scopes both sides to one registration_store — see
    get_grade_breakdown() docstring."""
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

    `store` optionally scopes every batch's counts to one registration_store.

    ONE query fetching only the small grade_counts field for every batch —
    never touches grade_members (the large per-customer vip_id-list field).
    This is what keeps trend-chart load time bounded by BATCH COUNT (a few KB
    each) rather than TOTAL ACCUMULATED CUSTOMER-ROWS — the old per-customer-
    row design degraded to a full Postgres Sequential Scan once total rows
    got large (measured: ~60s projected after 5 years of daily snapshots at
    100k customers), which storing only counts (not full per-customer rows)
    per batch avoids entirely, independent of how long the snapshot history
    grows. See App/models/membership.py docstring for the full measurement.
    """
    from App.models.membership import MembershipSnapshotBatch

    batches = MembershipSnapshotBatch.objects.order_by('snapshot_date', 'created_at').values(
        'id', 'snapshot_date', 'source', 'grade_counts',
    )
    out = []
    for b in batches:
        grade_counts = b['grade_counts']
        bucket = grade_counts.get('by_store', {}).get(store, {}) if store else grade_counts.get('overall', {})
        out.append({
            'batch_id': b['id'],
            'snapshot_date': b['snapshot_date'].isoformat(),
            'source': b['source'],
            'counts': {g: bucket.get(g, 0) for g in DISPLAY_GRADES},
        })
    return out


def _members_bucket(batch_id, store=None):
    """Internal helper. dict[grade] -> [vip_id, ...] for ONE batch, optionally
    scoped to one store — reads grade_members (the LARGE JSON field). Only
    ever call this for exactly 2 batches at a time (get_grade_changes) —
    never in a loop across many batches, which would reintroduce the
    O(total accumulated data) cost this redesign exists to avoid."""
    from App.models.membership import MembershipSnapshotBatch

    if not batch_id:
        return {}
    try:
        grade_members = MembershipSnapshotBatch.objects.values_list('grade_members', flat=True).get(pk=batch_id)
    except MembershipSnapshotBatch.DoesNotExist:
        return {}
    if store:
        return grade_members.get('by_store', {}).get(store, {})
    return grade_members.get('overall', {})


def get_grade_changes(from_batch_id, to_batch_id, store=None, grade=None, direction=None, limit=20, offset=0):
    """
    Customers whose grade CHANGED between from_batch and to_batch — added
    2026-09-01, PO feedback: the vip_id-list storage (grade_members) exists
    specifically to enable this. A customer present in only ONE of the two
    batches (new customer, or removed) is a different kind of event, not
    counted here — both sides must have the vip_id.

    Excludes VIP ID "0" (buyer without info, excluded from grade analytics
    everywhere in the codebase) and any transition involving 'No Grade' on
    either side (matches the DISPLAY_GRADES convention used by every other
    grade-level view on this page — 'No Grade' is noise, not an actionable
    tier change).

    `store` scopes both sides to one registration_store (a customer who
    changed store between the two snapshots would only show up if they were
    in that store in BOTH — reasonable given the feature answers "who changed
    grade at this store", not a customer-relocation report).
    `grade` filters on the customer's NEW (to) grade — deliberately a single
    filter, not separate old/new-grade filters: e.g. grade='Silver' shows
    BOTH Member->Silver upgrades and Gold->Silver downgrades, disambiguated
    per-row by `direction`.
    `direction` is 'upgrade' or 'downgrade'.

    Returns (rows, total_count) — same contract as get_live_customer_tier_table.
    The full filtered set is computed once (cheap — Python dict/set
    operations over at most ~100k entries, not a per-page DB query), THEN
    sliced by `offset`/`limit` — so `total_count` is always the true total,
    not just the current page size.

    `name`/`phone`/`registration_store` are joined from the LIVE Customer
    table for display only (not stored per-snapshot — matches the
    get_live_customer_tier_table precedent, and avoids roughly doubling
    grade_members' JSON size) — may be stale or missing if the customer's
    details changed, or the customer was deleted, since the snapshot was taken.
    """
    from App.models import Customer

    from_bucket = _members_bucket(from_batch_id, store)
    to_bucket = _members_bucket(to_batch_id, store)

    from_grade_of = {vid: g for g, vids in from_bucket.items() for vid in vids}
    to_grade_of = {vid: g for g, vids in to_bucket.items() for vid in vids}

    changed = []
    for vid in from_grade_of.keys() & to_grade_of.keys():
        if vid == '0':
            continue
        g_from, g_to = from_grade_of[vid], to_grade_of[vid]
        if g_from == g_to:
            continue
        if g_from not in DISPLAY_GRADES or g_to not in DISPLAY_GRADES:
            continue
        dirn = 'upgrade' if GRADE_ORDER[g_to] > GRADE_ORDER[g_from] else 'downgrade'
        if grade and g_to != grade:
            continue
        if direction and direction != dirn:
            continue
        changed.append({'vip_id': vid, 'from_grade': g_from, 'to_grade': g_to, 'direction': dirn})

    changed.sort(key=lambda r: r['vip_id'])
    total_count = len(changed)
    page = changed[offset:offset + limit] if limit is not None else changed[offset:]

    cust_map = {
        c['vip_id']: c
        for c in Customer.objects.filter(vip_id__in=[r['vip_id'] for r in page])
        .values('vip_id', 'name', 'phone', 'registration_store')
    }
    for r in page:
        c = cust_map.get(r['vip_id'])
        r['name'] = c['name'] if c else None
        r['phone'] = c['phone'] if c else None
        r['registration_store'] = c['registration_store'] if c else store

    return page, total_count


def get_live_customer_tier_table(grade_filter=None, shop_filter=None, sort='amount_to_next_tier', limit=500, as_of_date=None):
    """
    Reads directly from the Customer table, not any snapshot batch. PO
    feedback 2026-08-31: "Customer Tier Progress" should reflect current
    customer data — it has nothing to do with any snapshot batch, so it must
    work even if zero snapshots have ever been taken (e.g. right after this
    feature is deployed, before the next customer upload triggers the first
    auto-snapshot).

    Applies the exact same grade-resolution convention as
    App/services/membership_snapshot.py::_build_rows() — both call the
    shared customer_utils.resolve_grade() — so these numbers match what the
    next auto-snapshot would record.

    `shop_filter` is an exact match against `registration_store` — the
    membership.html store filter is a <select> of exact DB values, not free
    text.

    Returns (rows, total_count). `limit` caps the returned row list (default
    500); pass limit=None for the full unfiltered set.
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
