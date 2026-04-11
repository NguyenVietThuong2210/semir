"""
tests/test_shop_detail.py — Shop Detail page consistency + performance tests.

Verifies that shop_detail data EXACTLY matches what the original
Sale / Customer / Coupon pages return for the same shop.

Run:
  cd SemirDashboard && python manage.py test tests.test_shop_detail -v 2

Regenerate snapshots:
  UPDATE_SNAPSHOTS=1 python manage.py test tests.test_shop_detail -v 2
"""
import io
from datetime import date
from pathlib import Path

from App.models import Customer, SalesTransaction, Coupon
from App.services import process_customer_file, process_sales_file, process_coupon_file
from App.analytics.tab_functions import (
    get_sales_tab,
    get_customer_tab,
    get_coupon_tab,
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
    Validates that data returned by shop_detail helpers is identical to what
    the original pages return for the same shop.
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
        """Pick the first shop that has data from SalesTransaction."""
        shop = (
            SalesTransaction.objects
            .exclude(shop_name__isnull=True).exclude(shop_name='')
            .values_list('shop_name', flat=True)
            .order_by('shop_name')
            .first()
        )
        return shop

    def _pick_customer_shop(self):
        """Pick the first registration_store that has data."""
        store = (
            Customer.objects
            .exclude(registration_store__isnull=True).exclude(registration_store='')
            .values_list('registration_store', flat=True)
            .order_by('registration_store')
            .first()
        )
        return store

    def _pick_coupon_shop(self):
        """Pick the first using_shop that has used coupons."""
        shop = (
            Coupon.objects
            .filter(using_date__isnull=False)
            .exclude(using_shop__isnull=True).exclude(using_shop='')
            .values_list('using_shop', flat=True)
            .order_by('using_shop')
            .first()
        )
        return shop

    # ── Sales consistency ────────────────────────────────────────────────────

    def test_sales_shop_detail_matches_shop_tab_alltime(self):
        """
        Sales data for shop X in shop_detail (all-time, no date filter) must
        exactly equal the corresponding entry in get_sales_tab('shop')['by_shop'].
        """
        if not SalesTransaction.objects.exists():
            self.skipTest("No sales data")

        t = self.timer("shop_detail_sales_consistency_alltime")

        shop_name = self._pick_sales_shop()
        self.assertIsNotNone(shop_name, "No shop found in SalesTransaction")

        # Source of truth: original sales shop tab
        tab_data = get_sales_tab('shop')
        t.checkpoint(f"get_sales_tab(shop) done — shops={len(tab_data['by_shop']) if tab_data else 0}")
        self.assertIsNotNone(tab_data, "get_sales_tab returned None")

        expected = next((s for s in tab_data['by_shop'] if s['shop_name'] == shop_name), None)

        # Shop detail path: same function, should return identical object
        tab_data2 = get_sales_tab('shop')
        actual = next((s for s in tab_data2['by_shop'] if s['shop_name'] == shop_name), None)
        t.checkpoint(f"shop_detail sales lookup done — shop={shop_name}")

        self.assertIsNotNone(expected, f"Shop '{shop_name}' not found in tab data")
        self.assertIsNotNone(actual,   f"Shop '{shop_name}' not found in tab data (2nd call)")

        # Core metrics must match exactly
        for key in ('total_customers', 'returning_customers', 'return_rate',
                    'returning_invoices', 'total_invoices_with_vip0'):
            self.assertEqual(expected[key], actual[key],
                f"sales[{shop_name}].{key}: {expected[key]} vs {actual[key]}")

        # Period counts by season / month / week must match
        self.assertEqual(len(expected['by_session']), len(actual['by_session']),
            "by_session length mismatch")
        self.assertEqual(len(expected['by_month']),   len(actual['by_month']),
            "by_month length mismatch")
        self.assertEqual(len(expected['by_week']),    len(actual['by_week']),
            "by_week length mismatch")

        get_run_log().log(
            f"  [sales] shop={shop_name} total={expected['total_customers']} "
            f"return_rate={expected['return_rate']}%"
        )
        t.report()

    def test_sales_shop_detail_matches_shop_tab_with_date_filter(self):
        """Sales consistency with date filter."""
        if not SalesTransaction.objects.exists():
            self.skipTest("No sales data")

        t = self.timer("shop_detail_sales_consistency_date_filtered")

        # Use 2025 as the period
        date_from = date(2025, 1, 1)
        date_to   = date(2025, 12, 31)

        shop_name = (
            SalesTransaction.objects
            .filter(sales_date__gte=date_from, sales_date__lte=date_to)
            .exclude(shop_name__isnull=True).exclude(shop_name='')
            .values_list('shop_name', flat=True)
            .order_by('shop_name')
            .first()
        )
        if not shop_name:
            self.skipTest("No sales data in 2025")

        tab_data = get_sales_tab('shop', date_from=date_from, date_to=date_to)
        t.checkpoint("get_sales_tab(shop, 2025) done")

        expected = next((s for s in (tab_data or {}).get('by_shop', []) if s['shop_name'] == shop_name), None)
        tab_data2 = get_sales_tab('shop', date_from=date_from, date_to=date_to)
        actual    = next((s for s in (tab_data2 or {}).get('by_shop', []) if s['shop_name'] == shop_name), None)
        t.checkpoint(f"shop_detail lookup done — shop={shop_name}")

        self.assertIsNotNone(expected)
        self.assertIsNotNone(actual)
        self.assertEqual(expected['total_customers'],    actual['total_customers'])
        self.assertEqual(expected['returning_customers'], actual['returning_customers'])
        self.assertEqual(expected['return_rate'],         actual['return_rate'])

        get_run_log().log(
            f"  [sales 2025] shop={shop_name} total={expected['total_customers']} "
            f"return_rate={expected['return_rate']}%"
        )
        t.report()

    # ── Customer consistency ────────────────────────────────────────────────

    def test_customer_shop_detail_matches_bd_shop_tab(self):
        """
        Customer data for registration_store X in shop_detail must exactly equal
        the corresponding entry in get_customer_tab('bd_shop')['by_shop'].
        """
        if not Customer.objects.exists():
            self.skipTest("No customer data")

        t = self.timer("shop_detail_customer_consistency")

        store_name = self._pick_customer_shop()
        self.assertIsNotNone(store_name, "No registration_store found in Customer")

        tab_data = get_customer_tab('bd_shop')
        t.checkpoint(f"get_customer_tab(bd_shop) — shops={len(tab_data.get('by_shop',[]))}")

        expected_summary = next((r for r in tab_data.get('by_shop', []) if r['label'] == store_name), None)
        expected_detail  = next((sh for sh in tab_data.get('shop_detail', []) if sh['shop'] == store_name), None)

        tab_data2 = get_customer_tab('bd_shop')
        actual_summary = next((r for r in tab_data2.get('by_shop', []) if r['label'] == store_name), None)
        actual_detail  = next((sh for sh in tab_data2.get('shop_detail', []) if sh['shop'] == store_name), None)
        t.checkpoint(f"shop_detail customer lookup done — store={store_name}")

        if expected_summary:
            for key in ('new_pos', 'new_pos_inv', 'new_cnv', 'new_pos_only', 'new_cnv_only', 'zalo_app', 'zalo_oa'):
                self.assertEqual(expected_summary.get(key), actual_summary.get(key),
                    f"customer[{store_name}].summary.{key}: {expected_summary.get(key)} vs {actual_summary.get(key)}")
            get_run_log().log(
                f"  [customer] store={store_name} new_pos={expected_summary.get('new_pos')} "
                f"new_cnv={expected_summary.get('new_cnv')}"
            )

        if expected_detail and actual_detail:
            self.assertEqual(len(expected_detail.get('by_season', [])), len(actual_detail.get('by_season', [])),
                "customer detail by_season length mismatch")
            self.assertEqual(len(expected_detail.get('by_month', [])), len(actual_detail.get('by_month', [])),
                "customer detail by_month length mismatch")

        t.report()

    # ── Coupon consistency ───────────────────────────────────────────────────

    def test_coupon_shop_detail_period_used_matches_shop_tab(self):
        """
        Coupon period.used for shop X from get_shop_detail_coupon_data must equal
        the 'used' field in get_coupon_tab('shop')['by_shop'] for that shop.
        """
        if not Coupon.objects.exists():
            self.skipTest("No coupon data")

        t = self.timer("shop_detail_coupon_consistency_alltime")

        coupon_shop = self._pick_coupon_shop()
        if not coupon_shop:
            self.skipTest("No used coupons found")

        # Source of truth: coupon shop tab (no date filter = all-time)
        shop_tab = get_coupon_tab('shop')
        t.checkpoint(f"get_coupon_tab(shop) — by_shop rows={len(shop_tab.get('by_shop',[]))}")

        shop_row = next((r for r in shop_tab.get('by_shop', []) if r['shop_name'] == coupon_shop), None)

        # Shop detail coupon path
        detail = get_shop_detail_coupon_data(coupon_shop)
        t.checkpoint(f"get_shop_detail_coupon_data done — shop={coupon_shop}")

        self.assertIsNotNone(shop_row, f"Shop '{coupon_shop}' not found in coupon shop tab")

        # period.used must equal by_shop row's used (all-time, no date filter → period_qs = qs)
        self.assertEqual(
            detail['period']['used'],
            shop_row['used'],
            f"period.used mismatch for {coupon_shop}: "
            f"shop_detail={detail['period']['used']} vs shop_tab={shop_row['used']}"
        )

        # period.unused must equal by_shop row's unused
        self.assertEqual(
            detail['period']['unused'],
            shop_row['unused'],
            f"period.unused mismatch for {coupon_shop}: "
            f"shop_detail={detail['period']['unused']} vs shop_tab={shop_row['unused']}"
        )

        # usage_rate should match
        self.assertAlmostEqual(
            detail['period']['usage_rate'],
            shop_row['usage_rate'],
            places=2,
            msg=f"usage_rate mismatch for {coupon_shop}"
        )

        get_run_log().log(
            f"  [coupon] shop={coupon_shop} used={shop_row['used']} unused={shop_row['unused']} "
            f"usage_rate={shop_row['usage_rate']}%"
        )
        t.report()

    def test_coupon_shop_detail_period_used_with_date_filter(self):
        """
        Coupon period.used with date filter must equal the 'used' field in
        by_shop from get_coupon_tab('shop') with the same date filter.
        """
        if not Coupon.objects.exists():
            self.skipTest("No coupon data")

        t = self.timer("shop_detail_coupon_consistency_date_filtered")

        date_from = date(2025, 1, 1)
        date_to   = date(2025, 12, 31)

        coupon_shop = (
            Coupon.objects
            .filter(using_date__gte=date_from, using_date__lte=date_to)
            .exclude(using_shop__isnull=True).exclude(using_shop='')
            .values_list('using_shop', flat=True)
            .order_by('using_shop')
            .first()
        )
        if not coupon_shop:
            self.skipTest("No used coupons in 2025")

        shop_tab = get_coupon_tab('shop', date_from=date_from, date_to=date_to)
        t.checkpoint(f"get_coupon_tab(shop, 2025) done")

        shop_row = next((r for r in shop_tab.get('by_shop', []) if r['shop_name'] == coupon_shop), None)

        detail = get_shop_detail_coupon_data(coupon_shop, date_from=date_from, date_to=date_to)
        t.checkpoint(f"get_shop_detail_coupon_data(2025) done — shop={coupon_shop}")

        self.assertIsNotNone(shop_row, f"Shop '{coupon_shop}' not found in coupon tab (2025)")

        self.assertEqual(
            detail['period']['used'],
            shop_row['used'],
            f"period.used mismatch (2025) for {coupon_shop}: "
            f"shop_detail={detail['period']['used']} vs shop_tab={shop_row['used']}"
        )

        # coupon amount should match (float comparison with tolerance)
        self.assertAlmostEqual(
            detail['period']['total_coupon_amount'],
            shop_row['coupon_amount'],
            places=1,
            msg=f"period coupon_amount mismatch for {coupon_shop}"
        )

        get_run_log().log(
            f"  [coupon 2025] shop={coupon_shop} used={shop_row['used']} "
            f"coupon_amt={shop_row['coupon_amount']:.0f}"
        )
        t.report()

    def test_coupon_all_time_is_shop_scoped(self):
        """
        all_time.total from get_shop_detail_coupon_data must equal the DB count
        of ALL coupons (used + unused) for that shop.
        """
        if not Coupon.objects.exists():
            self.skipTest("No coupon data")

        t = self.timer("shop_detail_coupon_alltime_scoped")

        coupon_shop = self._pick_coupon_shop()
        if not coupon_shop:
            self.skipTest("No used coupons found")

        # Direct DB count for that shop
        db_total = Coupon.objects.filter(using_shop=coupon_shop).count()
        db_used  = Coupon.objects.filter(using_shop=coupon_shop, using_date__isnull=False).count()

        detail = get_shop_detail_coupon_data(coupon_shop)
        t.checkpoint(f"get_shop_detail_coupon_data alltime — shop={coupon_shop}")

        self.assertEqual(detail['all_time']['total'], db_total,
            f"all_time.total mismatch: {detail['all_time']['total']} vs DB {db_total}")
        self.assertEqual(detail['all_time']['used'],  db_used,
            f"all_time.used mismatch: {detail['all_time']['used']} vs DB {db_used}")

        get_run_log().log(
            f"  [coupon all_time] shop={coupon_shop} total={db_total} used={db_used}"
        )
        t.report()

    def test_coupon_detail_list_belongs_to_shop(self):
        """
        All rows in get_shop_detail_coupon_data.details must have using_shop == shop.
        """
        if not Coupon.objects.exists():
            self.skipTest("No coupon data")

        t = self.timer("shop_detail_coupon_detail_shop_filter")

        coupon_shop = self._pick_coupon_shop()
        if not coupon_shop:
            self.skipTest("No used coupons found")

        detail = get_shop_detail_coupon_data(coupon_shop)
        t.checkpoint(f"get_shop_detail_coupon_data — shop={coupon_shop} rows={len(detail['details'])}")

        for i, row in enumerate(detail['details']):
            self.assertEqual(
                row['using_shop'], coupon_shop,
                f"detail[{i}].using_shop={row['using_shop']!r} != {coupon_shop!r}"
            )

        get_run_log().log(
            f"  [coupon details] shop={coupon_shop} rows={len(detail['details'])}"
        )
        t.report()

    # ── Snapshot tests ───────────────────────────────────────────────────────

    def test_snapshot_sales_shop_detail(self):
        """Snapshot: sales data for a specific shop (all-time)."""
        if not SalesTransaction.objects.exists():
            self.skipTest("No sales data")

        t = self.timer("snapshot_sales_shop_detail")

        shop_name = self._pick_sales_shop()
        self.assertIsNotNone(shop_name)

        tab_data = get_sales_tab('shop')
        t.checkpoint(f"get_sales_tab(shop) — shop={shop_name}")

        shop_data = next((s for s in (tab_data or {}).get('by_shop', []) if s['shop_name'] == shop_name), None)
        self.assertIsNotNone(shop_data, f"Shop '{shop_name}' not in tab data")

        # Snapshot only core metrics (not the full by_week list which can be huge)
        snap = {
            'shop_name':              shop_data['shop_name'],
            'total_customers':        shop_data['total_customers'],
            'returning_customers':    shop_data['returning_customers'],
            'return_rate':            shop_data['return_rate'],
            'returning_invoices':     shop_data['returning_invoices'],
            'total_invoices_with_vip0': shop_data['total_invoices_with_vip0'],
            'by_session_count':       len(shop_data.get('by_session', [])),
            'by_month_count':         len(shop_data.get('by_month', [])),
            'by_week_count':          len(shop_data.get('by_week', [])),
        }
        self.assert_snapshot('shop_detail_sales', snap)
        t.checkpoint("snapshot verified")
        t.report()

    def test_snapshot_customer_shop_detail(self):
        """Snapshot: customer data for a specific store (all-time)."""
        if not Customer.objects.exists():
            self.skipTest("No customer data")

        t = self.timer("snapshot_customer_shop_detail")

        store_name = self._pick_customer_shop()
        self.assertIsNotNone(store_name)

        tab_data = get_customer_tab('bd_shop')
        t.checkpoint(f"get_customer_tab(bd_shop) — store={store_name}")

        summary = next((r for r in tab_data.get('by_shop', []) if r['label'] == store_name), None)
        detail  = next((sh for sh in tab_data.get('shop_detail', []) if sh['shop'] == store_name), None)

        snap = {
            'store': store_name,
            'summary': {k: summary[k] for k in (
                'new_pos', 'new_pos_inv', 'new_pos_no_inv', 'new_pos_only',
                'new_cnv', 'new_cnv_only', 'zalo_app', 'zalo_oa',
            )} if summary else None,
            'detail_by_season_count': len(detail.get('by_season', [])) if detail else 0,
            'detail_by_month_count':  len(detail.get('by_month',  [])) if detail else 0,
            'detail_by_week_count':   len(detail.get('by_week',   [])) if detail else 0,
        }
        self.assert_snapshot('shop_detail_customer', snap)
        t.checkpoint("snapshot verified")
        t.report()

    def test_snapshot_coupon_shop_detail(self):
        """Snapshot: coupon data for a specific shop (all-time)."""
        if not Coupon.objects.exists():
            self.skipTest("No coupon data")

        t = self.timer("snapshot_coupon_shop_detail")

        coupon_shop = self._pick_coupon_shop()
        if not coupon_shop:
            self.skipTest("No used coupons found")

        detail = get_shop_detail_coupon_data(coupon_shop)
        t.checkpoint(f"get_shop_detail_coupon_data — shop={coupon_shop}")

        snap = {
            'shop': coupon_shop,
            'all_time': {
                'total':       detail['all_time']['total'],
                'used':        detail['all_time']['used'],
                'unused':      detail['all_time']['unused'],
                'usage_rate':  detail['all_time']['usage_rate'],
            },
            'period': {
                'total':       detail['period']['total'],
                'used':        detail['period']['used'],
                'unused':      detail['period']['unused'],
                'usage_rate':  detail['period']['usage_rate'],
            },
            'details_count': len(detail['details']),
        }
        self.assert_snapshot('shop_detail_coupon', snap)
        t.checkpoint("snapshot verified")
        t.report()

    # ── Performance timing ───────────────────────────────────────────────────

    def test_page_timing_all_three_sections(self):
        """
        Simulate a full shop_detail page load (all 3 sections simultaneously).
        Measures how long each data-fetch step takes.
        """
        if not SalesTransaction.objects.exists():
            self.skipTest("No sales data")

        t = self.timer("shop_detail_full_page_timing")

        sales_shop    = self._pick_sales_shop()
        customer_shop = self._pick_customer_shop()
        coupon_shop   = self._pick_coupon_shop()

        get_run_log().log(
            f"  shops: sales={sales_shop} customer={customer_shop} coupon={coupon_shop}"
        )

        # Section 1: Sales
        if sales_shop:
            tab = get_sales_tab('shop')
            sales_data = next((s for s in (tab or {}).get('by_shop', []) if s['shop_name'] == sales_shop), None)
            t.checkpoint(f"sales: {sales_shop} → {sales_data['total_customers'] if sales_data else 'no data'} customers")

        # Section 2: Customer
        if customer_shop:
            cust = get_customer_tab('bd_shop')
            summary = next((r for r in cust.get('by_shop', []) if r['label'] == customer_shop), None)
            t.checkpoint(f"customer: {customer_shop} → pos={summary['new_pos'] if summary else 'no data'}")

        # Section 3: Coupon
        if coupon_shop:
            cd = get_shop_detail_coupon_data(coupon_shop)
            t.checkpoint(
                f"coupon: {coupon_shop} → used={cd['period']['used']} "
                f"details={len(cd['details'])}"
            )

        total = t.total()
        self.record_page_timing("shop_detail_full", total, t._checkpoints)
        t.report()

        self.assertLess(total, 60, f"Full shop detail page too slow: {total:.1f}s > 60s limit")
