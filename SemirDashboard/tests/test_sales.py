"""
tests/test_sales.py — Sales page: import + full analytics pipeline timing.

Run:
  cd SemirDashboard && python manage.py test tests.test_sales -v 2

Regenerate snapshots:
  UPDATE_SNAPSHOTS=1 python manage.py test tests.test_sales -v 2
"""
import io
import time
from datetime import date
from pathlib import Path

from App.models import Customer, SalesTransaction
from App.services import process_customer_file, process_sales_file
from App.analytics.core import calculate_return_rate_analytics
from App.analytics.aggregators import (
    aggregate_by_grade, aggregate_by_season, aggregate_by_month,
    aggregate_by_year, aggregate_by_week, aggregate_by_shop,
)
from App.analytics.calculations import calculate_return_visits
from App.analytics.customer_utils import build_customer_purchase_map, get_customer_info

from tests.base import SnapshotTestCase, INPUT_DIR, get_run_log

SALE_FILES    = [INPUT_DIR / "Sale 2024.xlsx", INPUT_DIR / "Sale 2025.xlsx", INPUT_DIR / "Sale 2026.xlsx"]
CUSTOMER_FILE = INPUT_DIR / "customer.xlsx"


def _named(path):
    with open(path, "rb") as f:
        data = f.read()
    class _N(io.BytesIO):
        pass
    obj = _N(data)
    obj.name = path.name
    return obj


class SalesImportTest(SnapshotTestCase):

    def test_import_customers(self):
        t = self.timer("import_customers")
        result = process_customer_file(_named(CUSTOMER_FILE))
        t.checkpoint(f"process_customer_file → created={result['created']} updated={result['updated']} total={result['total_processed']}")
        t.report()
        self.assertGreater(result["total_processed"], 0)
        self.assertEqual(len(result.get("errors", [])), 0, result.get("errors", [])[:3])

    def test_import_sales(self):
        t = self.timer("import_sales")
        for path in SALE_FILES:
            if not path.exists():
                continue
            result = process_sales_file(_named(path))
            t.checkpoint(f"{path.name} → created={result['created']} updated={result['updated']}")
        t.report()
        self.assertGreater(SalesTransaction.objects.count(), 0)


