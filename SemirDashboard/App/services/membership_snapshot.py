"""
App/services/membership_snapshot.py

Builds MembershipSnapshotBatch rows (grade_counts/grade_members JSON fields
— see App/models/membership.py docstring). Two entry points share
_build_rows() so the aggregation/write logic is never duplicated:

1. create_auto_snapshot() — snapshots the ENTIRE current Customer table.
   Called from the on_done_fn hook after a successful customer upload
   (App/views/upload.py::upload_customers) — runs in the same background
   thread as the import, so it adds no HTTP latency.

2. create_backfill_snapshot() — parses an uploaded historical file with the
   SAME column format as process_customer_file, via _parse_customer_rows()
   (kept separate from process_customer_file since it must never write to
   the live Customer table). As of 2026-09-02 (PO decision), each row's
   registration_store is overridden with that vip_id's CURRENT live
   Customer.registration_store (via _resolve_live_stores()) rather than the
   file's own column value — see create_backfill_snapshot()'s docstring for
   the full rationale/trade-off.
"""
import logging
from datetime import date

from App.analytics.customer_utils import resolve_grade
from App.services.file_reader import read_file, parse_date, safe_str, safe_int

logger = logging.getLogger(__name__)


def _parse_customer_rows(file, df=None):
    """
    Column-parsing ONLY — no DB write. Same VIP ID / PHONE NO. / NAME /
    VIP GRADE / REGISTRATION DATE / REGISTRATION STORE / POINTS columns as
    App/services/customer_import.py::process_customer_file, kept in sync
    manually since this read-only path must never reuse that function's
    bulk_create/bulk_update transaction logic.
    """
    if df is None:
        df = read_file(file)
    df.columns = df.columns.str.strip().str.upper()
    missing = [h for h in ("VIP ID", "PHONE NO.") if h not in df.columns]
    if missing:
        raise ValueError(f"Missing required column(s): {', '.join(missing)}. Found: {list(df.columns)}")

    parsed = []
    for row in df.to_dict('records'):
        vip_id = safe_str(row.get('VIP ID', ''))
        phone = safe_str(row.get('PHONE NO.', ''))
        if not vip_id or not phone:
            continue
        parsed.append({
            'vip_id': vip_id,
            'phone': phone,
            'name': safe_str(row.get('NAME', '')),
            'vip_grade': safe_str(row.get('VIP GRADE', '')),
            'registration_date': parse_date(row.get('REGISTRATION DATE')),
            'registration_store': safe_str(row.get('REGISTRATION STORE', '')),
            'points': safe_int(row.get('POINTS', 0)),
        })
    return parsed


def _resolve_live_stores(vip_ids):
    """
    Bulk-resolve the CURRENT live Customer.registration_store for a set of
    vip_ids in exactly ONE query (this file processes tens of thousands of
    rows per backfill upload — never loop a per-row query here).

    Returns dict[vip_id] -> registration_store for whichever of the given
    vip_ids currently exist in Customer. vip_ids with no live match are
    simply absent from the returned dict — callers must apply their own
    fallback (create_backfill_snapshot() keeps the file's own value).

    A blank live registration_store is coerced to the canonical '(No Store)'
    placeholder HERE, not left for each caller to remember — matches
    _build_rows()'s own `store_key = c['registration_store'] or '(No
    Store)'` convention. Centralized after a real bug (2026-09-02): the
    normalize_membership_stores management command originally used a raw ''
    value as a by_store dict key instead of '(No Store)', which silently
    diverged from every other store-keying path and broke
    get_grade_changes_store_transitions()'s from_store == to_store
    comparison for the affected vip_id. Coercing once here, instead of at
    each of this function's (currently 2, possibly more later) call sites,
    removes the chance of a future caller forgetting it.
    """
    from App.models import Customer

    rows = Customer.objects.filter(vip_id__in=list(vip_ids)).values_list('vip_id', 'registration_store')
    return {vip_id: (store or '(No Store)') for vip_id, store in rows}


