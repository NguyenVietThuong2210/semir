"""
Redesign MembershipSnapshotBatch storage: replace the per-customer
MembershipSnapshot child table (100k rows per batch at 100k customers) with
two JSON fields directly on the batch (grade_counts, grade_members). See
App/models/membership.py::MembershipSnapshotBatch docstring for the full
rationale (storage + trend-chart query-time measurements).

This migration is a one-time LOSSLESS CONVERSION, not a bare drop — any
MembershipSnapshotBatch rows that already exist (real dev/test data
accumulated this session; this feature has not shipped to PROD yet, see
CLAUDE.md) get their per-customer child rows aggregated into the two new
JSON fields before the old table is dropped.
"""
from django.db import migrations, models


def convert_snapshots_to_json(apps, schema_editor):
    MembershipSnapshotBatch = apps.get_model('App', 'MembershipSnapshotBatch')

    for batch in MembershipSnapshotBatch.objects.all():
        overall_counts = {}
        overall_members = {}
        by_store_counts = {}
        by_store_members = {}

        rows = batch.snapshots.values_list('vip_id', 'grade', 'registration_store')
        for vip_id, grade, store in rows:
            store_key = store or '(No Store)'

            overall_counts[grade] = overall_counts.get(grade, 0) + 1
            overall_members.setdefault(grade, []).append(vip_id)

            store_counts = by_store_counts.setdefault(store_key, {})
            store_counts[grade] = store_counts.get(grade, 0) + 1
            store_members = by_store_members.setdefault(store_key, {})
            store_members.setdefault(grade, []).append(vip_id)

        batch.grade_counts = {'overall': overall_counts, 'by_store': by_store_counts}
        batch.grade_members = {'overall': overall_members, 'by_store': by_store_members}
        batch.save(update_fields=['grade_counts', 'grade_members'])


def noop_reverse(apps, schema_editor):
    # Not reversible in practice — the per-customer MembershipSnapshot table
    # is dropped later in this same migration's operations, so there is
    # nothing left to convert back from on a reverse run.
    pass


class Migration(migrations.Migration):

    dependencies = [
        ('App', '0023_alter_cnvorder_customer_code'),
    ]

    operations = [
        migrations.AddField(
            model_name='membershipsnapshotbatch',
            name='grade_counts',
            field=models.JSONField(
                blank=True, default=dict,
                help_text=(
                    "Small (a few KB). {'overall': {grade: count}, 'by_store': "
                    "{store: {grade: count}}}. Keyed by all 5 grades including 'No "
                    "Grade'. Read by every list/chart view (get_grade_breakdown, "
                    "get_grade_breakdown_by_store, get_all_batch_grade_series) via "
                    "`.values('grade_counts')` — deliberately never joined with a read "
                    "of grade_members, so the trend chart's one-query-per-page-load "
                    "stays a few KB regardless of batch count or customer count."
                ),
            ),
        ),
        migrations.AddField(
            model_name='membershipsnapshotbatch',
            name='grade_members',
            field=models.JSONField(
                blank=True, default=dict,
                help_text=(
                    "Large (~1-2MB at 100k customers). Same shape as grade_counts but "
                    "lists of vip_id instead of counts: {'overall': {grade: [vip_id, "
                    "...]}, 'by_store': {store: {grade: [vip_id, ...]}}}. Read ONLY by "
                    "get_grade_changes() (the grade-change diff feature), always exactly "
                    "2 batches at a time — never read for the trend chart/breakdown/"
                    "comparison views, which use grade_counts instead."
                ),
            ),
        ),
        migrations.RunPython(convert_snapshots_to_json, noop_reverse),
        migrations.DeleteModel(
            name='MembershipSnapshot',
        ),
    ]
