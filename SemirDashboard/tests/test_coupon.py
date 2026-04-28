"""
tests/test_coupon.py — Coupon page: import + full analytics pipeline timing.

Run:
  cd SemirDashboard && python manage.py test tests.test_coupon -v 2

Regenerate snapshots:
  UPDATE_SNAPSHOTS=1 python manage.py test tests.test_coupon -v 2
"""
import io
import time
from datetime import date

from App.models import Coupon, SalesTransaction, Customer
from App.services import process_coupon_file, process_sales_file, process_customer_file
from App.analytics.coupon_analytics import calculate_coupon_analytics
from App.analytics.tab_functions import get_coupon_tab, COUPON_TABS

from tests.base import SnapshotTestCase, INPUT_DIR, get_run_log

COUPON_FILE   = INPUT_DIR / "coupon_1 (1).xlsx"
CUSTOMER_FILE = INPUT_DIR / "customer.xlsx"
SALE_FILES    = [INPUT_DIR / "Sale 2024.xlsx", INPUT_DIR / "Sale 2025.xlsx", INPUT_DIR / "Sale 2026.xlsx"]


def _named(path):
    with open(path, "rb") as f:
        data = f.read()
    class _N(io.BytesIO):
        pass
    obj = _N(data)
    obj.name = path.name
    return obj


class CouponImportTest(SnapshotTestCase):

    def test_import_coupons(self):
        if not COUPON_FILE.exists():
            self.skipTest(f"Missing: {COUPON_FILE}")
        t = self.timer("import_coupons")
        result = process_coupon_file(_named(COUPON_FILE))
        t.checkpoint(f"process_coupon_file → created={result['created']} updated={result['updated']} errors={result.get('errors',0)}")
        t.report()
        self.assertGreater(result["created"] + result["updated"], 0)


class CouponAnalyticsTest(SnapshotTestCase):

    @classmethod
    def setUpTestData(cls):
        if CUSTOMER_FILE.exists():
            process_customer_file(_named(CUSTOMER_FILE))
        for path in SALE_FILES:
            if path.exists():
                process_sales_file(_named(path))
        if COUPON_FILE.exists():
            process_coupon_file(_named(COUPON_FILE))

    # ── Full page timing ──────────────────────────────────────────────────

    def test_page_timing_alltime(self):
        """Simulate coupon dashboard page load using the production aggregate path."""
        log = get_run_log()
        log.section("COUPON PAGE TIMING (all-time) — production path")
        t = self.timer("coupon_page_alltime")

        if not Coupon.objects.exists():
            self.skipTest("No coupon data")

        # Production path: get_coupon_tab uses DB aggregates — no full row scan
        data = get_coupon_tab('shop')
        t.checkpoint(
            f"get_coupon_tab('shop') all-time → "
            f"total={data.get('all_time_total', 0)} used={data.get('all_time_used', 0)}"
        )

        data2 = get_coupon_tab('detail')
        t.checkpoint(f"get_coupon_tab('detail') → {len(data2.get('period_details', []))} rows")

        total = t.total()
        t.report()
        self.record_page_timing("COUPON (all-time)", total, t._checkpoints)
        self.assertLess(total, 5, f"Coupon page all-time took {total:.1f}s > 5s target")

    def test_page_timing_via_analytics_fn(self):
        """Time the official calculate_coupon_analytics function end-to-end."""
        if not Coupon.objects.exists():
            self.skipTest("No coupon data")
        log = get_run_log()
        log.section("COUPON PAGE TIMING — via calculate_coupon_analytics()")
        t = self.timer("coupon_analytics_fn")

        data = calculate_coupon_analytics()
        t.checkpoint(f"calculate_coupon_analytics(all-time) → "
                     f"total={data['all_time']['total']} used={data['all_time']['used']} "
                     f"shops={len(data['by_shop'])} details={len(data['details'])}")

        data2 = calculate_coupon_analytics(date_from=date(2025,1,1), date_to=date(2025,12,31))
        t.checkpoint(f"calculate_coupon_analytics(2025) → "
                     f"period_used={data2['period']['used']}")

        total = t.total()
        t.report()
        self.record_page_timing("COUPON (analytics fn)", total, t._checkpoints)

    # ── Snapshots ─────────────────────────────────────────────────────────

    def test_snapshot_alltime(self):
        if not Coupon.objects.exists():
            self.skipTest("No coupon data")
        t = self.timer("coupon_snapshot_alltime")
        data = calculate_coupon_analytics()
        t.checkpoint("calculate_coupon_analytics(all-time)")
        t.report()
        self.assert_snapshot("coupon_alltime", {
            "all_time": data["all_time"],
            "period": data["period"],
            "by_shop_count": len(data["by_shop"]),
            "details_count": len(data["details"]),
            "duplicate_invoices_count": len(data["duplicate_invoices"]),
            "by_shop": data["by_shop"],
        })

    def test_snapshot_2025(self):
        if not Coupon.objects.exists():
            self.skipTest("No coupon data")
        t = self.timer("coupon_snapshot_2025")
        data = calculate_coupon_analytics(date_from=date(2025,1,1), date_to=date(2025,12,31))
        t.checkpoint("calculate_coupon_analytics(2025)")
        t.report()
        self.assert_snapshot("coupon_2025", {
            "all_time": data["all_time"],
            "period": data["period"],
            "by_shop_count": len(data["by_shop"]),
            "details_count": len(data["details"]),
        })

    # ── Sanity ────────────────────────────────────────────────────────────

    def test_usage_rate_sanity(self):
        if not Coupon.objects.exists():
            self.skipTest("No coupon data")
        data = calculate_coupon_analytics()
        at = data["all_time"]
        self.assertEqual(at["total"], at["used"] + at["unused"], "total != used + unused")
        self.assertGreaterEqual(at["usage_rate"], 0.0)
        self.assertLessEqual(at["usage_rate"], 100.0)

    def test_prefix_filter(self):
        if not Coupon.objects.exists():
            self.skipTest("No coupon data")
        sample = Coupon.objects.values_list("coupon_id", flat=True).first()
        if not sample:
            self.skipTest("No coupon_ids")
        prefix = sample[:3]
        t = self.timer(f"coupon_prefix_{prefix}")
        data = calculate_coupon_analytics(coupon_id_prefix=prefix)
        full = calculate_coupon_analytics()
        t.checkpoint(f"prefix={prefix} total={data['all_time']['total']} vs full={full['all_time']['total']}")
        t.report()
        self.assertLessEqual(data["all_time"]["total"], full["all_time"]["total"])


