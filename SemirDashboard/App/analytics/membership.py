"""
App/analytics/membership.py

Read/aggregation helpers for the Customer Membership snapshot feature.
Business rule constants (grade thresholds, next_tier_info) live in
calculations.py (pure, no DB access) — this module does the DB queries that
feed them. Used by both the snapshot-writing service
(App/services/membership_snapshot.py) and the Membership page views
(App/views/membership.py).
"""
from decimal import Decimal

from django.db.models import Count, Sum

from App.analytics.calculations import next_tier_info
from App.analytics.customer_utils import GRADE_ORDER, _norm_vid

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


def get_grade_breakdown(batch_id):
    """dict[grade] -> count for each DISPLAY_GRADES key (0 if absent). Excludes
    'No Grade' — see DISPLAY_GRADES docstring."""
    from App.models.membership import MembershipSnapshot

    counts = {g: 0 for g in DISPLAY_GRADES}
    if not batch_id:
        return counts
    rows = (
        MembershipSnapshot.objects.filter(batch_id=batch_id, grade__in=DISPLAY_GRADES)
        .values('grade').annotate(cnt=Count('id'))
    )
    for r in rows:
        counts[r['grade']] = counts.get(r['grade'], 0) + r['cnt']
    return counts


def compare_batches(from_batch_id, to_batch_id):
    """Per-grade {from_count, to_count, delta, delta_pct}, ordered by GRADE_ORDER."""
    frm = get_grade_breakdown(from_batch_id)
    to = get_grade_breakdown(to_batch_id)
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


def get_all_batch_grade_series():
    """
    For the Chart.js line chart across ALL snapshots (not just the 2 selected
    on the compare view). Returns a chronological list:
    [{'batch_id', 'snapshot_date', 'source', 'counts': {grade: count}}]
    """
    batches = sorted(list_batches(), key=lambda b: (b.snapshot_date, b.created_at))
    return [
        {
            'batch_id': b.id,
            'snapshot_date': b.snapshot_date.isoformat(),
            'source': b.source,
            'counts': get_grade_breakdown(b.id),
        }
        for b in batches
    ]


def get_customer_tier_table(batch_id, grade_filter=None, shop_filter=None, sort='amount_to_next_tier', limit=500):
    """
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
        # icontains, not exact match — matches the shop-filter convention
        # used everywhere else in the codebase (e.g. coupon_analytics.py's
        # shop_group filter); an exact match against the free-text UI input
        # in membership.html would silently return 0 rows for any partial
        # shop name typed in (found via independent review 2026-08-30).
        qs = qs.filter(registration_store__icontains=shop_filter)
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
