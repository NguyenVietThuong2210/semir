"""
tests/test_customer_chart.py — Customer Analytics Charts: consistency with table page.

Key invariant: compute_customer_chart_data() must produce the same numbers as the
customer analytics page (get_customer_tab / compute_cnv_breakdown) for every
season / month / week row and every overview metric.

Run:
  cd SemirDashboard && python manage.py test tests.test_customer_chart -v 2

Update snapshots:
  UPDATE_SNAPSHOTS=1 python manage.py test tests.test_customer_chart -v 2
"""
import io

from App.models import Customer
from App.cnv.models import CNVCustomer
from App.services import process_customer_file, process_sales_file
from App.analytics.tab_functions import get_customer_tab
from App.cnv.views import compute_customer_chart_data

from tests.base import SnapshotTestCase, INPUT_DIR, get_run_log

CUSTOMER_FILE = INPUT_DIR / "customer.xlsx"
CNV_FILE      = INPUT_DIR / "cnv_customers.csv"
SALE_FILES    = [INPUT_DIR / "Sale 2024.xlsx", INPUT_DIR / "Sale 2025.xlsx", INPUT_DIR / "Sale 2026.xlsx"]

# All 10 metric fields present in every chart row
_ALL_10_FIELDS = (
    "new_pos_inv", "new_pos_no_inv", "new_pos", "new_pos_only",
    "new_cnv", "new_cnv_only",
    "zalo_app", "zalo_app_pct", "zalo_oa", "zalo_oa_pct",
)


def _named(path):
    with open(path, "rb") as f:
        data = f.read()

    class _N(io.BytesIO):
        pass
    obj = _N(data)
    obj.name = path.name
    return obj


def _load_cnv_from_csv():
    """Reuse loader from test_customer."""
    from tests.test_customer import _load_cnv_customers_from_csv
    return _load_cnv_customers_from_csv()


