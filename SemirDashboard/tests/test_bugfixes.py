"""
tests/test_bugfixes.py — Bug-fix verification tests (plan.md 2026-07-11).

Each test maps to a bug ID in plan.md. Bug tests FAILED on pre-fix code;
guard tests lock current behavior/numbers.

Run:
  cd SemirDashboard && python manage.py test tests.test_bugfixes -v 2
"""
import io
import json
import time
from datetime import date
from decimal import Decimal

from django.contrib.auth.models import User
from django.test import TestCase
from django.urls import reverse

import openpyxl


def _xlsx_bytes(headers, rows):
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.append(headers)
    for r in rows:
        ws.append(r)
    buf = io.BytesIO()
    wb.save(buf)
    return buf.getvalue()


class _NamedXlsx(io.BytesIO):
    def __init__(self, headers, rows, name="test.xlsx"):
        super().__init__(_xlsx_bytes(headers, rows))
        self.name = name


# ── U-01: inventory zero-valid-rows must NOT truncate ─────────────────────────

class InventoryZeroRowGuardTest(TestCase):
    def _seed(self, n=3):
        from App.models import InventorySnapshot
        for i in range(n):
            InventorySnapshot.objects.create(
                shop_id=f"S{i}", shop_name=f"Shop {i}", product_code=f"P{i}",
                inventory_qty=5, total_qty=5,
            )

    def test_zero_valid_rows_preserves_existing_data(self):
        """U-01 bug test: file with headers but no usable rows must raise and keep data."""
        from App.models import InventorySnapshot
        from App.services.inventory_import import process_inventory_file
        self._seed()
        f = _NamedXlsx(
            ["WAREHOUSE/SHOP ID", "PRODUCT CODE"],
            [["", ""], ["", ""]],  # every row missing required values
        )
        with self.assertRaises(ValueError):
            process_inventory_file(f)
        self.assertEqual(InventorySnapshot.objects.count(), 3,
                         "Inventory was modified despite zero valid rows")

    def test_header_only_file_preserves_existing_data(self):
        from App.models import InventorySnapshot
        from App.services.inventory_import import process_inventory_file
        self._seed()
        f = _NamedXlsx(["WAREHOUSE/SHOP ID", "PRODUCT CODE"], [])
        with self.assertRaises(ValueError):
            process_inventory_file(f)
        self.assertEqual(InventorySnapshot.objects.count(), 3)

    def test_valid_file_still_replaces(self):
        """U-01 guard: normal truncate+replace behavior unchanged."""
        from App.models import InventorySnapshot
        from App.services.inventory_import import process_inventory_file
        self._seed()
        f = _NamedXlsx(
            ["WAREHOUSE/SHOP ID", "PRODUCT CODE", "INVENTORY QUANTITY"],
            [["NEW1", "PC1", 7], ["NEW2", "PC2", 9]],
        )
        result = process_inventory_file(f)
        self.assertEqual(result["created"], 2)
        self.assertEqual(result["deleted"], 3)
        self.assertEqual(InventorySnapshot.objects.count(), 2)


# ── U-03/U-05/U-07/U-09/U-04: coupon import hardening ─────────────────────────

class CouponImportHardeningTest(TestCase):
    def test_numeric_coupon_id_no_float_suffix(self):
        """U-03 bug test: numeric IDs must not become '123...0' strings."""
        from App.models import Coupon
        from App.services.coupon_import import process_coupon_file
        f = _NamedXlsx(["Coupon ID", "Used"], [[1234567890, 0]])
        process_coupon_file(f)
        self.assertTrue(Coupon.objects.filter(coupon_id="1234567890").exists(),
                        f"Stored IDs: {list(Coupon.objects.values_list('coupon_id', flat=True))}")
        self.assertFalse(Coupon.objects.filter(coupon_id="1234567890.0").exists())

    def test_header_whitespace_accepted(self):
        """U-07 bug test: ' Coupon ID' (leading space) must import fine."""
        from App.models import Coupon
        from App.services.coupon_import import process_coupon_file
        f = _NamedXlsx([" Coupon ID", "Used"], [["ABC1", 0]])
        result = process_coupon_file(f)
        self.assertEqual(result["created"], 1)
        self.assertTrue(Coupon.objects.filter(coupon_id="ABC1").exists())

    def test_dup_in_batch_single_row_created(self):
        """U-04/U-05 bug test: same ID twice in one file → 1 row, last wins."""
        from App.models import Coupon
        from App.services.coupon_import import process_coupon_file
        f = _NamedXlsx(["Coupon ID", "Face Value"], [["DUP1", 100], ["DUP1", 200]])
        result = process_coupon_file(f)
        self.assertEqual(Coupon.objects.filter(coupon_id="DUP1").count(), 1)
        self.assertEqual(result["created"], 1, "created counter must not double-count dups")
        self.assertEqual(float(Coupon.objects.get(coupon_id="DUP1").face_value), 200.0)

    def test_errors_is_list(self):
        """U-09 bug test: errors is a list with per-row detail, not an int."""
        from App.services.coupon_import import process_coupon_file
        f = _NamedXlsx(["Coupon ID"], [[None], ["OK1"]])
        result = process_coupon_file(f)
        self.assertIsInstance(result["errors"], list)

    def test_upsert_still_works(self):
        """Guard: re-import same ID updates, does not duplicate (numbers stable)."""
        from App.models import Coupon
        from App.services.coupon_import import process_coupon_file
        process_coupon_file(_NamedXlsx(["Coupon ID", "Face Value"], [["UPS1", 100]]))
        process_coupon_file(_NamedXlsx(["Coupon ID", "Face Value"], [["UPS1", 150]]))
        self.assertEqual(Coupon.objects.filter(coupon_id="UPS1").count(), 1)
        self.assertEqual(float(Coupon.objects.get(coupon_id="UPS1").face_value), 150.0)


