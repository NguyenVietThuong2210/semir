"""
App/management/commands/normalize_membership_stores.py

One-time data-correction command: retroactively normalizes EXISTING
MembershipSnapshotBatch rows' `by_store` attribution to the CURRENT live
Customer.registration_store for each vip_id — the same rule
App/services/membership_snapshot.py::create_backfill_snapshot() now applies
to FUTURE manual-import backfills (via the shared _resolve_live_stores()
helper, see that function's docstring for the full PO rationale).

Problem (PO's own words, translated): "The live Customer table is the
latest/authoritative version — every vip_id's store should follow this
current store name. An old store name has no meaning. Convert everything to
the current store name... use one unified set of stores." Batches created
via source='manual_import' (the "Backfill a Historical Snapshot" feature —
a PO uploads an old customer-export file for a past date) before the
2026-09-02 fix have their by_store breakdown keyed by whatever store-name
FORMAT that specific old file happened to use — which can differ wildly from
the CURRENT live Customer.registration_store for the exact same physical
store (confirmed on real data: comparing a Dec-2025 manual-import batch
against a Jul-2026 auto-snapshot, only 3 of 39 distinct store names matched
exactly — the rest were the same physical stores reformatted, e.g.
'Savico Megamall' vs '巴拉越南河内市SAVICO MEGAMALL-直营店'). Automatic
batches (source='auto') already read registration_store straight from the
live Customer table at creation time and normally don't need correction —
excluded from the default scope, see --include-auto.

Only each batch's ALREADY-STORED `grade_members['overall']` (vip_id -> grade)
is used to reconstruct its customer list — the original uploaded file is not
persisted anywhere, so this JSON blob is the only surviving record of who
was in the batch and at what grade. Only `by_store` is rebuilt; `overall`
grade counts/members are never touched (store attribution has no bearing on
grade). For a vip_id no longer present in the live Customer table (deleted
since, or never re-uploaded), its store is left exactly as this batch
already has it recorded — never dropped, never blanked.

Usage:
    # Dry run (default) — prints what would change, writes nothing:
    python manage.py normalize_membership_stores

    # Actually persist the fix (scope: source='manual_import' batches only):
    python manage.py normalize_membership_stores --apply

    # Widen scope to ALL batches (auto-snapshot included), and apply:
    python manage.py normalize_membership_stores --include-auto --apply

    # Target one specific batch only (testing / incremental rollout):
    python manage.py normalize_membership_stores --batch-id 42 --apply

Safety: this mutates the real dev/prod database directly, not a test. Each
batch is read/recomputed/saved as its own unit (no top-level
transaction.atomic() wrapping the whole run) — if the process is killed
mid-run, batches already saved stay fixed rather than rolling back with the
ones still to come. --apply must be passed explicitly; the default
(--dry-run behavior, no flag needed) never writes to the database no matter
what other flags are passed.
"""
from django.core.management.base import BaseCommand, CommandError

from App.models.membership import MembershipSnapshotBatch


