"""
tests/test_sales.py — Sales page: import + full analytics pipeline timing.

Run:
  cd SemirDashboard && python manage.py test tests.test_sales -v 2

Regenerate snapshots:
  UPDATE_SNAPSHOTS=1 python manage.py test tests.test_sales -v 2
"""
import io
import time
from datetime import date
from pathlib import Path

from App.models import Customer, SalesTransaction
from App.services import process_customer_file, process_sales_file
from App.analytics.core import calculate_return_rate_analytics
from App.analytics.tab_functions import get_sales_tab, SALES_TABS
from App.analytics.aggregators import (
    aggregate_by_grade, aggregate_by_season, aggregate_by_month,
    aggregate_by_year, aggregate_by_week, aggregate_by_shop,
)
from App.analytics.calculations import calculate_return_visits
from App.analytics.customer_utils import build_customer_purchase_map, get_customer_info

from tests.base import SnapshotTestCase, INPUT_DIR, get_run_log

SALE_FILES    = [INPUT_DIR / "Sale 2024.xlsx", INPUT_DIR / "Sale 2025.xlsx", INPUT_DIR / "Sale 2026.xlsx"]
CUSTOMER_FILE = INPUT_DIR / "customer.xlsx"


def _named(path):
    with open(path, "rb") as f:
        data = f.read()
    class _N(io.BytesIO):
        pass
    obj = _N(data)
    obj.name = path.name
    return obj


class SalesImportTest(SnapshotTestCase):

    def test_import_customers(self):
        t = self.timer("import_customers")
        result = process_customer_file(_named(CUSTOMER_FILE))
        t.checkpoint(f"process_customer_file → created={result['created']} updated={result['updated']} total={result['total_processed']}")
        t.report()
        self.assertGreater(result["total_processed"], 0)
        self.assertEqual(len(result.get("errors", [])), 0, result.get("errors", [])[:3])

    def test_import_sales(self):
        t = self.timer("import_sales")
        for path in SALE_FILES:
            if not path.exists():
                continue
            result = process_sales_file(_named(path))
            t.checkpoint(f"{path.name} → created={result['created']} updated={result['updated']}")
        t.report()
        self.assertGreater(SalesTransaction.objects.count(), 0)


class SalesAnalyticsTest(SnapshotTestCase):

    @classmethod
    def setUpTestData(cls):
        process_customer_file(_named(CUSTOMER_FILE))
        for path in SALE_FILES:
            if path.exists():
                process_sales_file(_named(path))
        # Pre-warm sales caches — all tab tests in this class get cache hits
        from App.analytics.tab_functions import get_sales_tab
        from datetime import date as _date
        get_sales_tab('grade')  # warms _load_sales() all-time + overview
        get_sales_tab('shop')   # warms aggregate_by_shop all-time
        get_sales_tab('grade', date_from=_date(2025, 1, 1), date_to=_date(2025, 12, 31))
        get_sales_tab('shop',  date_from=_date(2025, 1, 1), date_to=_date(2025, 12, 31))

    # ── Full page timing (views → data ready for render) ──────────────────

    def test_page_timing_alltime(self):
        """Simulate full sales page load using production path (cached after setUpTestData)."""
        log = get_run_log()
        log.section("SALES PAGE TIMING (all-time) — production path")
        t = self.timer("sales_page_alltime")

        # Production path: get_sales_tab uses _load_sales() (cached) + aggregators
        data = get_sales_tab('grade')  # grade tab includes overview metrics
        t.checkpoint(
            f"get_sales_tab('grade') → "
            f"active={data['overview']['active_customers'] if data else 0} customers"
        )

        data_shop = get_sales_tab('shop')
        t.checkpoint(f"get_sales_tab('shop') → {len(data_shop.get('by_shop', []))} shops")

        total = t.total()
        t.report()
        self.record_page_timing("SALES (all-time)", total, t._checkpoints)
        self.assertLess(total, 5, f"Sales page all-time took {total:.1f}s > 5s target")

    def test_page_timing_2025(self):
        log = get_run_log()
        log.section("SALES PAGE TIMING (2025 filter)")
        t = self.timer("sales_page_2025")
        data = calculate_return_rate_analytics(date_from=date(2025,1,1), date_to=date(2025,12,31))
        total = t.total()
        t.checkpoint(f"calculate_return_rate_analytics(2025) → active={data['overview']['active_customers'] if data else 0}")
        t.report()
        self.record_page_timing("SALES (2025 filter)", total, t._checkpoints)

    # ── Snapshots ─────────────────────────────────────────────────────────

    def test_snapshot_alltime(self):
        t = self.timer("sales_snapshot_alltime")
        data = calculate_return_rate_analytics()
        t.checkpoint("calculate_return_rate_analytics(all-time)")
        t.report()
        self.assertIsNotNone(data)
        self.assert_snapshot("sales_alltime", {
            "overview": data["overview"],
            "by_grade_count": len(data["by_grade"]),
            "by_session_count": len(data["by_session"]),
            "by_month_count": len(data["by_month"]),
            "by_shop_count": len(data["by_shop"]),
            "by_grade": data["by_grade"],
            "by_session": data["by_session"],
            "customer_details_count": len(data["customer_details"]),
        })

    def test_snapshot_2025(self):
        t = self.timer("sales_snapshot_2025")
        data = calculate_return_rate_analytics(date_from=date(2025,1,1), date_to=date(2025,12,31))
        t.checkpoint("calculate_return_rate_analytics(2025)")
        t.report()
        if data is None:
            self.skipTest("No 2025 data")
        self.assert_snapshot("sales_2025", {
            "overview": data["overview"],
            "by_grade_count": len(data["by_grade"]),
            "by_session_count": len(data["by_session"]),
            "by_month_count": len(data["by_month"]),
            "by_shop_count": len(data["by_shop"]),
            "by_grade": data["by_grade"],
            "by_session": data["by_session"],
        })

    # ── Sanity ────────────────────────────────────────────────────────────

    def test_return_rate_sanity(self):
        data = calculate_return_rate_analytics()
        if not data:
            self.skipTest("No data")
        ov = data["overview"]
        self.assertGreaterEqual(ov["return_rate"], 0.0)
        self.assertLessEqual(ov["return_rate"], 100.0)
        self.assertLessEqual(ov["returning_customers"], ov["active_customers"])

    def test_grade_totals_consistent(self):
        data = calculate_return_rate_analytics()
        if not data:
            self.skipTest("No data")
        total_active = data["overview"]["active_customers"]
        grade_sum    = sum(g.get("total_customers", 0) for g in data["by_grade"])
        self.assertEqual(total_active, grade_sum,
            f"Grade sum ({grade_sum}) != overview active ({total_active})")