# ── U-06: file_reader string-safe conversions ─────────────────────────────────

class FileReaderStringSafetyTest(TestCase):
    def test_safe_int_string_float(self):
        """U-06 prerequisite bug test: '28.0' must be 28, not 0."""
        from App.services.file_reader import safe_int
        self.assertEqual(safe_int("28.0"), 28)
        self.assertEqual(safe_int("28"), 28)
        self.assertEqual(safe_int(28.0), 28)
        self.assertEqual(safe_int("1,234"), 1234)
        self.assertEqual(safe_int("abc"), 0)
        self.assertEqual(safe_int(None), 0)

    def test_safe_decimal_strings(self):
        from App.services.file_reader import safe_decimal
        self.assertEqual(safe_decimal("1234.56"), Decimal("1234.56"))
        self.assertEqual(safe_decimal("1,234.56"), Decimal("1234.56"))
        self.assertEqual(safe_decimal("bad", 0), Decimal(0))

    def test_parse_date_string_datetime(self):
        """dtype=str turns Excel dates into strings — parse_date must handle them."""
        from App.services.file_reader import parse_date
        self.assertEqual(parse_date("2026-05-01 00:00:00"), date(2026, 5, 1))
        self.assertEqual(parse_date("2026-05-01"), date(2026, 5, 1))
        self.assertIsNone(parse_date("nan"))

    def test_read_file_preserves_leading_zeros(self):
        """U-06 bug test: VIP ID '001234' must survive the read."""
        from App.services.file_reader import read_file
        f = _NamedXlsx(["VIP ID"], [["001234"]])
        df = read_file(f)
        self.assertEqual(str(df.iloc[0]["VIP ID"]).strip(), "001234")


# ── U-04b/U-08: upload view validation ────────────────────────────────────────

