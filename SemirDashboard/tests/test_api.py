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

from tests.base import SnapshotTestCase, INPUT_DIR, get_run_log

# ── URL constants ──────────────────────────────────────────────────────────────

SALES_URL       = '/api/v1/analytics/sales/'
CUSTOMER_URL    = '/api/v1/analytics/customer/'
COUPON_URL      = '/api/v1/analytics/coupon/'
SHOPS_URL       = '/api/v1/analytics/shops/'
SHOP_DETAIL_URL = '/api/v1/analytics/shop-detail/'
CUST_DETAIL_URL = '/api/v1/analytics/customer-detail/'
LOGIN_URL       = '/api/v1/auth/token/'

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
        for tbl_key in ('pos_only', 'cnv_only', 'both'):
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
        from App.models import SalesTransaction
        shop = (
            SalesTransaction.objects
            .exclude(shop_name='').exclude(shop_name__isnull=True)
            .values_list('shop_name', flat=True)
            .order_by('shop_name')
            .first()
        )
        return shop

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
        for key in ('vip_id', 'phone', 'grade', 'total_invoices', 'total_revenue'):
            self.assertIn(key, data, f"customer-detail missing: {key}")

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