class SalesAnalyticsTest(SnapshotTestCase):

    @classmethod
    def setUpTestData(cls):
        process_customer_file(_named(CUSTOMER_FILE))
        for path in SALE_FILES:
            if path.exists():
                process_sales_file(_named(path))

    # ── Full page timing (views → data ready for render) ──────────────────

    def test_page_timing_alltime(self):
        """Simulate full sales page load: measure each sub-step."""
        from django.db.models import Count, Q, Sum
        from decimal import Decimal

        log = get_run_log()
        log.section("SALES PAGE TIMING (all-time) — per-function breakdown")
        t = self.timer("sales_page_alltime")

        # Step 1: DB fetch (the main query)
        _t0 = time.perf_counter()
        SALES_FIELDS = ('vip_id', 'sales_date', 'invoice_number', 'sales_amount', 'shop_name', 'customer')
        CUST_FIELDS  = ('customer__id', 'customer__vip_id', 'customer__vip_grade',
                        'customer__registration_date', 'customer__name')
        qs = (SalesTransaction.objects
              .select_related('customer')
              .only(*SALES_FIELDS, *CUST_FIELDS)
              .order_by())
        sales_list = list(qs)
        t.checkpoint(f"DB fetch SalesTransaction (select_related) → {len(sales_list)} rows")

        # Step 2: VIP0 aggregate
        _vip0_q = Q(vip_id='') | Q(vip_id='0') | Q(vip_id__isnull=True)
        SalesTransaction.objects.filter(_vip0_q).aggregate(cnt=Count('id'), total=Sum('sales_amount'))
        t.checkpoint("DB aggregate VIP0 all-time counts")

        # Step 3: Customer totals
        Customer.objects.count()
        SalesTransaction.objects.exclude(_vip0_q).values('vip_id').distinct().count()
        t.checkpoint("DB count total_customers + member_active_all_time")

        # Step 4: Build purchase map (pure Python)
        customer_purchases = build_customer_purchase_map(sales_list)
        t.checkpoint(f"build_customer_purchase_map → {len(customer_purchases)} customers")

        # Step 5: Per-customer loop (return visits + get_customer_info)
        customer_details = []
        returning = set()
        for vip_id, purchases in customer_purchases.items():
            if vip_id == '0':
                continue
            purchases_sorted = sorted(purchases, key=lambda x: x['date'])
            grade, reg_date, name = get_customer_info(vip_id, purchases_sorted[0]['customer'])
            rc, is_ret = calculate_return_visits(purchases_sorted, reg_date)
            if is_ret:
                returning.add(vip_id)
            customer_details.append({
                'vip_id': vip_id, 'name': name, 'vip_grade': grade,
                'registration_date': reg_date,
                'first_purchase_date': purchases_sorted[0]['date'],
                'total_purchases': len(purchases_sorted),
                'return_visits': rc,
                'total_spent': float(sum(p['amount'] for p in purchases_sorted)),
            })
        t.checkpoint(f"per-customer loop (return_visits + customer_info) → {len(customer_details)} details")

        # Step 6: Aggregations
        grade_stats = aggregate_by_grade(customer_details)
        t.checkpoint(f"aggregate_by_grade → {len(grade_stats)} grades")

        session_stats = aggregate_by_season(customer_purchases, get_customer_info)
        t.checkpoint(f"aggregate_by_season → {len(session_stats)} sessions")

        month_stats = aggregate_by_month(customer_purchases, get_customer_info)
        t.checkpoint(f"aggregate_by_month → {len(month_stats)} months")

        year_stats = aggregate_by_year(customer_purchases, get_customer_info)
        t.checkpoint(f"aggregate_by_year → {len(year_stats)} years")

        week_stats = aggregate_by_week(customer_purchases, get_customer_info)
        t.checkpoint(f"aggregate_by_week → {len(week_stats)} weeks")

        from App.analytics.season_utils import session_sort_key, month_sort_key, year_sort_key, week_sort_key
        all_sk = sorted([s['session'] for s in session_stats], key=session_sort_key)
        all_mk = sorted([m['month'] for m in month_stats], key=month_sort_key)
        all_yk = sorted([y['year'] for y in year_stats], key=year_sort_key)
        all_wk = sorted([w['week_sort'] for w in week_stats], key=week_sort_key)
        shop_stats = aggregate_by_shop(customer_purchases, get_customer_info, all_sk, all_mk, all_yk, all_wk)
        t.checkpoint(f"aggregate_by_shop → {len(shop_stats)} shops")

        total = t.total()
        t.report()
        self.record_page_timing("SALES (all-time)", total, t._checkpoints)

        # Threshold check
        self.assertLess(total, 30, f"Sales page all-time took {total:.1f}s > 30s threshold")

    def test_page_timing_2025(self):
        log = get_run_log()
        log.section("SALES PAGE TIMING (2025 filter)")
        t = self.timer("sales_page_2025")
        data = calculate_return_rate_analytics(date_from=date(2025,1,1), date_to=date(2025,12,31))
        total = t.total()
        t.checkpoint(f"calculate_return_rate_analytics(2025) → active={data['overview']['active_customers'] if data else 0}")
        t.report()
        self.record_page_timing("SALES (2025 filter)", total, t._checkpoints)

    # ── Snapshots ─────────────────────────────────────────────────────────

    def test_snapshot_alltime(self):
        t = self.timer("sales_snapshot_alltime")
        data = calculate_return_rate_analytics()
        t.checkpoint("calculate_return_rate_analytics(all-time)")
        t.report()
        self.assertIsNotNone(data)
        self.assert_snapshot("sales_alltime", {
            "overview": data["overview"],
            "by_grade_count": len(data["by_grade"]),
            "by_session_count": len(data["by_session"]),
            "by_month_count": len(data["by_month"]),
            "by_shop_count": len(data["by_shop"]),
            "by_grade": data["by_grade"],
            "by_session": data["by_session"],
            "customer_details_count": len(data["customer_details"]),
        })

    def test_snapshot_2025(self):
        t = self.timer("sales_snapshot_2025")
        data = calculate_return_rate_analytics(date_from=date(2025,1,1), date_to=date(2025,12,31))
        t.checkpoint("calculate_return_rate_analytics(2025)")
        t.report()
        if data is None:
            self.skipTest("No 2025 data")
        self.assert_snapshot("sales_2025", {
            "overview": data["overview"],
            "by_grade_count": len(data["by_grade"]),
            "by_session_count": len(data["by_session"]),
            "by_month_count": len(data["by_month"]),
            "by_shop_count": len(data["by_shop"]),
            "by_grade": data["by_grade"],
            "by_session": data["by_session"],
        })

    # ── Sanity ────────────────────────────────────────────────────────────

    def test_return_rate_sanity(self):
        data = calculate_return_rate_analytics()
        if not data:
            self.skipTest("No data")
        ov = data["overview"]
        self.assertGreaterEqual(ov["return_rate"], 0.0)
        self.assertLessEqual(ov["return_rate"], 100.0)
        self.assertLessEqual(ov["returning_customers"], ov["active_customers"])

    def test_grade_totals_consistent(self):
        data = calculate_return_rate_analytics()
        if not data:
            self.skipTest("No data")
        total_active = data["overview"]["active_customers"]
        grade_sum    = sum(g.get("total_customers", 0) for g in data["by_grade"])
        self.assertEqual(total_active, grade_sum,
            f"Grade sum ({grade_sum}) != overview active ({total_active})")
