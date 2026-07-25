"""
App/management/commands/check_cnv_gap.py

Diagnostic for the 2026-07-25 silent-sync-loss incident: compares a full
customer export taken directly from the CNV Loyalty admin portal (source of
truth) against this DB's CNVCustomer table, reporting any customer IDs that
exist in CNV but were never synced here.

Root cause (see CNVSyncService.backfill_customers_by_ids docstring): the
incremental sync's checkpoint is `max(updated_at in this run) + 1us`; if
several customers share the exact same `updated_at` (a batch-write tie on
CNV's side) and that tie straddles a run's page cutoff, the stragglers are
permanently excluded by every future `updated_at >= checkpoint` filter —
with no exception thrown and nothing logged as an error.

Usage:
    python manage.py check_cnv_gap --export "tmp/Customers_File_*.xls" --out App/cnv/input/cnv_gap_20260725.txt

The export files are the raw .xls download(s) from the CNV admin portal's
customer list (column "Id khách hàng"). Multiple files (portal-side paging)
are all accepted via a glob pattern.
"""
import glob
from pathlib import Path

from django.core.management.base import BaseCommand, CommandError

from App.cnv.models import CNVCustomer


class Command(BaseCommand):
    help = "Compare a CNV admin-portal customer export against this DB, report/write missing IDs"

    def add_arguments(self, parser):
        parser.add_argument(
            "--export", required=True,
            help='Glob pattern for the CNV export .xls/.xlsx file(s), e.g. "tmp/Customers_File_*.xls"',
        )
        parser.add_argument(
            "--out", default=None,
            help="Write missing customer IDs (one per line) to this path, for use with "
                 "`sync_cnv --ids-file`. If omitted, only prints the report.",
        )

    def handle(self, *args, **options):
        try:
            import pandas as pd
        except ImportError:
            raise CommandError("pandas is required for this command")

        files = sorted(glob.glob(options["export"]))
        if not files:
            raise CommandError(f"No files matched: {options['export']}")

        self.stdout.write(f"Reading {len(files)} export file(s)...")
        frames = []
        for f in files:
            df = pd.read_excel(f, usecols=["Id khách hàng"])
            frames.append(df)
            self.stdout.write(f"  {Path(f).name}: {len(df)} rows")
        export = pd.concat(frames, ignore_index=True)
        export_ids = set(export["Id khách hàng"].dropna().astype("Int64").tolist())

        db_ids = set(CNVCustomer.objects.values_list("cnv_id", flat=True))

        missing = sorted(export_ids - db_ids)
        extra = sorted(db_ids - export_ids)

        self.stdout.write(self.style.SUCCESS("\n" + "=" * 60))
        self.stdout.write(f"CNV export unique IDs:  {len(export_ids)}")
        self.stdout.write(f"DB (CNVCustomer) IDs:   {len(db_ids)}")
        self.stdout.write(self.style.WARNING(f"Missing from DB (in CNV, not synced): {len(missing)}"))
        self.stdout.write(f"Extra in DB (not in this export — check export freshness): {len(extra)}")
        self.stdout.write("=" * 60)

        if missing:
            preview = ", ".join(str(i) for i in missing[:20])
            self.stdout.write(f"\nFirst {min(20, len(missing))} missing IDs: {preview}")

        if options["out"] and missing:
            out_path = Path(options["out"])
            out_path.parent.mkdir(parents=True, exist_ok=True)
            out_path.write_text("\n".join(str(i) for i in missing), encoding="utf-8")
            self.stdout.write(self.style.SUCCESS(
                f"\nWrote {len(missing)} missing IDs to {out_path}\n"
                f"Backfill with: python manage.py sync_cnv --customers --ids-file {out_path}"
            ))
