"""
tests/test_pages.py — Page-render smoke tests for all uncovered GET routes.

Covers: home, formulas, upload pages, customer-detail, users, admin-logs,
        coupons/chart, coupons/campaigns, cnv/sync-status, shop-detail/export,
        analytics/chart/export, coupons/chart/export, cnv/customer-chart/export,
        upload jobs JSON endpoints, POST trigger endpoints.

No fixture data is loaded here — every page must handle an empty DB gracefully.
Period-filter pages are tested in both variants: all-time + 2025.

Run:
  cd SemirDashboard && python manage.py test tests.test_pages -v 2
"""
import json
import time

from django.contrib.auth.models import User
from django.urls import reverse

from tests.base import SnapshotTestCase

PERIOD_2025_PARAMS = "?start_date=2025-01-01&end_date=2025-12-31"


class PageRenderTest(SnapshotTestCase):
    """
    Smoke tests: every GET route must return HTTP 200.
    No fixture data — tests graceful empty-state rendering.
    Period-filter routes tested in both all-time and 2025 variants.
    """

    @classmethod
    def setUpTestData(cls):
        cls.superuser = User.objects.create_superuser(
            username="testadmin", password="testpass", email="test@test.com"
        )

    def setUp(self):
        self.client.force_login(self.superuser)

    # ── Static / home pages ───────────────────────────────────────────────────

    def test_home_200(self):
        t = self.timer("home")
        r = self.client.get(reverse("home"))
        t.checkpoint("GET /")
        t.report()
        self.assertEqual(r.status_code, 200)

    def test_formulas_200(self):
        r = self.client.get(reverse("formulas"))
        self.assertEqual(r.status_code, 200)

    # ── Upload pages (GET only — form render, no file submitted) ─────────────

    def test_upload_customers_200(self):
        r = self.client.get(reverse("upload_customers"))
        self.assertEqual(r.status_code, 200)

    def test_upload_sales_200(self):
        r = self.client.get(reverse("upload_sales"))
        self.assertEqual(r.status_code, 200)

    def test_upload_coupons_200(self):
        r = self.client.get(reverse("upload_coupons"))
        self.assertEqual(r.status_code, 200)

    def test_upload_used_points_redirect(self):
        # upload_used_points is POST-only; GET redirects to upload_customers
        r = self.client.get(reverse("upload_used_points"), follow=True)
        self.assertEqual(r.status_code, 200)

    def test_upload_jobs_list_json(self):
        r = self.client.get(reverse("upload_jobs_list"))
        self.assertEqual(r.status_code, 200)
        data = json.loads(r.content)
        self.assertIn("jobs", data)

    # ── Customer detail ───────────────────────────────────────────────────────

    def test_customer_detail_empty_200(self):
        # No search params → show search form only
        r = self.client.get(reverse("customer_detail"))
        self.assertEqual(r.status_code, 200)

    def test_customer_detail_not_found_200(self):
        # VIP ID that doesn't exist → "no customer found" state, still 200
        r = self.client.get(reverse("customer_detail") + "?vip_id=XXXXNOTEXIST")
        self.assertEqual(r.status_code, 200)

    # ── Admin pages ───────────────────────────────────────────────────────────

    def test_users_200(self):
        r = self.client.get(reverse("user_management"))
        self.assertEqual(r.status_code, 200)

    def test_admin_logs_200(self):
        # Reads log files — graceful if logs/ is empty
        r = self.client.get(reverse("admin_logs"))
        self.assertEqual(r.status_code, 200)

    # ── Coupon pages (period-filter) ──────────────────────────────────────────

    def test_coupon_chart_alltime_200(self):
        t = self.timer("coupon_chart_alltime")
        r = self.client.get(reverse("coupon_chart"))
        t.checkpoint("GET /coupons/chart/")
        t.report()
        self.assertEqual(r.status_code, 200)

    def test_coupon_chart_period_2025_200(self):
        t = self.timer("coupon_chart_2025")
        r = self.client.get(reverse("coupon_chart") + PERIOD_2025_PARAMS)
        t.checkpoint("GET /coupons/chart/ with 2025 filter")
        t.report()
        self.assertEqual(r.status_code, 200)

    def test_coupon_campaigns_200(self):
        r = self.client.get(reverse("manage_campaigns"))
        self.assertEqual(r.status_code, 200)

    # ── CNV pages ─────────────────────────────────────────────────────────────

    def test_cnv_sync_status_200(self):
        t = self.timer("cnv_sync_status")
        r = self.client.get(reverse("cnv:sync_status"))
        t.checkpoint("GET /cnv/sync-status/")
        t.report()
        self.assertEqual(r.status_code, 200)

    # ── POST trigger endpoints (smoke — just check no crash) ──────────────────

    def test_trigger_sync_post(self):
        # POST to trigger sync — expect redirect or JSON, not 500
        r = self.client.post(
            reverse("cnv:trigger_sync"),
            data={"sync_type": "customers"},
            HTTP_X_REQUESTED_WITH="XMLHttpRequest",
        )
        self.assertIn(r.status_code, [200, 302, 400, 429])

    def test_trigger_zalo_sync_post(self):
        r = self.client.post(
            reverse("cnv:trigger_zalo_sync"),
            HTTP_X_REQUESTED_WITH="XMLHttpRequest",
        )
        self.assertIn(r.status_code, [200, 302, 400, 429])


