"""
tests/test_sale_detail.py — SaleDetail import + product analytics tests.

Tests:
  1. SaleDetail import: row count, upsert, no UNIQUE errors
  2. get_product_tab() returns correct structure for all tabs
  3. New tabs: sales_season, vip_grade, brand, year; cat_groups + top_products in period rows
  4. shop_name filter for get_product_tab()
  5. Product dashboard + all AJAX tab endpoints return 200
  6. shop_detail product partial endpoint returns 200

Run:
  cd SemirDashboard && python manage.py test tests.test_sale_detail -v 2
"""
import io
from django.contrib.auth.models import User
from django.urls import reverse

from App.models import SaleDetail
from App.services import process_sale_detail_file
from App.analytics.product_analytics import get_product_tab, PRODUCT_TABS

from tests.base import SnapshotTestCase, INPUT_DIR, Timer


class _NamedBytesIO(io.BytesIO):
    pass


def _open(path):
    with open(path, "rb") as f:
        data = f.read()
    obj = _NamedBytesIO(data)
    obj.name = path.name
    return obj


class SaleDetailImportTest(SnapshotTestCase):
    """Import sale detail.xlsx and verify DB state + no UNIQUE errors."""

    @classmethod
    def setUpTestData(cls):
        cls.superuser = User.objects.create_superuser(
            username="saledettest", password="testpass", email="saledet@test.com"
        )
        sd_file = INPUT_DIR / "sale detail.xlsx"
        if not sd_file.exists():
            cls._skip = True
            return
        cls._skip = False
        t = Timer("sale_detail_import")
        result = process_sale_detail_file(_open(sd_file))
        t.checkpoint("import done")
        t.report()
        cls.import_result = result

    def setUp(self):
        if getattr(self, '_skip', False):
            self.skipTest("tests/input/sale detail.xlsx not found")
        self.client.force_login(self.superuser)

    # ── Import ────────────────────────────────────────────────────────────────

    def test_import_no_errors(self):
        self.assertEqual(self.import_result['errors'], [],
                         f"Unexpected errors: {self.import_result['errors'][:5]}")

    def test_import_created_rows(self):
        total = self.import_result['created'] + self.import_result['updated']
        self.assertGreater(total, 0, "No rows imported")

    def test_db_count_matches_import(self):
        db_count = SaleDetail.objects.count()
        expected = self.import_result['created'] + self.import_result['updated']
        self.assertEqual(db_count, expected)

    def test_upsert_idempotent(self):
        sd_file = INPUT_DIR / "sale detail.xlsx"
        before = SaleDetail.objects.count()
        result2 = process_sale_detail_file(_open(sd_file))
        after = SaleDetail.objects.count()
        self.assertEqual(before, after, "Row count changed on re-import (upsert broken)")
        self.assertEqual(result2['errors'], [], f"Errors on re-import: {result2['errors'][:5]}")
        self.assertEqual(result2['created'], 0, "Expected 0 creates on re-import")

    def test_snapshot_db_shape(self):
        from django.db.models import Count, Sum, Min, Max
        stats = SaleDetail.objects.aggregate(
            total=Count('id'),
            min_date=Min('sales_date'),
            max_date=Max('sales_date'),
            total_qty=Sum('quantity'),
            total_amount=Sum('sales_amount'),
            total_settlement=Sum('settlement_amount'),
            total_tag=Sum('tag_amount'),
        )
        brands = list(
            SaleDetail.objects.values_list('brand', flat=True)
            .order_by('brand').distinct()
        )
        self.assert_snapshot("api_sale_detail_shape", {
            "total": stats['total'],
            "min_date": str(stats['min_date']) if stats['min_date'] else None,
            "max_date": str(stats['max_date']) if stats['max_date'] else None,
            "total_qty": int(stats['total_qty'] or 0),
            "total_amount": float(stats['total_amount'] or 0),
            "total_settlement": float(stats['total_settlement'] or 0),
            "total_tag": float(stats['total_tag'] or 0),
            "brands": brands,
        })

    def test_imported_fields_stored_correctly(self):
        obj = SaleDetail.objects.exclude(invoice_number='').first()
        self.assertIsNotNone(obj, "No rows in SaleDetail after import")
        self.assertTrue(obj.invoice_number, "invoice_number empty")
        self.assertIsNotNone(obj.sales_date, "sales_date is None")
        self.assertGreaterEqual(obj.quantity, 0)
        self.assertGreaterEqual(float(obj.sales_amount), 0)

    # ── Core tab structure ────────────────────────────────────────────────────

    def test_product_tab_month(self):
        data = get_product_tab('month')
        self.assertIn('by_month', data)
        rows = data['by_month']
        self.assertIsInstance(rows, list)
        self.assertGreater(len(rows), 0)
        row = rows[0]
        for field in ('label', 'qty', 'amount', 'lines', 'cat_groups', 'top_products'):
            self.assertIn(field, row, f"Missing by_month field '{field}'")
        self.assertRegex(row['label'], r'^\d{4}-\d{2}$', f"label format wrong: {row['label']!r}")
        self.assertIsInstance(row['cat_groups'], list)
        self.assertIsInstance(row['top_products'], list)

    def test_product_tab_year(self):
        data = get_product_tab('year')
        self.assertIn('by_year', data)
        rows = data['by_year']
        self.assertIsInstance(rows, list)
        self.assertGreater(len(rows), 0)
        row = rows[0]
        for field in ('label', 'qty', 'amount', 'lines', 'cat_groups', 'top_products'):
            self.assertIn(field, row, f"Missing by_year field '{field}'")

    def test_product_tab_week(self):
        data = get_product_tab('week')
        self.assertIn('by_week', data)
        rows = data['by_week']
        self.assertIsInstance(rows, list)
        if rows:
            row = rows[0]
            for field in ('label', 'qty', 'amount', 'lines', 'cat_groups', 'top_products'):
                self.assertIn(field, row, f"Missing by_week field '{field}'")
            self.assertRegex(row['label'], r'^W\d{1,2} \d{4}$', f"label format wrong: {row['label']!r}")

    def test_product_tab_sales_season(self):
        """New tab: By Sales Season (M2-4/M5-7/M8-10/M11-1 from sales_date)."""
        data = get_product_tab('sales_season')
        self.assertIn('by_sales_season', data)
        rows = data['by_sales_season']
        self.assertIsInstance(rows, list)
        self.assertGreater(len(rows), 0, "No sales_season rows returned")
        row = rows[0]
        for field in ('label', 'qty', 'amount', 'lines', 'cat_groups', 'top_products'):
            self.assertIn(field, row, f"Missing by_sales_season field '{field}'")
        # Label must match "M2-4 2024", "M5-7 2025", or "M11-1 2024-2025"
        import re
        for r in rows:
            lbl = r.get('label', '')
            self.assertRegex(lbl, r'^M(2-4|5-7|8-10|11-1) \d{4}(-\d{4})?$',
                             f"Unexpected sales_season label: {lbl!r}")

    def test_product_tab_product_season(self):
        """By Product Season (product design year/season)."""
        data = get_product_tab('product_season')
        self.assertIn('by_product_season', data)
        rows = data['by_product_season']
        self.assertIsInstance(rows, list)
        self.assertGreater(len(rows), 0, "No product_season rows returned")
        row = rows[0]
        for field in ('label', 'qty', 'amount', 'lines', 'cat_groups', 'top_products'):
            self.assertIn(field, row, f"Missing by_product_season field '{field}'")

    def test_product_tab_vip_grade(self):
        """By VIP Grade (joined via SaleDetail → SalesTransaction → Customer)."""
        data = get_product_tab('vip_grade')
        self.assertIn('by_vip_grade', data)
        rows = data['by_vip_grade']
        self.assertIsInstance(rows, list)
        for row in rows:
            self.assertIn('grade', row)
            self.assertIn('cat_groups', row)
            self.assertIn('top_products', row)

    def test_product_tab_brand(self):
        """By Brand — each brand row includes cat_groups + top_products."""
        data = get_product_tab('brand')
        self.assertIn('by_brand', data)
        rows = data['by_brand']
        self.assertIsInstance(rows, list)
        self.assertGreater(len(rows), 0, "No brand rows")
        row = rows[0]
        for field in ('brand', 'qty', 'amount', 'lines', 'cat_groups', 'top_products'):
            self.assertIn(field, row, f"Missing by_brand field '{field}'")

    def test_product_tab_category(self):
        data = get_product_tab('category')
        self.assertIn('by_category', data)
        rows = data['by_category']
        self.assertIsInstance(rows, list)
        if rows:
            grp = rows[0]
            for field in ('l1', 'rows', 'subtotal'):
                self.assertIn(field, grp, f"Missing by_category cat_groups field '{field}'")
            if grp['rows']:
                row = grp['rows'][0]
                for field in ('category_l1', 'category_l2', 'qty', 'amount', 'lines'):
                    self.assertIn(field, row, f"Missing by_category L2 row field '{field}'")

    def test_product_tab_shop(self):
        data = get_product_tab('shop')
        self.assertIn('by_shop', data)
        rows = data['by_shop']
        self.assertGreater(len(rows), 0)
        row = rows[0]
        for field in ('shop_name', 'qty', 'amount', 'lines', 'disc_pct'):
            self.assertIn(field, row, f"Missing by_shop field '{field}'")

    def test_shop_full_has_all_sub_tabs(self):
        """Each shop row in by_shop must include all 9 sub-tab data keys."""
        data = get_product_tab('shop')
        rows = data.get('by_shop', [])
        self.assertGreater(len(rows), 0)
        row = rows[0]
        for key in ('by_month', 'by_year', 'by_week', 'by_sales_season',
                    'by_product_season', 'by_vip_grade', 'by_brand',
                    'by_category', 'top_products'):
            self.assertIn(key, row, f"Missing shop sub-tab key '{key}'")
        # by_category for shop is already processed as cat_groups (list of dicts with 'l1')
        if row['by_category']:
            cg = row['by_category'][0]
            self.assertIn('l1', cg, "by_category should be cat_groups format (has 'l1' key)")

    def test_shop_name_filter(self):
        """get_product_tab with shop_name returns data for that shop only."""
        shops = list(SaleDetail.objects.exclude(shop_name='')
                     .values_list('shop_name', flat=True).order_by().distinct()[:2])
        if len(shops) < 2:
            self.skipTest("Need at least 2 shops in test data")
        data1 = get_product_tab('month', shop_name=shops[0])
        data2 = get_product_tab('month', shop_name=shops[1])
        full  = get_product_tab('month')
        qty1 = data1['overview'].get('total_qty') or 0
        qty2 = data2['overview'].get('total_qty') or 0
        qty_full = full['overview'].get('total_qty') or 0
        self.assertGreater(qty_full, max(qty1, qty2),
                           "Full data should have more qty than any single shop")
        # Numbers per shop must not exceed total
        self.assertLessEqual(qty1, qty_full)
        self.assertLessEqual(qty2, qty_full)

    def test_overview_totals_positive(self):
        data = get_product_tab('month')
        overview = data['overview']
        self.assertGreater(overview['total_qty'], 0)
        self.assertGreater(float(overview['total_amount'] or 0), 0)
        self.assertIn('date_range', overview)
        self.assertIsNotNone(overview['date_range']['from'])

    def test_product_tab_with_shop_group_filter(self):
        full = get_product_tab('shop')
        filtered = get_product_tab('shop', shop_group='Semir Group')
        if not filtered or not filtered.get('by_shop'):
            self.skipTest("No Semir group data in test DB")
        semir_rows = filtered.get('by_shop', [])
        full_qty = sum(r['qty'] for r in full.get('by_shop', []))
        filtered_qty = sum(r['qty'] for r in semir_rows)
        self.assertLessEqual(filtered_qty, full_qty)
        for r in semir_rows:
            name = r['shop_name'].lower()
            self.assertTrue(
                'semir' in name or '森马' in name,
                f"shop_group filter returned non-Semir shop: {r['shop_name']}"
            )

    # ── Snapshots ────────────────────────────────────────────────────────────

    def test_snapshot_product_season(self):
        data = get_product_tab('product_season')
        overview = data.get('overview', {})
        self.assert_snapshot("product_season", {
            "overview": {
                "total_lines": overview.get('total_lines'),
                "total_qty": int(overview.get('total_qty') or 0),
                "total_amount": float(overview.get('total_amount') or 0),
                "total_settlement": float(overview.get('total_settlement') or 0),
                "disc_pct": overview.get('disc_pct'),
            },
            "by_product_season": [
                {
                    "label": r.get('label'),
                    "qty": int(r.get('qty') or 0),
                    "amount": float(r.get('amount') or 0),
                    "settlement": float(r.get('settlement') or 0),
                    "disc_pct": r.get('disc_pct'),
                    "lines": r.get('lines'),
                    "has_cat_groups": bool(r.get('cat_groups')),
                    "has_top_products": bool(r.get('top_products')),
                }
                for r in data.get('by_product_season', [])
            ],
        })

    def test_snapshot_sales_season(self):
        data = get_product_tab('sales_season')
        overview = data.get('overview', {})
        self.assert_snapshot("sales_season", {
            "overview": {
                "total_lines": overview.get('total_lines'),
                "total_qty": int(overview.get('total_qty') or 0),
            },
            "by_sales_season": [
                {
                    "label": r.get('label'),
                    "qty": int(r.get('qty') or 0),
                    "disc_pct": r.get('disc_pct'),
                    "has_cat_groups": bool(r.get('cat_groups')),
                    "has_top_products": bool(r.get('top_products')),
                }
                for r in data.get('by_sales_season', [])
            ],
        })

    def test_snapshot_product_category(self):
        data = get_product_tab('category')
        cat_groups = data.get('by_category', [])
        all_l2 = [r for grp in cat_groups for r in grp.get('rows', [])]
        self.assert_snapshot("product_category", {
            "l1_count": len(cat_groups),
            "l2_count": len(all_l2),
            "l1_categories": sorted(grp.get('l1', '') for grp in cat_groups),
            "by_category": [
                {
                    "l1": grp.get('l1'),
                    "l2_count": len(grp.get('rows', [])),
                    "subtotal_qty": int((grp.get('subtotal') or {}).get('qty') or 0),
                    "subtotal_amount": float((grp.get('subtotal') or {}).get('amount') or 0),
                }
                for grp in cat_groups
            ],
        })

    def test_snapshot_product_shop(self):
        data = get_product_tab('shop')
        self.assert_snapshot("product_shop", {
            "shop_count": len(data.get('by_shop', [])),
            "by_shop": [
                {
                    "shop_name": r.get('shop_name'),
                    "qty": int(r.get('qty') or 0),
                    "amount": float(r.get('amount') or 0),
                    "disc_pct": r.get('disc_pct'),
                    "lines": r.get('lines'),
                    "sub_tab_keys": sorted(k for k in r if k.startswith('by_') or k == 'top_products'),
                }
                for r in data.get('by_shop', [])
            ],
        })

    # ── Page renders ──────────────────────────────────────────────────────────

    def test_product_dashboard_200(self):
        t = self.timer("product_dashboard")
        r = self.client.get(reverse("product_dashboard"), follow=True)
        t.checkpoint("GET /products/")
        t.report()
        self.assertEqual(r.status_code, 200)

    def test_product_all_tabs_200(self):
        """All AJAX tab endpoints must return 200."""
        for tab in PRODUCT_TABS:
            r = self.client.get(
                reverse("product_tab", kwargs={"tab": tab}),
                HTTP_X_REQUESTED_WITH="XMLHttpRequest",
            )
            self.assertEqual(r.status_code, 200, f"Tab '{tab}' returned {r.status_code}")

    def test_product_tab_with_shop_name_param_200(self):
        """product_tab endpoint with shop_name GET param must return 200."""
        shop = SaleDetail.objects.exclude(shop_name='').values_list('shop_name', flat=True).first()
        if not shop:
            self.skipTest("No SaleDetail rows in test DB")
        r = self.client.get(
            reverse("product_tab", kwargs={"tab": "month"}) + f"?shop_name={shop}",
            HTTP_X_REQUESTED_WITH="XMLHttpRequest",
        )
        self.assertEqual(r.status_code, 200)

    def test_product_dashboard_with_filter_200(self):
        r = self.client.get(
            reverse("product_dashboard") + "?start_date=2025-01-01&end_date=2025-12-31",
            follow=True,
        )
        self.assertEqual(r.status_code, 200)

    def test_shop_detail_product_partial_200(self):
        """shop_detail product partial endpoint must return 200 for a valid shop."""
        shop = SaleDetail.objects.exclude(shop_name='').values_list('shop_name', flat=True).first()
        if not shop:
            self.skipTest("No SaleDetail rows in test DB")
        r = self.client.get(
            reverse("shop_detail_product_partial") + f"?shop={shop}",
            HTTP_X_REQUESTED_WITH="XMLHttpRequest",
        )
        self.assertEqual(r.status_code, 200, f"product partial returned {r.status_code}")

    def test_shop_detail_product_partial_no_shop_returns_prompt(self):
        """Without shop param, partial returns 200 with a 'select a shop' message."""
        r = self.client.get(
            reverse("shop_detail_product_partial"),
            HTTP_X_REQUESTED_WITH="XMLHttpRequest",
        )
        self.assertEqual(r.status_code, 200)
        self.assertIn(b"Select a shop", r.content)

    def test_shop_detail_page_200(self):
        """shop_detail main page should still return 200 after adding product section."""
        r = self.client.get(reverse("shop_detail"), follow=True)
        self.assertEqual(r.status_code, 200)
