"""
tests/test_consistency.py
─────────────────────────
Data-consistency tests: verify that chart page, dashboard tabs, and
download (export) views all produce the same numbers for the same filters.

Since calculate_return_rate_analytics() now routes through _load_sales()
(the same 5-minute locmem cache used by get_sales_tab()), these tests
confirm the cache sharing works and no code path drifts from another.

Run:
    cd SemirDashboard
    python manage.py test tests.test_consistency -v 2
"""
import io
from datetime import date
from pathlib import Path

from App.services import process_customer_file, process_sales_file
from App.analytics.core import calculate_return_rate_analytics
from App.analytics.tab_functions import (
    get_sales_tab, SALES_TABS,
    get_coupon_tab, COUPON_TABS,
    get_customer_tab, CUSTOMER_TABS,
)
from App.analytics.coupon_analytics import (
    calculate_coupon_analytics,
    get_coupon_summary,
)
from App.cnv.service import get_cnv_comparison_data

from tests.base import SnapshotTestCase, INPUT_DIR, get_run_log

SALE_FILES    = [INPUT_DIR / "Sale 2024.xlsx", INPUT_DIR / "Sale 2025.xlsx", INPUT_DIR / "Sale 2026.xlsx"]
CUSTOMER_FILE = INPUT_DIR / "customer.xlsx"
COUPON_FILE   = INPUT_DIR / "coupon.xlsx"


def _named(path):
    with open(path, "rb") as f:
        data = f.read()
    class _N(io.BytesIO):
        pass
    obj = _N(data)
    obj.name = path.name
    return obj