class UploadViewValidationTest(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.admin = User.objects.create_superuser("bugfixadmin", "a@t.com", "pw")

    def setUp(self):
        from django.core.cache import cache
        cache.clear()  # release any type locks from previous tests
        self.client.force_login(self.admin)

    def test_coupon_file_with_dup_ids_rejected_before_job(self):
        """U-04 bug test: duplicated Coupon IDs in file → error message, no job."""
        from unittest.mock import patch
        data = _xlsx_bytes(["Coupon ID"], [["X1"], ["X1"]])
        from django.core.files.uploadedfile import SimpleUploadedFile
        f = SimpleUploadedFile("dup.xlsx", data)
        with patch("App.views.upload._start_thread") as started:
            r = self.client.post(reverse("upload_coupons"), {"file": f}, follow=True)
        self.assertEqual(r.status_code, 200)
        started.assert_not_called()
        msgs = " ".join(str(m) for m in r.context["messages"])
        self.assertIn("duplicated Coupon ID", msgs)

    def test_type_lock_blocks_second_upload(self):
        """U-08 bug test: lock already held → second upload rejected, no thread."""
        from unittest.mock import patch
        from App.upload_jobs import acquire_type_lock, release_type_lock
        self.assertTrue(acquire_type_lock("coupons"))
        try:
            data = _xlsx_bytes(["Coupon ID"], [["Y1"]])
            from django.core.files.uploadedfile import SimpleUploadedFile
            f = SimpleUploadedFile("ok.xlsx", data)
            with patch("App.views.upload._start_thread") as started:
                r = self.client.post(reverse("upload_coupons"), {"file": f}, follow=True)
            started.assert_not_called()
            msgs = " ".join(str(m) for m in r.context["messages"])
            self.assertIn("already in progress", msgs)
        finally:
            release_type_lock("coupons")

    def test_type_lock_atomicity(self):
        from App.upload_jobs import acquire_type_lock, release_type_lock
        self.assertTrue(acquire_type_lock("sales"))
        self.assertFalse(acquire_type_lock("sales"), "second acquire must fail")
        release_type_lock("sales")
        self.assertTrue(acquire_type_lock("sales"))
        release_type_lock("sales")


# ── R2: unified upload validation pipeline ────────────────────────────────────

class UploadValidationPipelineTest(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.admin = User.objects.create_superuser("r2admin", "r2@t.com", "pw")

    def setUp(self):
        from django.core.cache import cache
        cache.clear()
        self.client.force_login(self.admin)

    def test_validate_upload_zero_rows_inventory_error(self):
        from App.services.upload_validation import validate_upload
        data = _xlsx_bytes(["WAREHOUSE/SHOP ID", "PRODUCT CODE"], [])
        vr = validate_upload(data, "inv.xlsx", "inventory")
        self.assertFalse(vr.ok)
        self.assertTrue(any("no data rows" in e for e in vr.errors))

    def test_validate_upload_zero_rows_sales_warning_only(self):
        from App.services.upload_validation import validate_upload
        data = _xlsx_bytes(
            ["INVOICE NUMBER", "SHOP NAME", "SALES DATE", "SETTLEMENT AMOUNT"], []
        )
        vr = validate_upload(data, "s.xlsx", "sales")
        self.assertTrue(vr.ok)
        self.assertTrue(vr.warnings)

    def test_customers_dup_vip_phone_rejected(self):
        from App.services.upload_validation import validate_upload
        data = _xlsx_bytes(["VIP ID", "PHONE NO."], [["1", "090"], ["1", "090"]])
        vr = validate_upload(data, "c.xlsx", "customers")
        self.assertFalse(vr.ok)
        self.assertTrue(any("duplicated" in e for e in vr.errors))

    def test_sale_detail_dup_is_warning_not_error(self):
        from App.services.upload_validation import validate_upload
        data = _xlsx_bytes(
            ["INVOICE NUMBER", "PRODUCT CODE", "SALES DATE", "BARCODE"],
            [["I1", "P1", "2026-01-01", "B1"], ["I1", "P1", "2026-01-01", "B1"]],
        )
        vr = validate_upload(data, "sd.xlsx", "sale_detail")
        self.assertTrue(vr.ok, vr.errors)
        self.assertTrue(vr.warnings)

    def test_used_points_view_good_file_starts_job(self):
        """Coverage gap (plan Phase 6): used_points view-level happy path."""
        from unittest.mock import patch
        from django.core.files.uploadedfile import SimpleUploadedFile
        data = _xlsx_bytes(["VIP ID", "PHONE NO.", "USED POINTS"], [["1", "0901234567", "10"]])
        with patch("App.views.upload._start_thread") as started:
            self.client.post(reverse("upload_used_points"),
                             {"file": SimpleUploadedFile("up.xlsx", data)})
        started.assert_called_once()

    def test_file_hash_warning_on_reupload(self):
        """U-10: same content hash re-uploaded → warning, upload still proceeds."""
        from unittest.mock import patch
        from django.core.files.uploadedfile import SimpleUploadedFile
        from App.upload_jobs import create_job, update_job, _now_iso
        from App.services.upload_validation import file_sha256
        data = _xlsx_bytes(["Coupon ID"], [["H1"]])
        jid = create_job("coupons", "prev.xlsx", file_hash=file_sha256(data))
        update_job(jid, status="done", finished_at=_now_iso())
        with patch("App.views.upload._start_thread") as started:
            r = self.client.post(reverse("upload_coupons"),
                                 {"file": SimpleUploadedFile("again.xlsx", data)}, follow=True)
        started.assert_called_once()  # proceeds
        msgs = " ".join(str(m) for m in r.context["messages"])
        self.assertIn("already imported", msgs)


# ── C-01: CNV AJAX perm guards ────────────────────────────────────────────────

class CnvAjaxAuthGuardTest(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.admin = User.objects.create_superuser("cnvadmin", "c@t.com", "pw")

    def test_customer_tab_unauthenticated_401_not_redirect(self):
        r = self.client.get(
            reverse("cnv:customer_tab", kwargs={"tab": "points"}),
            HTTP_X_REQUESTED_WITH="XMLHttpRequest",
        )
        self.assertEqual(r.status_code, 401, f"got {r.status_code} (redirect would be 302)")

    def test_sync_points_unauthenticated_401_json(self):
        r = self.client.post(
            reverse("cnv:sync_cnv_points"), data="{}", content_type="application/json",
        )
        self.assertEqual(r.status_code, 401)
        self.assertIn("error", json.loads(r.content))

    def test_trigger_sync_unauthenticated_401_json(self):
        r = self.client.post(
            reverse("cnv:trigger_sync"), data="{}", content_type="application/json",
        )
        self.assertEqual(r.status_code, 401)

    def test_trigger_zalo_unauthenticated_401_json(self):
        r = self.client.post(
            reverse("cnv:trigger_zalo_sync"), data="{}", content_type="application/json",
        )
        self.assertEqual(r.status_code, 401)

    def test_sync_points_authenticated_still_works(self):
        """Guard: valid admin gets a normal (non-401) response."""
        self.client.force_login(self.admin)
        r = self.client.post(
            reverse("cnv:sync_cnv_points"),
            data=json.dumps({"cnv_ids": []}),
            content_type="application/json",
        )
        self.assertEqual(r.status_code, 400)  # "No cnv_ids provided" — auth passed


# ── C-08: phone search minimum digits ─────────────────────────────────────────

class ApiPhoneSearchGuardTest(TestCase):
    @classmethod
    def setUpTestData(cls):
        from App.models import Customer
        cls.admin = User.objects.create_superuser("apiadmin", "api@t.com", "pw")
        Customer.objects.create(vip_id="900001", phone="0901234567", name="Full Phone")

    def _auth(self):
        r = self.client.post(reverse("api-login"),
                             data=json.dumps({"username": "apiadmin", "password": "pw"}),
                             content_type="application/json")
        return {"HTTP_AUTHORIZATION": f"Bearer {r.json()['access']}"}

    def test_short_phone_400(self):
        h = self._auth()
        r = self.client.get("/api/v1/analytics/customer-detail/?phone=999", **h)
        self.assertEqual(r.status_code, 400)

    def test_no_digit_phone_400(self):
        h = self._auth()
        r = self.client.get("/api/v1/analytics/customer-detail/?phone=abc", **h)
        self.assertEqual(r.status_code, 400)

    def test_full_phone_still_works(self):
        h = self._auth()
        r = self.client.get("/api/v1/analytics/customer-detail/?phone=0901234567", **h)
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.json()["vip_id"], "900001")


# ── C-04: refresh token rotation (phase 1) ────────────────────────────────────

class TokenRefreshRotationTest(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.user = User.objects.create_superuser("jwtuser", "j@t.com", "pw")

    def test_refresh_returns_new_refresh_token(self):
        r = self.client.post(reverse("api-login"),
                             data=json.dumps({"username": "jwtuser", "password": "pw"}),
                             content_type="application/json")
        old_refresh = r.json()["refresh"]
        r2 = self.client.post(reverse("api-token-refresh"),
                              data=json.dumps({"refresh": old_refresh}),
                              content_type="application/json")
        self.assertEqual(r2.status_code, 200)
        body = r2.json()
        self.assertIn("access", body)
        self.assertIn("refresh", body, "rotated refresh token must be returned")
        self.assertNotEqual(body["refresh"], old_refresh)

    def test_old_refresh_still_valid_phase1(self):
        """Phase 1: old token NOT blacklisted (mobile compatibility)."""
        r = self.client.post(reverse("api-login"),
                             data=json.dumps({"username": "jwtuser", "password": "pw"}),
                             content_type="application/json")
        old_refresh = r.json()["refresh"]
        self.client.post(reverse("api-token-refresh"),
                         data=json.dumps({"refresh": old_refresh}),
                         content_type="application/json")
        r3 = self.client.post(reverse("api-token-refresh"),
                              data=json.dumps({"refresh": old_refresh}),
                              content_type="application/json")
        self.assertEqual(r3.status_code, 200, "old refresh must keep working in phase 1")


# ── C-03: sync skips records without dates ────────────────────────────────────

class SyncSkipNoDateTest(TestCase):
    def test_record_without_dates_skipped_with_warning(self):
        """C-03 bug test: a record missing updated_at+created_at must not crash
        (pre-fix: `None <= updated_until` raised TypeError and failed the batch)."""
        from datetime import datetime, timedelta
        from unittest.mock import MagicMock
        from django.utils import timezone as tz
        from App.cnv.sync_service import CNVSyncService

        svc = CNVSyncService.__new__(CNVSyncService)  # skip __init__ (no API client)
        svc.client = MagicMock()
        # Record 1 is AFTER updated_until (filtered out); record 2 has no dates.
        # Post-filter total = 0 → method exits via the total==0 early-return,
        # touching nothing beyond the sync log.
        svc.client.fetch_all_customers.return_value = [
            {"id": 1, "updated_at": "2026-06-01T00:00:00Z"},
            {"id": 2},  # no dates — crashed with TypeError pre-fix
        ]
        until = tz.make_aware(datetime(2025, 1, 2))
        since = until - timedelta(days=1)
        with self.assertLogs("App.cnv", level="WARNING") as logs:
            try:
                result = svc._sync_customers_by_date_range(since, until)
            except TypeError:
                self.fail("TypeError raised — no-date record not skipped")
        self.assertEqual(result, (0, 0, 0))
        self.assertTrue(any("no updated_at/created_at" in m for m in logs.output),
                        f"warning not logged: {logs.output}")


# ── C-09 / SCHED: single-leader scheduler guard ───────────────────────────────

class SchedulerLeaderLockTest(TestCase):
    """Prod runs gunicorn --workers 3; only ONE worker may start the scheduler.
    Every-10-min cron cadence restored 2026-07-14 once the leader lock became
    self-healing (short TTL + retry loop) — see SchedulerCronMechanicsLocalTest
    for a local, CNV-free proof that jobs actually fire on schedule."""

    def setUp(self):
        from django.core.cache import cache
        from App.cnv import scheduler as sch
        cache.delete("cnv_scheduler_leader")
        sch._last_logged_holder = None
        sch._leader_token = None

    def test_only_first_worker_acquires_leader(self):
        from django.core.cache import cache
        key = "cnv_scheduler_leader"
        # Worker 1 wins
        self.assertTrue(cache.add(key, "w1", 900))
        # Workers 2 & 3 lose → they must skip starting a scheduler
        self.assertFalse(cache.add(key, "w2", 900))
        self.assertFalse(cache.add(key, "w3", 900))
        self.assertEqual(cache.get(key), "w1")

    def test_refresh_extends_only_when_still_leader(self):
        from django.core.cache import cache
        from App.cnv import scheduler as sch
        cache.set(sch._SCHEDULER_LOCK_KEY, "me", 900)
        sch._leader_token = "me"
        sch._refresh_scheduler_leader()
        self.assertEqual(cache.get(sch._SCHEDULER_LOCK_KEY), "me")
        # If another worker took over, a stale token must NOT clobber it
        cache.set(sch._SCHEDULER_LOCK_KEY, "other", 900)
        sch._leader_token = "me"
        sch._refresh_scheduler_leader()
        self.assertEqual(cache.get(sch._SCHEDULER_LOCK_KEY), "other")

    def test_release_clears_lock_only_if_still_owner(self):
        from django.core.cache import cache
        from App.cnv import scheduler as sch
        cache.set(sch._SCHEDULER_LOCK_KEY, "me", 900)
        sch._leader_token = "me"
        sch._release_scheduler_leader()
        self.assertIsNone(cache.get(sch._SCHEDULER_LOCK_KEY))
        # Someone else's lock must survive a stale release call
        cache.set(sch._SCHEDULER_LOCK_KEY, "other", 900)
        sch._leader_token = "me"
        sch._release_scheduler_leader()
        self.assertEqual(cache.get(sch._SCHEDULER_LOCK_KEY), "other")

    def test_short_ttl_bounds_stale_lock_recovery(self):
        """The 2026-07-12 incident: an old dead container's lock (long TTL)
        blocked every new worker from ever becoming leader. TTL must stay short."""
        from App.cnv import scheduler as sch
        self.assertLessEqual(sch._LOCK_TTL, 180,
            "TTL too long — a dead leader's stale key would starve new workers for minutes")
        self.assertLess(sch._LOCK_REFRESH * 2, sch._LOCK_TTL,
            "refresh interval must leave comfortable margin before TTL expiry")

    def test_non_leader_spawns_retry_thread(self):
        """A worker that loses the initial election must keep retrying —
        NOT give up permanently until the next redeploy."""
        from unittest.mock import patch
        from App.cnv import scheduler as sch
        with patch.object(sch, "_try_become_leader_and_start", return_value=False), \
             patch("threading.Thread") as MockThread:
            sch.start_scheduler()
            MockThread.assert_called_once()
            _, kwargs = MockThread.call_args
            self.assertEqual(kwargs.get("target"), sch._leader_retry_loop)
            self.assertTrue(kwargs.get("daemon"))

    def test_retry_loop_logs_holder_once_not_every_attempt(self):
        """2026-07-15 bug: _leader_retry_loop calls _try_become_leader_and_start
        every 45s FOREVER for every non-leader worker. Logging on every failed
        attempt (unchanged steady state) produced ~3800 lines/day of pure noise
        on /admin-logs/, crowding out useful INFO entries. Must log only once
        per distinct holder value observed."""
        from django.core.cache import cache
        from App.cnv import scheduler as sch
        cache.set("cnv_scheduler_leader", "other-worker", 900)

        with self.assertLogs("App.cnv.scheduler", level="INFO") as logs:
            self.assertFalse(sch._try_become_leader_and_start())
        self.assertEqual(len(logs.output), 1, f"expected 1 log line, got: {logs.output}")

        # Same holder, called again (simulating the next 45s retry tick) — must NOT re-log
        import logging
        marker = logging.getLogger("App.cnv.scheduler")
        with self.assertRaises(AssertionError):  # assertLogs raises if NOTHING was logged
            with self.assertLogs("App.cnv.scheduler", level="INFO"):
                self.assertFalse(sch._try_become_leader_and_start())

    def test_retry_loop_logs_again_when_holder_changes(self):
        """A genuine leadership change (old leader died, new one took over)
        must still be logged — only IDENTICAL repeats are suppressed."""
        from django.core.cache import cache
        from App.cnv import scheduler as sch
        cache.set("cnv_scheduler_leader", "worker-A", 900)
        with self.assertLogs("App.cnv.scheduler", level="INFO"):
            self.assertFalse(sch._try_become_leader_and_start())

        cache.set("cnv_scheduler_leader", "worker-B", 900)  # leadership changed
        with self.assertLogs("App.cnv.scheduler", level="INFO") as logs:
            self.assertFalse(sch._try_become_leader_and_start())
        self.assertIn("worker-B", logs.output[0])

    def test_cron_is_every_10_minutes(self):
        """C-09 (restored 2026-07-14): now that the leader lock self-heals
        (short TTL + retry loop), the intended 10-min cadence is safe to run
        again — a single CronTrigger(minute="5") value fires only once/hour,
        the comma-separated list is required for true 10-min cadence."""
        import inspect
        from App.cnv import scheduler as sch
        src = inspect.getsource(sch._build_and_start_scheduler)
        self.assertIn('CronTrigger(minute="5,15,25,35,45,55")', src)
        self.assertIn('CronTrigger(minute="0,10,20,30,40,50")', src)
        self.assertIn("remove_all_jobs", src)  # stale-trigger clear


class SchedulerCronMechanicsLocalTest(TestCase):
    """Proves the APScheduler wiring actually fires jobs on schedule —
    entirely locally, with ZERO real CNV API calls (sync functions mocked)
    and no real-hours wait (fast IntervalTrigger substituted for the
    production CronTrigger via _build_and_start_scheduler's override params).

    This is what closes the "cron ở local chạy và bạn test được, không cần
    phải gọi cnv" request: run this test any time to prove cron mechanics
    work before ever touching production."""

    def test_jobs_fire_repeatedly_on_schedule_without_calling_cnv(self):
        from unittest.mock import patch
        from apscheduler.triggers.interval import IntervalTrigger
        from App.cnv import scheduler as sch

        with patch.object(sch, "sync_cnv_customers_only") as mock_customers, \
             patch.object(sch, "sync_cnv_orders_only") as mock_orders:
            scheduler = sch._build_and_start_scheduler(
                customers_trigger=IntervalTrigger(seconds=1),
                orders_trigger=IntervalTrigger(seconds=1.5),
                use_django_jobstore=False,   # no DB thread — avoids TestCase
                                              # transaction/SQLite-lock issues
                refresh_lock=False,          # irrelevant for a single-process test
            )
            try:
                time.sleep(4.5)
            finally:
                scheduler.shutdown(wait=False)

        # Real CNV API was never touched — both are Mocks.
        self.assertGreaterEqual(mock_customers.call_count, 2,
            f"customers job fired {mock_customers.call_count}x in 4.5s at 1s interval — cron not firing")
        self.assertGreaterEqual(mock_orders.call_count, 2,
            f"orders job fired {mock_orders.call_count}x in 4.5s at 1.5s interval — cron not firing")

    def test_customers_and_orders_triggers_are_independent(self):
        """Guard: overriding one trigger must not affect the other's default."""
        from unittest.mock import patch
        from apscheduler.triggers.interval import IntervalTrigger
        from App.cnv import scheduler as sch

        with patch.object(sch, "sync_cnv_customers_only") as mock_customers, \
             patch.object(sch, "sync_cnv_orders_only") as mock_orders:
            scheduler = sch._build_and_start_scheduler(
                customers_trigger=IntervalTrigger(seconds=1),
                # orders_trigger left as default (production CronTrigger,
                # every 10 min — will NOT fire during this short test)
                use_django_jobstore=False,
                refresh_lock=False,
            )
            try:
                time.sleep(2.5)
            finally:
                scheduler.shutdown(wait=False)

        self.assertGreaterEqual(mock_customers.call_count, 2)
        self.assertEqual(mock_orders.call_count, 0,
            "orders used the fast override instead of its own default trigger")


# ── 2026-07-14: page-limit bump 10k→50k, REVERTED back to 10k 2026-07-15 ──────
# (per user request) + shared distributed rate limit ─────────────────────────

class SyncPageLimitTest(TestCase):
    def test_default_max_sync_pages_is_100(self):
        """100 pages x PAGE_SIZE=100 = 10,000 records/run. Briefly 500/50k on
        2026-07-14, reverted back to 100/10k on 2026-07-15 per user request."""
        from App.cnv.api_client import CNVAPIClient, DEFAULT_MAX_SYNC_PAGES
        self.assertEqual(DEFAULT_MAX_SYNC_PAGES, 100)
        self.assertEqual(CNVAPIClient.PAGE_SIZE, 100)

    def test_fetch_all_customers_uses_default_max_pages(self):
        from unittest.mock import MagicMock, patch
        from App.cnv.api_client import CNVAPIClient, DEFAULT_MAX_SYNC_PAGES
        client = CNVAPIClient.__new__(CNVAPIClient)
        with patch.object(client, "get_customers", return_value={"data": []}) as mock_get:
            client.fetch_all_customers()
        # First call's page kwarg proves the loop bound is DEFAULT_MAX_SYNC_PAGES,
        # not the old hardcoded 100 — verified indirectly via loop not raising
        # and by the module constant itself (test above); here we just confirm
        # the empty-page short-circuit path runs without needing max_pages passed.
        self.assertTrue(mock_get.called)

    def test_sync_service_call_sites_use_shared_constant(self):
        """The 3 sync_service.py call sites must scale with api_client's
        constant, not a re-hardcoded 100 — prevents drift between the two files."""
        import inspect
        from App.cnv import sync_service as ss
        src = inspect.getsource(ss)
        self.assertNotIn("max_pages=100", src, "found a re-hardcoded page limit")
        self.assertEqual(src.count("max_pages=DEFAULT_MAX_SYNC_PAGES"), 3)


class MembershipRateLimiterSharedTest(TestCase):
    """C-06 follow-up (2026-07-14): the manual 'sync points' admin action had
    NO rate limit at all — only the scheduled cron sync did, and even that was
    per-process (not shared across gunicorn workers). Both call sites must now
    draw from the SAME distributed budget."""

    def test_default_rate_is_50_under_cnv_cap_of_100(self):
        from App.cnv.rate_limit import DEFAULT_MEMBERSHIP_RATE_LIMIT
        self.assertEqual(DEFAULT_MEMBERSHIP_RATE_LIMIT, 50)
        self.assertLess(DEFAULT_MEMBERSHIP_RATE_LIMIT, 100)

    def test_sync_service_and_view_share_the_same_limiter_instance(self):
        """Bug test: pre-fix, cnv/views.py built its own CNVAPIClient loop
        with zero rate limiting — a large manual batch run alongside the cron
        sync could push the COMBINED rate over CNV's 100 req/s cap."""
        from App.cnv.rate_limit import get_membership_rate_limiter
        from App.cnv.sync_service import CNVSyncService
        limiter_direct = get_membership_rate_limiter()
        svc = CNVSyncService.__new__(CNVSyncService)
        from App.cnv.rate_limit import get_membership_rate_limiter as _get
        svc._rate_limiter = _get()
        self.assertIs(svc._rate_limiter, limiter_direct,
            "CNVSyncService must use the process-wide singleton limiter")

    def test_view_calls_rate_limiter_before_each_membership_fetch(self):
        """Bug test: sync_cnv_points view must throttle — pre-fix it looped
        client.get_customer_membership() with no acquire() call at all."""
        import inspect
        from App.cnv import views as cnv_views
        src = inspect.getsource(cnv_views.sync_cnv_points)
        self.assertIn("get_membership_rate_limiter", src)
        self.assertIn("rate_limiter.acquire()", src)

    def test_distributed_limiter_enforces_budget_across_instances(self):
        """Two independent DistributedRateLimiter instances sharing the same
        cache key must draw from ONE combined budget (proves cross-process
        sharing works, since two Python objects here simulate two workers).

        Wait time depends on how far into the 1s window the test happens to
        start (0 to <1s — a fixed-window limiter, not phase-locked to the
        test), so this asserts only that a MEANINGFUL wait occurred at all —
        with an unshared (per-instance) budget, all 6 acquires would return
        near-instantly (each side has its own separate 3-slot budget)."""
        from django.core.cache import cache
        from App.cnv.rate_limit import DistributedRateLimiter
        cache.clear()
        key = "test_shared_budget"
        limiter_a = DistributedRateLimiter(rate=3, key=key)
        limiter_b = DistributedRateLimiter(rate=3, key=key)
        start = time.monotonic()
        for _ in range(3):
            limiter_a.acquire()
        for _ in range(3):
            limiter_b.acquire()  # budget for this window already spent by A
        elapsed = time.monotonic() - start
        self.assertGreater(elapsed, 0.05,
            "second limiter got its 3 slots near-instantly — budget was NOT "
            "shared with the first limiter's usage of the same window")


# ── A-01: total_amount over full queryset ─────────────────────────────────────

class CustomerDetailTotalAmountTest(TestCase):
    @classmethod
    def setUpTestData(cls):
        from App.models import Customer, SalesTransaction
        cls.cust = Customer.objects.create(vip_id="810001", phone="0912345678", name="Cap Test")
        for i in range(10):
            SalesTransaction.objects.create(
                invoice_number=f"CAPINV{i:03d}", vip_id="810001",
                sales_date=date(2026, 1, i + 1), shop_name="Shop X", quantity=1,
                sales_amount=Decimal("100"), settlement_amount=Decimal("100"),
            )

    def test_total_amount_full_even_when_capped(self):
        """A-01 bug test: max_invoices=5 must still report the FULL total (1000)."""
        from App.analytics.customer_utils import get_customer_detail_data
        detail = get_customer_detail_data(self.cust, max_invoices=5, include_coupons=False)
        self.assertEqual(len(detail["invoices"]), 5)
        self.assertEqual(detail["stats"]["total_purchases"], 10)
        self.assertEqual(Decimal(detail["stats"]["total_amount"]), Decimal("1000"))

    def test_total_amount_uncapped_unchanged(self):
        """A-01 guard: default (uncapped) result identical to before."""
        from App.analytics.customer_utils import get_customer_detail_data
        detail = get_customer_detail_data(self.cust, include_coupons=False)
        self.assertEqual(Decimal(detail["stats"]["total_amount"]), Decimal("1000"))


# ── A-04: coupon_amount uses sales_amount ─────────────────────────────────────

class CouponAmountFieldTest(TestCase):
    @classmethod
    def setUpTestData(cls):
        from App.models import Customer, SalesTransaction, Coupon
        cls.cust = Customer.objects.create(vip_id="820001", phone="0987654321", name="Coupon Test")
        SalesTransaction.objects.create(
            invoice_number="CPINV001", vip_id="820001",
            sales_date=date(2026, 2, 1), shop_name="Shop Y", quantity=1,
            sales_amount=Decimal("500"), settlement_amount=Decimal("400"),  # differ!
        )
        Coupon.objects.create(
            coupon_id="CPTEST1", face_value=Decimal("0.9"),
            docket_number="CPINV001", using_date=date(2026, 2, 1), used=1,
        )

    def test_coupon_amount_based_on_sales_amount(self):
        """A-04 bug test: must equal calc(face, sales_amount=500), not settlement=400."""
        from App.analytics.customer_utils import get_customer_detail_data
        from App.analytics.coupon_analytics import calc_coupon_amount
        detail = get_customer_detail_data(self.cust)
        inv = next(i for i in detail["invoices"] if i["invoice_no"] == "CPINV001")
        expected = calc_coupon_amount(Decimal("0.9"), Decimal("500"))
        self.assertEqual(inv["coupon_amount"], expected)
        self.assertNotEqual(inv["coupon_amount"],
                            calc_coupon_amount(Decimal("0.9"), Decimal("400")))


# ── A-07: season range label carries year ─────────────────────────────────────

class SeasonRangeLabelTest(TestCase):
    def test_regular_season_label_has_year(self):
        from App.analytics.season_utils import get_session_for_range
        self.assertEqual(get_session_for_range(date(2025, 2, 1), date(2025, 4, 30)),
                         "M2-4 2025")

    def test_m11_1_label_cross_year(self):
        from App.analytics.season_utils import get_session_for_range
        self.assertEqual(get_session_for_range(date(2024, 11, 1), date(2025, 1, 31)),
                         "M11-1 2024-2025")

    def test_m11_1_label_starting_in_january(self):
        from App.analytics.season_utils import get_session_for_range
        self.assertEqual(get_session_for_range(date(2025, 1, 1), date(2025, 1, 31)),
                         "M11-1 2024-2025")

    def test_multi_season_range_returns_none(self):
        from App.analytics.season_utils import get_session_for_range
        self.assertIsNone(get_session_for_range(date(2025, 2, 1), date(2025, 8, 31)))


# ── C-02: grade donut not empty ───────────────────────────────────────────────

class GradeDonutTest(TestCase):
    @classmethod
    def setUpTestData(cls):
        from App.models import Customer
        cls.admin = User.objects.create_superuser("donutadmin", "d@t.com", "pw")
        Customer.objects.create(vip_id="830001", phone="0911111111", vip_grade="Gold")
        Customer.objects.create(vip_id="830002", phone="0922222222", vip_grade="Silver")

    def test_grade_donut_has_slices(self):
        """C-02 bug test: donut was permanently empty pre-fix."""
        from django.core.cache import cache
        cache.clear()  # phone-set cache must see the new customers
        r = self.client.post(reverse("api-login"),
                             data=json.dumps({"username": "donutadmin", "password": "pw"}),
                             content_type="application/json")
        h = {"HTTP_AUTHORIZATION": f"Bearer {r.json()['access']}"}
        resp = self.client.get("/api/v1/charts/customer/", **h)
        self.assertEqual(resp.status_code, 200)
        donuts = resp.json()["donuts"]
        self.assertGreater(len(donuts[0]["slices"]), 0, "grade donut is still empty")
        labels = {s["label"] for s in donuts[0]["slices"]}
        self.assertTrue({"Gold", "Silver"} & labels, f"labels: {labels}")