def _build_rows(batch, customer_dicts):
    """
    Aggregates customer_dicts into batch.grade_counts/grade_members (JSON —
    see App/models/membership.py docstring) instead of writing one DB row
    per customer. annual_spend/annual_purchase_count/points are intentionally
    NOT stored here (they were only ever read by the now-deleted
    get_customer_tier_table(); "Customer Tier Progress" reads them live from
    Customer instead) — this is the storage reduction the redesign exists for.
    """
    overall_counts, overall_members = {}, {}
    by_store_counts, by_store_members = {}, {}

    for c in customer_dicts:
        grade = resolve_grade(c['vip_id'], c['vip_grade'])
        store_key = c['registration_store'] or '(No Store)'

        overall_counts[grade] = overall_counts.get(grade, 0) + 1
        overall_members.setdefault(grade, []).append(c['vip_id'])

        store_counts = by_store_counts.setdefault(store_key, {})
        store_counts[grade] = store_counts.get(grade, 0) + 1
        store_members = by_store_members.setdefault(store_key, {})
        store_members.setdefault(grade, []).append(c['vip_id'])

    batch.grade_counts = {'overall': overall_counts, 'by_store': by_store_counts}
    batch.grade_members = {'overall': overall_members, 'by_store': by_store_members}
    batch.row_count = len(customer_dicts)
    batch.save(update_fields=['grade_counts', 'grade_members', 'row_count'])

    from django.core.cache import cache
    cache.delete("membership_batches_dropdown")


def create_auto_snapshot(as_of_date=None, uploaded_by=None):
    from App.models import Customer
    from App.models.membership import MembershipSnapshotBatch

    as_of_date = as_of_date or date.today()
    batch = MembershipSnapshotBatch.objects.create(
        snapshot_date=as_of_date, source='auto', uploaded_by=uploaded_by,
    )
    customer_dicts = list(Customer.objects.values(
        'vip_id', 'phone', 'name', 'vip_grade', 'registration_date', 'registration_store', 'points',
    ))
    _build_rows(batch, customer_dicts)
    logger.info(
        "membership auto-snapshot batch=%s rows=%d as_of=%s",
        batch.id, batch.row_count, as_of_date, extra={"step": "membership_snapshot"},
    )
    return batch


def create_backfill_snapshot(file, progress_fn=None, df=None, *, snapshot_date, uploaded_by=None, note=''):
    """
    Signature matches the fn(file, progress_fn=..., df=...) shape
    App.views.upload._run_upload calls — snapshot_date/uploaded_by/note are
    bound via functools.partial() in the view before _start_thread runs it.
    Never writes to Customer.

    Store attribution (PO decision, 2026-09-02): each row's
    registration_store is overridden with that vip_id's CURRENT live
    Customer.registration_store (_resolve_live_stores()), NOT read literally
    from the uploaded file's own REGISTRATION STORE column. Old historical
    export files can use a completely different store-naming format than the
    live table (confirmed on real data: comparing a manual-import batch
    against an auto-snapshot, only 3 of 39 distinct store names matched
    exactly — the rest were the same physical stores under reformatted
    names, e.g. 'Savico Megamall' vs the live table's
    '巴拉越南河内市SAVICO MEGAMALL-直营店'). The PO's own words: "the live
    Customer table is the latest/authoritative version, and every vip_id's
    store should follow this current store name... use one unified set of
    store names." This is a deliberate trade-off, not an oversight: it makes
    ALL snapshots (auto and manual) share one consistent, current
    store-naming vocabulary for store-level grade comparisons, at the cost
    of losing byte-accurate historical store attribution for the (much
    rarer) case where a customer GENUINELY changed store between the file's
    date and today — that case is now indistinguishable from a mere
    naming-format change and gets silently attributed to the customer's
    current store instead of their true historical one. vip_ids with no live
    Customer match (deleted since, or never re-uploaded) keep the file's own
    registration_store value as the best available information.
    """
    from App.models.membership import MembershipSnapshotBatch

    customer_dicts = _parse_customer_rows(file, df=df)
    live_stores = _resolve_live_stores([c['vip_id'] for c in customer_dicts])
    for c in customer_dicts:
        if c['vip_id'] in live_stores:
            c['registration_store'] = live_stores[c['vip_id']]
    batch = MembershipSnapshotBatch.objects.create(
        snapshot_date=snapshot_date, source='manual_import', uploaded_by=uploaded_by,
        note=note, source_filename=getattr(file, 'name', ''),
    )
    _build_rows(batch, customer_dicts)
    logger.info(
        "membership backfill-snapshot batch=%s rows=%d as_of=%s file=%s",
        batch.id, batch.row_count, snapshot_date, batch.source_filename,
        extra={"step": "membership_snapshot"},
    )
    return {'batch_id': batch.id, 'row_count': batch.row_count}
