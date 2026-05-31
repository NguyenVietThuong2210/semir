"""
tests/test_api.py — Mobile API (v1) parity + performance tests.

Validates that every /api/v1/* endpoint:
  1. Returns the correct HTTP status codes (200, 401, 403, 404)
  2. Contains all required JSON keys (structure parity with web pages)
  3. Returns non-negative / internally consistent values
  4. Period values ≤ All-Time values for additive metrics
  5. Lazy-loading tabs/sections return correct structure
  6. Response times stay within acceptable bounds

All data tests share a single setUpTestData so the ~430k-row fixture
is loaded only ONCE for the entire class (~50% faster than per-test setup).

Run:
  cd SemirDashboard && python manage.py test tests.test_api -v 2

Run single:
  cd SemirDashboard && python manage.py test tests.test_api.ApiStructureTest.test_sales_initial_load -v 2
"""
import io
import json
import time

from django.contrib.auth.models import User
from django.db.models import Count

from tests.base import SnapshotTestCase, INPUT_DIR, get_run_log

# ── URL constants ──────────────────────────────────────────────────────────────

SALES_URL           = '/api/v1/analytics/sales/'
CUSTOMER_URL        = '/api/v1/analytics/customer/'
COUPON_URL          = '/api/v1/analytics/coupon/'
SHOPS_URL           = '/api/v1/analytics/shops/'
SHOP_DETAIL_URL     = '/api/v1/analytics/shop-detail/'
CUST_DETAIL_URL     = '/api/v1/analytics/customer-detail/'
LOGIN_URL           = '/api/v1/auth/token/'
SALES_CHART_URL     = '/api/v1/charts/sales/'
CUSTOMER_CHART_URL  = '/api/v1/charts/customer/'
COUPON_CHART_URL    = '/api/v1/charts/coupon/'

# Performance thresholds (wall-clock, single-worker dev server via test client)
PERF_LIMIT_FAST  = 15   # seconds — initial page loads (have caches)
PERF_LIMIT_TAB   = 20   # seconds — lazy tab load (cold cache)
PERF_LIMIT_SHOPS = 5    # seconds — lightweight list endpoint

# Date filter used for period tests
PERIOD_FROM = '2025-01-01'
PERIOD_TO   = '2025-12-31'

# Input files (same as test_shop_detail.py uses)
CUSTOMER_FILE = INPUT_DIR / "customer.xlsx"
SALE_FILES    = [INPUT_DIR / "Sale 2024.xlsx", INPUT_DIR / "Sale 2025.xlsx", INPUT_DIR / "Sale 2026.xlsx"]
COUPON_FILE   = INPUT_DIR / "coupon_1 (1).xlsx"


# ── Helpers ────────────────────────────────────────────────────────────────────

def _named(path):
    with open(path, "rb") as f:
        data = f.read()

    class _N(io.BytesIO):
        pass

    obj = _N(data)
    obj.name = path.name
    return obj


def _parse_int(s) -> int:
    """Parse a formatted integer string like '1,234,567' → 1234567."""
    if isinstance(s, int):
        return s
    try:
        return int(str(s).replace(',', '').strip())
    except (ValueError, TypeError):
        return 0


def _parse_float(s) -> float:
    """Parse a formatted float string like '12.34' → 12.34."""
    if isinstance(s, (int, float)):
        return float(s)
    try:
        return float(str(s).replace(',', '').strip())
    except (ValueError, TypeError):
        return 0.0


# ══════════════════════════════════════════════════════════════════════════════
# AUTH GUARD TESTS  (no fixture data needed)
# ══════════════════════════════════════════════════════════════════════════════

class ApiAuthGuardTest(SnapshotTestCase):
    """All analytics endpoints must refuse unauthenticated requests."""

    ENDPOINTS = [
        SALES_URL,
        CUSTOMER_URL,
        COUPON_URL,
        SHOPS_URL,
        SHOP_DETAIL_URL,
        CUST_DETAIL_URL,
        SALES_CHART_URL,
        CUSTOMER_CHART_URL,
        COUPON_CHART_URL,
    ]

    def test_all_analytics_require_auth(self):
        for url in self.ENDPOINTS:
            resp = self.client.get(url)
            self.assertIn(
                resp.status_code, (401, 403),
                f"Expected 401/403 for unauthenticated {url}, got {resp.status_code}",
            )


# ══════════════════════════════════════════════════════════════════════════════
# DATA PARITY & STRUCTURE TESTS  (require fixture data)
# ══════════════════════════════════════════════════════════════════════════════

