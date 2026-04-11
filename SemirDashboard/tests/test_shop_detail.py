"""
tests/test_shop_detail.py — Shop Detail page consistency + performance tests.

Validates that shop_detail direct-query functions return data IDENTICAL to what
the original Sale / Customer / Coupon pages produce for the same shop.

Performance target:
  - Sales (direct DB filter):  < original get_sales_tab('shop') (no all-shop pass)
  - Customer (store_filter):   < original get_customer_tab('bd_shop') (same cached fetch,
                                  only filtered Python accumulation)
  - Coupon (direct DB filter): already fast (DB-scoped, ~0.1s)

Run:
  cd SemirDashboard && python manage.py test tests.test_shop_detail -v 2

Regenerate snapshots:
  UPDATE_SNAPSHOTS=1 python manage.py test tests.test_shop_detail -v 2
"""
import io
from datetime import date

from App.models import Customer, SalesTransaction, Coupon
from App.services import process_customer_file, process_sales_file, process_coupon_file
from App.analytics.tab_functions import (
    get_sales_tab,
    get_customer_tab,
    get_coupon_tab,
    get_shop_detail_sales_data,
    get_shop_detail_customer_data,
    get_shop_detail_coupon_data,
)

from tests.base import SnapshotTestCase, INPUT_DIR, get_run_log

CUSTOMER_FILE = INPUT_DIR / "customer.xlsx"
SALE_FILES    = [INPUT_DIR / "Sale 2024.xlsx", INPUT_DIR / "Sale 2025.xlsx", INPUT_DIR / "Sale 2026.xlsx"]
COUPON_FILE   = INPUT_DIR / "coupon_1 (1).xlsx"


def _named(path):
    with open(path, "rb") as f:
        data = f.read()
    class _N(io.BytesIO):
        pass
    obj = _N(data)
    obj.name = path.name
    return obj