class SalesConsistencyTest(SnapshotTestCase):
    """
    Verify: dashboard grade tab == calculate_return_rate_analytics()
    for both all-time and 2025 filter.

    After the core.py refactor, both code paths share _load_sales() cache,
    so these checks confirm no accidental divergence between dashboard and export/chart.
    """

    @classmethod
    def setUpTestData(cls):
        process_customer_file(_named(CUSTOMER_FILE))
        for path in SALE_FILES:
            if path.exists():
                process_sales_file(_named(path))

    # ── All-time ────────────────────────────────────────────────────────────

    def test_overview_consistent_alltime(self):
        """grade tab overview == calculate_return_rate_analytics() overview."""
        log = get_run_log()
        log.section("CONSISTENCY: Sales overview (all-time)")
        t = self.timer("consistency_overview_alltime")

        tab_data  = get_sales_tab('grade')
        core_data = calculate_return_rate_analytics()

        t.checkpoint("get_sales_tab('grade') + calculate_return_rate_analytics()")
        t.report()

        self.assertIsNotNone(tab_data,  "grade tab returned None")
        self.assertIsNotNone(core_data, "calculate_return_rate_analytics returned None")

        ov_tab  = tab_data['overview']
        ov_core = core_data['overview']

        self.assertEqual(
            ov_tab['active_customers'], ov_core['active_customers'],
            "active_customers mismatch: grade_tab vs core"
        )
        self.assertEqual(
            ov_tab['returning_customers'], ov_core['returning_customers'],
            "returning_customers mismatch: grade_tab vs core"
        )
        self.assertAlmostEqual(
            ov_tab['return_rate'], ov_core['return_rate'], places=2,
            msg="return_rate mismatch: grade_tab vs core"
        )
        self.assertEqual(
            ov_tab['total_invoices_without_vip0'], ov_core['total_invoices_without_vip0'],
            "total_invoices_without_vip0 mismatch"
        )

    def test_grade_breakdown_consistent_alltime(self):
        """grade tab by_grade == calculate_return_rate_analytics() by_grade."""
        log = get_run_log()
        log.section("CONSISTENCY: Sales grade breakdown (all-time)")

        tab_data  = get_sales_tab('grade')
        core_data = calculate_return_rate_analytics()

        if not tab_data or not core_data:
            self.skipTest("No data")

        tab_grades  = {g['grade']: g for g in tab_data['by_grade']}
        core_grades = {g['grade']: g for g in core_data['by_grade']}

        self.assertEqual(set(tab_grades), set(core_grades), "grade keys differ")

        for grade in tab_grades:
            tg = tab_grades[grade]
            cg = core_grades[grade]
            self.assertEqual(tg['total_customers'], cg['total_customers'],
                f"[{grade}] total_customers mismatch")
            self.assertEqual(tg['returning_customers'], cg['returning_customers'],
                f"[{grade}] returning_customers mismatch")
            self.assertAlmostEqual(tg['return_rate'], cg['return_rate'], places=2,
                msg=f"[{grade}] return_rate mismatch")

    def test_season_tab_consistent_alltime(self):
        """season tab by_session == calculate_return_rate_analytics() by_session."""
        tab_data  = get_sales_tab('season')
        core_data = calculate_return_rate_analytics()

        if not tab_data or not core_data:
            self.skipTest("No data")

        tab_sessions  = {s['session']: s for s in tab_data['by_session']}
        core_sessions = {s['session']: s for s in core_data['by_session']}

        self.assertEqual(set(tab_sessions), set(core_sessions), "session keys differ between tab and core")

        for sk in tab_sessions:
            ts = tab_sessions[sk]
            cs = core_sessions[sk]
            self.assertEqual(ts['total_customers'], cs['total_customers'],
                f"[{sk}] total_customers mismatch")
            self.assertEqual(ts['returning_customers'], cs['returning_customers'],
                f"[{sk}] returning_customers mismatch")

    def test_month_tab_consistent_alltime(self):
        """month tab by_month count == core by_month count."""
        tab_data  = get_sales_tab('month')
        core_data = calculate_return_rate_analytics()

        if not tab_data or not core_data:
            self.skipTest("No data")

        self.assertEqual(len(tab_data['by_month']), len(core_data['by_month']),
            "by_month length mismatch between tab and core")

        tab_months  = {m['month']: m for m in tab_data['by_month']}
        core_months = {m['month']: m for m in core_data['by_month']}
        self.assertEqual(set(tab_months), set(core_months), "month keys differ")

        for mk in tab_months:
            self.assertEqual(
                tab_months[mk]['total_customers'],
                core_months[mk]['total_customers'],
                f"[{mk}] total_customers mismatch"
            )

    def test_shop_tab_consistent_alltime(self):
        """shop tab by_shop count == core by_shop count."""
        tab_data  = get_sales_tab('shop')
        core_data = calculate_return_rate_analytics()

        if not tab_data or not core_data:
            self.skipTest("No data")

        tab_shops  = {s['shop_name']: s for s in tab_data['by_shop']}
        core_shops = {s['shop_name']: s for s in core_data['by_shop']}

        self.assertEqual(set(tab_shops), set(core_shops), "shop names differ between tab and core")

        for shop in tab_shops:
            self.assertEqual(
                tab_shops[shop]['total_customers'],
                core_shops[shop]['total_customers'],
                f"[{shop}] total_customers mismatch"
            )

    # ── 2025 filter ─────────────────────────────────────────────────────────

    def test_overview_consistent_2025(self):
        """grade tab overview == calculate_return_rate_analytics() for 2025 filter."""
        log = get_run_log()
        log.section("CONSISTENCY: Sales overview (2025 filter)")
        t = self.timer("consistency_overview_2025")

        d_from, d_to = date(2025, 1, 1), date(2025, 12, 31)
        tab_data  = get_sales_tab('grade', date_from=d_from, date_to=d_to)
        core_data = calculate_return_rate_analytics(date_from=d_from, date_to=d_to)

        t.checkpoint("grade_tab + core (2025)")
        t.report()

        if not tab_data or not core_data:
            self.skipTest("No 2025 data")

        self.assertEqual(
            tab_data['overview']['active_customers'],
            core_data['overview']['active_customers'],
            "active_customers mismatch for 2025 filter"
        )
        self.assertEqual(
            tab_data['overview']['returning_customers'],
            core_data['overview']['returning_customers'],
            "returning_customers mismatch for 2025 filter"
        )

    # ── Export Excel consistency ─────────────────────────────────────────────

    def test_export_produces_workbook_alltime(self):
        """export_analytics_to_excel() runs without error and has expected sheets."""
        from App.analytics.excel_export import export_analytics_to_excel
        core_data = calculate_return_rate_analytics()
        if not core_data:
            self.skipTest("No data")
        wb = export_analytics_to_excel(core_data)
        self.assertIsNotNone(wb)
        sheet_names = [ws.title for ws in wb.worksheets]
        self.assertIn("Overview", sheet_names)
        self.assertIn("By VIP Grade", sheet_names)

    def test_export_tab_consistent_with_grade_tab(self):
        """export_tab_to_excel('grade') data matches get_sales_tab('grade') data."""
        from App.analytics.excel_export import export_tab_to_excel
        tab_data  = get_sales_tab('grade')
        core_data = calculate_return_rate_analytics()
        if not tab_data or not core_data:
            self.skipTest("No data")
        # Export uses core_data — verify grade rows match tab
        tab_grades  = {g['grade']: g['total_customers'] for g in tab_data['by_grade']}
        core_grades = {g['grade']: g['total_customers'] for g in core_data['by_grade']}
        self.assertEqual(tab_grades, core_grades, "grade tab vs export data mismatch")
        # Workbook builds without error
        wb = export_tab_to_excel('grade', core_data)
        self.assertIsNotNone(wb)


    def test_chart_only_overview_matches_full(self):
        """calculate_return_rate_analytics(chart_only=True) overview == full overview.

        analytics_chart view uses chart_only=True — must not change any overview number.
        """
        log = get_run_log()
        log.section("CONSISTENCY: Sales chart_only=True overview vs full")

        full  = calculate_return_rate_analytics()
        chart = calculate_return_rate_analytics(chart_only=True)

        if not full or not chart:
            self.skipTest("No data")

        for key in ('active_customers', 'returning_customers', 'return_rate',
                    'total_invoices_without_vip0', 'total_invoices_with_vip0',
                    'new_members_in_period', 'buyer_without_info'):
            self.assertEqual(
                full['overview'][key], chart['overview'][key],
                f"overview[{key!r}] differs between chart_only=True and False"
            )

        # chart_only skips grade — by_grade must be empty
        self.assertEqual(chart['by_grade'], [],
            "chart_only=True must return empty by_grade")

        # session/month/year/week/shop must all still be populated
        for dim in ('by_session', 'by_month', 'by_year', 'by_week', 'by_shop'):
            self.assertGreater(len(chart[dim]), 0,
                f"chart_only=True should still compute {dim}")

    def test_chart_by_session_matches_full(self):
        """analytics_chart by_session == calculate_return_rate_analytics() by_session."""
        chart = calculate_return_rate_analytics(chart_only=True)
        full  = calculate_return_rate_analytics()
        if not chart or not full:
            self.skipTest("No data")

        chart_sessions = {s['session']: s for s in chart['by_session']}
        full_sessions  = {s['session']: s for s in full['by_session']}
        self.assertEqual(set(chart_sessions), set(full_sessions), "by_session keys differ")

        for sk in chart_sessions:
            self.assertEqual(chart_sessions[sk]['total_customers'],
                             full_sessions[sk]['total_customers'],
                             f"[{sk}] total_customers differs chart vs full")

    def test_week_tab_consistent_alltime(self):
        """week tab by_week == calculate_return_rate_analytics() by_week."""
        tab_data  = get_sales_tab('week')
        core_data = calculate_return_rate_analytics()
        if not tab_data or not core_data:
            self.skipTest("No data")

        tab_weeks  = {w['week_sort']: w for w in tab_data['by_week']}
        core_weeks = {w['week_sort']: w for w in core_data['by_week']}
        self.assertEqual(set(tab_weeks), set(core_weeks), "week keys differ between tab and core")

        for wk in tab_weeks:
            self.assertEqual(
                tab_weeks[wk]['total_customers'],
                core_weeks[wk]['total_customers'],
                f"[{wk}] total_customers mismatch"
            )