class Command(BaseCommand):
    help = (
        "One-time fix: retroactively normalize existing MembershipSnapshotBatch "
        "rows' by_store attribution to match the current live "
        "Customer.registration_store per vip_id (dry-run by default, see --apply)."
    )

    def add_arguments(self, parser):
        parser.add_argument(
            "--apply", action="store_true",
            help="Actually persist the recomputed grade_counts/grade_members to "
                 "the affected batches. Without this flag (the default), nothing "
                 "is written — only a report is printed.",
        )
        parser.add_argument(
            "--include-auto", action="store_true",
            help="Widen scope to ALL batches, not just source='manual_import' "
                 "(auto-snapshot batches already used live-Customer store data at "
                 "creation time and don't normally need correction). Default OFF. "
                 "Ignored if --batch-id is also given.",
        )
        parser.add_argument(
            "--batch-id", type=int, default=None,
            help="Only process this one batch id, instead of every batch matching "
                 "the default/--include-auto scope. Useful for testing or an "
                 "incremental rollout before normalizing every batch.",
        )

    def handle(self, *args, **options):
        # Imported here (not at module load) so this command still loads even
        # if the parallel fix landing App.services.membership_snapshot hasn't
        # merged yet in some intermediate state — fails loudly at run time
        # instead, with a clear message, rather than at import time for every
        # other management command.
        try:
            from App.services.membership_snapshot import _resolve_live_stores
        except ImportError as e:
            raise CommandError(
                "Could not import _resolve_live_stores from "
                "App.services.membership_snapshot — this command depends on "
                f"that shared helper existing there. Original error: {e}"
            )

        apply_changes = options["apply"]
        batch_id = options["batch_id"]
        include_auto = options["include_auto"]

        qs = MembershipSnapshotBatch.objects.all()
        if batch_id is not None:
            qs = qs.filter(pk=batch_id)
        elif not include_auto:
            qs = qs.filter(source="manual_import")

        batches = list(qs.order_by("id"))
        if not batches:
            if batch_id is not None:
                raise CommandError(f"No MembershipSnapshotBatch found with id={batch_id}")
            self.stdout.write("No batches match the given scope — nothing to do.")
            return

        mode = "APPLY" if apply_changes else "DRY-RUN"
        self.stdout.write(self.style.SUCCESS("=" * 60))
        self.stdout.write(f"normalize_membership_stores — mode={mode}, batches in scope={len(batches)}")
        self.stdout.write(self.style.SUCCESS("=" * 60))

        total_batches_changed = 0
        total_vids_changed = 0

        for batch in batches:
            grade_members = batch.grade_members or {}
            overall = grade_members.get("overall", {})
            vid_to_grade = {vid: g for g, vids in overall.items() for vid in vids}
            all_vids = list(vid_to_grade.keys())

            self.stdout.write(
                f"\nBatch {batch.id} ({batch.snapshot_date}, source={batch.source}): "
                f"{len(all_vids)} vip_id(s)"
            )

            if not all_vids:
                self.stdout.write("    (empty batch — nothing to normalize)")
                continue

            # Reverse lookup vip_id -> its CURRENT store within this batch's
            # existing by_store data — the "keep as-is" fallback for vip_ids
            # with no live Customer match. Mirrors the pattern
            # App/analytics/membership.py::_vid_store_map() uses for the same
            # kind of reverse index (own copy here — management commands
            # don't import that module's internal helpers).
            old_store_of = {}
            for store, grades in grade_members.get("by_store", {}).items():
                for vids in grades.values():
                    for vid in vids:
                        old_store_of[vid] = store

            live_stores = _resolve_live_stores(all_vids)  # exactly 1 query, whole batch

            new_store_of = {}
            kept_as_is = 0
            for vid in all_vids:
                if vid in live_stores:
                    # _resolve_live_stores() already coerces a blank live
                    # registration_store to the canonical '(No Store)'
                    # placeholder (centralized there 2026-09-02 after this
                    # exact bug: a raw '' key here once diverged from every
                    # other store-keying path and broke
                    # get_grade_changes_store_transitions()'s from_store ==
                    # to_store comparison for the affected vip_id) — no
                    # coercion needed at this call site anymore.
                    new_store_of[vid] = live_stores[vid]
                else:
                    new_store_of[vid] = old_store_of.get(vid, "(No Store)")
                    kept_as_is += 1

            changed_vids = [
                vid for vid in all_vids
                if old_store_of.get(vid, "(No Store)") != new_store_of[vid]
            ]

            self.stdout.write(
                f"    {len(changed_vids)} vip_id(s) store attribution would change; "
                f"{kept_as_is} kept as-is (no live Customer match)"
            )
            if changed_vids:
                sample = changed_vids[:5]
                for vid in sample:
                    old = old_store_of.get(vid, "(No Store)")
                    self.stdout.write(f"      {vid}: {old!r} -> {new_store_of[vid]!r}")
                if len(changed_vids) > len(sample):
                    self.stdout.write(f"      ... and {len(changed_vids) - len(sample)} more")

            if not changed_vids:
                continue

            total_batches_changed += 1
            total_vids_changed += len(changed_vids)

            if not apply_changes:
                continue

            # Rebuild by_store grade_counts/grade_members using the same
            # aggregation shape App/services/membership_snapshot.py::_build_rows()
            # produces — 'overall' is left byte-identical to what this batch
            # already had, only 'by_store' is rebuilt from new_store_of.
            by_store_counts = {}
            by_store_members = {}
            for vid, grade in vid_to_grade.items():
                store_key = new_store_of[vid]
                store_counts = by_store_counts.setdefault(store_key, {})
                store_counts[grade] = store_counts.get(grade, 0) + 1
                store_members = by_store_members.setdefault(store_key, {})
                store_members.setdefault(grade, []).append(vid)

            existing_overall_counts = (batch.grade_counts or {}).get("overall", {})
            batch.grade_counts = {"overall": existing_overall_counts, "by_store": by_store_counts}
            batch.grade_members = {"overall": overall, "by_store": by_store_members}
            batch.save(update_fields=["grade_counts", "grade_members"])

            from django.core.cache import cache
            cache.delete("membership_batches_dropdown")

            self.stdout.write(self.style.SUCCESS(f"    Saved batch {batch.id}."))

        self.stdout.write(self.style.SUCCESS("\n" + "=" * 60))
        self.stdout.write(
            f"SUMMARY ({mode}): {len(batches)} batch(es) processed, "
            f"{total_batches_changed} batch(es) {'changed' if apply_changes else 'would change'}, "
            f"{total_vids_changed} vip_id(s) {'had' if apply_changes else 'would have'} "
            f"store attribution changed"
        )
        if not apply_changes:
            self.stdout.write(self.style.WARNING(
                "Dry-run only — no changes were written. Re-run with --apply to persist."
            ))
        self.stdout.write(self.style.SUCCESS("=" * 60))
