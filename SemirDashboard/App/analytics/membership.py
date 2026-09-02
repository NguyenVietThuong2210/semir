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
EXCEPT get_grade_changes()/get_grade_changes_overview_by_store()/
get_grade_changes_store_transitions()/_grade_members_json()/_vid_store_map()
which read grade_members (large, ~1-2MB at 100k customers) — never mix the
two in the same query, and never read grade_members for more than 2 batches
at once (see their docstrings).
"""
from datetime import date
from decimal import Decimal

from django.db.models import Count, Sum

from App.analytics.calculations import GRADE_DOWNGRADE_MIN_ANNUAL_PURCHASES, next_tier_info
from App.analytics.customer_utils import GRADE_ORDER, _norm_vid, resolve_grade
from App.analytics.grade_simulation import count_invoices_in_trailing_window

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
    'total_to', 'is_total'} for the union of stores present in either batch,
    sorted by store name, PLUS a final 'All Stores' row (is_total=True).
    Powers the "Members per Grade — by Registration Store" matrix's From/To
    columns (PO feedback 2026-09-01) — replaced the old single-store
    drill-down comparison mode, now redundant since this matrix already
    shows from/to per store and get_grade_changes() shows the actual
    individual customers who moved.

    The trailing 'All Stores' row (added 2026-09-01) is computed via
    get_grade_breakdown(from_batch_id)/get_grade_breakdown(to_batch_id) with
    no store= arg — i.e. the 'overall' bucket, the same authoritative
    all-stores source compare_batches() already uses — NOT a sum of the
    per-store rows above.
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
            'is_total': False,
        })

    overall_from = get_grade_breakdown(from_batch_id)
    overall_to = get_grade_breakdown(to_batch_id)
    overall_counts = [{'grade': g, 'from': overall_from[g], 'to': overall_to[g]} for g in DISPLAY_GRADES]
    out.append({
        'store': 'All Stores',
        'is_total': True,
        'counts': overall_counts,
        'total_from': sum(overall_from.values()),
        'total_to': sum(overall_to.values()),
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


def _grade_members_json(batch_id):
    """Internal helper. Fetches the WHOLE grade_members JSON field ONCE for
    ONE batch_id — mirrors _store_grade_counts_map()'s "fetch once, slice in
    Python" pattern for the smaller grade_counts field, applied here to the
    large grade_members field instead. Returns the raw
    {'overall': {grade: [vip_id,...]}, 'by_store': {store: {grade: [...]}}}
    dict, or {} if batch_id is falsy/missing.

    Exists specifically so get_grade_changes()/get_grade_changes_overview_by_store()/
    get_grade_changes_store_transitions() can compute an across-ALL-stores
    aggregate with exactly ONE query per batch, instead of one query PER
    STORE (looping a per-store fetch over ~30-40 stores would mean ~60-80
    queries for one page section). Callers slice per-store data out of the
    already-fetched dict in Python (see _vid_store_map() for the
    vip_id -> store reverse-index built the same way) — no further DB access."""
    from App.models.membership import MembershipSnapshotBatch

    if not batch_id:
        return {}
    try:
        return MembershipSnapshotBatch.objects.values_list('grade_members', flat=True).get(pk=batch_id)
    except MembershipSnapshotBatch.DoesNotExist:
        return {}


def _vid_store_map(grade_members_json):
    """Internal helper. dict[vip_id] -> store_name, built by iterating an
    ALREADY-FETCHED grade_members JSON dict's 'by_store' bucket (for each
    store, for each grade's vip_id list, map vip_id -> that store name). Pure
    Python over already-fetched data — no DB access — same "fetch once, slice
    in Python" discipline as _grade_members_json() itself.

    Used by get_grade_changes() (to attach from_store/to_store to each row)
    and get_grade_changes_store_transitions() (to group changes by
    (from_store, to_store) pair) so a changed vip_id's per-snapshot store can
    be recovered without a second query. A vip_id missing from every store's
    list (shouldn't normally happen — _add_snapshot_member always writes both
    'overall' and 'by_store') simply has no entry in the returned dict;
    callers use `.get(vid)` and treat a missing key as unknown (None)."""
    out = {}
    for store, grades in grade_members_json.get('by_store', {}).items():
        for vids in grades.values():
            for vid in vids:
                out[vid] = store
    return out


def _diff_grade_changes(from_bucket, to_bucket):
    """Internal helper — the vip_id-diff logic shared by get_grade_changes()
    and get_grade_changes_overview_by_store(), factored out so the two
    features can never disagree on what counts as a "grade change".
    `from_bucket`/`to_bucket` are already-fetched {grade: [vip_id,...]}
    dicts (no DB access here). Returns an unsorted, unfiltered, unpaged list
    of {'vip_id', 'from_grade', 'to_grade', 'direction'} — same per-row shape
    get_grade_changes() returns before its grade=/direction= filtering.

    Excludes VIP ID "0" (buyer without info, excluded from grade analytics
    everywhere in the codebase) and any transition involving 'No Grade' on
    either side (DISPLAY_GRADES convention — 'No Grade' is noise, not an
    actionable tier change). A vip_id present in only one bucket is a
    different kind of event (new/removed customer), not a grade change, and
    is naturally excluded by the `&` intersection below."""
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
        changed.append({'vip_id': vid, 'from_grade': g_from, 'to_grade': g_to, 'direction': dirn})
    return changed


def get_grade_changes_overview_by_store(from_batch_id, to_batch_id):
    """
    Aggregate overview for the "Comparison — Members Who Changed Grade"
    section (sits above the individual-customer list get_grade_changes()
    powers): for every store and every DISPLAY_GRADES grade, how many
    customers' NEW (to) grade is that grade, split downgrade vs upgrade.
    Reuses _diff_grade_changes() — the exact same diff logic get_grade_changes()
    uses (vip_id-in-both-buckets, exclude vid '0', exclude non-DISPLAY_GRADES
    transitions) — so the two features never disagree on what counts as a
    change.

    Performance: exactly 2 DB queries total, one per batch (via
    _grade_members_json()) — NOT one query per store. See
    _grade_members_json()'s docstring for why that matters (~30-40 stores on
    this page would otherwise mean ~60-80 queries).

    Returns a flat list, each element:
    {'store': str, 'counts': [{'grade','downgrade','upgrade'}, ...] (one per
    DISPLAY_GRADES), 'total_downgrade': int, 'total_upgrade': int,
    'is_total': bool}, sorted by store name, PLUS a final 'All Stores' row
    (is_total=True) computed directly from the 'overall' bucket of each
    batch's grade_members — NOT a sum of the per-store rows, matching how
    get_grade_breakdown()/get_grade_breakdown_by_store_comparison() treat
    'overall' as the authoritative all-stores figure rather than a derived
    sum.

    Unlike get_grade_breakdown_by_store()'s "No Grade"-only-store exclusion,
    a store with configured members but ZERO grade changes between the two
    batches is still meaningful and is NEVER excluded here — that other
    exclusion is about a store having zero real-grade MEMBERS at all, a
    different condition from zero CHANGES.

    Returns [] if from_batch_id or to_batch_id is falsy/missing (matches
    get_grade_changes()'s behavior with a missing batch — no 'All Stores'
    row either in that case).
    """
    if not from_batch_id or not to_batch_id:
        return []

    from_json = _grade_members_json(from_batch_id)  # 1 query
    to_json = _grade_members_json(to_batch_id)      # 1 query

    from_by_store = from_json.get('by_store', {})
    to_by_store = to_json.get('by_store', {})
    stores = sorted(set(from_by_store) | set(to_by_store))

    def _counts_for(from_bucket, to_bucket):
        changed = _diff_grade_changes(from_bucket, to_bucket)
        upgrade = {g: 0 for g in DISPLAY_GRADES}
        downgrade = {g: 0 for g in DISPLAY_GRADES}
        for r in changed:
            bucket = upgrade if r['direction'] == 'upgrade' else downgrade
            bucket[r['to_grade']] += 1
        counts = [{'grade': g, 'downgrade': downgrade[g], 'upgrade': upgrade[g]} for g in DISPLAY_GRADES]
        return counts, sum(downgrade.values()), sum(upgrade.values())

    out = []
    for store in stores:
        counts, total_downgrade, total_upgrade = _counts_for(
            from_by_store.get(store, {}), to_by_store.get(store, {}),
        )
        out.append({
            'store': store,
            'counts': counts,
            'total_downgrade': total_downgrade,
            'total_upgrade': total_upgrade,
            'is_total': False,
        })

    overall_counts, overall_total_downgrade, overall_total_upgrade = _counts_for(
        from_json.get('overall', {}), to_json.get('overall', {}),
    )
    out.append({
        'store': 'All Stores',
        'is_total': True,
        'counts': overall_counts,
        'total_downgrade': overall_total_downgrade,
        'total_upgrade': overall_total_upgrade,
    })
    return out


def get_grade_changes_store_transitions(from_batch_id, to_batch_id):
    """
    Itemized appendix to get_grade_changes_overview_by_store() (added 2026-09,
    PO feedback): that table only attributes a grade change to a store when
    the customer's recorded registration_store is the LITERAL SAME string in
    both the from- and to-snapshot's grade_members — a customer whose store
    name drifted between the two snapshots (e.g. an intervening customer
    re-import that changed store-name formatting, 'Savico Megamall' (old) vs
    the Vietnamese-branded name for the exact same physical store (new)) is
    correctly excluded from every per-store row there, and only shows up in
    that table's 'All Stores' total — invisible in the per-store breakdown.
    This function makes exactly those "invisible" changes visible: it groups
    them explicitly by their (from_store, to_store) pair instead of requiring
    an exact match, so a store-name rename shows up as its own row rather
    than disappearing.

    Reuses the exact same diff as get_grade_changes()/
    get_grade_changes_overview_by_store() — _diff_grade_changes() over each
    batch's 'overall' bucket — and the same _vid_store_map() reverse-index
    used by get_grade_changes() to recover each changed vip_id's per-snapshot
    store. Rows where from_store == to_store (same store both times — already
    correctly attributed by get_grade_changes_overview_by_store()) are
    skipped; this function exists specifically to surface the REMAINDER, so
    it is a strict partition of "changes NOT captured by the main per-store
    table" — see the reconciliation test in tests/test_membership.py, which
    asserts summing this function's total_downgrade/total_upgrade across all
    rows, plus summing get_grade_changes_overview_by_store()'s non-total-row
    totals, exactly equals its 'All Stores' row's totals.

    A missing/blank store on either side of a pair is the literal string
    '(No Store)' (matches the blank-store convention used everywhere else in
    this file, e.g. _add_snapshot_member()/get_snapshot_registration_stores()).

    Performance: exactly 2 DB queries total, one per batch (via
    _grade_members_json()) — same discipline as get_grade_changes_overview_by_store().

    Returns a flat list, each element:
    {'from_store': str, 'to_store': str, 'counts': [{'grade','downgrade',
    'upgrade'}, ...] (one per DISPLAY_GRADES), 'total_downgrade': int,
    'total_upgrade': int}, sorted by (total_downgrade + total_upgrade)
    descending — most-impactful renames first, since a real dataset can have
    dozens of distinct from->to pairs and only a handful matter. No
    'is_total'/'All Stores' row here — this is an itemized appendix, not a
    summary matrix; get_grade_changes_overview_by_store()'s 'All Stores' row
    remains the single source of truth for the true total.

    Returns [] if from_batch_id or to_batch_id is falsy/missing (matches
    get_grade_changes()/get_grade_changes_overview_by_store()).
    """
    if not from_batch_id or not to_batch_id:
        return []

    from_json = _grade_members_json(from_batch_id)  # 1 query
    to_json = _grade_members_json(to_batch_id)      # 1 query

    changed = _diff_grade_changes(from_json.get('overall', {}), to_json.get('overall', {}))
    from_store_of = _vid_store_map(from_json)
    to_store_of = _vid_store_map(to_json)

    groups = {}
    for r in changed:
        from_store = from_store_of.get(r['vip_id']) or '(No Store)'
        to_store = to_store_of.get(r['vip_id']) or '(No Store)'
        if from_store == to_store:
            # Already correctly attributed by get_grade_changes_overview_by_store() —
            # this function exists specifically to surface the remainder.
            continue
        groups.setdefault((from_store, to_store), []).append(r)

    def _counts_for(rows):
        # Same 4-line counting body as get_grade_changes_overview_by_store()'s
        # nested _counts_for() — that one starts from two raw grade_members
        # buckets and calls _diff_grade_changes() itself; this one starts
        # from an already-diffed row list (a (from_store, to_store) pair
        # isn't representable as a single grade_members bucket to re-diff),
        # but the counting logic below must not diverge from it.
        upgrade = {g: 0 for g in DISPLAY_GRADES}
        downgrade = {g: 0 for g in DISPLAY_GRADES}
        for r in rows:
            bucket = upgrade if r['direction'] == 'upgrade' else downgrade
            bucket[r['to_grade']] += 1
        counts = [{'grade': g, 'downgrade': downgrade[g], 'upgrade': upgrade[g]} for g in DISPLAY_GRADES]
        return counts, sum(downgrade.values()), sum(upgrade.values())

    out = []
    for (from_store, to_store), rows in groups.items():
        counts, total_downgrade, total_upgrade = _counts_for(rows)
        out.append({
            'from_store': from_store,
            'to_store': to_store,
            'counts': counts,
            'total_downgrade': total_downgrade,
            'total_upgrade': total_upgrade,
        })
    out.sort(key=lambda r: r['total_downgrade'] + r['total_upgrade'], reverse=True)
    return out


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

    Refactored 2026-09 to read each batch's WHOLE grade_members JSON once via
    _grade_members_json() (still exactly 2 queries total, one per batch — the
    same count as the old _members_bucket()-per-side approach) and ALWAYS
    diff the 'overall' buckets, never a store-scoped bucket — see `store`
    below for why. Each row also carries `from_store`/`to_store` (the
    customer's registration_store as recorded in the from-snapshot's and
    to-snapshot's grade_members['by_store'] JSON respectively, via the
    internal _vid_store_map() helper, built from the same already-fetched
    JSON — no extra queries). Either may be `None` if the vip_id has no
    by_store entry in that snapshot (shouldn't normally happen). These are
    NEW fields, independent of the live-Customer-joined `registration_store`
    field below (which is unchanged).

    `store` filters the result POST-HOC with OR semantics (changed 2026-09):
    a row is kept if `store is None or row['from_store'] == store or
    row['to_store'] == store`. Previously `store` scoped BOTH the from- and
    to-buckets to that store BEFORE diffing, which meant a customer whose
    recorded store differed between the two snapshots (e.g. a customer
    re-import that changed store-name formatting — 'Savico Megamall' (old) vs
    the Vietnamese-branded name for the exact same physical store (new)) was
    invisible under ANY store filter, since their vip_id was never in the
    same store's bucket on both sides — exactly the customers this filter
    most needs to surface. See get_grade_changes_store_transitions() for the
    dedicated (from_store, to_store) pair breakdown of these drift cases.
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

    from_json = _grade_members_json(from_batch_id)  # 1 query
    to_json = _grade_members_json(to_batch_id)       # 1 query

    changed = _diff_grade_changes(from_json.get('overall', {}), to_json.get('overall', {}))

    from_store_of = _vid_store_map(from_json)
    to_store_of = _vid_store_map(to_json)
    for r in changed:
        r['from_store'] = from_store_of.get(r['vip_id'])
        r['to_store'] = to_store_of.get(r['vip_id'])

    if grade:
        changed = [r for r in changed if r['to_grade'] == grade]
    if direction:
        changed = [r for r in changed if r['direction'] == direction]
    if store:
        changed = [r for r in changed if r['from_store'] == store or r['to_store'] == store]

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


def _grade_progress_map(vip_ids):
    """Internal helper. ONE query: CustomerGradeProgress rows for exactly the
    given vip_ids -> dict[vip_id] -> row dict. Used by
    get_live_customer_tier_table() both for its date-based sort modes (whole
    filtered set) and its per-row enrichment (page only) — see that
    function's docstring for which scope each caller passes."""
    from App.models.membership import CustomerGradeProgress

    if not vip_ids:
        return {}
    rows = CustomerGradeProgress.objects.filter(vip_id__in=vip_ids).values(
        'vip_id', 'last_grade_change_date', 'change_direction', 'simulated_grade', 'status', 'next_check_date',
    )
    return {r['vip_id']: r for r in rows}


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

    Each row also carries the grade-change-date feature's fields (2026-09-02,
    App/services/grade_progress_calc.py::compute_all_grade_progress — see
    that module for how CustomerGradeProgress is computed):
      - grade_progress_status: 'ok' | 'mismatch' | 'no_data' | 'not_computed'
        ('not_computed' means the compute-grade-progress job has never been
        run for this vip_id at all — no CustomerGradeProgress row exists).
      - last_grade_change_date / change_direction: populated ONLY when
        grade_progress_status == 'ok' (None otherwise) — a 'mismatch' row's
        simulated date is not trustworthy for display, per
        CustomerGradeProgress's docstring; this function is the "caller"
        responsible for hiding it from the UI.
      - next_check_date: date, or None if status != 'ok' or the current grade
        has no downgrade floor — the customer's next scheduled downgrade
        anniversary check (CustomerGradeProgress.next_check_date; NOT simply
        last_grade_change_date + 365, see that field's docstring), shown in
        the UI as the expected downgrade review date.
      - purchases_needed_to_avoid_downgrade: int, or None if status != 'ok'
        or if the customer's current grade has no downgrade floor (Member /
        No Grade — GRADE_DOWNGRADE_MIN_ANNUAL_PURCHASES.get(grade) is None).
        Computed against the customer's TRUE next anniversary check window
        (CustomerGradeProgress.next_check_date), not a naive "365 days ending
        today" window — see that field's docstring for why the two differ.

    `sort` accepts `<field>_asc` / `<field>_desc` for any of: vip_id, grade,
    annual_spend, annual_purchase_count, points, amount_to_next_tier,
    last_grade_change_date, next_check_date, purchases_needed_to_avoid_downgrade.
    The bare string 'amount_to_next_tier' (no suffix) is kept as a legacy
    alias for 'amount_to_next_tier_asc' (the original default before
    per-column sort existed). Any other/unrecognized value falls back to
    that same default.
    Rows where the sort field doesn't apply (no CustomerGradeProgress yet,
    Diamond has no next tier, current grade has no downgrade floor, etc.)
    always sort last regardless of direction — never silently reordered to
    the top by an arbitrary None/0 comparison.
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
        sort = 'amount_to_next_tier_asc'  # legacy alias, see docstring
    _progress_date_fields = ('last_grade_change_date', 'next_check_date')
    _special_fields = _progress_date_fields + ('purchases_needed_to_avoid_downgrade', 'amount_to_next_tier')
    field, _, direction = (sort or '').rpartition('_')
    reverse = direction == 'desc'
    if field not in _PLAIN_SORT_KEYS and field not in _special_fields:
        field, reverse = 'amount_to_next_tier', False

    # last_grade_change_date / next_check_date / purchases_needed_to_avoid_downgrade
    # all need CustomerGradeProgress data (and purchases_needed additionally
    # needs SalesTransaction invoice dates) across the WHOLE filtered set to
    # sort correctly — not just the eventual page — since the page is
    # whatever `limit` rows land on TOP after sorting. Every other sort field
    # only touches values already computed above, so this fetch is skipped
    # for those (avoids querying CustomerGradeProgress/SalesTransaction for
    # up to ~75k customers on every page load — only when these specific
    # sorts are actually requested).
    needs_progress_for_sort = field in _progress_date_fields or field == 'purchases_needed_to_avoid_downgrade'
    # amount_to_next_tier needs its own explicit branch (below), NOT a plain
    # `rows.sort(key=..., reverse=True)`: its key is a tuple
    # `(next_grade is None, amount)` so Diamond/no-next-tier rows always sort
    # last on the ASCENDING default -- but Python's reverse=True flips the
    # WHOLE tuple including that leading group flag, so under descending sort
    # those same rows would incorrectly jump to the FRONT instead of staying
    # last (2026-09-02 code review finding, same bug class as the original
    # purchases_needed_to_avoid_downgrade blocker this dispatch was
    # rewritten to fix -- must use the same manual (0/1, +/-value) scheme
    # as the other "some rows don't apply" fields instead of reverse=True).
    progress_map = _grade_progress_map([r['vip_id'] for r in rows]) if needs_progress_for_sort else None

    if field in _progress_date_fields:
        def _sort_key(r):
            p = progress_map.get(r['vip_id'])
            d = p[field] if p and p['status'] == 'ok' else None
            if d is None:
                return (1, 0)  # None/not-computed always sorts last, either direction
            ordinal = d.toordinal()
            return (0, -ordinal if reverse else ordinal)
        rows.sort(key=_sort_key)
    elif field == 'purchases_needed_to_avoid_downgrade':
        # Compute the figure for the WHOLE filtered set (not just the page) —
        # bounded to customers where it's even applicable (status='ok' AND
        # current grade has a downgrade floor), typically a small fraction of
        # the total (e.g. Silver/Gold/Diamond only, excluding Member/No
        # Grade), so this stays a single grouped query, not one query per
        # customer or a full-table scan.
        eligible_vip_ids = [
            r['vip_id'] for r in rows
            if (progress_map.get(r['vip_id']) or {}).get('status') == 'ok'
            and GRADE_DOWNGRADE_MIN_ANNUAL_PURCHASES.get(r['grade']) is not None
        ]
        invoice_dates_by_vip = _invoice_dates_by_vip(eligible_vip_ids)
        needed_map = {}
        for vid in eligible_vip_ids:
            grade = next(r['grade'] for r in rows if r['vip_id'] == vid)
            min_req = GRADE_DOWNGRADE_MIN_ANNUAL_PURCHASES[grade]
            progress = progress_map.get(vid) or {}
            check_date = progress.get('next_check_date') or as_of_date
            cnt = count_invoices_in_trailing_window(invoice_dates_by_vip.get(vid, []), check_date)
            needed_map[vid] = max(0, min_req - cnt)

        def _sort_key(r):
            n = needed_map.get(r['vip_id'])
            if n is None:
                return (1, 0)  # not applicable always sorts last, either direction
            return (0, -n if reverse else n)
        rows.sort(key=_sort_key)
    elif field == 'amount_to_next_tier':
        def _sort_key(r):
            if r['next_grade'] is None:
                return (1, Decimal('0'))  # Diamond/no-next-tier always sorts last, either direction
            amt = r['amount_to_next_tier']
            return (0, -amt if reverse else amt)
        rows.sort(key=_sort_key)
    else:
        rows.sort(key=_PLAIN_SORT_KEYS[field], reverse=reverse)

    if limit is not None:
        rows = rows[:limit]

    # Grade-progress enrichment for DISPLAY — ONE query for exactly the
    # page's vip_ids (post-slice), per this module's convention of never
    # running an unbounded per-row query. Reuses progress_map if a sort
    # above already fetched it for the whole filtered set (now sliced to
    # this same page) — cheap dict lookups, no second query in that case.
    page_vip_ids = [r['vip_id'] for r in rows]
    if progress_map is None:
        progress_map = _grade_progress_map(page_vip_ids)

    ok_vip_ids = [
        vid for vid in page_vip_ids
        if (progress_map.get(vid) or {}).get('status') == 'ok'
    ]
    invoice_dates_by_vip = _invoice_dates_by_vip(ok_vip_ids)

    for r in rows:
        progress = progress_map.get(r['vip_id'])
        status = progress['status'] if progress else 'not_computed'
        r['grade_progress_status'] = status
        if status == 'ok':
            r['last_grade_change_date'] = progress['last_grade_change_date']
            r['change_direction'] = progress['change_direction'] or None
            r['next_check_date'] = progress['next_check_date']
            min_req = GRADE_DOWNGRADE_MIN_ANNUAL_PURCHASES.get(r['grade'])
            if min_req is None:
                r['purchases_needed_to_avoid_downgrade'] = None
            else:
                check_date = progress.get('next_check_date') or as_of_date
                cnt = count_invoices_in_trailing_window(
                    invoice_dates_by_vip.get(r['vip_id'], []), check_date,
                )
                r['purchases_needed_to_avoid_downgrade'] = max(0, min_req - cnt)
        else:
            r['last_grade_change_date'] = None
            r['change_direction'] = None
            r['next_check_date'] = None
            r['purchases_needed_to_avoid_downgrade'] = None

    return rows, total_count