class CouponConsistencyTest(SnapshotTestCase):
    """
    Verify: coupon dashboard tab data == calculate_coupon_analytics() data.
    coupon chart (get_coupon_summary) overview == tab 'shop' overview.
    """

    @classmethod
    def setUpTestData(cls):
        from App.services import process_coupon_file
        if COUPON_FILE.exists():
            process_coupon_file(_named(COUPON_FILE))

    def _skip_if_no_data(self):
        from App.models import Coupon
        if Coupon.objects.count() == 0:
            self.skipTest("No coupon data")

    def test_shop_tab_vs_calculate_coupon_analytics(self):
        """get_coupon_tab('shop') summary counts == calculate_coupon_analytics() summary."""
        self._skip_if_no_data()
        log = get_run_log()
        log.section("CONSISTENCY: Coupon shop tab vs full analytics")
        t = self.timer("consistency_coupon_shop")

        tab_data  = get_coupon_tab('shop')
        full_data = calculate_coupon_analytics()

        t.checkpoint("get_coupon_tab('shop') + calculate_coupon_analytics()")
        t.report()

        self.assertIsNotNone(tab_data,  "coupon shop tab returned None")
        self.assertIsNotNone(full_data, "calculate_coupon_analytics returned None")

        # all_time totals should match
        self.assertEqual(
            tab_data['all_time']['total'], full_data['all_time']['total'],
            "all_time.total mismatch between shop tab and full analytics"
        )
        self.assertEqual(
            tab_data['all_time']['used_count'], full_data['all_time']['used_count'],
            "all_time.used_count mismatch"
        )

        # by_shop count should match
        tab_shops  = {s['shop']: s for s in tab_data['by_shop']}
        full_shops = {s['shop']: s for s in full_data['by_shop']}
        self.assertEqual(set(tab_shops), set(full_shops),
            "shop names differ between tab and full analytics")

        for shop in tab_shops:
            self.assertEqual(
                tab_shops[shop]['used_count'],
                full_shops[shop]['used_count'],
                f"[{shop}] used_count mismatch"
            )

    def test_chart_summary_vs_shop_tab(self):
        """get_coupon_summary() overview == get_coupon_tab('shop') overview."""
        self._skip_if_no_data()
        t = self.timer("consistency_coupon_chart_vs_tab")

        tab_data  = get_coupon_tab('shop')
        chart_sum = get_coupon_summary()

        t.checkpoint("get_coupon_tab('shop') + get_coupon_summary()")
        t.report()

        self.assertEqual(
            tab_data['all_time']['total'], chart_sum['all_time']['total'],
            "all_time.total mismatch: shop tab vs chart summary"
        )
        self.assertEqual(
            tab_data['all_time']['used_count'], chart_sum['all_time']['used_count'],
            "all_time.used_count mismatch: shop tab vs chart summary"
        )

    def test_chart_period_summary_vs_shop_tab(self):
        """get_coupon_summary() period totals == get_coupon_tab('shop') period totals (2025 filter).

        coupon_chart view uses get_coupon_summary() — ensure it agrees with the dashboard tab
        when a date range is applied.
        """
        self._skip_if_no_data()
        d_from, d_to = date(2025, 1, 1), date(2025, 12, 31)

        tab_data  = get_coupon_tab('shop', date_from=d_from, date_to=d_to)
        chart_sum = get_coupon_summary(date_from=d_from, date_to=d_to)

        self.assertIsNotNone(tab_data,  "coupon shop tab (2025) returned None")
        self.assertIsNotNone(chart_sum, "get_coupon_summary (2025) returned None")

        self.assertEqual(
            tab_data['period']['used_count'], chart_sum['period']['used_count'],
            "period.used_count mismatch: shop tab vs chart summary (2025 filter)"
        )
        self.assertEqual(
            tab_data['period']['total'], chart_sum['period']['total'],
            "period.total mismatch: shop tab vs chart summary (2025 filter)"
        )

    def test_coupon_trend_data_smoke(self):
        """calculate_coupon_trend_data() returns valid structure with expected keys."""
        self._skip_if_no_data()
        from App.analytics.coupon_analytics import calculate_coupon_trend_data

        trend = calculate_coupon_trend_data()

        self.assertIsNotNone(trend)
        self.assertIn('shop_series', trend,       "trend missing shop_series")
        self.assertIn('time_labels', trend,       "trend missing time_labels")
        self.assertIn('campaign_series', trend,   "trend missing campaign_series")
        self.assertIn('time_labels_camp', trend,  "trend missing time_labels_camp")

        # shop_series must be a list of dicts with required keys
        if trend['shop_series']:
            shop = trend['shop_series'][0]
            for k in ('shop', 'data'):
                self.assertIn(k, shop, f"shop_series[0] missing key {k!r}")

    def test_coupon_export_consistent_with_tab(self):
        """export_coupon_to_excel() runs without error and uses same totals as tab."""
        self._skip_if_no_data()
        from App.analytics.coupon_analytics import export_coupon_to_excel
        full_data = calculate_coupon_analytics()
        if not full_data:
            self.skipTest("No coupon data")
        tab_data = get_coupon_tab('shop')
        wb = export_coupon_to_excel(full_data)
        self.assertIsNotNone(wb)
        # Totals must match
        self.assertEqual(
            full_data['all_time']['total'], tab_data['all_time']['total'],
            "all_time.total: export data vs tab data mismatch"
        )


