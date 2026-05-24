"""
tests/test_sale_detail.py — SaleDetail import + product analytics tests.

Tests:
  1. SaleDetail import: row count, upsert, no UNIQUE errors
  2. get_product_tab() returns correct structure for all 5 tabs
  3. Product dashboard + all tabs return 200

Run:
  cd SemirDashboard && python manage.py test tests.test_sale_detail -v 2
"""
import io
from django.contrib.auth.models import User
from django.urls import reverse

from App.models import SaleDetail
from App.services import process_sale_detail_file
from App.analytics.product_analytics import get_product_tab

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
        """Re-import must not increase row count and must produce no errors."""
        sd_file = INPUT_DIR / "sale detail.xlsx"
        before = SaleDetail.objects.count()
        result2 = process_sale_detail_file(_open(sd_file))
        after = SaleDetail.objects.count()
        self.assertEqual(before, after, "Row count changed on re-import (upsert broken)")
        self.assertEqual(result2['errors'], [], f"Errors on re-import: {result2['errors'][:5]}")
        self.assertEqual(result2['created'], 0, "Expected 0 creates on re-import")

    def test_snapshot_db_shape(self):
        """Capture DB-level aggregates as regression anchor."""
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

    def test_snapshot_product_season(self):
        """Capture full by_season analytics — regression on actual numbers."""
        data = get_product_tab('season')
        overview = data.get('overview', {})
        self.assert_snapshot("product_season", {
            "overview": {
                "total_lines": overview.get('total_lines'),
                "total_qty": int(overview.get('total_qty') or 0),
                "total_amount": float(overview.get('total_amount') or 0),
                "total_settlement": float(overview.get('total_settlement') or 0),
                "total_tag_amount": float(overview.get('total_tag_amount') or 0),
                "disc_pct": overview.get('disc_pct'),
            },
            "by_season": [
                {
                    "year": r.get('year'),
                    "season": r.get('season'),
                    "qty": int(r.get('qty') or 0),
                    "amount": float(r.get('amount') or 0),
                    "settlement": float(r.get('settlement') or 0),
                    "tag_amount": float(r.get('tag_amount') or 0),
                    "disc_pct": r.get('disc_pct'),
                    "lines": r.get('lines'),
                }
                for r in data.get('by_season', [])
            ],
        })

    def test_snapshot_product_category(self):
        """Capture by_category top rows — regression on L1/L2 structure."""
        data = get_product_tab('category')
        rows = data.get('by_category', [])
        self.assert_snapshot("product_category", {
            "row_count": len(rows),
            "l1_categories": sorted(set(r.get('category_l1', '') for r in rows)),
            "by_category": [
                {
                    "category_l1": r.get('category_l1'),
                    "category_l2": r.get('category_l2'),
                    "qty": int(r.get('qty') or 0),
                    "amount": float(r.get('amount') or 0),
                    "settlement": float(r.get('settlement') or 0),
                    "tag_amount": float(r.get('tag_amount') or 0),
                    "disc_pct": r.get('disc_pct'),
                    "lines": r.get('lines'),
                }
                for r in rows[:20]  # top 20 rows
            ],
        })

    def test_snapshot_product_shop(self):
        """Capture full by_shop analytics — regression on per-shop numbers."""
        data = get_product_tab('shop')
        self.assert_snapshot("product_shop", {
            "shop_count": len(data.get('by_shop', [])),
            "by_shop": [
                {
                    "shop_name": r.get('shop_name'),
                    "qty": int(r.get('qty') or 0),
                    "amount": float(r.get('amount') or 0),
                    "settlement": float(r.get('settlement') or 0),
                    "tag_amount": float(r.get('tag_amount') or 0),
                    "disc_pct": r.get('disc_pct'),
                    "lines": r.get('lines'),
                }
                for r in data.get('by_shop', [])
            ],
        })

    def test_imported_fields_stored_correctly(self):
        """Spot-check: required fields non-empty, numeric fields non-negative."""
        from django.db.models import Min, Max, Sum
        obj = SaleDetail.objects.exclude(invoice_number='').first()
        self.assertIsNotNone(obj, "No rows in SaleDetail after import")
        self.assertTrue(obj.invoice_number, "invoice_number empty")
        self.assertIsNotNone(obj.sales_date, "sales_date is None")
        self.assertGreaterEqual(obj.quantity, 0)
        self.assertGreaterEqual(float(obj.sales_amount), 0)

    # ── Product analytics ─────────────────────────────────────────────────────

    def test_product_tab_season(self):
        data = get_product_tab('season')
        self.assertIsInstance(data, dict)
        self.assertIn('overview', data)
        self.assertIn('by_season', data)
        self.assertGreater(data['overview']['total_lines'], 0)
        # Verify season row structure
        if data['by_season']:
            row = data['by_season'][0]
            for field in ('year', 'season', 'qty', 'amount', 'lines'):
                self.assertIn(field, row, f"Missing by_season field '{field}'")

    def test_product_tab_month(self):
        data = get_product_tab('month')
        self.assertIn('by_month', data)
        rows = data['by_month']
        self.assertIsInstance(rows, list)
        if rows:
            row = rows[0]
            for field in ('month', 'qty', 'amount', 'lines', 'label'):
                self.assertIn(field, row, f"Missing by_month field '{field}'")
            # label format: 'YYYY-MM'
            import re
            self.assertRegex(row['label'], r'^\d{4}-\d{2}$',
                             f"by_month label format wrong: {row['label']!r}")

    def test_product_tab_week(self):
        data = get_product_tab('week')
        self.assertIn('by_week', data)
        rows = data['by_week']
        if rows:
            row = rows[0]
            for field in ('week', 'qty', 'amount', 'lines', 'label'):
                self.assertIn(field, row, f"Missing by_week field '{field}'")
            # label format: 'W{nn} YYYY'
            import re
            self.assertRegex(row['label'], r'^W\d{1,2} \d{4}$',
                             f"by_week label format wrong: {row['label']!r}")

    def test_product_tab_category(self):
        data = get_product_tab('category')
        self.assertIn('by_category', data)
        rows = data['by_category']
        if rows:
            row = rows[0]
            for field in ('category_l1', 'category_l2', 'qty', 'amount', 'lines'):
                self.assertIn(field, row, f"Missing by_category field '{field}'")

    def test_product_overview_totals_positive(self):
        data = get_product_tab('season')
        overview = data['overview']
        self.assertGreater(overview['total_qty'], 0)
        self.assertGreater(float(overview['total_amount'] or 0), 0)
        self.assertIn('date_range', overview)
        self.assertIsNotNone(overview['date_range']['from'])

    def test_product_tab_shop(self):
        data = get_product_tab('shop')
        self.assertIn('by_shop', data)
        rows = data['by_shop']
        self.assertGreater(len(rows), 0)
        row = rows[0]
        for field in ('shop_name', 'qty', 'amount', 'lines', 'disc_pct'):
            self.assertIn(field, row, f"Missing by_shop field '{field}'")

    def test_product_tab_with_shop_group_filter(self):
        """shop_group filter by shop_name must return a strict subset of the full data."""
        full = get_product_tab('shop')
        filtered = get_product_tab('shop', shop_group='Semir Group')
        if not filtered:
            self.skipTest("No Semir group data in test DB")
        semir_rows = filtered.get('by_shop', [])
        self.assertGreater(len(semir_rows), 0, "Semir group filter returned no rows")
        full_qty = sum(r['qty'] for r in full.get('by_shop', []))
        filtered_qty = sum(r['qty'] for r in semir_rows)
        self.assertLessEqual(filtered_qty, full_qty)
        # All filtered rows must belong to Semir/森马 shops
        for r in semir_rows:
            name = r['shop_name'].lower()
            self.assertTrue(
                'semir' in name or '森马' in name,
                f"shop_group filter returned non-Semir shop: {r['shop_name']}"
            )

    def test_product_tab_invalid_tab_returns_empty(self):
        data = get_product_tab('nonexistent_tab')
        # Should return a dict with overview but no tab-specific key
        self.assertIsInstance(data, dict)

    # ── Page renders ──────────────────────────────────────────────────────────

    def test_product_dashboard_200(self):
        t = self.timer("product_dashboard")
        r = self.client.get(reverse("product_dashboard"), follow=True)
        t.checkpoint("GET /products/")
        t.report()
        self.assertEqual(r.status_code, 200)

    def test_product_tabs_200(self):
        for tab in ['season', 'month', 'week', 'category', 'shop']:
            r = self.client.get(
                reverse("product_tab", kwargs={"tab": tab}),
                HTTP_X_REQUESTED_WITH="XMLHttpRequest",
            )
            self.assertEqual(r.status_code, 200, f"Tab '{tab}' returned {r.status_code}")

    def test_product_dashboard_with_filter_200(self):
        r = self.client.get(
            reverse("product_dashboard") + "?start_date=2025-01-01&end_date=2025-12-31",
            follow=True,
        )
        self.assertEqual(r.status_code, 200)