class ShopDetailConsistencyTest(SnapshotTestCase):
    """
    Validates direct-query functions match the original all-shops path exactly,
    and that direct queries are faster than loading all shops.
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

    # ── Helpers ───────────────────────────────────────────────────────────────

    def _pick_sales_shop(self):
        return (
            SalesTransaction.objects
            .exclude(shop_name__isnull=True).exclude(shop_name='')
            .values_list('shop_name', flat=True).order_by('shop_name').first()
        )

    def _pick_customer_shop(self):
        return (
            Customer.objects
            .exclude(registration_store__isnull=True).exclude(registration_store='')
            .values_list('registration_store', flat=True).order_by('registration_store').first()
        )

    def _pick_coupon_shop(self):
        return (
            Coupon.objects.filter(using_date__isnull=False)
            .exclude(using_shop__isnull=True).exclude(using_shop='')
            .values_list('using_shop', flat=True).order_by('using_shop').first()
        )

    # ── Sales consistency: direct vs all-shop path ───────────────────────────

    def test_sales_direct_matches_shop_tab_alltime(self):
        """
        get_shop_detail_sales_data(shop) must return identical core metrics to
        get_sales_tab('shop')['by_shop'] for the same shop (all-time).
        """
        if not SalesTransaction.objects.exists():
            self.skipTest("No sales data")

        t = self.timer("sales_direct_vs_shop_tab_alltime")
        shop_name = self._pick_sales_shop()
        self.assertIsNotNone(shop_name)

        # Source of truth: original all-shops tab
        tab_data = get_sales_tab('shop')
        t.checkpoint(f"get_sales_tab(shop) — shops={len(tab_data['by_shop']) if tab_data else 0}")
        expected = next((s for s in (tab_data or {}).get('by_shop', []) if s['shop_name'] == shop_name), None)
        self.assertIsNotNone(expected, f"'{shop_name}' not in shop tab")

        # Direct query path
        actual = get_shop_detail_sales_data(shop_name)
        t.checkpoint(f"get_shop_detail_sales_data — shop={shop_name}")

        self.assertIsNotNone(actual, f"get_shop_detail_sales_data returned None for '{shop_name}'")

        for key in ('total_customers', 'returning_customers', 'return_rate',
                    'returning_invoices', 'total_invoices_with_vip0'):
            self.assertEqual(expected[key], actual[key],
                f"sales[{shop_name}].{key}: expected={expected[key]} actual={actual[key]}")

        # Sub-breakdown row counts: filter empty-period rows from both paths.
        # - tab path (aggregate_by_shop): fills all global period keys, some with zero data
        # - direct path (aggregate_by_season): includes VIP0-only sessions (total_customers=0)
        # Compare only rows where non-VIP0 customers actually transacted.
        exp_by_session = [r for r in expected['by_session'] if r['total_customers'] > 0]
        act_by_session = [r for r in actual['by_session']   if r['total_customers'] > 0]
        exp_by_month   = [r for r in expected['by_month']   if r['total_customers'] > 0]
        act_by_month   = [r for r in actual['by_month']     if r['total_customers'] > 0]
        exp_by_week    = [r for r in expected['by_week']    if r['total_customers'] > 0]
        act_by_week    = [r for r in actual['by_week']      if r['total_customers'] > 0]

        self.assertEqual(len(exp_by_session), len(act_by_session), "by_session length mismatch")
        self.assertEqual(len(exp_by_month),   len(act_by_month),   "by_month length mismatch")
        self.assertEqual(len(exp_by_week),    len(act_by_week),    "by_week length mismatch")

        # Sub-breakdown values for first season must match (using non-zero filtered lists)
        if exp_by_session and act_by_session:
            es, as_ = exp_by_session[0], act_by_session[0]
            self.assertEqual(es['session'],           as_['session'])
            self.assertEqual(es['total_customers'],   as_['total_customers'])
            self.assertEqual(es['returning_customers'], as_['returning_customers'])
            self.assertAlmostEqual(float(es['return_rate']), float(as_['return_rate']), places=2)

        get_run_log().log(
            f"  [sales alltime] shop={shop_name} total={expected['total_customers']} "
            f"ret={expected['return_rate']}%"
        )
        t.report()

    def test_sales_direct_matches_shop_tab_with_date(self):
        """Sales direct vs tab with 2025 date filter."""
        if not SalesTransaction.objects.exists():
            self.skipTest("No sales data")

        t = self.timer("sales_direct_vs_shop_tab_2025")
        date_from, date_to = date(2025, 1, 1), date(2025, 12, 31)

        shop_name = (
            SalesTransaction.objects
            .filter(sales_date__gte=date_from, sales_date__lte=date_to)
            .exclude(shop_name__isnull=True).exclude(shop_name='')
            .values_list('shop_name', flat=True).order_by('shop_name').first()
        )
        if not shop_name:
            self.skipTest("No 2025 sales data")

        tab_data = get_sales_tab('shop', date_from=date_from, date_to=date_to)
        t.checkpoint("get_sales_tab(shop, 2025)")
        expected = next((s for s in (tab_data or {}).get('by_shop', []) if s['shop_name'] == shop_name), None)

        actual = get_shop_detail_sales_data(shop_name, date_from=date_from, date_to=date_to)
        t.checkpoint(f"get_shop_detail_sales_data(2025) — shop={shop_name}")

        self.assertIsNotNone(expected)
        self.assertIsNotNone(actual)
        self.assertEqual(expected['total_customers'],     actual['total_customers'])
        self.assertEqual(expected['returning_customers'], actual['returning_customers'])
        self.assertEqual(expected['return_rate'],         actual['return_rate'])
        self.assertEqual(len(expected['by_month']),       len(actual['by_month']))

        get_run_log().log(
            f"  [sales 2025] shop={shop_name} total={expected['total_customers']} "
            f"ret={expected['return_rate']}%"
        )
        t.report()

    def test_sales_direct_is_faster_than_all_shops(self):
        """
        Direct shop query should be faster than loading all shops when many shops exist.
        (Skipped if only 1 shop — no meaningful comparison.)
        """
        if not SalesTransaction.objects.exists():
            self.skipTest("No sales data")

        n_shops = SalesTransaction.objects.values('shop_name').distinct().count()
        if n_shops < 3:
            self.skipTest(f"Only {n_shops} shops — comparison not meaningful")

        import time
        shop_name = self._pick_sales_shop()

        t0 = time.perf_counter()
        get_sales_tab('shop')
        t_all = time.perf_counter() - t0

        t0 = time.perf_counter()
        get_shop_detail_sales_data(shop_name)
        t_direct = time.perf_counter() - t0

        get_run_log().log(
            f"  [sales speed] all_shops={t_all:.2f}s direct={t_direct:.2f}s "
            f"speedup={t_all/t_direct:.1f}x shops={n_shops}"
        )
        self.assertLess(t_direct, t_all,
            f"Direct query ({t_direct:.2f}s) not faster than all-shops ({t_all:.2f}s)")

    # ── Customer consistency: store_filter vs all-shops path ─────────────────

    def test_customer_direct_matches_bd_shop_tab(self):
        """
        get_shop_detail_customer_data(store) summary must match
        get_customer_tab('bd_shop')['by_shop'] for the same store.
        """
        if not Customer.objects.exists():
            self.skipTest("No customer data")

        t = self.timer("customer_direct_vs_bd_shop_tab")
        store_name = self._pick_customer_shop()
        self.assertIsNotNone(store_name)

        # Source of truth
        tab_data = get_customer_tab('bd_shop')
        t.checkpoint(f"get_customer_tab(bd_shop) — shops={len(tab_data.get('by_shop',[]))}")
        expected_summary = next((r for r in tab_data.get('by_shop', []) if r['label'] == store_name), None)
        expected_detail  = next((sh for sh in tab_data.get('shop_detail', []) if sh['shop'] == store_name), None)

        # Direct (store_filter) path
        actual = get_shop_detail_customer_data(store_name)
        t.checkpoint(f"get_shop_detail_customer_data — store={store_name}")

        if expected_summary:
            self.assertIsNotNone(actual, f"store_filter returned None for '{store_name}'")
            actual_summary = actual.get('summary', {}) or {}
            for key in ('new_pos', 'new_pos_inv', 'new_cnv', 'new_pos_only', 'new_cnv_only',
                        'zalo_app', 'zalo_oa'):
                self.assertEqual(
                    expected_summary.get(key), actual_summary.get(key),
                    f"customer[{store_name}].{key}: expected={expected_summary.get(key)} "
                    f"actual={actual_summary.get(key)}"
                )
            get_run_log().log(
                f"  [customer] store={store_name} new_pos={expected_summary.get('new_pos')} "
                f"new_cnv={expected_summary.get('new_cnv')}"
            )

        if expected_detail and actual:
            self.assertEqual(
                len(expected_detail.get('by_season', [])),
                len(actual.get('by_season', [])),
                "by_season length mismatch"
            )
            self.assertEqual(
                len(expected_detail.get('by_month', [])),
                len(actual.get('by_month', [])),
                "by_month length mismatch"
            )
            self.assertEqual(
                len(expected_detail.get('by_week', [])),
                len(actual.get('by_week', [])),
                "by_week length mismatch"
            )
            # First season row values
            if expected_detail.get('by_season') and actual.get('by_season'):
                es, as_ = expected_detail['by_season'][0], actual['by_season'][0]
                self.assertEqual(es['label'],   as_['label'])
                self.assertEqual(es['new_pos'], as_['new_pos'])
                self.assertEqual(es['new_cnv'], as_['new_cnv'])

        t.report()

    def test_customer_store_filter_is_faster_than_all_stores(self):
        """
        store_filter accumulation should be faster than loading all stores
        (same cached DB fetch, but fewer Python loop iterations).
        """
        if not Customer.objects.exists():
            self.skipTest("No customer data")

        n_stores = Customer.objects.exclude(registration_store__isnull=True).exclude(
            registration_store='').values('registration_store').distinct().count()
        if n_stores < 3:
            self.skipTest(f"Only {n_stores} stores — comparison not meaningful")

        import time
        store_name = self._pick_customer_shop()

        t0 = time.perf_counter()
        get_customer_tab('bd_shop')
        t_all = time.perf_counter() - t0

        t0 = time.perf_counter()
        get_shop_detail_customer_data(store_name)
        t_direct = time.perf_counter() - t0

        get_run_log().log(
            f"  [customer speed] all_stores={t_all:.2f}s store_filter={t_direct:.2f}s "
            f"speedup={t_all/t_direct:.1f}x stores={n_stores}"
        )
        self.assertLess(t_direct, t_all,
            f"store_filter ({t_direct:.2f}s) not faster than all-stores ({t_all:.2f}s)")

    # ── Coupon consistency: DB-filtered vs all-shops path ────────────────────

    def test_coupon_direct_matches_shop_tab_alltime(self):
        """
        get_shop_detail_coupon_data(shop).period.used must equal
        get_coupon_tab('shop')['by_shop'] used for the same shop (all-time).
        """
        if not Coupon.objects.exists():
            self.skipTest("No coupon data")

        t = self.timer("coupon_direct_vs_shop_tab")
        coupon_shop = self._pick_coupon_shop()
        if not coupon_shop:
            self.skipTest("No used coupons found")

        shop_tab = get_coupon_tab('shop')
        t.checkpoint(f"get_coupon_tab(shop) — rows={len(shop_tab.get('by_shop',[]))}")
        expected = next((r for r in shop_tab.get('by_shop', []) if r['shop_name'] == coupon_shop), None)
        self.assertIsNotNone(expected, f"'{coupon_shop}' not in coupon tab")

        actual = get_shop_detail_coupon_data(coupon_shop)
        t.checkpoint(f"get_shop_detail_coupon_data — shop={coupon_shop}")

        self.assertEqual(actual['period']['used'],   expected['used'],
            f"period.used: {actual['period']['used']} vs tab {expected['used']}")
        self.assertEqual(actual['period']['unused'], expected['unused'],
            f"period.unused: {actual['period']['unused']} vs tab {expected['unused']}")
        self.assertAlmostEqual(actual['period']['usage_rate'], expected['usage_rate'], places=2)
        self.assertAlmostEqual(
            actual['period']['total_coupon_amount'], expected['coupon_amount'], places=1,
            msg="period.coupon_amount mismatch"
        )

        get_run_log().log(
            f"  [coupon] shop={coupon_shop} used={expected['used']} rate={expected['usage_rate']}%"
        )
        t.report()

    def test_coupon_direct_matches_shop_tab_2025(self):
        """Coupon direct vs tab with 2025 date filter."""
        if not Coupon.objects.exists():
            self.skipTest("No coupon data")

        t = self.timer("coupon_direct_vs_shop_tab_2025")
        date_from, date_to = date(2025, 1, 1), date(2025, 12, 31)

        coupon_shop = (
            Coupon.objects.filter(using_date__gte=date_from, using_date__lte=date_to)
            .exclude(using_shop__isnull=True).exclude(using_shop='')
            .values_list('using_shop', flat=True).order_by('using_shop').first()
        )
        if not coupon_shop:
            self.skipTest("No 2025 coupon data")

        shop_tab = get_coupon_tab('shop', date_from=date_from, date_to=date_to)
        t.checkpoint("get_coupon_tab(shop, 2025)")
        expected = next((r for r in shop_tab.get('by_shop', []) if r['shop_name'] == coupon_shop), None)

        actual = get_shop_detail_coupon_data(coupon_shop, date_from=date_from, date_to=date_to)
        t.checkpoint(f"get_shop_detail_coupon_data(2025) — shop={coupon_shop}")

        self.assertIsNotNone(expected)
        self.assertEqual(actual['period']['used'],   expected['used'])
        self.assertEqual(actual['period']['unused'], expected['unused'])
        self.assertAlmostEqual(
            actual['period']['total_coupon_amount'], expected['coupon_amount'], places=1
        )

        get_run_log().log(
            f"  [coupon 2025] shop={coupon_shop} used={expected['used']}"
        )
        t.report()

    def test_coupon_all_time_scoped_to_shop(self):
        """all_time.total/used must equal direct DB count for that shop."""
        if not Coupon.objects.exists():
            self.skipTest("No coupon data")

        t = self.timer("coupon_alltime_scope")
        coupon_shop = self._pick_coupon_shop()
        if not coupon_shop:
            self.skipTest("No used coupons")

        db_total = Coupon.objects.filter(using_shop=coupon_shop).count()
        db_used  = Coupon.objects.filter(using_shop=coupon_shop, using_date__isnull=False).count()

        actual = get_shop_detail_coupon_data(coupon_shop)
        t.checkpoint(f"get_shop_detail_coupon_data — shop={coupon_shop}")

        self.assertEqual(actual['all_time']['total'], db_total)
        self.assertEqual(actual['all_time']['used'],  db_used)

        get_run_log().log(f"  [coupon alltime] shop={coupon_shop} total={db_total} used={db_used}")
        t.report()

    def test_coupon_details_all_belong_to_shop(self):
        """Every row in details must have using_shop == requested shop."""
        if not Coupon.objects.exists():
            self.skipTest("No coupon data")

        t = self.timer("coupon_detail_filter")
        coupon_shop = self._pick_coupon_shop()
        if not coupon_shop:
            self.skipTest("No used coupons")

        actual = get_shop_detail_coupon_data(coupon_shop)
        t.checkpoint(f"rows={len(actual['details'])}")

        for i, row in enumerate(actual['details']):
            self.assertEqual(row['using_shop'], coupon_shop,
                f"detail[{i}].using_shop={row['using_shop']!r} != {coupon_shop!r}")

        t.report()

    # ── Snapshot tests ────────────────────────────────────────────────────────

    def test_snapshot_sales_shop_detail(self):
        """Snapshot: direct sales query output (core metrics only)."""
        if not SalesTransaction.objects.exists():
            self.skipTest("No sales data")

        t = self.timer("snapshot_sales_direct")
        shop_name = self._pick_sales_shop()
        self.assertIsNotNone(shop_name)

        data = get_shop_detail_sales_data(shop_name)
        t.checkpoint(f"shop={shop_name}")
        self.assertIsNotNone(data)

        self.assert_snapshot('shop_detail_sales', {
            'shop_name':                data['shop_name'],
            'total_customers':          data['total_customers'],
            'returning_customers':      data['returning_customers'],
            'return_rate':              data['return_rate'],
            'returning_invoices':       data['returning_invoices'],
            'total_invoices_with_vip0': data['total_invoices_with_vip0'],
            'by_session_count':         len(data.get('by_session', [])),
            'by_month_count':           len(data.get('by_month', [])),
            'by_week_count':            len(data.get('by_week', [])),
        })
        t.checkpoint("snapshot verified")
        t.report()

    def test_snapshot_customer_shop_detail(self):
        """Snapshot: store_filter customer output."""
        if not Customer.objects.exists():
            self.skipTest("No customer data")

        t = self.timer("snapshot_customer_direct")
        store_name = self._pick_customer_shop()
        self.assertIsNotNone(store_name)

        data = get_shop_detail_customer_data(store_name)
        t.checkpoint(f"store={store_name}")

        s = (data or {}).get('summary') or {}
        self.assert_snapshot('shop_detail_customer', {
            'store': store_name,
            'summary': {k: s.get(k) for k in (
                'new_pos', 'new_pos_inv', 'new_pos_no_inv', 'new_pos_only',
                'new_cnv', 'new_cnv_only', 'zalo_app', 'zalo_oa',
            )} if s else None,
            'by_season_count': len((data or {}).get('by_season', [])),
            'by_month_count':  len((data or {}).get('by_month',  [])),
            'by_week_count':   len((data or {}).get('by_week',   [])),
        })
        t.checkpoint("snapshot verified")
        t.report()

    def test_snapshot_coupon_shop_detail(self):
        """Snapshot: direct coupon query output."""
        if not Coupon.objects.exists():
            self.skipTest("No coupon data")

        t = self.timer("snapshot_coupon_direct")
        coupon_shop = self._pick_coupon_shop()
        if not coupon_shop:
            self.skipTest("No used coupons")

        data = get_shop_detail_coupon_data(coupon_shop)
        t.checkpoint(f"shop={coupon_shop}")

        self.assert_snapshot('shop_detail_coupon', {
            'shop': coupon_shop,
            'all_time': {k: data['all_time'][k] for k in ('total','used','unused','usage_rate')},
            'period':   {k: data['period'][k]   for k in ('total','used','unused','usage_rate')},
            'details_count': len(data['details']),
        })
        t.checkpoint("snapshot verified")
        t.report()

    # ── Full page timing ──────────────────────────────────────────────────────

    def test_page_timing_all_three_sections(self):
        """Simulate full shop_detail page load with direct queries for all 3 sections."""
        if not SalesTransaction.objects.exists():
            self.skipTest("No sales data")

        t = self.timer("shop_detail_full_page_direct")

        sales_shop    = self._pick_sales_shop()
        customer_shop = self._pick_customer_shop()
        coupon_shop   = self._pick_coupon_shop()

        get_run_log().log(
            f"  shops: sales={sales_shop} customer={customer_shop} coupon={coupon_shop}"
        )

        if sales_shop:
            sd = get_shop_detail_sales_data(sales_shop)
            t.checkpoint(f"sales direct: {sales_shop} → {sd['total_customers'] if sd else 'no data'} customers")

        if customer_shop:
            cd = get_shop_detail_customer_data(customer_shop)
            s = (cd or {}).get('summary') or {}
            t.checkpoint(f"customer store_filter: {customer_shop} → pos={s.get('new_pos','no data')}")

        if coupon_shop:
            cpd = get_shop_detail_coupon_data(coupon_shop)
            t.checkpoint(f"coupon direct: {coupon_shop} → used={cpd['period']['used']} details={len(cpd['details'])}")

        total = t.total()
        self.record_page_timing("shop_detail_full_direct", total, t._checkpoints)
        t.report()

        self.assertLess(total, 60, f"Full page load too slow: {total:.1f}s")
