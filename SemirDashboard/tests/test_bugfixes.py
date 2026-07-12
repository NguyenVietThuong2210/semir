"""
tests/test_bugfixes.py — Bug-fix verification tests (plan.md 2026-07-11).

Each test maps to a bug ID in plan.md. Bug tests FAILED on pre-fix code;
guard tests lock current behavior/numbers.

Run:
  cd SemirDashboard && python manage.py test tests.test_bugfixes -v 2
"""
import io
import json
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
    Reverted to hourly cron (:05 / :10) for stability after the 3-scheduler fix."""

    def setUp(self):
        from django.core.cache import cache
        cache.delete("cnv_scheduler_leader")

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

    def test_cron_is_hourly_for_stability(self):
        import inspect
        from App.cnv import scheduler as sch
        src = inspect.getsource(sch.start_scheduler)
        self.assertIn('CronTrigger(minute="5")', src)
        self.assertIn('CronTrigger(minute="10")', src)
        self.assertIn("remove_all_jobs", src)  # stale-trigger clear


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