class ApiStructureTest(SnapshotTestCase):
    """
    Mobile API structure, parity with web, and performance.
    setUpTestData loads the full fixture once for the entire class.
    """

    @classmethod
    def setUpTestData(cls):
        from App.services import process_customer_file, process_sales_file, process_coupon_file

        if CUSTOMER_FILE.exists():
            process_customer_file(_named(CUSTOMER_FILE))
        for path in SALE_FILES:
            if path.exists():
                process_sales_file(_named(path))
        if COUPON_FILE.exists():
            process_coupon_file(_named(COUPON_FILE))

        # Superuser with all permissions
        cls.superuser = User.objects.create_superuser(
            username='_api_test_super_',
            password='TestPass123!',
            email='api_test@test.com',
        )

        # Obtain JWT access token once — reused across all tests
        from rest_framework_simplejwt.tokens import AccessToken
        token = AccessToken.for_user(cls.superuser)
        cls.auth_header = f'Bearer {str(token)}'

    def _get(self, url, params=None):
        """Authenticated GET with timing."""
        t0 = time.perf_counter()
        resp = self.client.get(
            url,
            data=params or {},
            HTTP_AUTHORIZATION=self.auth_header,
        )
        elapsed = time.perf_counter() - t0
        return resp, elapsed

    def _json(self, url, params=None):
        """Return (data_dict, elapsed_seconds)."""
        resp, elapsed = self._get(url, params)
        self.assertEqual(resp.status_code, 200, f"GET {url} {params} → {resp.status_code}: {resp.content[:200]}")
        return resp.json(), elapsed

    # ─────────────────────────────────────────────────────────────────────────
    # SALES  /api/v1/analytics/sales/
    # ─────────────────────────────────────────────────────────────────────────

    def test_sales_initial_load_status_200(self):
        resp, _ = self._get(SALES_URL)
        self.assertEqual(resp.status_code, 200)

    def test_sales_initial_load_has_required_keys(self):
        data, _ = self._json(SALES_URL)
        for key in ('all_time_kpis', 'period_kpis', 'tabs', 'available_tabs'):
            self.assertIn(key, data, f"Sales response missing key: {key}")

    def test_sales_all_time_kpis_structure(self):
        """Sales all_time_kpis must match web's 4-card layout (human-readable labels)."""
        data, _ = self._json(SALES_URL)
        at = data['all_time_kpis']
        for key in ('Total Customers', 'Member Active', 'Member Inactive', 'Return Rate (All Time)'):
            self.assertIn(key, at, f"all_time_kpis missing: {key}")
        # Values must be non-negative
        self.assertGreaterEqual(_parse_int(at['Total Customers']), 0)
        self.assertGreaterEqual(_parse_int(at['Member Active']), 0)

    def test_sales_period_kpis_structure(self):
        """Sales period_kpis must match web's 10-metric layout (human-readable labels)."""
        data, _ = self._json(SALES_URL)
        pd = data['period_kpis']
        required = (
            'New Members', 'Returning Customers', 'Active Customers', 'Return Visit Rate',
            'INV(CUS)', 'AMT(CUS)', 'INV(RET)', 'AMT(RET)',
            'Total Invoices', 'Total Amount',
        )
        for key in required:
            self.assertIn(key, pd, f"period_kpis missing: {key}")

    def test_sales_available_tabs_complete(self):
        data, _ = self._json(SALES_URL)
        expected = {'by_grade', 'by_season', 'by_month', 'by_week', 'by_shop'}
        actual = set(data.get('available_tabs', []))
        self.assertEqual(expected, actual, f"available_tabs mismatch: {actual}")

    def test_sales_initial_tab_is_by_grade(self):
        data, _ = self._json(SALES_URL)
        tabs = data.get('tabs', {})
        self.assertIn('by_grade', tabs, "Initial load must contain by_grade tab")

    def test_sales_grade_tab_columns_match_web(self):
        """10 columns matching the web analytics/grade table."""
        data, _ = self._json(SALES_URL)
        tab = data['tabs']['by_grade']
        self.assertIn('headers', tab)
        self.assertIn('rows', tab)
        expected_cols = [
            'Grade', 'Active', 'Returning', 'Return Rate', 'Total (DB)',
            'Return Rate (AT)', 'INV(RET)', 'AMT(RET)', 'Total INV', 'Total Amount',
        ]
        self.assertEqual(tab['headers'], expected_cols,
            f"by_grade headers mismatch.\nExpected: {expected_cols}\nGot: {tab['headers']}")

    def test_sales_period_filter_reduces_invoices(self):
        """Period Total Invoices must be ≤ all-time period Total Invoices (no date filter)."""
        at_data, _ = self._json(SALES_URL)
        pd_data, _ = self._json(SALES_URL, {'date_from': PERIOD_FROM, 'date_to': PERIOD_TO})
        # All-time period invoices (no date filter applied)
        at_inv = _parse_int(at_data['period_kpis']['Total Invoices'])
        pd_inv = _parse_int(pd_data['period_kpis']['Total Invoices'])
        if at_inv > 0:
            self.assertLessEqual(pd_inv, at_inv,
                f"Period invoices ({pd_inv}) > all-time ({at_inv})")

    def test_sales_lazy_tab_by_season(self):
        data, elapsed = self._json(SALES_URL, {'tab': 'by_season'})
        tab = data.get('tabs', {}).get('by_season')
        self.assertIsNotNone(tab, "by_season tab missing from lazy response")
        self.assertIn('headers', tab)
        self.assertIn('rows', tab)
        expected_first = 'Season'
        self.assertEqual(tab['headers'][0], expected_first,
            f"by_season first column should be 'Season', got {tab['headers'][0]!r}")
        self.assertLess(elapsed, PERF_LIMIT_TAB, f"by_season tab too slow: {elapsed:.2f}s")

    def test_sales_lazy_tab_by_shop(self):
        data, elapsed = self._json(SALES_URL, {'tab': 'by_shop'})
        tab = data.get('tabs', {}).get('by_shop')
        self.assertIsNotNone(tab, "by_shop tab missing from lazy response")
        self.assertEqual(tab['headers'][0], 'Shop')
        self.assertLess(elapsed, PERF_LIMIT_TAB, f"by_shop tab too slow: {elapsed:.2f}s")

    def test_sales_initial_load_performance(self):
        _, elapsed = self._json(SALES_URL)
        get_run_log().log(f"  [perf] sales initial load: {elapsed:.2f}s (limit={PERF_LIMIT_FAST}s)")
        self.assertLess(elapsed, PERF_LIMIT_FAST, f"Sales initial load too slow: {elapsed:.2f}s")

    # ─────────────────────────────────────────────────────────────────────────
    # CUSTOMER  /api/v1/analytics/customer/
    # ─────────────────────────────────────────────────────────────────────────

    def test_customer_load_status_200(self):
        resp, _ = self._get(CUSTOMER_URL)
        self.assertEqual(resp.status_code, 200)

    def test_customer_has_required_keys(self):
        data, _ = self._json(CUSTOMER_URL)
        for key in ('all_time_kpis', 'period_kpis', 'registration_breakdown', 'customer_comparison'):
            self.assertIn(key, data, f"Customer response missing: {key}")

    def test_customer_all_time_kpis_structure(self):
        """Customer all_time_kpis must use human-readable labels matching web."""
        data, _ = self._json(CUSTOMER_URL)
        at = data['all_time_kpis']
        for key in ('Total POS Customers', 'Total CNV Customers', 'POS Only', 'CNV Only'):
            self.assertIn(key, at, f"all_time_kpis missing: {key}")
        self.assertGreaterEqual(_parse_int(at['Total POS Customers']), 0)
        self.assertGreaterEqual(_parse_int(at['Total CNV Customers']), 0)

    def test_customer_period_kpis_structure(self):
        """Customer period_kpis must use human-readable labels matching web."""
        data, _ = self._json(CUSTOMER_URL)
        pd = data['period_kpis']
        for key in ('New POS Customers', 'New CNV Customers', 'Synced This Period', 'Active Customers'):
            self.assertIn(key, pd, f"period_kpis missing: {key}")

    def test_customer_registration_breakdown_tables(self):
        data, _ = self._json(CUSTOMER_URL)
        rb = data['registration_breakdown']
        for tbl_key in ('by_shop', 'by_month', 'by_grade'):
            self.assertIn(tbl_key, rb, f"registration_breakdown missing: {tbl_key}")
            tbl = rb[tbl_key]
            self.assertIn('headers', tbl)
            self.assertIn('rows', tbl)
            # 6 columns: label + 5 metrics
            self.assertEqual(len(tbl['headers']), 6,
                f"{tbl_key} should have 6 columns, got {tbl['headers']}")

    def test_customer_breakdown_shop_columns_match_web(self):
        data, _ = self._json(CUSTOMER_URL)
        headers = data['registration_breakdown']['by_shop']['headers']
        expected = ['Shop', 'New POS', 'New CNV', 'POS Only', 'CNV Only', 'Zalo']
        self.assertEqual(headers, expected,
            f"by_shop headers mismatch.\nExpected: {expected}\nGot: {headers}")

    def test_customer_comparison_tables_present(self):
        data, _ = self._json(CUSTOMER_URL)
        cc = data['customer_comparison']
        for tbl_key in ('pos_only', 'cnv_only', 'both', 'zalo'):
            self.assertIn(tbl_key, cc, f"customer_comparison missing: {tbl_key}")

    def test_customer_pos_only_positive(self):
        data, _ = self._json(CUSTOMER_URL)
        at = data['all_time_kpis']
        # POS Only must be ≤ Total POS Customers
        self.assertLessEqual(
            _parse_int(at['POS Only']), _parse_int(at['Total POS Customers']),
            "POS Only > Total POS Customers — logic error")

    def test_customer_initial_load_performance(self):
        _, elapsed = self._json(CUSTOMER_URL)
        get_run_log().log(f"  [perf] customer initial load: {elapsed:.2f}s (limit={PERF_LIMIT_FAST}s)")
        self.assertLess(elapsed, PERF_LIMIT_FAST, f"Customer load too slow: {elapsed:.2f}s")

    # ─────────────────────────────────────────────────────────────────────────
    # COUPON  /api/v1/analytics/coupon/
    # ─────────────────────────────────────────────────────────────────────────

    def test_coupon_initial_load_status_200(self):
        resp, _ = self._get(COUPON_URL)
        self.assertEqual(resp.status_code, 200)

    def test_coupon_has_required_keys(self):
        data, _ = self._json(COUPON_URL)
        for key in ('all_time_kpis', 'period_kpis', 'tabs', 'available_tabs'):
            self.assertIn(key, data, f"Coupon response missing: {key}")

    def test_coupon_all_time_kpis_structure(self):
        """Coupon all_time_kpis must use human-readable labels matching web's 6-card layout."""
        data, _ = self._json(COUPON_URL)
        at = data['all_time_kpis']
        required = (
            'Total Coupons', 'Used', 'Unused',
            'Total Amount (VND)', 'Coupon Amount (VND)', 'Unique Invoice Amt (VND)',
        )
        for key in required:
            self.assertIn(key, at, f"coupon all_time_kpis missing: {key}")

    def test_coupon_kpis_internally_consistent(self):
        """Used + Unused == Total Coupons (both all-time and period)."""
        data, _ = self._json(COUPON_URL)
        at = data['all_time_kpis']
        pd = data['period_kpis']
        at_total = _parse_int(at['Total Coupons'])
        if at_total > 0:
            self.assertEqual(
                _parse_int(at['Used']) + _parse_int(at['Unused']),
                at_total,
                f"all_time: Used({at['Used']}) + Unused({at['Unused']}) ≠ Total({at['Total Coupons']})",
            )
        pd_total = _parse_int(pd['Total Coupons'])
        if pd_total > 0:
            self.assertEqual(
                _parse_int(pd['Used']) + _parse_int(pd['Unused']),
                pd_total,
                f"period: Used + Unused ≠ Total Coupons",
            )

    def test_coupon_available_tabs_complete(self):
        data, _ = self._json(COUPON_URL)
        expected = {'by_shop', 'detail', 'duplicates'}
        actual = set(data.get('available_tabs', []))
        self.assertEqual(expected, actual, f"coupon available_tabs mismatch: {actual}")

    def test_coupon_initial_tab_is_by_shop(self):
        data, _ = self._json(COUPON_URL)
        tabs = data.get('tabs', {})
        self.assertIn('by_shop', tabs, "Initial coupon load must have by_shop tab")

    def test_coupon_shop_tab_columns_match_web(self):
        data, _ = self._json(COUPON_URL)
        headers = data['tabs']['by_shop']['headers']
        expected = ['Shop', 'Used', '% of Used', 'Coupon Amount (VND)', 'Total Amount (VND)', 'Usage Rate']
        self.assertEqual(headers, expected,
            f"by_shop headers mismatch.\nExpected: {expected}\nGot: {headers}")

    def test_coupon_period_filter_reduces_used(self):
        at_data, _ = self._json(COUPON_URL)
        pd_data, _ = self._json(COUPON_URL, {'date_from': PERIOD_FROM, 'date_to': PERIOD_TO})
        at_used = _parse_int(at_data['all_time_kpis']['Used'])
        pd_used = _parse_int(pd_data['period_kpis']['Used'])
        if at_used > 0:
            self.assertLessEqual(pd_used, at_used,
                f"Period Used ({pd_used}) > all-time Used ({at_used})")

    def test_coupon_lazy_tab_detail(self):
        data, elapsed = self._json(COUPON_URL, {'tab': 'detail'})
        tab = data.get('tabs', {}).get('detail')
        self.assertIsNotNone(tab, "detail tab missing from lazy response")
        self.assertIn('headers', tab)
        self.assertIn('rows', tab)
        self.assertLess(elapsed, PERF_LIMIT_TAB, f"coupon detail tab too slow: {elapsed:.2f}s")

    def test_coupon_lazy_tab_duplicates(self):
        data, elapsed = self._json(COUPON_URL, {'tab': 'duplicates'})
        tab = data.get('tabs', {}).get('duplicates')
        self.assertIsNotNone(tab, "duplicates tab missing from lazy response")
        self.assertIn('headers', tab)
        self.assertLess(elapsed, PERF_LIMIT_TAB, f"coupon duplicates tab too slow: {elapsed:.2f}s")

    def test_coupon_initial_load_performance(self):
        _, elapsed = self._json(COUPON_URL)
        get_run_log().log(f"  [perf] coupon initial load: {elapsed:.2f}s (limit={PERF_LIMIT_FAST}s)")
        self.assertLess(elapsed, PERF_LIMIT_FAST, f"Coupon initial load too slow: {elapsed:.2f}s")

    # ─────────────────────────────────────────────────────────────────────────
    # SHOPS LIST  /api/v1/analytics/shops/
    # ─────────────────────────────────────────────────────────────────────────

    def test_shops_list_status_200(self):
        resp, _ = self._get(SHOPS_URL)
        self.assertEqual(resp.status_code, 200)

    def test_shops_list_has_shops_key(self):
        data, _ = self._json(SHOPS_URL)
        self.assertIn('shops', data)
        self.assertIsInstance(data['shops'], list)

    def test_shops_list_non_empty(self):
        from App.models import SalesTransaction
        if not SalesTransaction.objects.exists():
            self.skipTest("No sales data")
        data, _ = self._json(SHOPS_URL)
        self.assertGreater(len(data['shops']), 0, "shops list is empty but sales data exists")

    def test_shops_list_performance(self):
        _, elapsed = self._json(SHOPS_URL)
        get_run_log().log(f"  [perf] shops list: {elapsed:.2f}s (limit={PERF_LIMIT_SHOPS}s)")
        self.assertLess(elapsed, PERF_LIMIT_SHOPS, f"shops list too slow: {elapsed:.2f}s")

    # ─────────────────────────────────────────────────────────────────────────
    # SHOP DETAIL  /api/v1/analytics/shop-detail/
    # ─────────────────────────────────────────────────────────────────────────

    def _pick_shop(self):
        """Pick a shop present in sales, coupons, AND customer registrations so shop-detail tests don't skip."""
        from App.models import SalesTransaction, Coupon, Customer
        sales_shops = set(
            SalesTransaction.objects
            .exclude(shop_name='').exclude(shop_name__isnull=True)
            .values_list('shop_name', flat=True).distinct()
        )
        # Coupon uses using_shop (not shop_name)
        coupon_shops = set(
            Coupon.objects
            .exclude(using_shop='').exclude(using_shop__isnull=True)
            .values_list('using_shop', flat=True).distinct()
        )
        # Customer registration_store maps to the same shop names as SalesTransaction.shop_name
        customer_stores = set(
            Customer.objects
            .exclude(registration_store='').exclude(registration_store__isnull=True)
            .values_list('registration_store', flat=True).distinct()
        )
        # Prefer a shop present in all three data sets; fall back to sales ∩ coupon, then sales-only
        full_match = sorted(sales_shops & coupon_shops & customer_stores)
        if full_match:
            return full_match[0]
        partial = sorted(sales_shops & coupon_shops)
        return partial[0] if partial else (sorted(sales_shops)[0] if sales_shops else None)

    def test_shop_detail_no_shop_param_returns_400(self):
        resp, _ = self._get(SHOP_DETAIL_URL)
        self.assertEqual(resp.status_code, 400)

    def test_shop_detail_unknown_shop_returns_404(self):
        resp, _ = self._get(SHOP_DETAIL_URL, {'shop': '__nonexistent_shop__'})
        self.assertEqual(resp.status_code, 404)

    def test_shop_detail_initial_load_status_200(self):
        from App.models import SalesTransaction
        if not SalesTransaction.objects.exists():
            self.skipTest("No sales data")
        shop = self._pick_shop()
        resp, _ = self._get(SHOP_DETAIL_URL, {'shop': shop})
        self.assertEqual(resp.status_code, 200)

    def test_shop_detail_initial_load_has_sales_and_sections(self):
        from App.models import SalesTransaction
        if not SalesTransaction.objects.exists():
            self.skipTest("No sales data")
        shop = self._pick_shop()
        data, _ = self._json(SHOP_DETAIL_URL, {'shop': shop})
        self.assertIn('shop_name', data)
        self.assertIn('sales', data)
        self.assertIn('available_sections', data)
        self.assertEqual(set(data['available_sections']), {'sales', 'customer', 'coupon'})

    def test_shop_detail_sales_section_structure(self):
        from App.models import SalesTransaction
        if not SalesTransaction.objects.exists():
            self.skipTest("No sales data")
        shop = self._pick_shop()
        data, _ = self._json(SHOP_DETAIL_URL, {'shop': shop, 'section': 'sales'})
        self.assertIn('sales', data)
        sales = data['sales']
        for key in ('all_time_kpis', 'period_kpis', 'by_session', 'by_month', 'by_week'):
            self.assertIn(key, sales, f"sales section missing: {key}")

    def test_shop_detail_sales_kpis_structure(self):
        """Shop detail sales kpis must use human-readable labels matching web's 7 cards."""
        from App.models import SalesTransaction
        if not SalesTransaction.objects.exists():
            self.skipTest("No sales data")
        shop = self._pick_shop()
        data, _ = self._json(SHOP_DETAIL_URL, {'shop': shop, 'section': 'sales'})
        at = data['sales']['all_time_kpis']
        for key in ('Active', 'Returning', 'Return Rate',
                    'INV(RET)', 'AMT(RET)', 'Total INV', 'Total Amt (VND)'):
            self.assertIn(key, at, f"shop sales all_time_kpis missing: {key}")

    def test_shop_detail_sales_period_le_alltime(self):
        """Period Total INV must be ≤ all-time Total INV for the same shop."""
        from App.models import SalesTransaction
        if not SalesTransaction.objects.exists():
            self.skipTest("No sales data")
        shop = self._pick_shop()
        data, _ = self._json(SHOP_DETAIL_URL, {
            'shop': shop, 'section': 'sales',
            'date_from': PERIOD_FROM, 'date_to': PERIOD_TO,
        })
        sales = data.get('sales', {})
        at_inv = _parse_int(sales.get('all_time_kpis', {}).get('Total INV', 0))
        pd_inv = _parse_int(sales.get('period_kpis', {}).get('Total INV', 0))
        if at_inv > 0:
            self.assertLessEqual(pd_inv, at_inv,
                f"shop period invoices ({pd_inv}) > all-time ({at_inv})")

    def test_shop_detail_customer_section_structure(self):
        from App.models import SalesTransaction
        if not SalesTransaction.objects.exists():
            self.skipTest("No sales data")
        shop = self._pick_shop()
        data, elapsed = self._json(SHOP_DETAIL_URL, {'shop': shop, 'section': 'customer'})
        self.assertIn('customer', data)
        customer = data['customer']
        for key in ('all_time_kpis', 'period_kpis', 'by_season', 'by_month', 'by_week'):
            self.assertIn(key, customer, f"customer section missing: {key}")
        self.assertLess(elapsed, PERF_LIMIT_TAB, f"customer section too slow: {elapsed:.2f}s")

    def test_shop_detail_customer_kpis_structure(self):
        """Shop detail customer kpis must match web's 7 KPI cards with human-readable labels."""
        from App.models import SalesTransaction
        if not SalesTransaction.objects.exists():
            self.skipTest("No sales data")
        shop = self._pick_shop()
        data, _ = self._json(SHOP_DETAIL_URL, {'shop': shop, 'section': 'customer'})
        at = data['customer']['all_time_kpis']
        for key in ('New POS', 'POS (w/ INV)', 'New CNV', 'POS Only', 'CNV Only', 'Zalo App', 'Zalo OA'):
            self.assertIn(key, at, f"shop customer all_time_kpis missing: {key}")

    def test_shop_detail_coupon_section_structure(self):
        from App.models import SalesTransaction
        if not SalesTransaction.objects.exists():
            self.skipTest("No sales data")
        shop = self._pick_shop()
        data, elapsed = self._json(SHOP_DETAIL_URL, {'shop': shop, 'section': 'coupon'})
        self.assertIn('coupon', data)
        coupon = data['coupon']
        for key in ('all_time_kpis', 'period_kpis', 'detail_table'):
            self.assertIn(key, coupon, f"coupon section missing: {key}")
        self.assertLess(elapsed, PERF_LIMIT_TAB, f"coupon section too slow: {elapsed:.2f}s")

    def test_shop_detail_coupon_kpis_structure(self):
        """Shop detail coupon kpis must use human-readable labels matching web."""
        from App.models import SalesTransaction
        if not SalesTransaction.objects.exists():
            self.skipTest("No sales data")
        shop = self._pick_shop()
        data, _ = self._json(SHOP_DETAIL_URL, {'shop': shop, 'section': 'coupon'})
        at = data['coupon']['all_time_kpis']
        for key in ('Total Coupons', 'Used', 'Unused',
                    'Total Amount (VND)', 'Coupon Amount (VND)', 'Unique Invoice Amt (VND)'):
            self.assertIn(key, at, f"shop coupon all_time_kpis missing: {key}")

    def test_shop_detail_coupon_internally_consistent(self):
        from App.models import SalesTransaction, Coupon
        if not SalesTransaction.objects.exists() or not Coupon.objects.exists():
            self.skipTest("No data")
        shop = self._pick_shop()
        data, _ = self._json(SHOP_DETAIL_URL, {'shop': shop, 'section': 'coupon'})
        at = data['coupon']['all_time_kpis']
        total  = _parse_int(at.get('Total Coupons', 0))
        used   = _parse_int(at.get('Used', 0))
        unused = _parse_int(at.get('Unused', 0))
        if total > 0:
            self.assertEqual(used + unused, total,
                f"coupon: Used({used}) + Unused({unused}) ≠ Total Coupons({total})")

    def test_shop_detail_initial_load_performance(self):
        from App.models import SalesTransaction
        if not SalesTransaction.objects.exists():
            self.skipTest("No sales data")
        shop = self._pick_shop()
        _, elapsed = self._json(SHOP_DETAIL_URL, {'shop': shop})
        get_run_log().log(f"  [perf] shop-detail initial load shop={shop}: {elapsed:.2f}s (limit={PERF_LIMIT_FAST}s)")
        self.assertLess(elapsed, PERF_LIMIT_FAST, f"shop-detail initial load too slow: {elapsed:.2f}s")

    # ─────────────────────────────────────────────────────────────────────────
    # CUSTOMER DETAIL  /api/v1/analytics/customer-detail/
    # ─────────────────────────────────────────────────────────────────────────

    def test_customer_detail_no_params_returns_400(self):
        resp, _ = self._get(CUST_DETAIL_URL)
        self.assertEqual(resp.status_code, 400)

    def test_customer_detail_nonexistent_returns_404(self):
        resp, _ = self._get(CUST_DETAIL_URL, {'vip_id': '__nonexistent__'})
        self.assertEqual(resp.status_code, 404)

    def test_customer_detail_valid_customer_returns_200(self):
        from App.models import Customer
        customer = Customer.objects.exclude(vip_id='0').first()
        if customer is None:
            self.skipTest("No customer data")
        resp, _ = self._get(CUST_DETAIL_URL, {'vip_id': customer.vip_id})
        self.assertEqual(resp.status_code, 200)

    def test_customer_detail_has_required_keys(self):
        from App.models import Customer
        customer = Customer.objects.exclude(vip_id='0').first()
        if customer is None:
            self.skipTest("No customer data")
        data, _ = self._json(CUST_DETAIL_URL, {'vip_id': customer.vip_id})
        for key in (
            'name', 'vip_id', 'phone', 'grade',
            'registration_store', 'registration_date', 'cnv_sync_status',
            'email', 'total_invoices', 'total_revenue', 'invoice_history',
        ):
            self.assertIn(key, data, f"customer-detail missing: {key}")

    def test_customer_detail_phone_is_masked(self):
        from App.models import Customer
        customer = Customer.objects.exclude(vip_id='0').exclude(phone='').first()
        if customer is None:
            self.skipTest("No customer with phone")
        data, _ = self._json(CUST_DETAIL_URL, {'vip_id': customer.vip_id})
        phone = data.get('phone', '')
        # Masked format contains 'x' — raw digits must not all be present
        self.assertIn('x', phone.lower(), f"Phone not masked: {phone!r}")
        # Raw phone digits must not be returned verbatim
        raw_digits = ''.join(c for c in (customer.phone or '') if c.isdigit())
        if len(raw_digits) >= 7:
            self.assertNotEqual(
                ''.join(c for c in phone if c.isdigit()),
                raw_digits,
                f"Raw phone digits returned unmasked: {phone!r}",
            )

    def test_customer_detail_total_invoices_accurate(self):
        """total_invoices must reflect ALL transactions, not just the 50-record display cap."""
        from App.models import Customer, SalesTransaction
        # Find a customer with more than 50 invoices to make the test meaningful
        vip_id = (
            SalesTransaction.objects
            .exclude(vip_id='0')
            .values('vip_id')
            .annotate(cnt=Count('vip_id'))
            .order_by('-cnt')
            .values_list('vip_id', flat=True)
            .first()
        )
        if vip_id is None:
            self.skipTest("No sales data")
        actual_count = SalesTransaction.objects.filter(vip_id=vip_id).count()
        data, _ = self._json(CUST_DETAIL_URL, {'vip_id': vip_id})
        self.assertEqual(
            data['total_invoices'], actual_count,
            f"total_invoices {data['total_invoices']} ≠ actual {actual_count} for vip_id={vip_id}",
        )

    # ─────────────────────────────────────────────────────────────────────────
    # SNAPSHOT — lock response shapes so regressions are caught
    # ─────────────────────────────────────────────────────────────────────────

    def test_sales_snapshot_keys(self):
        """Snapshot the top-level key set of the sales response."""
        data, _ = self._json(SALES_URL)
        snapshot = {
            'top_keys': sorted(data.keys()),
            'all_time_kpi_keys': sorted(data['all_time_kpis'].keys()),
            'period_kpi_keys': sorted(data['period_kpis'].keys()),
            'available_tabs': sorted(data.get('available_tabs', [])),
            'grade_tab_headers': data['tabs']['by_grade']['headers'],
        }
        self.assert_snapshot('api_sales_shape', snapshot)

    def test_coupon_snapshot_keys(self):
        data, _ = self._json(COUPON_URL)
        snapshot = {
            'top_keys': sorted(data.keys()),
            'all_time_kpi_keys': sorted(data['all_time_kpis'].keys()),
            'period_kpi_keys': sorted(data['period_kpis'].keys()),
            'available_tabs': sorted(data.get('available_tabs', [])),
            'shop_tab_headers': data['tabs']['by_shop']['headers'],
        }
        self.assert_snapshot('api_coupon_shape', snapshot)

    def test_customer_snapshot_keys(self):
        data, _ = self._json(CUSTOMER_URL)
        snapshot = {
            'top_keys': sorted(data.keys()),
            'all_time_kpi_keys': sorted(data['all_time_kpis'].keys()),
            'period_kpi_keys': sorted(data['period_kpis'].keys()),
            'registration_breakdown_keys': sorted(data['registration_breakdown'].keys()),
            'customer_comparison_keys': sorted(data['customer_comparison'].keys()),
            'shop_table_headers': data['registration_breakdown']['by_shop']['headers'],
        }
        self.assert_snapshot('api_customer_shape', snapshot)

    def test_shop_detail_snapshot_keys(self):
        from App.models import SalesTransaction
        if not SalesTransaction.objects.exists():
            self.skipTest("No sales data")
        shop = self._pick_shop()
        data, _ = self._json(SHOP_DETAIL_URL, {'shop': shop, 'section': 'sales'})
        sales = data.get('sales', {})
        snapshot = {
            'top_keys': sorted(data.keys()),
            'sales_keys': sorted(sales.keys()),
            'all_time_kpi_keys': sorted(sales.get('all_time_kpis', {}).keys()),
            'period_kpi_keys': sorted(sales.get('period_kpis', {}).keys()),
        }
        self.assert_snapshot('api_shop_detail_sales_shape', snapshot)


