"""
tests/test_inventory.py — Inventory import service + analytics tests.

Tests:
  1. Inventory file import: row count, upsert behaviour
  2. InventorySnapshot DB state after import
  3. get_shop_inventory_data() returns correct structure
  4. get_inventory_overview() — dead stock fields, top 50, year/season filter
  5. gender_name template filter
  6. /inventory/ dashboard renders 200 (with/without filters)
  7. /shop-detail/partial/inventory/ AJAX partial renders 200

Run:
  cd SemirDashboard && python manage.py test tests.test_inventory -v 2
"""
import io
from django.contrib.auth.models import User
from django.db.models import Count, Sum
from django.urls import reverse
from django.template import Context, Template

from App.models import InventorySnapshot
from App.services import process_inventory_file
from App.analytics.inventory_functions import get_shop_inventory_data, get_inventory_overview

from tests.base import SnapshotTestCase, INPUT_DIR, Timer


class _NamedBytesIO(io.BytesIO):
    pass


def _open(path):
    with open(path, "rb") as f:
        data = f.read()
    obj = _NamedBytesIO(data)
    obj.name = path.name
    return obj


class InventoryImportTest(SnapshotTestCase):
    """Import inventory.xlsx and verify DB state + analytics output."""

    @classmethod
    def setUpTestData(cls):
        cls.superuser = User.objects.create_superuser(
            username="invtest", password="testpass", email="inv@test.com"
        )
        inv_file = INPUT_DIR / "inventory.xlsx"
        if not inv_file.exists():
            cls._skip = True
            return
        cls._skip = False
        t = Timer("inventory_import")
        result = process_inventory_file(_open(inv_file))
        t.checkpoint("import done")
        t.report()
        cls.import_result = result

    def setUp(self):
        if getattr(self, '_skip', False):
            self.skipTest("tests/input/inventory.xlsx not found")
        self.client.force_login(self.superuser)

    # ── Import result ─────────────────────────────────────────────────────────

    def test_import_no_errors(self):
        self.assertEqual(self.import_result['errors'], [],
                         f"Expected no errors, got: {self.import_result['errors'][:5]}")

    def test_import_created_rows(self):
        total = self.import_result['created'] + self.import_result['updated']
        self.assertGreater(total, 0, "No rows imported")

    def test_db_row_count_matches_import(self):
        db_count = InventorySnapshot.objects.count()
        expected = self.import_result['created'] + self.import_result['updated']
        self.assertEqual(db_count, expected)

    def test_upsert_idempotent(self):
        """Re-importing same file must not increase row count."""
        inv_file = INPUT_DIR / "inventory.xlsx"
        before = InventorySnapshot.objects.count()
        result2 = process_inventory_file(_open(inv_file))
        after = InventorySnapshot.objects.count()
        self.assertEqual(before, after, "Row count changed on re-import (upsert broken)")
        self.assertEqual(result2['created'], 0, "Expected 0 created on re-import")

    def test_snapshot_db_shape(self):
        """Capture DB-level aggregates — regression anchor on imported data."""
        from django.db.models import Sum
        stats = InventorySnapshot.objects.aggregate(
            total_rows=Count('id'),
            total_on_hand=Sum('inventory_qty'),
            total_in_transit=Sum('in_transit_qty'),
            total_qty=Sum('total_qty'),
            total_value=Sum('tag_amount'),
        )
        self.assert_snapshot("api_inventory_shape", {
            "total_rows": stats['total_rows'],
            "total_on_hand": int(stats['total_on_hand'] or 0),
            "total_in_transit": int(stats['total_in_transit'] or 0),
            "total_qty": int(stats['total_qty'] or 0),
            "total_value": float(stats['total_value'] or 0),
            "shops": list(
                InventorySnapshot.objects
                .values_list('shop_name', flat=True)
                .order_by('shop_name').distinct()
            ),
        })

    def test_snapshot_inventory_analytics(self):
        """Capture actual analytics for the first shop — regression on KPIs and breakdown."""
        shop = self._first_shop()
        if not shop:
            self.skipTest("No shops in inventory DB")
        data = get_shop_inventory_data(shop)
        totals = data.get('totals', {})
        self.assert_snapshot("inventory_shop_analytics", {
            "shop": shop,
            "totals": {
                "sku_lines":      totals.get('sku_lines'),
                "on_hand_qty":    int(totals.get('on_hand_qty') or 0),
                "in_transit_qty": int(totals.get('in_transit_qty') or 0),
                "total_qty":      int(totals.get('total_qty') or 0),
                "inv_value":      float(totals.get('inv_value') or 0),
                "total_tag_amt":  float(totals.get('total_tag_amt') or 0),
            },
            "by_brand": [
                {
                    "brand":      r.get('brand'),
                    "qty":        int(r.get('qty') or 0),
                    "in_transit": int(r.get('in_transit') or 0),
                    "total":      int(r.get('total') or 0),
                    "value":      float(r.get('value') or 0),
                    "lines":      r.get('lines'),
                }
                for r in data.get('by_brand', [])
            ],
            "dead_sku_lines": data.get('dead', {}).get('sku_lines', 0),
            "top_skus_count": len(data.get('top_skus', [])),
        })

    # ── Analytics ─────────────────────────────────────────────────────────────

    def test_imported_fields_stored_correctly(self):
        """Spot-check a real row: required fields non-empty, numeric fields non-negative."""
        obj = InventorySnapshot.objects.exclude(shop_id='').exclude(product_code='').first()
        self.assertIsNotNone(obj, "No rows in InventorySnapshot after import")
        self.assertTrue(obj.shop_id, "shop_id empty")
        self.assertTrue(obj.product_code, "product_code empty")
        self.assertGreaterEqual(obj.inventory_qty, 0)
        self.assertGreaterEqual(obj.total_qty, 0)
        self.assertGreaterEqual(float(obj.tag_amount), 0)

    # ── Analytics ─────────────────────────────────────────────────────────────

    @classmethod
    def _first_shop(cls):
        return InventorySnapshot.objects.order_by('shop_name').values_list('shop_name', flat=True).first()

    def test_get_shop_inventory_data_returns_dict(self):
        shop = self._first_shop()
        if not shop:
            self.skipTest("No shops in inventory DB")
        data = get_shop_inventory_data(shop)
        self.assertIsInstance(data, dict)
        for key in ('totals', 'by_brand', 'by_season', 'top_skus', 'dead'):
            self.assertIn(key, data, f"Missing key '{key}' in analytics output")

    def test_shop_inventory_totals_keys(self):
        shop = self._first_shop()
        if not shop:
            self.skipTest("No shops in inventory DB")
        data = get_shop_inventory_data(shop)
        totals = data['totals']
        # Keys match inventory_functions.py aggregate aliases
        for field in ('sku_lines', 'on_hand_qty', 'in_transit_qty', 'total_qty', 'inv_value', 'total_tag_amt'):
            self.assertIn(field, totals, f"Missing totals field '{field}'")
        self.assertGreater(totals['sku_lines'], 0)

    def test_dead_dict_keys(self):
        shop = self._first_shop()
        if not shop:
            self.skipTest("No shops in inventory DB")
        data = get_shop_inventory_data(shop)
        dead = data['dead']
        for field in ('sku_lines', 'dead_qty', 'dead_value'):
            self.assertIn(field, dead, f"Missing dead field '{field}'")

    def test_by_brand_row_structure(self):
        shop = self._first_shop()
        if not shop:
            self.skipTest("No shops in inventory DB")
        data = get_shop_inventory_data(shop)
        if not data['by_brand']:
            self.skipTest("No by_brand rows for this shop")
        row = data['by_brand'][0]
        for field in ('brand', 'qty', 'in_transit', 'total', 'value', 'lines'):
            self.assertIn(field, row, f"Missing by_brand field '{field}'")

    def test_by_season_row_structure(self):
        shop = self._first_shop()
        if not shop:
            self.skipTest("No shops in inventory DB")
        data = get_shop_inventory_data(shop)
        if not data['by_season']:
            self.skipTest("No by_season rows for this shop")
        row = data['by_season'][0]
        for field in ('year', 'season', 'qty', 'total', 'value'):
            self.assertIn(field, row, f"Missing by_season field '{field}'")

    def test_top_skus_list_bounded(self):
        shop = self._first_shop()
        if not shop:
            self.skipTest("No shops in inventory DB")
        data = get_shop_inventory_data(shop)
        self.assertLessEqual(len(data['top_skus']), 20)

    def test_unknown_shop_returns_empty(self):
        data = get_shop_inventory_data("__nonexistent_shop_xyz__")
        self.assertEqual(data, {})

    # ── get_inventory_overview — dead stock fields & top 50 ──────────────────

    def test_overview_dead_top_limit_50(self):
        """Global dead stock should return at most 50 items."""
        data = get_inventory_overview()
        dead_top = data.get('for_sale', {}).get('dead', {}).get('top', [])
        self.assertLessEqual(len(dead_top), 50)

    def test_overview_dead_top_has_new_fields(self):
        """Each dead stock row must contain the new detail fields."""
        data = get_inventory_overview()
        dead_top = data.get('for_sale', {}).get('dead', {}).get('top', [])
        if not dead_top:
            self.skipTest("No dead stock in test data")
        row = dead_top[0]
        for field in ('product_code', 'product_name', 'product_name_vn',
                      'color', 'size', 'brand', 'category_l1', 'category_l3',
                      'gender', 'year', 'season', 'qty', 'value'):
            self.assertIn(field, row, f"Missing dead stock field '{field}'")

    def test_overview_per_shop_dead_skus_limit_50(self):
        """Per-shop dead_skus should return at most 50 items."""
        data = get_inventory_overview()
        shops = data.get('for_sale', {}).get('by_shop_full', [])
        for shop in shops:
            self.assertLessEqual(
                len(shop.get('dead_skus', [])), 50,
                f"dead_skus for {shop['shop_name']} exceeds 50"
            )

    def test_overview_per_shop_dead_skus_has_new_fields(self):
        """Per-shop dead_skus rows must contain the new detail fields."""
        data = get_inventory_overview()
        shops = data.get('for_sale', {}).get('by_shop_full', [])
        for shop in shops:
            skus = shop.get('dead_skus', [])
            if skus:
                row = skus[0]
                for field in ('product_code', 'product_name', 'product_name_vn',
                              'color', 'size', 'category_l1', 'category_l3',
                              'gender', 'year', 'season', 'qty', 'value'):
                    self.assertIn(field, row,
                                  f"Shop '{shop['shop_name']}' dead_skus missing field '{field}'")
                break

    def test_overview_year_filter(self):
        """year filter should reduce or equal total vs unfiltered."""
        year = InventorySnapshot.objects.exclude(year__isnull=True).values_list('year', flat=True).first()
        if not year:
            self.skipTest("No rows with year in inventory")
        full = get_inventory_overview()
        filtered = get_inventory_overview(year=year)
        full_lines = (full.get('for_sale') or {}).get('totals', {}).get('sku_lines') or 0
        filt_lines = (filtered.get('for_sale') or {}).get('totals', {}).get('sku_lines') or 0
        self.assertLessEqual(filt_lines, full_lines)
        # All dead stock rows in filtered result must match the year
        dead_top = (filtered.get('for_sale') or {}).get('dead', {}).get('top', [])
        for row in dead_top:
            self.assertLessEqual(row['year'], year,
                                 f"Dead stock row year {row['year']} > filter year {year}")

    def test_overview_season_filter(self):
        """season filter must return only rows for that season."""
        season = InventorySnapshot.objects.exclude(season='').values_list('season', flat=True).first()
        if not season:
            self.skipTest("No rows with season in inventory")
        filtered = get_inventory_overview(season=season)
        # by_season breakdown should only contain the filtered season
        by_season = (filtered.get('for_sale') or {}).get('by_season', [])
        for row in by_season:
            self.assertEqual(row['season'], season,
                             f"by_season row season '{row['season']}' != filter '{season}'")

    def test_snapshot_dead_stock_shape(self):
        """Snapshot dead stock summary + first-row field presence."""
        data = get_inventory_overview()
        dead = (data.get('for_sale') or {}).get('dead', {})
        summary = dead.get('summary', {})
        top = dead.get('top', [])
        self.assert_snapshot("inventory_dead_stock", {
            "sku_lines":       summary.get('sku_lines', 0),
            "dead_qty":        int(summary.get('dead_qty') or 0),
            "top_count":       len(top),
            "top_limit":       50,
            "first_row_fields": sorted(top[0].keys()) if top else [],
        })

    # ── gender_name template filter ───────────────────────────────────────────

    def test_gender_name_filter_known_chinese(self):
        t = Template("{% load custom_filters %}{{ val|gender_name }}")
        self.assertEqual(t.render(Context({'val': '男装'})), '男装 (Nam)')
        self.assertEqual(t.render(Context({'val': '女装'})), '女装 (Nữ)')
        self.assertEqual(t.render(Context({'val': '童装'})), '童装 (Trẻ em)')

    def test_gender_name_filter_unknown_passthrough(self):
        t = Template("{% load custom_filters %}{{ val|gender_name }}")
        result = t.render(Context({'val': 'XYZ_UNKNOWN'}))
        self.assertEqual(result, 'XYZ_UNKNOWN')

    def test_gender_name_filter_empty(self):
        t = Template("{% load custom_filters %}{{ val|gender_name }}")
        self.assertEqual(t.render(Context({'val': ''})), '—')

    # ── Inventory dashboard page renders ──────────────────────────────────────

    def test_inventory_dashboard_200(self):
        r = self.client.get(reverse("inventory_dashboard"), follow=True)
        self.assertEqual(r.status_code, 200)

    def test_inventory_dashboard_with_year_filter_200(self):
        year = InventorySnapshot.objects.exclude(year__isnull=True).values_list('year', flat=True).first()
        if not year:
            self.skipTest("No year data in inventory")
        r = self.client.get(
            reverse("inventory_dashboard") + f"?year={year}",
            follow=True,
        )
        self.assertEqual(r.status_code, 200)

    def test_inventory_dashboard_with_season_filter_200(self):
        season = InventorySnapshot.objects.exclude(season='').values_list('season', flat=True).first()
        if not season:
            self.skipTest("No season data in inventory")
        r = self.client.get(
            reverse("inventory_dashboard") + f"?season={season}",
            follow=True,
        )
        self.assertEqual(r.status_code, 200)

    def test_inventory_dashboard_with_shop_group_200(self):
        r = self.client.get(
            reverse("inventory_dashboard") + "?shop_group=semir",
            follow=True,
        )
        self.assertEqual(r.status_code, 200)

    def test_export_dead_stock_csv_200(self):
        r = self.client.get(reverse("export_inventory_dead_stock"))
        self.assertEqual(r.status_code, 200)
        self.assertIn("text/csv", r["Content-Type"])
        # CSV must include the new column headers
        content = r.content.decode("utf-8-sig")
        for col in ("Product Code", "Product Name", "商品名称", "Color", "Size",
                    "Large Class", "Small Class", "Gender"):
            self.assertIn(col, content, f"CSV missing column '{col}'")

    # ── Page renders ──────────────────────────────────────────────────────────

    def test_upload_inventory_page_200(self):
        r = self.client.get(reverse("upload_inventory"))
        self.assertEqual(r.status_code, 200)

    def test_shop_detail_inventory_partial_no_shop(self):
        r = self.client.get(
            reverse("shop_detail_inventory_partial"),
            HTTP_X_REQUESTED_WITH="XMLHttpRequest",
        )
        self.assertEqual(r.status_code, 200)
        self.assertIn(b"Select a shop", r.content)

    def test_shop_detail_inventory_partial_with_shop(self):
        shop = self._first_shop()
        if not shop:
            self.skipTest("No shops in inventory DB")
        r = self.client.get(
            reverse("shop_detail_inventory_partial") + f"?shop={shop}",
            HTTP_X_REQUESTED_WITH="XMLHttpRequest",
        )
        self.assertEqual(r.status_code, 200)
        self.assertNotIn(b"Select a shop", r.content)