class ExportSmokeTest(SnapshotTestCase):
    """
    Export endpoint smoke tests — verify workbook is returned (Content-Type: Excel).
    These need fixture data so they share a setUpTestData with full import.
    Period-filter exports tested in both all-time and 2025 variants.
    """

    @classmethod
    def setUpTestData(cls):
        import io
        from App.services import process_customer_file, process_sales_file, process_coupon_file
        from tests.base import INPUT_DIR

        cls.superuser = User.objects.create_superuser(
            username="exportadmin", password="testpass", email="export@test.com"
        )

        def _named(path):
            with open(path, "rb") as f:
                data = f.read()
            class _N(io.BytesIO):
                pass
            obj = _N(data)
            obj.name = path.name
            return obj

        customer_file = INPUT_DIR / "customer.xlsx"
        sale_files = [INPUT_DIR / "Sale 2024.xlsx", INPUT_DIR / "Sale 2025.xlsx", INPUT_DIR / "Sale 2026.xlsx"]
        coupon_file = INPUT_DIR / "coupon_1 (1).xlsx"

        if customer_file.exists():
            process_customer_file(_named(customer_file))
        for path in sale_files:
            if path.exists():
                process_sales_file(_named(path))
        if coupon_file.exists():
            process_coupon_file(_named(coupon_file))

    def setUp(self):
        self.client.force_login(self.superuser)

    EXCEL_CONTENT_TYPES = (
        "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        "application/vnd.ms-excel",
        "application/octet-stream",
    )

    def _assert_excel(self, response):
        self.assertEqual(response.status_code, 200)
        ct = response.get("Content-Type", "")
        self.assertTrue(
            any(ct.startswith(t) for t in self.EXCEL_CONTENT_TYPES),
            f"Expected Excel Content-Type, got: {ct}",
        )

    # ── Analytics chart export [period-filter] ────────────────────────────────

    def test_analytics_chart_export_alltime(self):
        t = self.timer("analytics_chart_export_alltime")
        r = self.client.get(reverse("export_sales_chart_excel"))
        t.checkpoint("GET /analytics/chart/export/ all-time")
        t.report()
        self._assert_excel(r)

    def test_analytics_chart_export_period_2025(self):
        t = self.timer("analytics_chart_export_2025")
        r = self.client.get(reverse("export_sales_chart_excel") + PERIOD_2025_PARAMS)
        t.checkpoint("GET /analytics/chart/export/ 2025 filter")
        t.report()
        self._assert_excel(r)

    # ── Coupon chart export [period-filter] ───────────────────────────────────

    def test_coupon_chart_export_alltime(self):
        t = self.timer("coupon_chart_export_alltime")
        r = self.client.get(reverse("export_coupon_chart_excel"))
        t.checkpoint("GET /coupons/chart/export/ all-time")
        t.report()
        self._assert_excel(r)

    def test_coupon_chart_export_period_2025(self):
        t = self.timer("coupon_chart_export_2025")
        r = self.client.get(reverse("export_coupon_chart_excel") + PERIOD_2025_PARAMS)
        t.checkpoint("GET /coupons/chart/export/ 2025 filter")
        t.report()
        self._assert_excel(r)

    # ── Shop detail export [period-filter] ────────────────────────────────────

    def test_shop_detail_export_alltime(self):
        from App.models import SalesTransaction
        shop = SalesTransaction.objects.order_by().values_list("shop_name", flat=True).first()
        if not shop:
            self.skipTest("No sales data in fixture")
        t = self.timer("shop_detail_export_alltime")
        from urllib.parse import urlencode
        params = urlencode({"section": "sales", "sales_shop": shop})
        r = self.client.get(reverse("export_shop_detail_excel") + f"?{params}")
        t.checkpoint(f"GET /shop-detail/export/ shop={shop}")
        t.report()
        self._assert_excel(r)

    def test_shop_detail_export_period_2025(self):
        from App.models import SalesTransaction
        shop = SalesTransaction.objects.order_by().values_list("shop_name", flat=True).first()
        if not shop:
            self.skipTest("No sales data in fixture")
        t = self.timer("shop_detail_export_2025")
        from urllib.parse import urlencode
        params = urlencode({"section": "sales", "sales_shop": shop,
                            "start_date": "2025-01-01", "end_date": "2025-12-31"})
        r = self.client.get(reverse("export_shop_detail_excel") + f"?{params}")
        t.checkpoint(f"GET /shop-detail/export/ shop={shop} 2025 filter")
        t.report()
        self._assert_excel(r)

    # ── CNV customer chart export [period-filter] ─────────────────────────────

    def test_cnv_customer_chart_export_alltime(self):
        t = self.timer("cnv_chart_export_alltime")
        r = self.client.get(reverse("cnv:export_customer_chart_excel"))
        t.checkpoint("GET /cnv/customer-chart/export/ all-time")
        t.report()
        self._assert_excel(r)

    def test_cnv_customer_chart_export_period_2025(self):
        t = self.timer("cnv_chart_export_2025")
        r = self.client.get(reverse("cnv:export_customer_chart_excel") + PERIOD_2025_PARAMS)
        t.checkpoint("GET /cnv/customer-chart/export/ 2025 filter")
        t.report()
        self._assert_excel(r)