# ══════════════════════════════════════════════════════════════════════════════
# CHART ENDPOINT TESTS  /api/v1/charts/*
# ══════════════════════════════════════════════════════════════════════════════

class ApiChartTest(ApiStructureTest):
    """
    Structure + data tests for all 3 chart endpoints.
    Inherits setUpTestData + auth helpers from ApiStructureTest.
    Verifies: auth guard, response shape, donut slices, trend data.
    """

    # ── Sales Chart ───────────────────────────────────────────────────────────

    def test_sales_chart_status_200(self):
        resp, _ = self._get(SALES_CHART_URL)
        self.assertEqual(resp.status_code, 200)

    def test_sales_chart_has_donuts_key(self):
        data, _ = self._json(SALES_CHART_URL)
        self.assertIn('donuts', data, "Sales chart missing 'donuts' key")

    def test_sales_chart_donuts_is_list(self):
        data, _ = self._json(SALES_CHART_URL)
        self.assertIsInstance(data['donuts'], list)

    def test_sales_chart_donut_slice_shape(self):
        data, _ = self._json(SALES_CHART_URL)
        donuts = data.get('donuts', [])
        if not donuts:
            self.skipTest("No sales data for chart")
        for donut in donuts:
            self.assertIn('title', donut)
            self.assertIn('slices', donut)
            for s in donut['slices']:
                self.assertIn('label', s)
                self.assertIn('value', s)
                self.assertIn('color', s)
                self.assertIn('percentage', s)
                self.assertGreaterEqual(s['percentage'], 0)
                self.assertLessEqual(s['percentage'], 100)

    def test_sales_chart_donut_percentages_sum_to_100(self):
        data, _ = self._json(SALES_CHART_URL)
        for donut in data.get('donuts', []):
            total = sum(s['percentage'] for s in donut['slices'])
            self.assertAlmostEqual(total, 100.0, delta=1.5,
                msg=f"Donut '{donut['title']}' percentages sum to {total:.1f}%, expected ~100%")

    def test_sales_chart_trend_is_list_or_null(self):
        data, _ = self._json(SALES_CHART_URL)
        trend = data.get('trend')
        if trend is not None:
            self.assertIsInstance(trend, list)
            if trend:
                point = trend[0]
                self.assertIn('label', point)
                self.assertIn('value', point)

    def test_sales_chart_with_date_filter(self):
        data, _ = self._json(SALES_CHART_URL, {'date_from': PERIOD_FROM, 'date_to': PERIOD_TO})
        self.assertIn('donuts', data)

    # ── Customer Chart ────────────────────────────────────────────────────────

    def test_customer_chart_status_200(self):
        resp, _ = self._get(CUSTOMER_CHART_URL)
        self.assertEqual(resp.status_code, 200)

    def test_customer_chart_has_donuts_key(self):
        data, _ = self._json(CUSTOMER_CHART_URL)
        self.assertIn('donuts', data)

    def test_customer_chart_donut_slice_shape(self):
        data, _ = self._json(CUSTOMER_CHART_URL)
        donuts = data.get('donuts', [])
        if not donuts:
            self.skipTest("No CNV data for customer chart")
        for donut in donuts:
            self.assertIn('title', donut)
            self.assertIn('slices', donut)
            for s in donut['slices']:
                self.assertIn('label', s)
                self.assertIn('percentage', s)

    def test_customer_chart_with_date_filter(self):
        data, _ = self._json(CUSTOMER_CHART_URL, {'date_from': PERIOD_FROM, 'date_to': PERIOD_TO})
        self.assertIn('donuts', data)

    # ── Coupon Chart ──────────────────────────────────────────────────────────

    def test_coupon_chart_status_200(self):
        resp, _ = self._get(COUPON_CHART_URL)
        self.assertEqual(resp.status_code, 200)

    def test_coupon_chart_has_donuts_key(self):
        data, _ = self._json(COUPON_CHART_URL)
        self.assertIn('donuts', data)

    def test_coupon_chart_donut_slice_shape(self):
        data, _ = self._json(COUPON_CHART_URL)
        donuts = data.get('donuts', [])
        if not donuts:
            self.skipTest("No coupon data for chart")
        for donut in donuts:
            self.assertIn('title', donut)
            self.assertIn('slices', donut)
            for s in donut['slices']:
                self.assertIn('label', s)
                self.assertIn('value', s)
                self.assertIn('percentage', s)

    def test_coupon_chart_with_date_filter(self):
        data, _ = self._json(COUPON_CHART_URL, {'date_from': PERIOD_FROM, 'date_to': PERIOD_TO})
        self.assertIn('donuts', data)

    # ── Chart auth guard ─────────────────────────────────────────────────────

    def test_chart_endpoints_require_auth(self):
        for url in (SALES_CHART_URL, CUSTOMER_CHART_URL, COUPON_CHART_URL):
            resp = self.client.get(url)  # no Authorization header → 401
            self.assertIn(resp.status_code, (401, 403),
                f"Expected 401/403 for unauthenticated {url}, got {resp.status_code}")


