"""
App/services/membership_snapshot.py

Builds MembershipSnapshotBatch + MembershipSnapshot rows. Two entry points
share _build_rows() so the aggregation/write logic is never duplicated:

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

from App.analytics.customer_utils import normalize_grade, _norm_vid
from App.analytics.membership import compute_annual_spend_map
from App.services.file_reader import read_file, parse_date, safe_str, safe_int

logger = logging.getLogger(__name__)
BATCH_SIZE = 1000


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


def _build_rows(batch, customer_dicts, as_of_date):
    from App.models.membership import MembershipSnapshot

    spend_map = compute_annual_spend_map(as_of_date)
    zero = {'annual_spend': 0, 'annual_purchase_count': 0}
    to_create = []
    for c in customer_dicts:
        agg = spend_map.get(_norm_vid(c['vip_id']), zero)
        # VIP ID "0" = buyer without info, excluded from grade analytics
        # everywhere else in the codebase (customer_utils.get_ci, aggregators,
        # core.py, sales_tabs.py) — force 'No Grade' here too regardless of
        # whatever raw vip_grade value the import file happens to carry.
        grade = 'No Grade' if c['vip_id'] == '0' else normalize_grade(c['vip_grade'])
        to_create.append(MembershipSnapshot(
            batch=batch,
            vip_id=c['vip_id'],
            phone=c['phone'],
            name=c['name'],
            grade=grade,
            registration_date=c['registration_date'],
            registration_store=c['registration_store'],
            annual_spend=agg['annual_spend'],
            annual_purchase_count=agg['annual_purchase_count'],
            points=c['points'],
            grade_changed_at=None,
        ))
        if len(to_create) >= BATCH_SIZE:
            MembershipSnapshot.objects.bulk_create(to_create, batch_size=BATCH_SIZE, ignore_conflicts=True)
            to_create = []
    if to_create:
        MembershipSnapshot.objects.bulk_create(to_create, batch_size=BATCH_SIZE, ignore_conflicts=True)

    batch.row_count = len(customer_dicts)
    batch.save(update_fields=['row_count'])

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
    _build_rows(batch, customer_dicts, as_of_date)
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
    _build_rows(batch, customer_dicts, snapshot_date)
    logger.info(
        "membership backfill-snapshot batch=%s rows=%d as_of=%s file=%s",
        batch.id, batch.row_count, snapshot_date, batch.source_filename,
        extra={"step": "membership_snapshot"},
    )
    return {'batch_id': batch.id, 'row_count': batch.row_count}
