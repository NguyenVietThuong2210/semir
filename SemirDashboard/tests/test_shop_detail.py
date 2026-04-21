"""
tests/test_shop_detail.py — Shop Detail page consistency + performance tests.

Validates:
 1. Direct-query functions match the original all-shops tab for any shop.
 2. All-Time KPIs and Period KPIs are structurally correct and consistent.
 3. Breakdown rows (by_season / by_month / by_week) have the right shape.
 4. AJAX partial views return 200 with expected HTML content.
 5. Snapshots cover full KPI dicts for both all-time and period (2025 filter).

Both consistency tests and AJAX tests share a single setUpTestData so the
~430 k-row fixture is loaded only ONCE per test run (~50% faster).

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

DATE_2025 = (date(2025, 1, 1), date(2025, 12, 31))


def _named(path):
    with open(path, "rb") as f:
        data = f.read()
    class _N(io.BytesIO):
        pass
    obj = _N(data)
    obj.name = path.name
    return obj


# ── Snapshot helpers ──────────────────────────────────────────────────────────

def _sales_kpi(d):
    """Extract all sales KPI fields from a KPI dict."""
    if not d:
        return None
    return {k: d.get(k) for k in (
        'total_customers', 'returning_customers', 'return_rate',
        'returning_invoices', 'returning_amount',
        'total_invoices_with_vip0', 'total_amount_with_vip0',
    )}


def _sales_row(r, label_key):
    """Extract snapshot-worthy fields from a sales breakdown row."""
    if not r:
        return None
    return {
        'label':              r.get(label_key),
        'total_customers':    r.get('total_customers'),
        'returning_customers':r.get('returning_customers'),
        'return_rate':        r.get('return_rate'),
        'returning_invoices': r.get('returning_invoices'),
    }


def _cnv_kpi(d):
    """Extract all CNV/customer KPI fields from a summary row."""
    if not d:
        return None
    return {k: d.get(k) for k in (
        'new_pos', 'new_pos_inv', 'new_pos_no_inv', 'new_pos_only',
        'new_cnv', 'new_cnv_only', 'zalo_app', 'zalo_oa',
    )}


def _cnv_row(r):
    """Extract snapshot-worthy fields from a customer breakdown row."""
    if not r:
        return None
    return {k: r.get(k) for k in ('label', 'new_pos', 'new_pos_inv', 'new_cnv', 'zalo_app', 'zalo_oa')}


def _coupon_kpi(d):
    """Extract all coupon KPI fields."""
    if not d:
        return None
    return {k: d.get(k) for k in ('total', 'used', 'unused', 'usage_rate', 'total_coupon_amount', 'total_amount')}


# ── Single test class (setUpTestData runs ONCE) ───────────────────────────────

class ShopDetailTest(SnapshotTestCase):
    """
    All shop_detail tests — consistency, AJAX, snapshots — in one class so
    setUpTestData loads the ~430k-row fixture exactly once per test run.
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

    # ── Shop pickers ──────────────────────────────────────────────────────────

    def _pick_sales_shop(self, date_from=None, date_to=None):
        qs = SalesTransaction.objects.exclude(shop_name__isnull=True).exclude(shop_name='')
        if date_from:
            qs = qs.filter(sales_date__gte=date_from)
        if date_to:
            qs = qs.filter(sales_date__lte=date_to)
        return qs.values_list('shop_name', flat=True).order_by('shop_name').first()

    def _pick_customer_shop(self):
        return (
            Customer.objects
            .exclude(registration_store__isnull=True).exclude(registration_store='')
            .values_list('registration_store', flat=True).order_by('registration_store').first()
        )

    def _pick_coupon_shop(self, date_from=None, date_to=None):
        qs = Coupon.objects.filter(using_date__isnull=False)
        if date_from:
            qs = qs.filter(using_date__gte=date_from)
        if date_to:
            qs = qs.filter(using_date__lte=date_to)
        return (
            qs.exclude(using_shop__isnull=True).exclude(using_shop='')
            .values_list('using_shop', flat=True).order_by('using_shop').first()
        )

    def _ajax_login(self):
        from django.contrib.auth import get_user_model
        User = get_user_model()
        user, _ = User.objects.get_or_create(
            username='_test_ajax_', defaults={'is_superuser': True, 'is_staff': True})
        user.set_password('x')
        user.save()
        self.client.force_login(user)

    # ══════════════════════════════════════════════════════════════════════════
    #  SECTION A — Sales Consistency
    # ══════════════════════════════════════════════════════════════════════════

    def test_sales_alltime_matches_shop_tab(self):
        """all_time KPIs must equal get_sales_tab('shop') for the same shop."""
        if not SalesTransaction.objects.exists():
            self.skipTest("No sales data")

        t = self.timer("sales_alltime_vs_shop_tab")
        shop = self._pick_sales_shop()
        self.assertIsNotNone(shop)

        tab = get_sales_tab('shop')
        t.checkpoint(f"get_sales_tab — shops={len(tab['by_shop']) if tab else 0}")
        exp = next((s for s in (tab or {}).get('by_shop', []) if s['shop_name'] == shop), None)
        self.assertIsNotNone(exp, f"'{shop}' not in shop tab")

        data = get_shop_detail_sales_data(shop)
        t.checkpoint(f"get_shop_detail_sales_data — shop={shop}")
        self.assertIsNotNone(data)

        at = data['all_time']
        for key in ('total_customers', 'returning_customers', 'return_rate',
                    'returning_invoices', 'total_invoices_with_vip0'):
            self.assertEqual(exp[key], at[key],
                f"all_time.{key}: tab={exp[key]} direct={at[key]}")

        # Breakdown row counts (non-zero rows)
        exp_ss = [r for r in exp['by_session'] if r['total_customers'] > 0]
        act_ss = [r for r in data['by_session'] if r['total_customers'] > 0]
        self.assertEqual(len(exp_ss), len(act_ss), "by_session length mismatch")
        self.assertEqual(
            len([r for r in exp['by_month'] if r['total_customers'] > 0]),
            len([r for r in data['by_month'] if r['total_customers'] > 0]),
            "by_month length mismatch")
        if exp_ss and act_ss:
            self.assertEqual(exp_ss[0]['session'], act_ss[0]['session'])
            self.assertEqual(exp_ss[0]['total_customers'], act_ss[0]['total_customers'])

        get_run_log().log(
            f"  [sales alltime] shop={shop} total={at['total_customers']} ret={at['return_rate']}%")
        t.report()

    def test_sales_period_matches_shop_tab(self):
        """period KPIs must equal get_sales_tab('shop', date_from, date_to) for same shop."""
        if not SalesTransaction.objects.exists():
            self.skipTest("No sales data")

        date_from, date_to = DATE_2025
        shop = self._pick_sales_shop(date_from=date_from, date_to=date_to)
        if not shop:
            self.skipTest("No 2025 sales data")

        t = self.timer("sales_period_vs_shop_tab_2025")
        tab = get_sales_tab('shop', date_from=date_from, date_to=date_to)
        t.checkpoint("get_sales_tab(shop,2025)")
        exp = next((s for s in (tab or {}).get('by_shop', []) if s['shop_name'] == shop), None)

        data = get_shop_detail_sales_data(shop, date_from=date_from, date_to=date_to)
        t.checkpoint(f"get_shop_detail_sales_data(2025) — shop={shop}")

        self.assertIsNotNone(exp)
        self.assertIsNotNone(data)
        pd = data['period']
        for key in ('total_customers', 'returning_customers', 'return_rate',
                    'returning_invoices', 'total_invoices_with_vip0'):
            self.assertEqual(exp[key], pd[key],
                f"period.{key}: tab={exp[key]} direct={pd[key]}")

        get_run_log().log(
            f"  [sales 2025] shop={shop} total={pd['total_customers']} ret={pd['return_rate']}%")
        t.report()

    def test_sales_alltime_gte_period(self):
        """all_time customer counts must be >= period counts (all-time covers more dates)."""
        if not SalesTransaction.objects.exists():
            self.skipTest("No sales data")
        shop = self._pick_sales_shop(date_from=DATE_2025[0], date_to=DATE_2025[1])
        if not shop:
            self.skipTest("No 2025 sales data")
        data = get_shop_detail_sales_data(shop, date_from=DATE_2025[0], date_to=DATE_2025[1])
        self.assertIsNotNone(data)
        at, pd = data['all_time'], data['period']
        self.assertGreaterEqual(at['total_customers'],       pd['total_customers'])
        self.assertGreaterEqual(at['total_invoices_with_vip0'], pd['total_invoices_with_vip0'])
        for key in ('total_customers','returning_customers','return_rate',
                    'returning_invoices','returning_amount',
                    'total_invoices_with_vip0','total_amount_with_vip0'):
            self.assertIn(key, at, f"all_time missing '{key}'")
            self.assertIn(key, pd, f"period missing '{key}'")

    def test_sales_direct_is_faster_than_all_shops(self):
        """Direct shop query must be faster than loading all shops."""
        if not SalesTransaction.objects.exists():
            self.skipTest("No sales data")
        n = SalesTransaction.objects.values('shop_name').distinct().count()
        if n < 3:
            self.skipTest(f"Only {n} shops — comparison not meaningful")

        import time
        shop = self._pick_sales_shop()
        t0 = time.perf_counter(); get_sales_tab('shop'); t_all = time.perf_counter() - t0
        t0 = time.perf_counter(); get_shop_detail_sales_data(shop); t_dir = time.perf_counter() - t0

        get_run_log().log(
            f"  [sales speed] all={t_all:.2f}s direct={t_dir:.2f}s speedup={t_all/t_dir:.1f}x shops={n}")
        self.assertLess(t_dir, t_all,
            f"Direct ({t_dir:.2f}s) not faster than all-shops ({t_all:.2f}s)")

    # ══════════════════════════════════════════════════════════════════════════
    #  SECTION B — Customer Consistency
    # ══════════════════════════════════════════════════════════════════════════

    def test_customer_alltime_matches_bd_shop_tab(self):
        """all_time KPIs must match get_customer_tab('bd_shop') for same store."""
        if not Customer.objects.exists():
            self.skipTest("No customer data")

        t = self.timer("customer_alltime_vs_bd_shop_tab")
        store = self._pick_customer_shop()
        self.assertIsNotNone(store)

        tab = get_customer_tab('bd_shop')
        t.checkpoint(f"get_customer_tab(bd_shop) — shops={len(tab.get('by_shop', []))}")
        exp_summary = next((r for r in tab.get('by_shop', []) if r['label'] == store), None)
        exp_detail  = next((d for d in tab.get('shop_detail', []) if d['shop'] == store), None)

        data = get_shop_detail_customer_data(store)
        t.checkpoint(f"get_shop_detail_customer_data — store={store}")

        if exp_summary:
            self.assertIsNotNone(data)
            at = data.get('all_time', {}) or {}
            for key in ('new_pos', 'new_pos_inv', 'new_cnv', 'new_pos_only', 'new_cnv_only',
                        'zalo_app', 'zalo_oa'):
                self.assertEqual(exp_summary.get(key), at.get(key),
                    f"all_time.{key}: tab={exp_summary.get(key)} direct={at.get(key)}")
            get_run_log().log(
                f"  [customer] store={store} new_pos={at.get('new_pos')} new_cnv={at.get('new_cnv')}")

        if exp_detail and data:
            for dim in ('by_season', 'by_month', 'by_week'):
                self.assertEqual(len(exp_detail.get(dim, [])), len(data.get(dim, [])),
                    f"{dim} length mismatch")
            if exp_detail.get('by_season') and data.get('by_season'):
                es, ad = exp_detail['by_season'][0], data['by_season'][0]
                self.assertEqual(es['label'], ad['label'])
                self.assertEqual(es['new_pos'], ad['new_pos'])

        t.report()

    def test_customer_period_matches_bd_shop_tab(self):
        """period KPIs must match get_customer_tab with 2025 filter for same store."""
        if not Customer.objects.exists():
            self.skipTest("No customer data")

        store = self._pick_customer_shop()
        t = self.timer("customer_period_vs_bd_shop_tab_2025")

        tab = get_customer_tab('bd_shop', start_date='2025-01-01', end_date='2025-12-31')
        t.checkpoint("get_customer_tab(bd_shop, 2025)")
        exp = next((r for r in tab.get('by_shop', []) if r['label'] == store), None)

        data = get_shop_detail_customer_data(store, start_date='2025-01-01', end_date='2025-12-31')
        t.checkpoint(f"get_shop_detail_customer_data(2025) — store={store}")

        if not exp or not data:
            self.skipTest(f"No 2025 data for store '{store}'")

        pd = data.get('period') or {}
        for key in ('new_pos', 'new_pos_inv', 'new_cnv', 'new_pos_only',
                    'new_cnv_only', 'zalo_app', 'zalo_oa'):
            self.assertEqual(exp.get(key), pd.get(key),
                f"period.{key}: tab={exp.get(key)} direct={pd.get(key)}")

        get_run_log().log(
            f"  [customer 2025] store={store} new_pos={pd.get('new_pos')} new_cnv={pd.get('new_cnv')}")
        t.report()

    def test_customer_alltime_gte_period(self):
        """all_time.new_pos must be >= period.new_pos (all-time covers more dates)."""
        if not Customer.objects.exists():
            self.skipTest("No customer data")
        store = self._pick_customer_shop()
        data = get_shop_detail_customer_data(store, start_date='2025-01-01', end_date='2025-12-31')
        if not data:
            self.skipTest("No data for store")
        at = data.get('all_time') or {}
        pd = data.get('period') or {}
        if at and pd:
            self.assertGreaterEqual(at.get('new_pos', 0), pd.get('new_pos', 0))
        for key in ('new_pos', 'new_pos_inv', 'new_cnv', 'zalo_app', 'zalo_oa'):
            if at:
                self.assertIn(key, at, f"all_time missing '{key}'")
            if pd:
                self.assertIn(key, pd, f"period missing '{key}'")

    def test_customer_direct_is_faster_than_all_stores(self):
        """store_filter accumulation must be faster than loading all stores."""
        if not Customer.objects.exists():
            self.skipTest("No customer data")
        n = Customer.objects.exclude(registration_store__isnull=True).exclude(
            registration_store='').values('registration_store').distinct().count()
        if n < 3:
            self.skipTest(f"Only {n} stores — comparison not meaningful")

        import time
        store = self._pick_customer_shop()
        t0 = time.perf_counter(); get_customer_tab('bd_shop'); t_all = time.perf_counter() - t0
        t0 = time.perf_counter(); get_shop_detail_customer_data(store); t_dir = time.perf_counter() - t0

        get_run_log().log(
            f"  [customer speed] all={t_all:.2f}s direct={t_dir:.2f}s speedup={t_all/t_dir:.1f}x stores={n}")
        self.assertLess(t_dir, t_all,
            f"store_filter ({t_dir:.2f}s) not faster than all-stores ({t_all:.2f}s)")

    # ══════════════════════════════════════════════════════════════════════════
    #  SECTION C — Coupon Consistency
    # ══════════════════════════════════════════════════════════════════════════

    def test_coupon_alltime_matches_shop_tab(self):
        """period (all-time) KPIs must match get_coupon_tab('shop') for same shop."""
        if not Coupon.objects.exists():
            self.skipTest("No coupon data")

        t = self.timer("coupon_alltime_vs_shop_tab")
        shop = self._pick_coupon_shop()
        if not shop:
            self.skipTest("No used coupons")

        tab = get_coupon_tab('shop')
        t.checkpoint(f"get_coupon_tab — rows={len(tab.get('by_shop', []))}")
        exp = next((r for r in tab.get('by_shop', []) if r['shop_name'] == shop), None)
        self.assertIsNotNone(exp)

        data = get_shop_detail_coupon_data(shop)
        t.checkpoint(f"get_shop_detail_coupon_data — shop={shop}")

        self.assertEqual(data['period']['used'],    exp['used'])
        self.assertEqual(data['period']['unused'],  exp['unused'])
        self.assertAlmostEqual(data['period']['usage_rate'], exp['usage_rate'], places=2)
        self.assertAlmostEqual(data['period']['total_coupon_amount'], exp['coupon_amount'], places=1)

        get_run_log().log(
            f"  [coupon alltime] shop={shop} used={exp['used']} rate={exp['usage_rate']}%")
        t.report()

    def test_coupon_period_matches_shop_tab(self):
        """period KPIs must match get_coupon_tab('shop', 2025) for same shop."""
        if not Coupon.objects.exists():
            self.skipTest("No coupon data")

        date_from, date_to = DATE_2025
        shop = self._pick_coupon_shop(date_from=date_from, date_to=date_to)
        if not shop:
            self.skipTest("No 2025 coupon data")

        t = self.timer("coupon_period_vs_shop_tab_2025")
        tab = get_coupon_tab('shop', date_from=date_from, date_to=date_to)
        t.checkpoint("get_coupon_tab(shop,2025)")
        exp = next((r for r in tab.get('by_shop', []) if r['shop_name'] == shop), None)

        data = get_shop_detail_coupon_data(shop, date_from=date_from, date_to=date_to)
        t.checkpoint(f"get_shop_detail_coupon_data(2025) — shop={shop}")

        self.assertIsNotNone(exp)
        self.assertEqual(data['period']['used'],   exp['used'])
        self.assertEqual(data['period']['unused'], exp['unused'])
        self.assertAlmostEqual(data['period']['total_coupon_amount'], exp['coupon_amount'], places=1)

        get_run_log().log(f"  [coupon 2025] shop={shop} used={exp['used']}")
        t.report()

    def test_coupon_alltime_scoped_to_shop(self):
        """all_time.total/used must equal direct DB count for that shop."""
        if not Coupon.objects.exists():
            self.skipTest("No coupon data")

        t = self.timer("coupon_alltime_scope")
        shop = self._pick_coupon_shop()
        if not shop:
            self.skipTest("No used coupons")

        db_total = Coupon.objects.filter(using_shop=shop).count()
        db_used  = Coupon.objects.filter(using_shop=shop, using_date__isnull=False).count()

        data = get_shop_detail_coupon_data(shop)
        t.checkpoint(f"shop={shop}")
        self.assertEqual(data['all_time']['total'], db_total)
        self.assertEqual(data['all_time']['used'],  db_used)

        get_run_log().log(f"  [coupon scope] shop={shop} total={db_total} used={db_used}")
        t.report()

    def test_coupon_details_all_belong_to_shop(self):
        """Every row in details must have using_shop == requested shop."""
        if not Coupon.objects.exists():
            self.skipTest("No coupon data")

        t = self.timer("coupon_detail_filter")
        shop = self._pick_coupon_shop()
        if not shop:
            self.skipTest("No used coupons")

        data = get_shop_detail_coupon_data(shop)
        t.checkpoint(f"rows={len(data['details'])}")
        for i, row in enumerate(data['details']):
            self.assertEqual(row['using_shop'], shop,
                f"detail[{i}].using_shop={row['using_shop']!r} != {shop!r}")
        t.report()

    # ══════════════════════════════════════════════════════════════════════════
    #  SECTION D — Snapshot Tests (full KPI data + period + breakdown rows)
    # ══════════════════════════════════════════════════════════════════════════

    def test_snapshot_sales_full(self):
        """
        Full snapshot: sales all_time + period (2025) KPIs + first row of each
        breakdown table (by_season, by_month, by_week).
        Single DB call: one get_shop_detail_sales_data(shop, 2025) returns both.
        """
        if not SalesTransaction.objects.exists():
            self.skipTest("No sales data")

        t = self.timer("snapshot_sales_full")
        shop = self._pick_sales_shop(date_from=DATE_2025[0], date_to=DATE_2025[1]) \
               or self._pick_sales_shop()
        self.assertIsNotNone(shop)

        # One call with 2025 filter → returns all_time (no filter) + period (2025)
        data = get_shop_detail_sales_data(shop, date_from=DATE_2025[0], date_to=DATE_2025[1])
        t.checkpoint(f"shop={shop}")
        self.assertIsNotNone(data)

        by_session = data.get('by_session', [])
        by_month   = data.get('by_month', [])
        by_week    = data.get('by_week', [])

        self.assert_snapshot('shop_detail_sales', {
            'shop_name':   data['shop_name'],
            'all_time':    _sales_kpi(data['all_time']),
            'period_2025': _sales_kpi(data['period']),
            'by_season': {
                'count':     len(by_session),
                'first_row': _sales_row(by_session[0], 'session') if by_session else None,
            },
            'by_month': {
                'count':     len(by_month),
                'first_row': _sales_row(by_month[0], 'month') if by_month else None,
            },
            'by_week': {
                'count':     len(by_week),
                'first_row': _sales_row(by_week[0], 'week_label') if by_week else None,
            },
        })
        t.checkpoint("snapshot verified")
        t.report()

    def test_snapshot_customer_full(self):
        """
        Full snapshot: customer all_time KPIs + period_2025 KPIs (if any) +
        first row of each breakdown table.
        Uses all-time call for reference data so snapshot is always meaningful.
        Period (2025) captured as a bonus when 2025 CNV data exists for the store.
        """
        if not Customer.objects.exists():
            self.skipTest("No customer data")

        t = self.timer("snapshot_customer_full")

        # Prefer a store that has all-time CNV data (returns non-None)
        store = None
        for candidate in (
            Customer.objects
            .exclude(registration_store__isnull=True).exclude(registration_store='')
            .values_list('registration_store', flat=True).order_by('registration_store')
        ):
            if get_shop_detail_customer_data(candidate):
                store = candidate
                break
        if not store:
            self.skipTest("No store with customer data")

        t.checkpoint(f"picked store={store}")

        # All-time call: gives all_time KPIs + breakdowns (no period filter)
        data_at = get_shop_detail_customer_data(store)
        self.assertIsNotNone(data_at)

        # 2025 call: gives both all_time + period for the same store
        data_pd = get_shop_detail_customer_data(store, start_date='2025-01-01', end_date='2025-12-31')
        t.checkpoint(f"data fetched")

        by_season = data_at.get('by_season', [])
        by_month  = data_at.get('by_month',  [])
        by_week   = data_at.get('by_week',   [])

        self.assert_snapshot('shop_detail_customer', {
            'store':       store,
            'all_time':    _cnv_kpi(data_at.get('all_time')),
            'period_2025': _cnv_kpi((data_pd or {}).get('period')) if data_pd else None,
            'by_season': {
                'count':     len(by_season),
                'first_row': _cnv_row(by_season[0]) if by_season else None,
            },
            'by_month': {
                'count':     len(by_month),
                'first_row': _cnv_row(by_month[0]) if by_month else None,
            },
            'by_week': {
                'count':     len(by_week),
            },
        })
        t.checkpoint("snapshot verified")
        t.report()

    def test_snapshot_coupon_full(self):
        """
        Full snapshot: coupon all_time + period (2025) — both include amounts.
        """
        if not Coupon.objects.exists():
            self.skipTest("No coupon data")

        t = self.timer("snapshot_coupon_full")
        shop = self._pick_coupon_shop()
        if not shop:
            self.skipTest("No used coupons")

        # One call with 2025 filter → all_time (no filter) + period (2025)
        data = get_shop_detail_coupon_data(shop, date_from=DATE_2025[0], date_to=DATE_2025[1])
        t.checkpoint(f"shop={shop}")

        self.assert_snapshot('shop_detail_coupon', {
            'shop':        shop,
            'all_time':    _coupon_kpi(data['all_time']),
            'period_2025': _coupon_kpi(data['period']),
            'details_count': len(data['details']),
        })
        t.checkpoint("snapshot verified")
        t.report()

    # ══════════════════════════════════════════════════════════════════════════
    #  SECTION E — AJAX Partial Views
    # ══════════════════════════════════════════════════════════════════════════

    def test_sales_partial_200(self):
        """Sales partial returns 200 with KPI cards and breakdown tables."""
        if not SalesTransaction.objects.exists():
            self.skipTest("No sales data")
        self._ajax_login()
        shop = self._pick_sales_shop()
        t = self.timer("ajax_sales_partial")
        resp = self.client.get('/shop-detail/partial/sales/', {'shop': shop},
                               HTTP_X_REQUESTED_WITH='XMLHttpRequest')
        t.checkpoint(f"shop={shop}")
        self.assertEqual(resp.status_code, 200)
        html = resp.content.decode()
        self.assertIn('kpi-val', html, "Missing KPI cards")
        self.assertIn('All-Time', html)
        self.assertIn('Period', html)
        self.assertIn('By Season', html)
        self.assertIn('By Month', html)
        self.assertIn('By Week', html)
        get_run_log().log(f"  [ajax sales] shop={shop} bytes={len(html)}")
        t.report()

    def test_sales_partial_empty_shop(self):
        """Sales partial with no shop returns placeholder."""
        self._ajax_login()
        resp = self.client.get('/shop-detail/partial/sales/', HTTP_X_REQUESTED_WITH='XMLHttpRequest')
        self.assertEqual(resp.status_code, 200)
        self.assertIn('Select a shop', resp.content.decode())

    def test_sales_partial_with_date_filter(self):
        """Sales partial respects date filter; returns either data or no-data message."""
        if not SalesTransaction.objects.exists():
            self.skipTest("No sales data")
        self._ajax_login()
        shop = self._pick_sales_shop()
        resp = self.client.get('/shop-detail/partial/sales/',
                               {'shop': shop, 'start_date': '2025-01-01', 'end_date': '2025-12-31'})
        self.assertEqual(resp.status_code, 200)
        html = resp.content.decode()
        self.assertTrue('kpi-val' in html or 'No' in html)

    def test_sales_partial_performance(self):
        """Sales partial must respond in < 3s."""
        if not SalesTransaction.objects.exists():
            self.skipTest("No sales data")
        self._ajax_login()
        shop = self._pick_sales_shop()
        import time
        t0 = time.perf_counter()
        resp = self.client.get('/shop-detail/partial/sales/', {'shop': shop})
        elapsed = time.perf_counter() - t0
        self.assertEqual(resp.status_code, 200)
        get_run_log().log(f"  [ajax sales perf] {elapsed:.2f}s shop={shop}")
        self.assertLess(elapsed, 3.0, f"Sales partial too slow: {elapsed:.2f}s")

    def test_customer_partial_200(self):
        """Customer partial returns 200 with KPI cards and breakdown tables."""
        if not Customer.objects.exists():
            self.skipTest("No customer data")
        self._ajax_login()
        store = self._pick_customer_shop()
        t = self.timer("ajax_customer_partial")
        resp = self.client.get('/shop-detail/partial/customer/', {'shop': store},
                               HTTP_X_REQUESTED_WITH='XMLHttpRequest')
        t.checkpoint(f"store={store}")
        self.assertEqual(resp.status_code, 200)
        html = resp.content.decode()
        self.assertIn('kpi-val', html, "Missing KPI cards")
        self.assertIn('All-Time', html)
        self.assertIn('Period', html)
        self.assertIn('By Season', html)
        self.assertIn('By Month', html)
        get_run_log().log(f"  [ajax customer] store={store} bytes={len(html)}")
        t.report()

    def test_customer_partial_empty_shop(self):
        """Customer partial with no shop returns placeholder."""
        self._ajax_login()
        resp = self.client.get('/shop-detail/partial/customer/')
        self.assertEqual(resp.status_code, 200)
        self.assertIn('Select a', resp.content.decode())

    def test_customer_partial_performance(self):
        """Customer partial must respond in < 3s."""
        if not Customer.objects.exists():
            self.skipTest("No customer data")
        self._ajax_login()
        store = self._pick_customer_shop()
        import time
        t0 = time.perf_counter()
        resp = self.client.get('/shop-detail/partial/customer/', {'shop': store})
        elapsed = time.perf_counter() - t0
        self.assertEqual(resp.status_code, 200)
        get_run_log().log(f"  [ajax customer perf] {elapsed:.2f}s store={store}")
        self.assertLess(elapsed, 3.0, f"Customer partial too slow: {elapsed:.2f}s")

    def test_coupon_partial_200(self):
        """Coupon partial returns 200 with All-Time and Period cards."""
        if not Coupon.objects.exists():
            self.skipTest("No coupon data")
        self._ajax_login()
        shop = self._pick_coupon_shop()
        if not shop:
            self.skipTest("No used coupons")
        t = self.timer("ajax_coupon_partial")
        resp = self.client.get('/shop-detail/partial/coupon/', {'shop': shop},
                               HTTP_X_REQUESTED_WITH='XMLHttpRequest')
        t.checkpoint(f"shop={shop}")
        self.assertEqual(resp.status_code, 200)
        html = resp.content.decode()
        self.assertIn('kpi-val', html, "Missing KPI cards")
        self.assertIn('All-Time', html)
        self.assertIn('Period', html)
        get_run_log().log(f"  [ajax coupon] shop={shop} bytes={len(html)}")
        t.report()

    def test_coupon_partial_empty_shop(self):
        """Coupon partial with no shop returns placeholder."""
        self._ajax_login()
        resp = self.client.get('/shop-detail/partial/coupon/')
        self.assertEqual(resp.status_code, 200)
        self.assertIn('Select a shop', resp.content.decode())

    def test_coupon_partial_performance(self):
        """Coupon partial must respond in < 2s."""
        if not Coupon.objects.exists():
            self.skipTest("No coupon data")
        self._ajax_login()
        shop = self._pick_coupon_shop()
        if not shop:
            self.skipTest("No used coupons")
        import time
        t0 = time.perf_counter()
        resp = self.client.get('/shop-detail/partial/coupon/', {'shop': shop})
        elapsed = time.perf_counter() - t0
        self.assertEqual(resp.status_code, 200)
        get_run_log().log(f"  [ajax coupon perf] {elapsed:.2f}s shop={shop}")
        self.assertLess(elapsed, 2.0, f"Coupon partial too slow: {elapsed:.2f}s")

    def test_main_page_loads(self):
        """Main page loads with dropdowns populated, no shop selected."""
        self._ajax_login()
        import time
        t0 = time.perf_counter()
        resp = self.client.get('/shop-detail/')
        elapsed = time.perf_counter() - t0
        self.assertEqual(resp.status_code, 200)
        html = resp.content.decode()
        self.assertIn('Select shop', html)
        self.assertIn('Select store', html)
        get_run_log().log(f"  [main page] {elapsed:.2f}s")
        self.assertLess(elapsed, 3.0, f"Main page too slow: {elapsed:.2f}s")

    # ══════════════════════════════════════════════════════════════════════════
    #  SECTION F — AJAX HTML Structure Snapshots
    # ══════════════════════════════════════════════════════════════════════════

    def test_snapshot_ajax_sales_partial(self):
        """Snapshot: sales partial HTML structure (All-Time + Period + breakdowns)."""
        if not SalesTransaction.objects.exists():
            self.skipTest("No sales data")
        self._ajax_login()
        shop = self._pick_sales_shop()
        resp = self.client.get('/shop-detail/partial/sales/', {'shop': shop})
        self.assertEqual(resp.status_code, 200)
        html = resp.content.decode()
        self.assert_snapshot('ajax_sales_partial', {
            'shop': shop,
            'has_kpi':       'kpi-val' in html,
            'has_alltime':   'All-Time' in html,
            'has_period':    'Period' in html,
            'has_by_season': 'By Season' in html,
            'has_by_month':  'By Month' in html,
            'has_by_week':   'By Week' in html,
            'byte_len': len(html),
        })

    def test_snapshot_ajax_customer_partial(self):
        """Snapshot: customer partial HTML structure (All-Time + Period + breakdowns)."""
        if not Customer.objects.exists():
            self.skipTest("No customer data")
        self._ajax_login()
        store = self._pick_customer_shop()
        resp = self.client.get('/shop-detail/partial/customer/', {'shop': store})
        self.assertEqual(resp.status_code, 200)
        html = resp.content.decode()
        self.assert_snapshot('ajax_customer_partial', {
            'store': store,
            'has_kpi':       'kpi-val' in html,
            'has_alltime':   'All-Time' in html,
            'has_period':    'Period' in html,
            'has_by_season': 'By Season' in html,
            'has_by_month':  'By Month' in html,
            'has_by_week':   'By Week' in html,
            'byte_len': len(html),
        })

    def test_snapshot_ajax_coupon_partial(self):
        """Snapshot: coupon partial HTML structure."""
        if not Coupon.objects.exists():
            self.skipTest("No coupon data")
        self._ajax_login()
        shop = self._pick_coupon_shop()
        if not shop:
            self.skipTest("No used coupons")
        resp = self.client.get('/shop-detail/partial/coupon/', {'shop': shop})
        self.assertEqual(resp.status_code, 200)
        html = resp.content.decode()
        self.assert_snapshot('ajax_coupon_partial', {
            'shop': shop,
            'has_alltime':      'All-Time' in html,
            'has_period':       'Period' in html,
            'has_detail_table': 'Coupon ID' in html,
            'byte_len': len(html),
        })

    # ══════════════════════════════════════════════════════════════════════════
    #  SECTION G — Full Page Timing
    # ══════════════════════════════════════════════════════════════════════════

    def test_page_timing_all_three_sections(self):
        """Simulate full shop_detail page with direct queries for all 3 sections."""
        if not SalesTransaction.objects.exists():
            self.skipTest("No sales data")

        t = self.timer("shop_detail_full_page_direct")
        sales_shop    = self._pick_sales_shop()
        customer_shop = self._pick_customer_shop()
        coupon_shop   = self._pick_coupon_shop()
        get_run_log().log(
            f"  shops: sales={sales_shop} customer={customer_shop} coupon={coupon_shop}")

        if sales_shop:
            sd = get_shop_detail_sales_data(sales_shop)
            t.checkpoint(
                f"sales: {sales_shop} → {sd['all_time']['total_customers'] if sd else 'no data'} customers")

        if customer_shop:
            cd = get_shop_detail_customer_data(customer_shop)
            s = (cd or {}).get('all_time') or {}
            t.checkpoint(f"customer: {customer_shop} → pos={s.get('new_pos', 'no data')}")

        if coupon_shop:
            cpd = get_shop_detail_coupon_data(coupon_shop)
            t.checkpoint(
                f"coupon: {coupon_shop} → used={cpd['period']['used']} details={len(cpd['details'])}")

        total = t.total()
        self.record_page_timing("shop_detail_full_direct", total, t._checkpoints)
        t.report()
        self.assertLess(total, 60, f"Full page load too slow: {total:.1f}s")