class SalesTabSnapshotTest(SnapshotTestCase):
    """
    Per-tab lazy-loading tests.
    Each test calls get_sales_tab(tab) — the actual AJAX endpoint path.
    Measures tab-level load time and locks snapshot for regression.
    """

    @classmethod
    def setUpTestData(cls):
        process_customer_file(_named(CUSTOMER_FILE))
        for path in SALE_FILES:
            if path.exists():
                process_sales_file(_named(path))

    def _tab(self, tab):
        data = get_sales_tab(tab)
        if not data:
            self.skipTest("No sales data")
        return data

    def test_tab_perf_all(self):
        """Time each sales tab individually via get_sales_tab() and compare."""
        log = get_run_log()
        log.section("SALES TAB PERF — per-tab via get_sales_tab()")
        timings = {}
        for tab in SALES_TABS:
            t = self.timer(f"sales_tab_{tab}")
            data = get_sales_tab(tab)
            elapsed = t.total()
            timings[tab] = elapsed
            t.checkpoint(f"{tab} → {elapsed:.2f}s")
            t.report()
        self.record_page_timing("SALES per-tab timings", sum(timings.values()),
                                [(f"tab:{k}", 0, v) for k, v in timings.items()])
        # Each individual tab must complete within 15s
        for tab, elapsed in timings.items():
            self.assertLess(elapsed, 15, f"Tab '{tab}' took {elapsed:.1f}s > 15s threshold")

    def test_tab_snapshot_grade(self):
        t = self.timer("sales_tab_grade")
        data = self._tab('grade')
        t.checkpoint(f"by_grade → {len(data['by_grade'])} rows  [{t.total():.2f}s]")
        t.report()
        self.assert_snapshot("sales_tab_grade", {"by_grade": data["by_grade"]})

    def test_tab_snapshot_season(self):
        t = self.timer("sales_tab_season")
        data = self._tab('season')
        t.checkpoint(f"by_session → {len(data['by_session'])} rows  [{t.total():.2f}s]")
        t.report()
        self.assert_snapshot("sales_tab_season", {"by_session": data["by_session"]})

    def test_tab_snapshot_month(self):
        t = self.timer("sales_tab_month")
        data = self._tab('month')
        t.checkpoint(f"by_month → {len(data['by_month'])} rows  [{t.total():.2f}s]")
        t.report()
        self.assert_snapshot("sales_tab_month", {"by_month": data["by_month"]})

    def test_tab_snapshot_week(self):
        t = self.timer("sales_tab_week")
        data = self._tab('week')
        t.checkpoint(f"by_week → {len(data['by_week'])} rows  [{t.total():.2f}s]")
        t.report()
        self.assert_snapshot("sales_tab_week", {"by_week": data["by_week"]})

    def test_tab_snapshot_shop(self):
        t = self.timer("sales_tab_shop")
        data = self._tab('shop')
        t.checkpoint(f"by_shop → {len(data['by_shop'])} shops  [{t.total():.2f}s]")
        t.report()
        self.assert_snapshot("sales_tab_shop", {"by_shop": data["by_shop"]})

    def test_tab_snapshot_grade_allshops(self):
        t = self.timer("sales_tab_grade_allshops")
        data = self._tab('grade_allshops')
        periods = data['periods_by_grade']
        t.checkpoint(f"grade_allshops → {len(periods)} grade periods  [{t.total():.2f}s]")
        t.report()
        self.assertIn('periods_by_grade', data)
        self.assertNotIn('by_grade', data, "by_grade should not be in tab data (removed for perf)")
        self.assertNotIn('by_shop', data,  "by_shop should not be in tab data (removed for perf)")
        # Each period has label + shops list
        for p in periods:
            self.assertIn('label', p)
            self.assertIn('shops', p)
            for sh in p['shops']:
                self.assertIn('shop_name', sh)
                self.assertIn('total_customers', sh)
                self.assertIn('return_rate', sh)
        self.assert_snapshot("sales_tab_grade_allshops", {"periods_by_grade": periods})

    def test_tab_snapshot_season_allshops(self):
        t = self.timer("sales_tab_season_allshops")
        data = self._tab('season_allshops')
        periods = data['periods_by_season']
        t.checkpoint(f"season_allshops → {len(periods)} season periods  [{t.total():.2f}s]")
        t.report()
        self.assertIn('periods_by_season', data)
        self.assertNotIn('by_session', data, "by_session should not be in tab data (removed for perf)")
        self.assertNotIn('by_shop', data,    "by_shop should not be in tab data (removed for perf)")
        for p in periods:
            self.assertIn('label', p)
            self.assertIn('shops', p)
            for sh in p['shops']:
                self.assertIn('shop_name', sh)
                self.assertIn('total_customers', sh)
                self.assertIn('total_invoices_with_vip0', sh)
                self.assertIn('return_rate', sh)
        self.assert_snapshot("sales_tab_season_allshops", {"periods_by_season": periods})

    def test_tab_snapshot_month_allshops(self):
        t = self.timer("sales_tab_month_allshops")
        data = self._tab('month_allshops')
        periods = data['periods_by_month']
        t.checkpoint(f"month_allshops → {len(periods)} month periods  [{t.total():.2f}s]")
        t.report()
        self.assertIn('periods_by_month', data)
        self.assertNotIn('by_month', data, "by_month should not be in tab data (removed for perf)")
        self.assertNotIn('by_shop', data,  "by_shop should not be in tab data (removed for perf)")
        for p in periods:
            self.assertIn('label', p)
            self.assertIn('shops', p)
            for sh in p['shops']:
                self.assertIn('shop_name', sh)
                self.assertIn('total_customers', sh)
                self.assertIn('total_invoices_with_vip0', sh)
                self.assertIn('return_rate', sh)
        self.assert_snapshot("sales_tab_month_allshops", {"periods_by_month": periods})

    def test_tab_snapshot_week_allshops(self):
        t = self.timer("sales_tab_week_allshops")
        data = self._tab('week_allshops')
        periods = data['periods_by_week']
        t.checkpoint(f"week_allshops → {len(periods)} week periods  [{t.total():.2f}s]")
        t.report()
        self.assertIn('periods_by_week', data)
        self.assertNotIn('by_week', data, "by_week should not be in tab data (removed for perf)")
        self.assertNotIn('by_shop', data, "by_shop should not be in tab data (removed for perf)")
        for p in periods:
            self.assertIn('label', p)
            self.assertIn('shops', p)
            for sh in p['shops']:
                self.assertIn('shop_name', sh)
                self.assertIn('total_customers', sh)
                self.assertIn('total_invoices_with_vip0', sh)
                self.assertIn('return_rate', sh)
        self.assert_snapshot("sales_tab_week_allshops", {"periods_by_week": periods})

    def test_export_tab_keys_cover_allshops(self):
        """Download button tab keys must exist in _TAB_SHEETS."""
        from App.analytics.excel_export import _TAB_SHEETS
        for tab in ('grade_allshops', 'season_allshops', 'month_allshops', 'week_allshops'):
            self.assertIn(tab, _TAB_SHEETS, f"Missing tab key in _TAB_SHEETS: {tab}")

    def test_export_cnv_tab_keys_cover_allshops(self):
        """Download button CNV tab keys must exist in _CNV_TAB_SHEETS."""
        from App.analytics.excel_export import _CNV_TAB_SHEETS
        for tab in ('bd_season_allshops', 'bd_month_allshops', 'bd_week_allshops'):
            self.assertIn(tab, _CNV_TAB_SHEETS, f"Missing tab key in _CNV_TAB_SHEETS: {tab}")