_PLAIN_SORT_KEYS = {
    'vip_id': lambda r: r['vip_id'],
    'grade': lambda r: GRADE_ORDER.get(r['grade'], -1),
    'annual_spend': lambda r: r['annual_spend'],
    'annual_purchase_count': lambda r: r['annual_purchase_count'],
    'points': lambda r: r['points'],
}


def _invoice_dates_by_vip(vip_ids):
    """Internal helper. ONE grouped query: for exactly the given vip_ids,
    return dict[vip_id] -> sorted list of DISTINCT-invoice dates (earliest
    line-item date per invoice_number — same convention as
    grade_simulation.load_customer_transactions()'s invoices_by_vip). Used
    by get_live_customer_tier_table() for the live "purchases needed" figure,
    both when sorting by it (whole filtered set) and when displaying it
    (page only) — callers pass whichever vip_id scope they need."""
    if not vip_ids:
        return {}
    from App.models import SalesTransaction

    txn_rows = (
        SalesTransaction.objects
        .filter(vip_id__in=vip_ids)
        .order_by()
        .values('vip_id', 'invoice_number', 'sales_date')
    )
    earliest_by_invoice = {}
    for t in txn_rows:
        key = (t['vip_id'], t['invoice_number'])
        d = t['sales_date']
        if key not in earliest_by_invoice or d < earliest_by_invoice[key]:
            earliest_by_invoice[key] = d
    invoice_dates_by_vip = {}
    for (vid, _inv), d in earliest_by_invoice.items():
        invoice_dates_by_vip.setdefault(vid, []).append(d)
    for dates in invoice_dates_by_vip.values():
        dates.sort()
    return invoice_dates_by_vip