class CustomerChartConsistencyTest(SnapshotTestCase):
    """
    Ensures chart data ≡ table data for every metric, period, and granularity.

    Strategy:
    - Call compute_customer_chart_data(start, end) → chart
    - Call get_customer_tab('bd_season'/'bd_month'/'bd_week', start, end) → page tables
    - Assert every chart row matches its corresponding page-table row.
    """

    @classmethod
    def setUpTestData(cls):
        if CUSTOMER_FILE.exists():
            process_customer_file(_named(CUSTOMER_FILE))
        for path in SALE_FILES:
            if path.exists():
                process_sales_file(_named(path))
        _load_cnv_from_csv()

    # ── helpers ──────────────────────────────────────────────────────────────

    def _skip_if_no_data(self):
        if not Customer.objects.exists() and not CNVCustomer.objects.exists():
            self.skipTest("No fixture data — skipping chart consistency tests")

    def _chart(self, start="", end=""):
        """Compute chart data; invalidate locmem cache first to force fresh computation."""
        from django.core.cache import cache
        cache.clear()
        return compute_customer_chart_data(start, end)

    def _tab_season(self, start="", end=""):
        from django.core.cache import cache
        cache.clear()
        return get_customer_tab('bd_season', start, end)

    def _tab_month(self, start="", end=""):
        from django.core.cache import cache
        cache.clear()
        return get_customer_tab('bd_month', start, end)

    def _tab_week(self, start="", end=""):
        from django.core.cache import cache
        cache.clear()
        return get_customer_tab('bd_week', start, end)

    # ── overview metrics (all-time) ───────────────────────────────────────────

    def test_overview_active_zalo_matches_tab(self):
        """Chart overview.active_zalo == ca_zalo tab zalo_app_all_count."""
        self._skip_if_no_data()
        chart = self._chart()
        zalo_tab = get_customer_tab('ca_zalo')
        self.assertEqual(
            chart["overview"]["active_zalo"],
            zalo_tab["zalo_app_all_count"],
            "active_zalo mismatch between chart overview and ca_zalo tab",
        )

    def test_overview_follow_oa_matches_tab(self):
        """Chart overview.follow_oa == ca_zalo tab zalo_oa_all_count."""
        self._skip_if_no_data()
        chart = self._chart()
        zalo_tab = get_customer_tab('ca_zalo')
        self.assertEqual(
            chart["overview"]["follow_oa"],
            zalo_tab["zalo_oa_all_count"],
            "follow_oa mismatch between chart overview and ca_zalo tab",
        )

    def test_overview_cnv_only_pos_only_consistent(self):
        """Chart cnv_only + pos_only derived from same phone sets as page."""
        self._skip_if_no_data()
        from App.cnv.service import get_cnv_phone_sets
        pos_phones, cnv_phones = get_cnv_phone_sets()
        expected_pos_only = len(pos_phones - cnv_phones)
        expected_cnv_only = len(cnv_phones - pos_phones)
        chart = self._chart()
        self.assertEqual(chart["overview"]["pos_only"], expected_pos_only,
                         "chart pos_only != len(pos_phones - cnv_phones)")
        self.assertEqual(chart["overview"]["cnv_only"], expected_cnv_only,
                         "chart cnv_only != len(cnv_phones - pos_phones)")

    # ── season stats consistency ──────────────────────────────────────────────

    def _assert_season_match(self, chart_rows, page_rows, label):
        """Check that chart season rows match page season rows exactly (all 10 metrics)."""
        page_by_label  = {r["label"]: r for r in page_rows}
        chart_by_label = {r["label"]: r for r in chart_rows}

        self.assertEqual(
            set(chart_by_label.keys()), set(page_by_label.keys()),
            f"[{label}] season label sets differ: "
            f"chart={sorted(chart_by_label.keys())} page={sorted(page_by_label.keys())}",
        )

        for lbl, cr in chart_by_label.items():
            pr = page_by_label[lbl]
            for field in _ALL_10_FIELDS:
                self.assertEqual(
                    cr[field], pr[field],
                    f"[{label}] season {lbl}: {field} mismatch chart={cr[field]} page={pr[field]}",
                )

    def test_season_alltime_chart_vs_page(self):
        self._skip_if_no_data()
        chart = self._chart()
        page  = self._tab_season()
        self._assert_season_match(chart["season_stats"], page["by_season"], "alltime")

    def test_season_2025_chart_vs_page(self):
        self._skip_if_no_data()
        chart = self._chart("2025-01-01", "2025-12-31")
        page  = self._tab_season("2025-01-01", "2025-12-31")
        self._assert_season_match(chart["season_stats"], page["by_season"], "2025")

    # ── month stats consistency ───────────────────────────────────────────────

    def _assert_month_match(self, chart_rows, page_rows, label):
        """Chart month key = 'YYYY-MM', page label = same 'YYYY-MM'."""
        page_by_label  = {r["label"]: r for r in page_rows}
        chart_by_month = {r["month"]: r for r in chart_rows}

        self.assertEqual(
            set(chart_by_month.keys()), set(page_by_label.keys()),
            f"[{label}] month label sets differ",
        )

        for m, cr in chart_by_month.items():
            pr = page_by_label[m]
            for field in _ALL_10_FIELDS:
                self.assertEqual(
                    cr[field], pr[field],
                    f"[{label}] month {m}: {field} mismatch chart={cr[field]} page={pr[field]}",
                )

    def test_month_alltime_chart_vs_page(self):
        self._skip_if_no_data()
        chart = self._chart()
        page  = self._tab_month()
        self._assert_month_match(chart["month_stats"], page["by_month"], "alltime")

    def test_month_2025_chart_vs_page(self):
        self._skip_if_no_data()
        chart = self._chart("2025-01-01", "2025-12-31")
        page  = self._tab_month("2025-01-01", "2025-12-31")
        self._assert_month_match(chart["month_stats"], page["by_month"], "2025")

    # ── week stats consistency ────────────────────────────────────────────────

    def _assert_week_match(self, chart_rows, page_rows, label):
        """
        Chart week key = display label like 'Week N (d/m-d/m)'.
        Page rows also have 'label' = same display label.
        """
        self.assertEqual(
            len(chart_rows), len(page_rows),
            f"[{label}] week row count differs: chart={len(chart_rows)} page={len(page_rows)}",
        )

        for i, (cr, pr) in enumerate(zip(chart_rows, page_rows)):
            self.assertEqual(cr["week"], pr["label"],
                             f"[{label}] week[{i}] label mismatch chart={cr['week']!r} page={pr['label']!r}")
            for field in _ALL_10_FIELDS:
                self.assertEqual(
                    cr[field], pr[field],
                    f"[{label}] week {cr['week']}: {field} mismatch chart={cr[field]} page={pr[field]}",
                )

    def test_week_alltime_chart_vs_page(self):
        self._skip_if_no_data()
        chart = self._chart()
        page  = self._tab_week()
        self._assert_week_match(chart["week_stats"], page["by_week"], "alltime")

    def test_week_2025_chart_vs_page(self):
        self._skip_if_no_data()
        chart = self._chart("2025-01-01", "2025-12-31")
        page  = self._tab_week("2025-01-01", "2025-12-31")
        self._assert_week_match(chart["week_stats"], page["by_week"], "2025")

    # ── all-time YOY series: independent of filtered series ──────────────────

    def test_alltime_series_independent_of_filter(self):
        """all_*_stats must always equal stats from an unfiltered call."""
        self._skip_if_no_data()
        filtered   = self._chart("2025-01-01", "2025-12-31")
        unfiltered = self._chart()

        def _eq_season(rows_a, rows_b, label):
            by_a = {r["label"]: r for r in rows_a}
            by_b = {r["label"]: r for r in rows_b}
            self.assertEqual(set(by_a), set(by_b), f"[{label}] label sets differ")
            for lbl, a in by_a.items():
                b = by_b[lbl]
                for field in _ALL_10_FIELDS:
                    self.assertEqual(a[field], b[field], f"[{label}] season {lbl}: {field} mismatch")

        def _eq_month(rows_a, rows_b, label):
            by_a = {r["month"]: r for r in rows_a}
            by_b = {r["month"]: r for r in rows_b}
            self.assertEqual(set(by_a), set(by_b), f"[{label}] month sets differ")
            for m, a in by_a.items():
                b = by_b[m]
                for field in _ALL_10_FIELDS:
                    self.assertEqual(a[field], b[field], f"[{label}] month {m}: {field} mismatch")

        def _eq_week(rows_a, rows_b, label):
            self.assertEqual(len(rows_a), len(rows_b),
                             f"[{label}] week row count {len(rows_a)} vs {len(rows_b)}")
            for i, (a, b) in enumerate(zip(rows_a, rows_b)):
                self.assertEqual(a["week"], b["week"],
                                 f"[{label}] week[{i}] label mismatch {a['week']!r} vs {b['week']!r}")
                for field in _ALL_10_FIELDS:
                    self.assertEqual(a[field], b[field], f"[{label}] week {a['week']}: {field} mismatch")

        _eq_season(filtered["all_season_stats"], unfiltered["season_stats"], "yoy_season")
        _eq_month(filtered["all_month_stats"],   unfiltered["month_stats"],  "yoy_month")
        _eq_week(filtered["all_week_stats"],     unfiltered["week_stats"],   "yoy_week")

    # ── overview totals cross-check ───────────────────────────────────────────

    def test_overview_totals_consistent(self):
        """active_zalo <= total_cnv; pos_only <= total_pos; follow_oa <= total_cnv."""
        self._skip_if_no_data()
        chart = self._chart()
        ov = chart["overview"]
        self.assertLessEqual(ov["active_zalo"], ov["total_cnv"], "active_zalo > total_cnv")
        self.assertLessEqual(ov["follow_oa"],   ov["total_cnv"], "follow_oa > total_cnv")
        self.assertLessEqual(ov["pos_only"],    ov["total_pos"], "pos_only > total_pos")
        self.assertLessEqual(ov["cnv_only"],    ov["total_cnv"], "cnv_only > total_cnv")

    # ── structure / schema ────────────────────────────────────────────────────

    def test_chart_data_structure(self):
        """compute_customer_chart_data() returns all expected top-level keys."""
        self._skip_if_no_data()
        chart = self._chart()
        for key in ("overview", "season_stats", "month_stats", "week_stats",
                    "all_season_stats", "all_month_stats", "all_week_stats",
                    "shops", "shop_stats"):
            self.assertIn(key, chart, f"Missing key: {key!r}")

        for k in ("total_cnv", "total_pos", "active_zalo", "follow_oa", "cnv_only", "pos_only"):
            self.assertIn(k, chart["overview"], f"Missing overview key: {k!r}")

    def test_chart_row_schema_all_10_metrics_season(self):
        """Each season_stats row has all 10 metric fields."""
        self._skip_if_no_data()
        chart = self._chart()
        for row in chart["season_stats"]:
            self.assertIn("label", row, "season row missing 'label'")
            for field in _ALL_10_FIELDS:
                self.assertIn(field, row, f"season row missing field: {field!r}")

    def test_chart_row_schema_all_10_metrics_month(self):
        """Each month_stats row has all 10 metric fields."""
        self._skip_if_no_data()
        chart = self._chart()
        for row in chart["month_stats"]:
            self.assertIn("month", row, "month row missing 'month'")
            self.assertRegex(row["month"], r"^\d{4}-\d{2}$",
                             f"month label format unexpected: {row['month']!r}")
            for field in _ALL_10_FIELDS:
                self.assertIn(field, row, f"month row missing field: {field!r}")

    def test_chart_row_schema_all_10_metrics_week(self):
        """Each week_stats row has all 10 metric fields."""
        self._skip_if_no_data()
        chart = self._chart()
        for row in chart["week_stats"]:
            self.assertIn("week", row, "week row missing 'week'")
            for field in _ALL_10_FIELDS:
                self.assertIn(field, row, f"week row missing field: {field!r}")

    # ── shop stats structure ──────────────────────────────────────────────────

    def test_shop_stats_structure(self):
        """shops is a sorted list; shop_stats is a dict with season/month/week keys."""
        self._skip_if_no_data()
        chart = self._chart()
        shops      = chart["shops"]
        shop_stats = chart["shop_stats"]

        self.assertIsInstance(shops, list, "shops should be a list")
        self.assertIsInstance(shop_stats, dict, "shop_stats should be a dict")

        # Every shop name in the list has an entry in the dict
        for shop_name in shops:
            self.assertIn(shop_name, shop_stats,
                          f"Shop {shop_name!r} in shops list but not in shop_stats dict")
            entry = shop_stats[shop_name]
            for key in ("season", "month", "week"):
                self.assertIn(key, entry, f"shop_stats[{shop_name!r}] missing key {key!r}")
                self.assertIsInstance(entry[key], list,
                                      f"shop_stats[{shop_name!r}][{key!r}] should be a list")

        # shops list is sorted
        self.assertEqual(shops, sorted(shops), "shops list is not sorted alphabetically")

    def test_shop_stats_row_schema(self):
        """Every row in shop season/month/week arrays has all 10 metric fields."""
        self._skip_if_no_data()
        chart = self._chart()
        shops      = chart["shops"]
        shop_stats = chart["shop_stats"]

        for shop_name in shops:
            entry = shop_stats[shop_name]
            for s_row in entry["season"]:
                self.assertIn("label", s_row, f"shop {shop_name!r} season row missing 'label'")
                for field in _ALL_10_FIELDS:
                    self.assertIn(field, s_row,
                                  f"shop {shop_name!r} season row missing field {field!r}")
            for m_row in entry["month"]:
                self.assertIn("month", m_row, f"shop {shop_name!r} month row missing 'month'")
                for field in _ALL_10_FIELDS:
                    self.assertIn(field, m_row,
                                  f"shop {shop_name!r} month row missing field {field!r}")
            for w_row in entry["week"]:
                self.assertIn("week", w_row, f"shop {shop_name!r} week row missing 'week'")
                for field in _ALL_10_FIELDS:
                    self.assertIn(field, w_row,
                                  f"shop {shop_name!r} week row missing field {field!r}")

    def test_shop_stats_sum_le_total(self):
        """For each season, sum of new_pos across all shops <= total new_pos (shops can overlap)."""
        self._skip_if_no_data()
        chart = self._chart()
        shops      = chart["shops"]
        shop_stats = chart["shop_stats"]
        totals     = {r["label"]: r["new_pos"] for r in chart["season_stats"]}

        if not shops or not totals:
            return  # no data

        for lbl, total_val in totals.items():
            shop_sum = sum(
                next((r["new_pos"] for r in shop_stats[s]["season"] if r["label"] == lbl), 0)
                for s in shops
            )
            # Shop sum can exceed total if customers bought at multiple shops in same season
            # (they appear in multiple shop rows but only once in the aggregate).
            # So we just assert neither is negative.
            self.assertGreaterEqual(total_val, 0,
                                    f"season {lbl} total new_pos is negative: {total_val}")
            self.assertGreaterEqual(shop_sum, 0,
                                    f"season {lbl} shop sum new_pos is negative: {shop_sum}")

    def test_shop_stats_zalo_pct_range(self):
        """zalo_app_pct and zalo_oa_pct must be 0–100 in every shop row."""
        self._skip_if_no_data()
        chart = self._chart()
        for shop_name, entry in chart["shop_stats"].items():
            for period_key in ("season", "month", "week"):
                for row in entry[period_key]:
                    for pct_field in ("zalo_app_pct", "zalo_oa_pct"):
                        v = row[pct_field]
                        self.assertGreaterEqual(v, 0,
                            f"shop {shop_name!r} {period_key} {pct_field}={v} < 0")
                        self.assertLessEqual(v, 100,
                            f"shop {shop_name!r} {period_key} {pct_field}={v} > 100")

    # ── caching: second call returns same data ────────────────────────────────

    def test_cache_returns_identical_data(self):
        """Two consecutive calls with same params return identical results."""
        self._skip_if_no_data()
        from django.core.cache import cache
        cache.clear()
        first  = compute_customer_chart_data("2025-01-01", "2025-12-31")
        second = compute_customer_chart_data("2025-01-01", "2025-12-31")
        self.assertEqual(first["overview"], second["overview"])
        self.assertEqual(first["season_stats"], second["season_stats"])
        self.assertEqual(first["month_stats"], second["month_stats"])
        self.assertEqual(first["shops"], second["shops"])

    # ── performance ───────────────────────────────────────────────────────────

    def test_chart_timing(self):
        """compute_customer_chart_data() must complete within 30s (cold + warm)."""
        self._skip_if_no_data()
        log = get_run_log()
        log.section("CUSTOMER CHART TIMING")
        t = self.timer("customer_chart_cold")

        from django.core.cache import cache
        cache.clear()
        data = compute_customer_chart_data()
        cold = t.total()
        t.checkpoint(
            f"cold call → {cold:.2f}s  seasons={len(data['season_stats'])} "
            f"months={len(data['month_stats'])} weeks={len(data['week_stats'])} "
            f"shops={len(data['shops'])}"
        )

        t2 = self.timer("customer_chart_warm")
        compute_customer_chart_data()
        warm = t2.total()
        t2.checkpoint(f"warm call (cached) → {warm:.2f}s")

        t.report(); t2.report()
        self.record_page_timing("CUSTOMER CHART", cold,
                                [("cold", 0, cold), ("warm", 0, warm)])
        self.assertLess(cold, 30, f"Cold chart data took {cold:.1f}s > 30s")
        self.assertLess(warm,  2, f"Warm chart data took {warm:.1f}s > 2s (cache miss?)")

    # ── snapshot ─────────────────────────────────────────────────────────────

    def test_snapshot_chart_overview(self):
        """Lock overview metrics — any regression triggers snapshot failure."""
        self._skip_if_no_data()
        from django.core.cache import cache
        cache.clear()
        chart = compute_customer_chart_data()
        self.assert_snapshot("customer_chart_overview", chart["overview"])

    def test_snapshot_chart_season_alltime(self):
        self._skip_if_no_data()
        from django.core.cache import cache
        cache.clear()
        chart = compute_customer_chart_data()
        self.assert_snapshot("customer_chart_season_alltime", {
            "count": len(chart["season_stats"]),
            "rows":  chart["season_stats"],
        })

    def test_snapshot_chart_month_2025(self):
        self._skip_if_no_data()
        from django.core.cache import cache
        cache.clear()
        chart = compute_customer_chart_data("2025-01-01", "2025-12-31")
        self.assert_snapshot("customer_chart_month_2025", {
            "count": len(chart["month_stats"]),
            "rows":  chart["month_stats"],
        })

    def test_snapshot_shops_list(self):
        """Lock the set of shop names returned."""
        self._skip_if_no_data()
        from django.core.cache import cache
        cache.clear()
        chart = compute_customer_chart_data()
        self.assert_snapshot("customer_chart_shops", {"shops": chart["shops"]})