class CouponTabSnapshotTest(SnapshotTestCase):
    """
    Step 1 — Lock per-tab data for all Coupon Analytics tabs (all-time).
    These snapshots are the ground-truth for Step 4 regression checks.
    """

    @classmethod
    def setUpTestData(cls):
        if CUSTOMER_FILE.exists():
            process_customer_file(_named(CUSTOMER_FILE))
        for path in SALE_FILES:
            if path.exists():
                process_sales_file(_named(path))
        if COUPON_FILE.exists():
            process_coupon_file(_named(COUPON_FILE))

    def _tab(self, tab):
        if not Coupon.objects.exists():
            self.skipTest("No coupon data")
        return get_coupon_tab(tab)

    def test_tab_perf_all(self):
        """Time each coupon tab individually via get_coupon_tab() and compare."""
        if not Coupon.objects.exists():
            self.skipTest("No coupon data")
        log = get_run_log()
        log.section("COUPON TAB PERF — per-tab via get_coupon_tab()")
        timings = {}
        for tab in COUPON_TABS:
            t = self.timer(f"coupon_tab_{tab}")
            get_coupon_tab(tab)
            elapsed = t.total()
            timings[tab] = elapsed
            t.checkpoint(f"{tab} → {elapsed:.2f}s")
            t.report()
        self.record_page_timing("COUPON per-tab timings", sum(timings.values()),
                                [(f"tab:{k}", 0, v) for k, v in timings.items()])
        for tab, elapsed in timings.items():
            self.assertLess(elapsed, 15, f"Tab '{tab}' took {elapsed:.1f}s > 15s threshold")

    def test_tab_snapshot_shop(self):
        t = self.timer("coupon_tab_shop")
        data = self._tab('shop')
        t.checkpoint(f"by_shop → {len(data['by_shop'])} rows  [{t.total():.2f}s]")
        t.report()
        self.assert_snapshot("coupon_tab_shop", {
            "all_time": data["all_time"],
            "period": data["period"],
            "by_shop": data["by_shop"],
        })

    def test_tab_snapshot_detail(self):
        t = self.timer("coupon_tab_detail")
        data = self._tab('detail')
        t.checkpoint(f"details → {len(data['details'])} rows  [{t.total():.2f}s]")
        t.report()
        self.assert_snapshot("coupon_tab_detail", {
            "details_count": len(data["details"]),
            "details": data["details"],
        })

    def test_tab_snapshot_duplicates(self):
        t = self.timer("coupon_tab_duplicates")
        data = self._tab('duplicates')
        t.checkpoint(f"duplicate_invoices → {len(data['duplicate_invoices'])} rows  [{t.total():.2f}s]")
        t.report()
        self.assert_snapshot("coupon_tab_duplicates", {
            "duplicate_invoices_count": len(data["duplicate_invoices"]),
            "duplicate_invoices": data["duplicate_invoices"],
        })
