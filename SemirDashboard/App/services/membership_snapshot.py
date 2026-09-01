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
   the live Customer table).
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
    """
    from App.models.membership import MembershipSnapshotBatch

    customer_dicts = _parse_customer_rows(file, df=df)
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