class CustomerConsistencyTest(SnapshotTestCase):
    """
    Verify: customer dashboard bd_season tab data == compute_cnv_comparison() bd_season data.
    Ensure get_customer_tab() (dashboard) and get_cnv_comparison_data() (export) agree.
    """

    @classmethod
    def setUpTestData(cls):
        from App.services import process_customer_file as _pcf
        _pcf(_named(CUSTOMER_FILE))
        # Load CNV customers from CSV (same approach as test_customer.py)
        from tests.test_customer import _load_cnv_customers_from_csv
        _cnv = INPUT_DIR / "cnv_customers.csv"
        if _cnv.exists() and _cnv.stat().st_size > 10:
            _load_cnv_customers_from_csv()

    def _skip_if_no_cnv(self):
        from App.cnv.models import CNVCustomer
        if CNVCustomer.objects.count() == 0:
            self.skipTest("No CNV data")

    def test_bd_season_tab_vs_export(self):
        """get_customer_tab('bd_season') season rows == export data bd_season."""
        self._skip_if_no_cnv()
        log = get_run_log()
        log.section("CONSISTENCY: Customer bd_season tab vs export")
        t = self.timer("consistency_customer_bd_season")

        tab_data   = get_customer_tab('bd_season')
        export_d, _ = get_cnv_comparison_data('', '')

        t.checkpoint("get_customer_tab('bd_season') + get_cnv_comparison_data()")
        t.report()

        self.assertIsNotNone(tab_data, "bd_season tab returned None")
        self.assertIsNotNone(export_d, "get_cnv_comparison_data returned None")

        # export_d['breakdown']['season'] is the season list (compute_cnv_breakdown structure)
        export_breakdown = export_d.get('breakdown', {})
        tab_seasons    = {s['label']: s for s in tab_data.get('by_season', [])}
        export_seasons = {s['label']: s for s in export_breakdown.get('season', [])}

        self.assertEqual(set(tab_seasons), set(export_seasons),
            "season labels differ between bd_season tab and export data")

        for lbl in tab_seasons:
            self.assertEqual(
                tab_seasons[lbl]['new_pos'],
                export_seasons[lbl]['new_pos'],
                f"[{lbl}] new_pos mismatch"
            )

    def test_customer_export_produces_workbook(self):
        """export_customer_analytics_to_excel() runs without error."""
        self._skip_if_no_cnv()
        from App.models import Customer
        from App.cnv.models import CNVCustomer
        from App.analytics.excel_export import export_customer_analytics_to_excel
        d, _ = get_cnv_comparison_data('', '')
        if not d:
            self.skipTest("No CNV comparison data")
        wb = export_customer_analytics_to_excel(
            Customer.objects.all(),
            CNVCustomer.objects.all(),
            None, None,
            points_mismatch=d.get("points_mismatch", []),
            total_points_mismatch=d.get("total_points_mismatch", 0),
            cnv_used_points=list(CNVCustomer.objects.filter(used_points__gt=0)),
            zalo_mini_app_list=d.get("zalo_mini_app_list", []),
            zalo_oa_list=d.get("zalo_oa_list", []),
            zalo_stats={k: d.get(k, 0) for k in (
                "zalo_app_all_count", "zalo_oa_all_count",
                "zalo_app_all_pct", "zalo_oa_all_pct",
                "zalo_app_period_count", "zalo_oa_period_count",
                "zalo_app_period_pct", "zalo_oa_period_pct",
            )},
        )
        self.assertIsNotNone(wb)
        self.assertGreater(len(wb.worksheets), 0)
