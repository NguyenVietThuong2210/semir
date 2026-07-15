"""
App/management/commands/cnv_scheduler_smoketest.py

Watch the CNV scheduler actually fire jobs locally, in real time, with ZERO
calls to the real CNV API (sync functions are mocked) and without waiting
real hours for a CronTrigger -- a fast IntervalTrigger stands in.

Answers: "does cron actually work on this machine?" -- a yes/no you can watch
with your own eyes before ever deploying, no CNV credentials required.

Usage:
    python manage.py cnv_scheduler_smoketest
    python manage.py cnv_scheduler_smoketest --duration 60 --interval 3
"""
import time

from django.core.management.base import BaseCommand


class Command(BaseCommand):
    help = "Locally smoke-test the CNV scheduler's cron mechanics (mocked sync calls, no CNV API hit)."

    def add_arguments(self, parser):
        parser.add_argument("--duration", type=int, default=30,
                             help="How many seconds to watch (default: 30)")
        parser.add_argument("--interval", type=float, default=3.0,
                             help="Fake job interval in seconds (default: 3)")

    def handle(self, *args, **options):
        from unittest.mock import patch
        from apscheduler.triggers.interval import IntervalTrigger
        from App.cnv import scheduler as sch

        duration = options["duration"]
        interval = options["interval"]

        counts = {"customers": 0, "orders": 0}

        def _fake_customers():
            counts["customers"] += 1
            self.stdout.write(self.style.SUCCESS(
                f"  [{time.strftime('%H:%M:%S')}] customers sync FIRED (#{counts['customers']}) -- NOT calling CNV, mocked"
            ))

        def _fake_orders():
            counts["orders"] += 1
            self.stdout.write(self.style.SUCCESS(
                f"  [{time.strftime('%H:%M:%S')}] orders sync FIRED (#{counts['orders']}) -- NOT calling CNV, mocked"
            ))

        self.stdout.write(self.style.WARNING(
            f"Starting local cron smoketest: interval={interval}s, watching for {duration}s. "
            f"No real CNV API calls will be made."
        ))

        with patch.object(sch, "sync_cnv_customers_only", side_effect=_fake_customers), \
             patch.object(sch, "sync_cnv_orders_only", side_effect=_fake_orders):
            scheduler = sch._build_and_start_scheduler(
                customers_trigger=IntervalTrigger(seconds=interval),
                orders_trigger=IntervalTrigger(seconds=interval * 1.5),
                use_django_jobstore=False,
                refresh_lock=False,
            )
            try:
                time.sleep(duration)
            finally:
                scheduler.shutdown(wait=False)

        self.stdout.write("")
        if counts["customers"] > 0 and counts["orders"] > 0:
            self.stdout.write(self.style.SUCCESS(
                f"PASS -- customers fired {counts['customers']}x, orders fired {counts['orders']}x. "
                f"Cron mechanics work on this machine."
            ))
        else:
            self.stdout.write(self.style.ERROR(
                f"FAIL -- customers={counts['customers']}, orders={counts['orders']}. "
                f"Cron did not fire as expected -- investigate before deploying."
            ))