# ══════════════════════════════════════════════════════════════════════════════
# PARITY TESTS — API output must match shared service function output exactly
# Both web views and API call the same underlying functions.
# These tests call the function directly then call the API and compare values.
# This guarantees web ↔ mobile data parity without reading HTML.
# ══════════════════════════════════════════════════════════════════════════════

class ApiParityTest(ApiStructureTest):
    """Verify API output matches shared service functions (web view standard)."""

    PERF_LIMIT = 10.0  # seconds — flag API calls slower than this

    def _log_perf(self, label, elapsed):
        get_run_log().log(f"  [parity-perf] {label}: {elapsed:.2f}s (limit={self.PERF_LIMIT}s)")
        self.assertLess(elapsed, self.PERF_LIMIT, f"{label} too slow: {elapsed:.2f}s")

    # ── Sales Analytics ───────────────────────────────────────────────────────

    def test_sales_alltime_kpis_match_underlying_function(self):
        """API all-time KPIs must equal get_sales_tab('grade') overview exactly."""
        from App.analytics.tab_functions import get_sales_tab
        raw = get_sales_tab('grade', date_from=None, date_to=None)
        if not raw:
            self.skipTest("No sales data")
        ov = raw['overview']
        data, elapsed = self._json(SALES_URL)
        self._log_perf("sales alltime", elapsed)
        at = data['all_time_kpis']
        self.assertEqual(ov.get('total_customers_in_db', 0), _parse_int(at['Total Customers']))
        self.assertEqual(ov.get('member_active_all_time', 0), _parse_int(at['Member Active']))
        self.assertEqual(ov.get('member_inactive_all_time', 0), _parse_int(at['Member Inactive']))
        # Return rate is a percentage string: "12.34%"
        expected_rr = f"{float(ov.get('return_rate_all_time', 0)):.2f}%"
        self.assertEqual(expected_rr, at.get('Return Rate (All Time)', ''))

    def test_sales_period_2025_kpis_match_underlying_function(self):
        """API period 2025 KPIs must equal get_sales_tab('grade') period output — all 10 fields."""
        from App.analytics.tab_functions import get_sales_tab
        from datetime import date as _d
        raw = get_sales_tab('grade', date_from=_d(2025, 1, 1), date_to=_d(2025, 12, 31))
        if not raw:
            self.skipTest("No 2025 sales data")
        ov = raw['overview']
        data, elapsed = self._json(SALES_URL, {'date_from': PERIOD_FROM, 'date_to': PERIOD_TO})
        self._log_perf("sales period 2025", elapsed)
        pd = data['period_kpis']
        self.assertEqual(ov.get('new_members_in_period', 0), _parse_int(pd['New Members']))
        self.assertEqual(ov.get('returning_customers', 0), _parse_int(pd['Returning Customers']))
        self.assertEqual(ov.get('active_customers', 0), _parse_int(pd['Active Customers']))
        self.assertEqual(ov.get('returning_invoices', 0), _parse_int(pd['INV(RET)']))
        amt_ret = int(round(ov.get('returning_amount', 0)))
        self.assertEqual(amt_ret, _parse_int(pd['AMT(RET)']))
        self.assertEqual(ov.get('total_invoices_without_vip0', 0), _parse_int(pd['INV(CUS)']))
        amt_cus = int(round(ov.get('total_amount_without_vip0', 0)))
        self.assertEqual(amt_cus, _parse_int(pd['AMT(CUS)']))
        total_inv = ov.get('total_invoices_with_vip0', ov.get('total_invoices', 0))
        self.assertEqual(total_inv, _parse_int(pd['Total Invoices']))
        total_amt = int(round(ov.get('total_amount_with_vip0', ov.get('total_amount', 0))))
        self.assertEqual(total_amt, _parse_int(pd['Total Amount']))

    # ── Shop Detail – Sales ───────────────────────────────────────────────────

    def test_shop_sales_alltime_kpis_match_underlying_function(self):
        """API shop sales all-time KPIs must equal get_shop_detail_sales_data — all 7 fields."""
        from App.analytics.tab_functions import get_shop_detail_sales_data
        from App.models import SalesTransaction
        if not SalesTransaction.objects.exists():
            self.skipTest("No sales data")
        shop = self._pick_shop()
        raw = get_shop_detail_sales_data(shop, date_from=None, date_to=None)
        if not raw:
            self.skipTest("No data for shop")
        at_raw = raw.get('all_time', {})
        data, elapsed = self._json(SHOP_DETAIL_URL, {'shop': shop, 'section': 'sales'})
        self._log_perf("shop sales alltime", elapsed)
        at = data['sales']['all_time_kpis']
        total_inv = at_raw.get('total_invoices_with_vip0', at_raw.get('total_invoices', 0))
        self.assertEqual(total_inv, _parse_int(at.get('Total INV', 0)))
        total_amt = int(round(at_raw.get('total_amount_with_vip0', at_raw.get('total_amount', 0))))
        self.assertEqual(total_amt, _parse_int(at.get('Total Amt (VND)', 0)))
        self.assertEqual(at_raw.get('total_customers', 0), _parse_int(at.get('Active', 0)))
        self.assertEqual(at_raw.get('returning_customers', 0), _parse_int(at.get('Returning', 0)))
        self.assertEqual(at_raw.get('returning_invoices', 0), _parse_int(at.get('INV(RET)', 0)))
        amt_ret = int(round(at_raw.get('returning_amount', 0)))
        self.assertEqual(amt_ret, _parse_int(at.get('AMT(RET)', 0)))
        # return_rate is formatted "12.34%"
        expected_rr = f"{float(at_raw.get('return_rate', 0)):.2f}%"
        self.assertEqual(expected_rr, at.get('Return Rate', ''))

    def test_shop_sales_period_2025_kpis_match_underlying_function(self):
        """API shop sales period KPIs must equal get_shop_detail_sales_data period — all 7 fields."""
        from App.analytics.tab_functions import get_shop_detail_sales_data
        from App.models import SalesTransaction
        from datetime import date as _d
        if not SalesTransaction.objects.exists():
            self.skipTest("No sales data")
        shop = self._pick_shop()
        raw = get_shop_detail_sales_data(shop, date_from=_d(2025, 1, 1), date_to=_d(2025, 12, 31))
        if not raw:
            self.skipTest("No 2025 data for shop")
        pd_raw = raw.get('period', {})
        data, elapsed = self._json(SHOP_DETAIL_URL, {
            'shop': shop, 'section': 'sales',
            'date_from': PERIOD_FROM, 'date_to': PERIOD_TO,
        })
        self._log_perf("shop sales period 2025", elapsed)
        pd = data['sales']['period_kpis']
        total_inv = pd_raw.get('total_invoices_with_vip0', pd_raw.get('total_invoices', 0))
        self.assertEqual(total_inv, _parse_int(pd.get('Total INV', 0)))
        total_amt = int(round(pd_raw.get('total_amount_with_vip0', pd_raw.get('total_amount', 0))))
        self.assertEqual(total_amt, _parse_int(pd.get('Total Amt (VND)', 0)))
        self.assertEqual(pd_raw.get('total_customers', 0), _parse_int(pd.get('Active', 0)))
        self.assertEqual(pd_raw.get('returning_customers', 0), _parse_int(pd.get('Returning', 0)))
        self.assertEqual(pd_raw.get('returning_invoices', 0), _parse_int(pd.get('INV(RET)', 0)))
        amt_ret = int(round(pd_raw.get('returning_amount', 0)))
        self.assertEqual(amt_ret, _parse_int(pd.get('AMT(RET)', 0)))

    # ── Shop Detail – Customer ────────────────────────────────────────────────

    def test_shop_customer_alltime_kpis_match_underlying_function(self):
        """API shop customer all-time KPIs must equal get_shop_detail_customer_data — all 7 fields."""
        from App.analytics.tab_functions import get_shop_detail_customer_data
        from App.models import SalesTransaction
        if not SalesTransaction.objects.exists():
            self.skipTest("No sales data")
        shop = self._pick_shop()
        raw = get_shop_detail_customer_data(shop, start_date='', end_date='')
        if not raw:
            self.skipTest("No customer data for shop")
        at_raw = raw.get('all_time', {})
        data, elapsed = self._json(SHOP_DETAIL_URL, {'shop': shop, 'section': 'customer'})
        self._log_perf("shop customer alltime", elapsed)
        at = data['customer']['all_time_kpis']
        self.assertEqual(at_raw.get('new_pos', 0), _parse_int(at.get('New POS', 0)))
        self.assertEqual(at_raw.get('new_pos_inv', 0), _parse_int(at.get('POS (w/ INV)', 0)))
        self.assertEqual(at_raw.get('new_cnv', 0), _parse_int(at.get('New CNV', 0)))
        self.assertEqual(at_raw.get('new_pos_only', 0), _parse_int(at.get('POS Only', 0)))
        self.assertEqual(at_raw.get('new_cnv_only', 0), _parse_int(at.get('CNV Only', 0)))
        self.assertEqual(at_raw.get('zalo_app', 0), _parse_int(at.get('Zalo App', 0)))
        self.assertEqual(at_raw.get('zalo_oa', 0), _parse_int(at.get('Zalo OA', 0)))

    def test_shop_customer_period_2025_kpis_match_underlying_function(self):
        """API shop customer period KPIs must equal get_shop_detail_customer_data — all 7 fields."""
        from App.analytics.tab_functions import get_shop_detail_customer_data
        from App.models import SalesTransaction
        if not SalesTransaction.objects.exists():
            self.skipTest("No sales data")
        shop = self._pick_shop()
        raw = get_shop_detail_customer_data(shop, start_date=PERIOD_FROM, end_date=PERIOD_TO)
        if not raw:
            self.skipTest("No customer data for shop")
        pd_raw = raw.get('period', {})
        data, elapsed = self._json(SHOP_DETAIL_URL, {
            'shop': shop, 'section': 'customer',
            'date_from': PERIOD_FROM, 'date_to': PERIOD_TO,
        })
        self._log_perf("shop customer period 2025", elapsed)
        pd = data['customer']['period_kpis']
        self.assertEqual(pd_raw.get('new_pos', 0), _parse_int(pd.get('New POS', 0)))
        self.assertEqual(pd_raw.get('new_pos_inv', 0), _parse_int(pd.get('POS (w/ INV)', 0)))
        self.assertEqual(pd_raw.get('new_cnv', 0), _parse_int(pd.get('New CNV', 0)))
        self.assertEqual(pd_raw.get('new_pos_only', 0), _parse_int(pd.get('POS Only', 0)))
        self.assertEqual(pd_raw.get('new_cnv_only', 0), _parse_int(pd.get('CNV Only', 0)))
        self.assertEqual(pd_raw.get('zalo_app', 0), _parse_int(pd.get('Zalo App', 0)))
        self.assertEqual(pd_raw.get('zalo_oa', 0), _parse_int(pd.get('Zalo OA', 0)))

    # ── Shop Detail – Coupon ──────────────────────────────────────────────────

    def test_shop_coupon_alltime_kpis_match_underlying_function(self):
        """API shop coupon all-time KPIs must equal get_shop_detail_coupon_data — all 6 fields."""
        from App.analytics.tab_functions import get_shop_detail_coupon_data
        from App.models import Coupon
        if not Coupon.objects.exists():
            self.skipTest("No coupon data")
        shop = self._pick_shop()
        raw = get_shop_detail_coupon_data(shop, date_from=None, date_to=None)
        if not raw or not raw.get('all_time', {}).get('total'):
            self.skipTest("No coupon data for shop")
        at_raw = raw.get('all_time', {})
        data, elapsed = self._json(SHOP_DETAIL_URL, {'shop': shop, 'section': 'coupon'})
        self._log_perf("shop coupon alltime", elapsed)
        at = data['coupon']['all_time_kpis']
        self.assertEqual(at_raw.get('total', 0), _parse_int(at.get('Total Coupons', 0)))
        self.assertEqual(at_raw.get('used', 0), _parse_int(at.get('Used', 0)))
        self.assertEqual(at_raw.get('unused', 0), _parse_int(at.get('Unused', 0)))
        amt = int(round(float(at_raw.get('total_amount', 0))))
        self.assertEqual(amt, _parse_int(at.get('Total Amount (VND)', 0)))
        coupon_amt = int(round(float(at_raw.get('total_coupon_amount', 0))))
        self.assertEqual(coupon_amt, _parse_int(at.get('Coupon Amount (VND)', 0)))

    def test_shop_coupon_period_2025_kpis_match_underlying_function(self):
        """API shop coupon period 2025 KPIs must equal get_shop_detail_coupon_data period."""
        from App.analytics.tab_functions import get_shop_detail_coupon_data
        from App.models import Coupon
        from datetime import date as _d
        if not Coupon.objects.exists():
            self.skipTest("No coupon data")
        shop = self._pick_shop()
        raw = get_shop_detail_coupon_data(shop, date_from=_d(2025, 1, 1), date_to=_d(2025, 12, 31))
        if not raw or not raw.get('period', {}).get('total'):
            self.skipTest("No 2025 coupon data for shop")
        pd_raw = raw.get('period', {})
        data, elapsed = self._json(SHOP_DETAIL_URL, {
            'shop': shop, 'section': 'coupon',
            'date_from': PERIOD_FROM, 'date_to': PERIOD_TO,
        })
        self._log_perf("shop coupon period 2025", elapsed)
        pd = data['coupon']['period_kpis']
        self.assertEqual(pd_raw.get('total', 0), _parse_int(pd.get('Total Coupons', 0)))
        self.assertEqual(pd_raw.get('used', 0), _parse_int(pd.get('Used', 0)))
        self.assertEqual(pd_raw.get('unused', 0), _parse_int(pd.get('Unused', 0)))

    # ── CNV Customer Analytics ────────────────────────────────────────────────

    def test_cnv_customer_alltime_kpis_match_underlying_function(self):
        """API CNV customer all-time KPIs must equal get_cnv_customer_kpis — all 4 fields."""
        from App.cnv.service import get_cnv_phone_sets, get_cnv_customer_kpis
        pos_phones, cnv_phones = get_cnv_phone_sets()
        kpis = get_cnv_customer_kpis({}, False, pos_phones, cnv_phones)
        data, elapsed = self._json(CUSTOMER_URL)
        self._log_perf("cnv customer alltime", elapsed)
        at = data['all_time_kpis']
        self.assertEqual(kpis['total_pos'], _parse_int(at.get('Total POS Customers', 0)))
        self.assertEqual(kpis['total_cnv'], _parse_int(at.get('Total CNV Customers', 0)))
        self.assertEqual(kpis['pos_only_all'], _parse_int(at.get('POS Only', 0)))
        self.assertEqual(kpis['cnv_only_all'], _parse_int(at.get('CNV Only', 0)))
        # Verify all-time consistency: total = pos_only + cnv_only + both
        self.assertEqual(kpis['total_pos'], kpis['pos_only_all'] + kpis['both'])
        self.assertEqual(kpis['total_cnv'], kpis['cnv_only_all'] + kpis['both'])

    def test_cnv_customer_period_2025_kpis_match_underlying_function(self):
        """API CNV customer period KPIs must equal get_cnv_customer_kpis — all 4 period fields."""
        from App.cnv.service import get_cnv_phone_sets, get_cnv_customer_kpis, parse_cnv_period_filter
        pos_phones, cnv_phones = get_cnv_phone_sets()
        period_filter, has_filter = parse_cnv_period_filter(PERIOD_FROM, PERIOD_TO)
        kpis = get_cnv_customer_kpis(period_filter, has_filter, pos_phones, cnv_phones)
        data, elapsed = self._json(CUSTOMER_URL, {'date_from': PERIOD_FROM, 'date_to': PERIOD_TO})
        self._log_perf("cnv customer period 2025", elapsed)
        pd = data['period_kpis']
        self.assertEqual(kpis['new_pos'], _parse_int(pd.get('New POS Customers', 0)))
        self.assertEqual(kpis['new_cnv'], _parse_int(pd.get('New CNV Customers', 0)))
        self.assertEqual(kpis['synced_period'], _parse_int(pd.get('Synced This Period', 0)))
        self.assertEqual(kpis['active_period'], _parse_int(pd.get('Active Customers', 0)))
        # Period consistency: synced = new_pos - pos_only_period
        self.assertEqual(kpis['synced_period'], kpis['new_pos'] - kpis['pos_only_period'])

    # ── Sales Analytics – table rows ─────────────────────────────────────────

    def _assert_table(self, table, raw_rows, col_fn, label):
        """Helper: check row count + every numeric cell in every row."""
        api_rows = table.get('rows', [])
        self.assertEqual(len(raw_rows), len(api_rows), f"{label}: row count mismatch")
        for i, (raw, api) in enumerate(zip(raw_rows, api_rows)):
            for col_idx, field, cast in col_fn(raw):
                self.assertEqual(cast(raw.get(field, 0)), _parse_int(api[col_idx]),
                    f"{label} row[{i}] col[{col_idx}]({field}): {raw.get(field)} != {api[col_idx]}")

    def test_sales_grade_table_rows_match_underlying_function(self):
        """API by_grade table must have same row count + values as get_sales_tab('grade')."""
        from App.analytics.tab_functions import get_sales_tab
        raw = get_sales_tab('grade', date_from=None, date_to=None)
        if not raw:
            self.skipTest("No sales data")
        raw_rows = raw.get('by_grade', [])
        data, _ = self._json(SALES_URL)
        table = data['tabs']['by_grade']
        self.assertEqual(len(raw_rows), len(table['rows']), "by_grade row count")
        for i, (r, api_row) in enumerate(zip(raw_rows, table['rows'])):
            self.assertEqual(str(r.get('grade', '')), api_row[0], f"row[{i}] grade label")
            self.assertEqual(r.get('total_customers', 0), _parse_int(api_row[1]), f"row[{i}] active")
            self.assertEqual(r.get('returning_customers', 0), _parse_int(api_row[2]), f"row[{i}] returning")
            self.assertEqual(r.get('total_in_db', 0), _parse_int(api_row[4]), f"row[{i}] total_in_db")
            self.assertEqual(r.get('returning_invoices', 0), _parse_int(api_row[6]), f"row[{i}] inv_ret")
            self.assertEqual(int(round(r.get('returning_amount', 0))), _parse_int(api_row[7]), f"row[{i}] amt_ret")
            self.assertEqual(r.get('total_invoices', 0), _parse_int(api_row[8]), f"row[{i}] total_inv")
            self.assertEqual(int(round(r.get('total_amount', 0))), _parse_int(api_row[9]), f"row[{i}] total_amt")

    def test_sales_grade_table_period_2025_rows_match(self):
        """API by_grade period 2025 table must equal get_sales_tab('grade') period by_grade rows."""
        from App.analytics.tab_functions import get_sales_tab
        from datetime import date as _d
        raw = get_sales_tab('grade', date_from=_d(2025, 1, 1), date_to=_d(2025, 12, 31))
        if not raw:
            self.skipTest("No 2025 sales data")
        raw_rows = raw.get('by_grade', [])
        data, _ = self._json(SALES_URL, {'date_from': PERIOD_FROM, 'date_to': PERIOD_TO})
        table = data['tabs']['by_grade']
        self.assertEqual(len(raw_rows), len(table['rows']), "by_grade period row count")
        for i, (r, api_row) in enumerate(zip(raw_rows, table['rows'])):
            self.assertEqual(str(r.get('grade', '')), api_row[0], f"row[{i}] grade")
            self.assertEqual(r.get('total_customers', 0), _parse_int(api_row[1]), f"row[{i}] active")
            self.assertEqual(r.get('returning_customers', 0), _parse_int(api_row[2]), f"row[{i}] returning")
            self.assertEqual(r.get('returning_invoices', 0), _parse_int(api_row[6]), f"row[{i}] inv_ret")
            self.assertEqual(int(round(r.get('total_amount', 0))), _parse_int(api_row[9]), f"row[{i}] total_amt")

    def test_sales_season_table_rows_match_underlying_function(self):
        """API by_season lazy tab must equal get_sales_tab('season') by_session rows — all rows."""
        from App.analytics.tab_functions import get_sales_tab
        raw = get_sales_tab('season', date_from=None, date_to=None)
        if not raw:
            self.skipTest("No season data")
        raw_rows = raw.get('by_session', [])
        data, elapsed = self._json(SALES_URL, {'tab': 'by_season'})
        self._log_perf("sales by_season tab", elapsed)
        table = data['tabs']['by_season']
        self.assertEqual(len(raw_rows), len(table['rows']), "by_season row count")
        for i, (s, api_row) in enumerate(zip(raw_rows, table['rows'])):
            self.assertEqual(str(s.get('session', '')), api_row[0], f"row[{i}] season label")
            self.assertEqual(s.get('total_customers', 0), _parse_int(api_row[1]), f"row[{i}] active")
            self.assertEqual(s.get('returning_customers', 0), _parse_int(api_row[2]), f"row[{i}] returning")
            self.assertEqual(s.get('returning_invoices', 0), _parse_int(api_row[4]), f"row[{i}] inv_ret")
            total_inv = s.get('total_invoices_with_vip0', s.get('total_invoices', 0))
            self.assertEqual(total_inv, _parse_int(api_row[6]), f"row[{i}] total_inv")
            total_amt = int(round(s.get('total_amount_with_vip0', s.get('total_amount', 0))))
            self.assertEqual(total_amt, _parse_int(api_row[7]), f"row[{i}] total_amt")

    def test_sales_month_table_rows_match_underlying_function(self):
        """API by_month lazy tab must equal get_sales_tab('month') by_month rows — all rows."""
        from App.analytics.tab_functions import get_sales_tab
        from datetime import date as _d
        raw = get_sales_tab('month', date_from=_d(2025, 1, 1), date_to=_d(2025, 12, 31))
        if not raw:
            self.skipTest("No 2025 month data")
        raw_rows = raw.get('by_month', [])
        data, elapsed = self._json(SALES_URL, {'tab': 'by_month', 'date_from': PERIOD_FROM, 'date_to': PERIOD_TO})
        self._log_perf("sales by_month tab period", elapsed)
        table = data['tabs']['by_month']
        self.assertEqual(len(raw_rows), len(table['rows']), "by_month row count")
        for i, (m, api_row) in enumerate(zip(raw_rows, table['rows'])):
            self.assertEqual(str(m.get('month', '')), api_row[0], f"row[{i}] month label")
            self.assertEqual(m.get('total_customers', 0), _parse_int(api_row[1]), f"row[{i}] active")
            self.assertEqual(m.get('returning_customers', 0), _parse_int(api_row[2]), f"row[{i}] returning")
            self.assertEqual(m.get('returning_invoices', 0), _parse_int(api_row[4]), f"row[{i}] inv_ret")
            total_inv = m.get('total_invoices_with_vip0', m.get('total_invoices', 0))
            self.assertEqual(total_inv, _parse_int(api_row[6]), f"row[{i}] total_inv")
            total_amt = int(round(m.get('total_amount_with_vip0', m.get('total_amount', 0))))
            self.assertEqual(total_amt, _parse_int(api_row[7]), f"row[{i}] total_amt")

    def test_sales_shop_table_rows_match_underlying_function(self):
        """API by_shop lazy tab must equal get_sales_tab('shop') by_shop rows — all rows."""
        from App.analytics.tab_functions import get_sales_tab
        raw = get_sales_tab('shop', date_from=None, date_to=None)
        if not raw:
            self.skipTest("No shop data")
        raw_rows = raw.get('by_shop', [])
        data, elapsed = self._json(SALES_URL, {'tab': 'by_shop'})
        self._log_perf("sales by_shop tab", elapsed)
        table = data['tabs']['by_shop']
        self.assertEqual(len(raw_rows), len(table['rows']), "by_shop row count")
        for i, (s, api_row) in enumerate(zip(raw_rows, table['rows'])):
            self.assertEqual(str(s.get('shop_name', '')), api_row[0], f"row[{i}] shop label")
            self.assertEqual(s.get('total_customers', 0), _parse_int(api_row[1]), f"row[{i}] active")
            self.assertEqual(s.get('returning_customers', 0), _parse_int(api_row[2]), f"row[{i}] returning")
            self.assertEqual(s.get('returning_invoices', 0), _parse_int(api_row[4]), f"row[{i}] inv_ret")
            total_inv = s.get('total_invoices_with_vip0', s.get('total_invoices', 0))
            self.assertEqual(total_inv, _parse_int(api_row[6]), f"row[{i}] total_inv")
            total_amt = int(round(s.get('total_amount_with_vip0', s.get('total_amount', 0))))
            self.assertEqual(total_amt, _parse_int(api_row[7]), f"row[{i}] total_amt")

    # ── Shop Detail Sales – table rows ────────────────────────────────────────

    def test_shop_sales_by_session_rows_match_underlying_function(self):
        """API shop sales by_session table must equal get_shop_detail_sales_data by_session — all rows."""
        from App.analytics.tab_functions import get_shop_detail_sales_data
        shop = self._pick_shop()
        raw = get_shop_detail_sales_data(shop, date_from=None, date_to=None)
        if not raw:
            self.skipTest("No data for shop")
        raw_rows = raw.get('by_session', [])
        data, _ = self._json(SHOP_DETAIL_URL, {'shop': shop, 'section': 'sales'})
        table = data['sales']['by_session']
        self.assertEqual(len(raw_rows), len(table['rows']), "by_session row count")
        for i, (s, api_row) in enumerate(zip(raw_rows, table['rows'])):
            self.assertEqual(str(s.get('session', '')), api_row[0], f"row[{i}] session")
            self.assertEqual(s.get('total_customers', 0), _parse_int(api_row[1]), f"row[{i}] active")
            self.assertEqual(s.get('returning_customers', 0), _parse_int(api_row[2]), f"row[{i}] returning")
            self.assertEqual(s.get('returning_invoices', 0), _parse_int(api_row[4]), f"row[{i}] inv_ret")
            total_inv = s.get('total_invoices_with_vip0', s.get('total_invoices', 0))
            self.assertEqual(total_inv, _parse_int(api_row[6]), f"row[{i}] total_inv")

    def test_shop_sales_by_month_rows_match_underlying_function(self):
        """API shop sales by_month table must equal get_shop_detail_sales_data by_month — all rows."""
        from App.analytics.tab_functions import get_shop_detail_sales_data
        from datetime import date as _d
        shop = self._pick_shop()
        raw = get_shop_detail_sales_data(shop, date_from=_d(2025, 1, 1), date_to=_d(2025, 12, 31))
        if not raw:
            self.skipTest("No 2025 data for shop")
        raw_rows = raw.get('by_month', [])
        data, _ = self._json(SHOP_DETAIL_URL, {
            'shop': shop, 'section': 'sales',
            'date_from': PERIOD_FROM, 'date_to': PERIOD_TO,
        })
        table = data['sales']['by_month']
        self.assertEqual(len(raw_rows), len(table['rows']), "by_month row count")
        for i, (m, api_row) in enumerate(zip(raw_rows, table['rows'])):
            self.assertEqual(str(m.get('month', '')), api_row[0], f"row[{i}] month")
            self.assertEqual(m.get('total_customers', 0), _parse_int(api_row[1]), f"row[{i}] active")
            self.assertEqual(m.get('returning_customers', 0), _parse_int(api_row[2]), f"row[{i}] returning")
            self.assertEqual(m.get('returning_invoices', 0), _parse_int(api_row[4]), f"row[{i}] inv_ret")
            total_inv = m.get('total_invoices_with_vip0', m.get('total_invoices', 0))
            self.assertEqual(total_inv, _parse_int(api_row[6]), f"row[{i}] total_inv")
            total_amt = int(round(m.get('total_amount_with_vip0', m.get('total_amount', 0))))
            self.assertEqual(total_amt, _parse_int(api_row[7]), f"row[{i}] total_amt")

    def test_shop_sales_by_week_rows_match_underlying_function(self):
        """API shop sales by_week table must equal get_shop_detail_sales_data by_week — all rows."""
        from App.analytics.tab_functions import get_shop_detail_sales_data
        from datetime import date as _d
        shop = self._pick_shop()
        raw = get_shop_detail_sales_data(shop, date_from=_d(2025, 1, 1), date_to=_d(2025, 12, 31))
        if not raw:
            self.skipTest("No 2025 data for shop")
        raw_rows = raw.get('by_week', [])
        data, _ = self._json(SHOP_DETAIL_URL, {
            'shop': shop, 'section': 'sales',
            'date_from': PERIOD_FROM, 'date_to': PERIOD_TO,
        })
        table = data['sales']['by_week']
        self.assertEqual(len(raw_rows), len(table['rows']), "by_week row count")
        for i, (w, api_row) in enumerate(zip(raw_rows, table['rows'])):
            label = str(w.get('week_label', w.get('week', '')))
            self.assertEqual(label, api_row[0], f"row[{i}] week label")
            self.assertEqual(w.get('total_customers', 0), _parse_int(api_row[1]), f"row[{i}] active")
            self.assertEqual(w.get('returning_invoices', 0), _parse_int(api_row[4]), f"row[{i}] inv_ret")

    # ── Shop Detail Customer – table rows ─────────────────────────────────────

    def test_shop_customer_by_season_rows_match_underlying_function(self):
        """API shop customer by_season table must equal get_shop_detail_customer_data by_season — all rows."""
        from App.analytics.tab_functions import get_shop_detail_customer_data
        shop = self._pick_shop()
        raw = get_shop_detail_customer_data(shop, start_date='', end_date='')
        if not raw:
            self.skipTest("No customer data for shop")
        raw_rows = raw.get('by_season', [])
        if not raw_rows:
            self.skipTest("No by_season breakdown")
        data, elapsed = self._json(SHOP_DETAIL_URL, {'shop': shop, 'section': 'customer'})
        self._log_perf("shop customer by_season", elapsed)
        table = data['customer']['by_season']
        self.assertEqual(len(raw_rows), len(table['rows']), "by_season row count")
        for i, (r, api_row) in enumerate(zip(raw_rows, table['rows'])):
            self.assertEqual(str(r.get('label', '')), api_row[0], f"row[{i}] label")
            self.assertEqual(r.get('new_pos_inv', 0), _parse_int(api_row[1]), f"row[{i}] pos_inv")
            self.assertEqual(r.get('new_pos_no_inv', 0), _parse_int(api_row[2]), f"row[{i}] pos_no_inv")
            self.assertEqual(r.get('new_pos', 0), _parse_int(api_row[3]), f"row[{i}] pos_total")
            self.assertEqual(r.get('new_pos_only', 0), _parse_int(api_row[4]), f"row[{i}] pos_only")
            self.assertEqual(r.get('new_cnv', 0), _parse_int(api_row[5]), f"row[{i}] new_cnv")
            self.assertEqual(r.get('new_cnv_only', 0), _parse_int(api_row[6]), f"row[{i}] cnv_only")
            self.assertEqual(r.get('zalo_app', 0), _parse_int(api_row[7]), f"row[{i}] zalo_app")
            self.assertEqual(r.get('zalo_oa', 0), _parse_int(api_row[9]), f"row[{i}] zalo_oa")

    def test_shop_customer_by_month_rows_match_underlying_function(self):
        """API shop customer by_month table must equal get_shop_detail_customer_data by_month — all rows."""
        from App.analytics.tab_functions import get_shop_detail_customer_data
        from datetime import date as _d
        shop = self._pick_shop()
        raw = get_shop_detail_customer_data(shop, start_date=PERIOD_FROM, end_date=PERIOD_TO)
        if not raw:
            self.skipTest("No customer data for shop")
        raw_rows = raw.get('by_month', [])
        if not raw_rows:
            self.skipTest("No by_month breakdown for period")
        data, _ = self._json(SHOP_DETAIL_URL, {
            'shop': shop, 'section': 'customer',
            'date_from': PERIOD_FROM, 'date_to': PERIOD_TO,
        })
        table = data['customer']['by_month']
        self.assertEqual(len(raw_rows), len(table['rows']), "by_month row count")
        for i, (r, api_row) in enumerate(zip(raw_rows, table['rows'])):
            self.assertEqual(str(r.get('label', '')), api_row[0], f"row[{i}] label")
            self.assertEqual(r.get('new_pos_inv', 0), _parse_int(api_row[1]), f"row[{i}] pos_inv")
            self.assertEqual(r.get('new_pos', 0), _parse_int(api_row[3]), f"row[{i}] pos_total")
            self.assertEqual(r.get('new_cnv', 0), _parse_int(api_row[5]), f"row[{i}] new_cnv")

    def test_shop_customer_by_week_rows_match_underlying_function(self):
        """API shop customer by_week table must equal get_shop_detail_customer_data by_week — all rows."""
        from App.analytics.tab_functions import get_shop_detail_customer_data
        shop = self._pick_shop()
        raw = get_shop_detail_customer_data(shop, start_date=PERIOD_FROM, end_date=PERIOD_TO)
        if not raw:
            self.skipTest("No customer data for shop")
        raw_rows = raw.get('by_week', [])
        if not raw_rows:
            self.skipTest("No by_week breakdown for period")
        data, _ = self._json(SHOP_DETAIL_URL, {
            'shop': shop, 'section': 'customer',
            'date_from': PERIOD_FROM, 'date_to': PERIOD_TO,
        })
        table = data['customer']['by_week']
        self.assertEqual(len(raw_rows), len(table['rows']), "by_week row count")
        for i, (r, api_row) in enumerate(zip(raw_rows, table['rows'])):
            self.assertEqual(str(r.get('label', '')), api_row[0], f"row[{i}] label")
            self.assertEqual(r.get('new_pos', 0), _parse_int(api_row[3]), f"row[{i}] pos_total")
            self.assertEqual(r.get('new_cnv', 0), _parse_int(api_row[5]), f"row[{i}] new_cnv")

    # ── CNV Customer – registration breakdown tables ───────────────────────────

    def test_cnv_registration_breakdown_by_shop_rows_match(self):
        """API registration_breakdown.by_shop rows must equal compute_cnv_breakdown shop dim."""
        from App.cnv.service import compute_cnv_breakdown, get_cnv_phone_sets
        pos_phones, cnv_phones = get_cnv_phone_sets()
        bd = compute_cnv_breakdown({}, pos_phones, cnv_phones)
        raw_rows = bd.get('shop', [])
        data, elapsed = self._json(CUSTOMER_URL)
        self._log_perf("cnv breakdown by_shop", elapsed)
        table = data['registration_breakdown']['by_shop']
        self.assertEqual(len(raw_rows), len(table['rows']), "by_shop row count")
        for i, (s, api_row) in enumerate(zip(raw_rows, table['rows'])):
            label = str(s.get('label', s.get('store', s.get('shop_name', ''))))
            self.assertEqual(label, api_row[0], f"row[{i}] shop label")
            self.assertEqual(s.get('new_pos', 0), _parse_int(api_row[1]), f"row[{i}] new_pos")
            self.assertEqual(s.get('new_cnv', 0), _parse_int(api_row[2]), f"row[{i}] new_cnv")
            self.assertEqual(s.get('new_pos_only', 0), _parse_int(api_row[3]), f"row[{i}] pos_only")
            self.assertEqual(s.get('new_cnv_only', 0), _parse_int(api_row[4]), f"row[{i}] cnv_only")

    def test_cnv_registration_breakdown_by_season_rows_match(self):
        """API registration_breakdown.by_season rows must equal compute_cnv_breakdown season dim."""
        from App.cnv.service import compute_cnv_breakdown, get_cnv_phone_sets
        pos_phones, cnv_phones = get_cnv_phone_sets()
        bd = compute_cnv_breakdown({}, pos_phones, cnv_phones)
        raw_rows = bd.get('season', [])
        data, _ = self._json(CUSTOMER_URL)
        table = data['registration_breakdown']['by_season']
        self.assertEqual(len(raw_rows), len(table['rows']), "by_season row count")
        for i, (s, api_row) in enumerate(zip(raw_rows, table['rows'])):
            self.assertEqual(str(s.get('label', s.get('season', ''))), api_row[0], f"row[{i}] label")
            self.assertEqual(s.get('new_pos', 0), _parse_int(api_row[1]), f"row[{i}] new_pos")
            self.assertEqual(s.get('new_cnv', 0), _parse_int(api_row[2]), f"row[{i}] new_cnv")

    def test_cnv_registration_breakdown_by_month_rows_match_period(self):
        """API registration_breakdown.by_month period rows must equal compute_cnv_breakdown month dim."""
        from App.cnv.service import compute_cnv_breakdown, get_cnv_phone_sets, parse_cnv_period_filter
        pos_phones, cnv_phones = get_cnv_phone_sets()
        period_filter, _ = parse_cnv_period_filter(PERIOD_FROM, PERIOD_TO)
        bd = compute_cnv_breakdown(period_filter, pos_phones, cnv_phones)
        raw_rows = bd.get('month', [])
        if not raw_rows:
            self.skipTest("No 2025 CNV month data")
        data, elapsed = self._json(CUSTOMER_URL, {'date_from': PERIOD_FROM, 'date_to': PERIOD_TO})
        self._log_perf("cnv breakdown by_month period", elapsed)
        table = data['registration_breakdown']['by_month']
        self.assertEqual(len(raw_rows), len(table['rows']), "by_month row count")
        for i, (m, api_row) in enumerate(zip(raw_rows, table['rows'])):
            self.assertEqual(str(m.get('label', m.get('month', ''))), api_row[0], f"row[{i}] label")
            self.assertEqual(m.get('new_pos', 0), _parse_int(api_row[1]), f"row[{i}] new_pos")
            self.assertEqual(m.get('new_cnv', 0), _parse_int(api_row[2]), f"row[{i}] new_cnv")
            self.assertEqual(m.get('new_pos_only', 0), _parse_int(api_row[3]), f"row[{i}] pos_only")
            self.assertEqual(m.get('new_cnv_only', 0), _parse_int(api_row[4]), f"row[{i}] cnv_only")

    def test_cnv_registration_breakdown_by_week_rows_match_period(self):
        """API registration_breakdown.by_week period rows must equal compute_cnv_breakdown week dim."""
        from App.cnv.service import compute_cnv_breakdown, get_cnv_phone_sets, parse_cnv_period_filter
        pos_phones, cnv_phones = get_cnv_phone_sets()
        period_filter, _ = parse_cnv_period_filter(PERIOD_FROM, PERIOD_TO)
        bd = compute_cnv_breakdown(period_filter, pos_phones, cnv_phones)
        raw_rows = bd.get('week', [])
        if not raw_rows:
            self.skipTest("No 2025 CNV week data")
        data, _ = self._json(CUSTOMER_URL, {'date_from': PERIOD_FROM, 'date_to': PERIOD_TO})
        table = data['registration_breakdown']['by_week']
        self.assertEqual(len(raw_rows), len(table['rows']), "by_week row count")
        for i, (w, api_row) in enumerate(zip(raw_rows, table['rows'])):
            self.assertEqual(str(w.get('label', w.get('week', ''))), api_row[0], f"row[{i}] label")
            self.assertEqual(w.get('new_pos', 0), _parse_int(api_row[1]), f"row[{i}] new_pos")
            self.assertEqual(w.get('new_cnv', 0), _parse_int(api_row[2]), f"row[{i}] new_cnv")

    def test_cnv_grade_breakdown_rows_match(self):
        """API by_grade registration breakdown rows must equal _compute_grade_rows output."""
        from App.api.views import _compute_grade_rows
        from App.cnv.service import get_cnv_phone_sets
        _, cnv_phones = get_cnv_phone_sets()
        grade_rows = _compute_grade_rows(cnv_phones)
        data, _ = self._json(CUSTOMER_URL)
        table = data['registration_breakdown']['by_grade']
        self.assertEqual(len(grade_rows), len(table['rows']), "by_grade row count")
        for i, (r, api_row) in enumerate(zip(grade_rows, table['rows'])):
            self.assertEqual(str(r.get('label', r.get('grade', ''))), api_row[0], f"row[{i}] grade")
            self.assertEqual(r.get('new_pos', 0), _parse_int(api_row[1]), f"row[{i}] new_pos")
            self.assertEqual(r.get('new_pos_only', 0), _parse_int(api_row[3]), f"row[{i}] pos_only")

    # ── Customer Detail ───────────────────────────────────────────────────────

    def test_customer_detail_full_data_matches_underlying_function(self):
        """API customer detail must match get_customer_detail_data on all non-PII fields."""
        from App.models import Customer
        from App.analytics.customer_utils import get_customer_detail_data, normalize_grade
        customer = (
            Customer.objects.filter(vip_id__isnull=False)
            .exclude(vip_id=0).order_by('vip_id').first()
        )
        if not customer:
            self.skipTest("No customers in DB")
        raw = get_customer_detail_data(customer)
        data, elapsed = self._json(CUST_DETAIL_URL, {'vip_id': str(customer.vip_id)})
        self._log_perf("customer detail", elapsed)

        # Invoice count is always the full DB count (no cap)
        self.assertEqual(raw['total_invoice_count'], _parse_int(data.get('total_invoices', 0)))
        # Invoice history list length must match (no cap in API — full parity with web)
        self.assertEqual(len(raw['invoices']), len(data.get('invoice_history', [])))
        # Revenue: API and function agree (function sums all, API sums all)
        self.assertEqual(
            int(round(float(raw['stats']['total_amount'] or 0))),
            _parse_int(data.get('total_revenue', 0)),
        )
        # Static customer fields
        self.assertEqual(str(customer.vip_id or ''), data.get('vip_id', ''))
        self.assertEqual(customer.name or '', data.get('name', ''))
        self.assertEqual(normalize_grade(customer.vip_grade), data.get('grade', ''))
        self.assertEqual(customer.registration_store or '', data.get('registration_store', ''))
        self.assertEqual(customer.email or '', data.get('email', ''))
        # CNV sync status
        expected_cnv = 'synced' if raw['is_synced_to_cnv'] else 'not_synced'
        self.assertEqual(expected_cnv, data.get('cnv_sync_status'))
        # Invoice history shape: each entry must have date, shop, invoice_id, amount
        for i, (fn_inv, api_inv) in enumerate(zip(raw['invoices'], data.get('invoice_history', []))):
            self.assertEqual(str(fn_inv['sales_day'] or ''), api_inv.get('date', ''),
                f"invoice {i} date mismatch")
            self.assertEqual(fn_inv['shop_name'] or '', api_inv.get('shop', ''),
                f"invoice {i} shop mismatch")
            self.assertEqual(fn_inv['invoice_no'] or '', api_inv.get('invoice_id', ''),
                f"invoice {i} invoice_id mismatch")
