"""
tests/test_membership.py — Customer Membership snapshot feature tests.

Covers:
  1. next_tier_info() pure-function correctness (calculations.py)
  2. compute_annual_spend_map() correctness — year window + as_of_date cutoff
  3. create_auto_snapshot() — snapshots the entire Customer table
  4. Auto-hook wiring into upload_customers — runs on success, never flips
     the customer-import job to "error" if the snapshot itself fails
  5. create_backfill_snapshot() never touches the live Customer table
  6. compare_batches() delta calculation
  7. get_customer_tier_table() sort order + grade/shop filters
  8. Web smoke — /membership/ permission gating

Run:
  cd SemirDashboard && python manage.py test tests.test_membership -v 2
"""
import io
from datetime import date
from decimal import Decimal
from unittest.mock import patch

import pandas as pd
from django.contrib.auth.models import User
from django.test import Client, TestCase

from App.models import Customer, SalesTransaction
from App.models.membership import MembershipSnapshot, MembershipSnapshotBatch
from App.analytics.calculations import next_tier_info, GRADE_UPGRADE_THRESHOLDS
from App.analytics.membership import (
    compute_annual_spend_map, compare_batches, get_customer_tier_table,
    get_grade_breakdown, get_all_batch_grade_series,
)
from App.services.membership_snapshot import create_auto_snapshot, create_backfill_snapshot

from tests.base import SnapshotTestCase


def _make_xlsx(headers, rows=None):
    buf = io.BytesIO()
    df = pd.DataFrame(rows or [], columns=headers)
    df.to_excel(buf, index=False)
    return buf.getvalue()


def _django_file(data, filename):
    from django.core.files.uploadedfile import SimpleUploadedFile
    return SimpleUploadedFile(filename, data)


def _customer(vip_id, phone, grade='Member', reg_date=None, points=0, store=''):
    return Customer.objects.create(
        vip_id=vip_id, phone=phone, name=f"Cust {vip_id}", vip_grade=grade,
        registration_date=reg_date, points=points, registration_store=store,
    )


def _sale(vip_id, sales_date, amount, invoice):
    return SalesTransaction.objects.create(
        invoice_number=invoice, shop_id="S1", shop_name="Test Shop", country="VN",
        sales_date=sales_date, vip_id=vip_id, vip_name=f"Cust {vip_id}",
        quantity=1, settlement_amount=Decimal(str(amount)), sales_amount=Decimal(str(amount)),
    )


# ---------------------------------------------------------------------------
# 1. next_tier_info() — pure function
# ---------------------------------------------------------------------------

class NextTierInfoTest(TestCase):
    def test_no_grade_targets_silver(self):
        target, remaining = next_tier_info('No Grade', Decimal('0'))
        self.assertEqual(target, 'Silver')
        self.assertEqual(remaining, GRADE_UPGRADE_THRESHOLDS['Silver'])

    def test_member_just_under_silver_threshold(self):
        target, remaining = next_tier_info('Member', Decimal('5999999'))
        self.assertEqual(target, 'Silver')
        self.assertEqual(remaining, Decimal('1'))

    def test_member_exactly_at_silver_threshold(self):
        target, remaining = next_tier_info('Member', GRADE_UPGRADE_THRESHOLDS['Silver'])
        self.assertEqual(target, 'Silver')
        self.assertEqual(remaining, Decimal('0'))

    def test_silver_over_gold_threshold_floors_at_zero(self):
        target, remaining = next_tier_info('Silver', Decimal('99999999'))
        self.assertEqual(target, 'Gold')
        self.assertEqual(remaining, Decimal('0'))

    def test_gold_targets_diamond(self):
        target, remaining = next_tier_info('Gold', Decimal('15000000'))
        self.assertEqual(target, 'Diamond')
        self.assertEqual(remaining, Decimal('5000000'))

    def test_diamond_has_no_next_tier(self):
        target, remaining = next_tier_info('Diamond', Decimal('50000000'))
        self.assertIsNone(target)
        self.assertEqual(remaining, Decimal('0'))

    def test_unrecognized_grade_has_no_next_tier(self):
        target, remaining = next_tier_info('Unknown Grade', Decimal('0'))
        self.assertIsNone(target)
        self.assertEqual(remaining, Decimal('0'))


# ---------------------------------------------------------------------------
# 2. compute_annual_spend_map() — year window + as_of_date cutoff
# ---------------------------------------------------------------------------

class ComputeAnnualSpendMapTest(TestCase):
    def test_only_target_year_counted(self):
        _sale('V1', date(2025, 3, 1), 1000000, 'INV-2025-1')
        _sale('V1', date(2026, 2, 1), 2000000, 'INV-2026-1')  # different year — excluded
        result = compute_annual_spend_map(date(2025, 12, 31))
        self.assertEqual(result['V1']['annual_spend'], Decimal('1000000'))
        self.assertEqual(result['V1']['annual_purchase_count'], 1)

    def test_sale_after_as_of_date_excluded(self):
        _sale('V2', date(2026, 6, 1), 1000000, 'INV-A')
        _sale('V2', date(2026, 6, 2), 5000000, 'INV-B')  # day AFTER as_of_date — excluded
        result = compute_annual_spend_map(date(2026, 6, 1))
        self.assertEqual(result['V2']['annual_spend'], Decimal('1000000'))
        self.assertEqual(result['V2']['annual_purchase_count'], 1)

    def test_sale_on_as_of_date_included(self):
        _sale('V3', date(2026, 6, 1), 3000000, 'INV-C')
        result = compute_annual_spend_map(date(2026, 6, 1))
        self.assertEqual(result['V3']['annual_spend'], Decimal('3000000'))

    def test_multiple_invoices_sum_and_count(self):
        _sale('V4', date(2026, 1, 5), 1000000, 'INV-D1')
        _sale('V4', date(2026, 2, 5), 2000000, 'INV-D2')
        result = compute_annual_spend_map(date(2026, 12, 31))
        self.assertEqual(result['V4']['annual_spend'], Decimal('3000000'))
        self.assertEqual(result['V4']['annual_purchase_count'], 2)

    def test_customer_with_no_sales_absent_from_map(self):
        result = compute_annual_spend_map(date(2026, 6, 1))
        self.assertNotIn('V-NONEXISTENT', result)

    def test_vip_id_zero_excluded(self):
        # vip_id "0" = buyer without info, excluded from grade analytics
        # everywhere else in the codebase — must not accumulate spend here.
        _sale('0', date(2026, 3, 1), 9999999, 'INV-ANON')
        result = compute_annual_spend_map(date(2026, 12, 31))
        self.assertNotIn('0', result)


# ---------------------------------------------------------------------------
# 3. create_auto_snapshot() — snapshots the entire Customer table
# ---------------------------------------------------------------------------

class CreateAutoSnapshotTest(TestCase):
    def test_snapshots_entire_customer_table(self):
        _customer('C1', 'P1', grade='Silver')
        _customer('C2', 'P2', grade='Gold')
        _customer('C3', 'P3', grade='No Grade')

        batch = create_auto_snapshot(as_of_date=date(2026, 6, 1))

        self.assertEqual(batch.source, 'auto')
        self.assertEqual(batch.row_count, Customer.objects.count())
        self.assertEqual(MembershipSnapshot.objects.filter(batch=batch).count(), 3)

    def test_grade_changed_at_always_null(self):
        _customer('C4', 'P4', grade='Diamond')
        batch = create_auto_snapshot(as_of_date=date(2026, 6, 1))
        rows = MembershipSnapshot.objects.filter(batch=batch)
        self.assertTrue(rows.exists())
        for row in rows:
            self.assertIsNone(row.grade_changed_at)

    def test_annual_spend_computed_from_sales(self):
        _customer('C5', 'P5', grade='Member')
        _sale('C5', date(2026, 3, 1), 7000000, 'INV-E1')
        batch = create_auto_snapshot(as_of_date=date(2026, 6, 1))
        row = MembershipSnapshot.objects.get(batch=batch, vip_id='C5')
        self.assertEqual(row.annual_spend, Decimal('7000000'))
        self.assertEqual(row.grade, 'Member')

    def test_vip_id_zero_forced_to_no_grade_regardless_of_stored_grade(self):
        # VIP ID "0" = buyer without info, excluded from grade analytics
        # everywhere else in the codebase — a raw vip_grade of "Gold" on such
        # a row must not leak into the Gold bucket.
        _customer('0', 'P6', grade='Gold')
        batch = create_auto_snapshot(as_of_date=date(2026, 6, 1))
        row = MembershipSnapshot.objects.get(batch=batch, vip_id='0')
        self.assertEqual(row.grade, 'No Grade')


# ---------------------------------------------------------------------------
# 4. Auto-hook wiring into upload_customers
# ---------------------------------------------------------------------------

class MembershipAutoHookTest(TestCase):
    def setUp(self):
        # _start_thread is mocked in every test below, so the real thread
        # (which normally releases the per-type upload lock in its finally
        # block) never runs — clear the cache each test so the "customers"
        # type lock from a previous test method doesn't block this one.
        from django.core.cache import cache
        cache.clear()
        self.client = Client()
        self.user = User.objects.create_superuser("testadmin", password="pw")
        self.client.force_login(self.user)

    def test_membership_hook_passed_to_start_thread_on_successful_upload(self):
        data = _make_xlsx(["VIP ID", "PHONE NO.", "Name"], [{"VIP ID": "X1", "PHONE NO.": "0900", "Name": "A"}])
        with patch("App.views.upload._start_thread") as mock_thread:
            r = self.client.post(
                "/upload/customers/",
                {"file": _django_file(data, "good.xlsx")},
                SERVER_NAME="localhost",
            )
        self.assertEqual(r.status_code, 302)
        mock_thread.assert_called_once()
        on_done_fn = mock_thread.call_args[0][4]
        self.assertTrue(callable(on_done_fn))

    def test_membership_hook_calls_create_auto_snapshot(self):
        data = _make_xlsx(["VIP ID", "PHONE NO.", "Name"], [{"VIP ID": "X2", "PHONE NO.": "0901", "Name": "B"}])
        with patch("App.views.upload._start_thread") as mock_thread:
            self.client.post(
                "/upload/customers/",
                {"file": _django_file(data, "good.xlsx")},
                SERVER_NAME="localhost",
            )
        on_done_fn = mock_thread.call_args[0][4]
        with patch("App.services.membership_snapshot.create_auto_snapshot") as mock_snap:
            on_done_fn()
        mock_snap.assert_called_once()

    def test_membership_hook_swallows_its_own_exceptions(self):
        """A snapshot failure must NOT propagate — the customer-import job's
        status must stay based on the import result, not the hook."""
        data = _make_xlsx(["VIP ID", "PHONE NO.", "Name"], [{"VIP ID": "X3", "PHONE NO.": "0902", "Name": "C"}])
        with patch("App.views.upload._start_thread") as mock_thread:
            self.client.post(
                "/upload/customers/",
                {"file": _django_file(data, "good.xlsx")},
                SERVER_NAME="localhost",
            )
        on_done_fn = mock_thread.call_args[0][4]
        with patch("App.services.membership_snapshot.create_auto_snapshot", side_effect=RuntimeError("boom")):
            on_done_fn()  # must not raise


# ---------------------------------------------------------------------------
# 5. create_backfill_snapshot() never touches live Customer
# ---------------------------------------------------------------------------

class CreateBackfillSnapshotTest(TestCase):
    def test_does_not_modify_live_customer_table(self):
        live = _customer('B1', 'PB1', grade='Silver', points=100)
        before_count = Customer.objects.count()
        before_grade = live.vip_grade
        before_points = live.points

        data = _make_xlsx(
            ["VIP ID", "PHONE NO.", "Name", "VIP GRADE", "POINTS"],
            [{"VIP ID": "B1", "PHONE NO.": "PB1", "Name": "Backfilled", "VIP GRADE": "Diamond", "POINTS": 9999}],
        )
        f = _django_file(data, "backfill.xlsx")
        result = create_backfill_snapshot(f, snapshot_date=date(2025, 1, 15), note="test backfill")

        self.assertEqual(Customer.objects.count(), before_count)
        live.refresh_from_db()
        self.assertEqual(live.vip_grade, before_grade)
        self.assertEqual(live.points, before_points)

        batch = MembershipSnapshotBatch.objects.get(pk=result['batch_id'])
        self.assertEqual(batch.source, 'manual_import')
        row = MembershipSnapshot.objects.get(batch=batch, vip_id='B1')
        self.assertEqual(row.grade, 'Diamond')
        self.assertEqual(row.points, 9999)


# ---------------------------------------------------------------------------
# 6. compare_batches() delta calculation
# ---------------------------------------------------------------------------

class CompareBatchesTest(TestCase):
    def test_delta_and_delta_pct(self):
        b1 = MembershipSnapshotBatch.objects.create(snapshot_date=date(2026, 1, 1), source='auto')
        b2 = MembershipSnapshotBatch.objects.create(snapshot_date=date(2026, 6, 1), source='auto')
        for i in range(2):
            MembershipSnapshot.objects.create(batch=b1, vip_id=f"S{i}", phone=f"P{i}", grade='Silver')
        for i in range(3):
            MembershipSnapshot.objects.create(batch=b2, vip_id=f"S{i}", phone=f"P{i}", grade='Silver')

        rows = {r['grade']: r for r in compare_batches(b1.id, b2.id)}
        self.assertEqual(rows['Silver']['from_count'], 2)
        self.assertEqual(rows['Silver']['to_count'], 3)
        self.assertEqual(rows['Silver']['delta'], 1)
        self.assertEqual(rows['Silver']['delta_pct'], 50.0)
        self.assertEqual(rows['Gold']['from_count'], 0)
        self.assertIsNone(rows['Gold']['delta_pct'])  # division by zero guarded

    def test_no_from_batch_treats_as_zero(self):
        b2 = MembershipSnapshotBatch.objects.create(snapshot_date=date(2026, 6, 1), source='auto')
        MembershipSnapshot.objects.create(batch=b2, vip_id="Z1", phone="PZ1", grade='Gold')
        rows = {r['grade']: r for r in compare_batches(None, b2.id)}
        self.assertEqual(rows['Gold']['from_count'], 0)
        self.assertEqual(rows['Gold']['to_count'], 1)

    def test_no_grade_excluded_from_breakdown_and_comparison(self):
        # PO feedback 2026-08-14: "No Grade" is noise in the grade-level KPI
        # view, but individual "No Grade" customers must still show up in
        # get_customer_tier_table() (see GetCustomerTierTableTest below) —
        # only the grade-level summary/comparison/chart excludes them.
        b1 = MembershipSnapshotBatch.objects.create(snapshot_date=date(2026, 1, 1), source='auto')
        b2 = MembershipSnapshotBatch.objects.create(snapshot_date=date(2026, 6, 1), source='auto')
        MembershipSnapshot.objects.create(batch=b1, vip_id="N1", phone="PN1", grade='No Grade')
        MembershipSnapshot.objects.create(batch=b2, vip_id="N1", phone="PN1", grade='No Grade')
        MembershipSnapshot.objects.create(batch=b2, vip_id="N2", phone="PN2", grade='No Grade')

        breakdown = get_grade_breakdown(b2.id)
        self.assertNotIn('No Grade', breakdown)

        grades = [r['grade'] for r in compare_batches(b1.id, b2.id)]
        self.assertNotIn('No Grade', grades)

        series = get_all_batch_grade_series()
        for entry in series:
            self.assertNotIn('No Grade', entry['counts'])


# ---------------------------------------------------------------------------
# 7. get_customer_tier_table() sort order + filters
# ---------------------------------------------------------------------------

class GetCustomerTierTableTest(TestCase):
    def setUp(self):
        self.batch = MembershipSnapshotBatch.objects.create(snapshot_date=date(2026, 6, 1), source='auto')
        MembershipSnapshot.objects.create(
            batch=self.batch, vip_id='T1', phone='PT1', grade='Member',
            annual_spend=Decimal('5900000'), registration_store='Shop A')  # close to Silver
        MembershipSnapshot.objects.create(
            batch=self.batch, vip_id='T2', phone='PT2', grade='Member',
            annual_spend=Decimal('1000000'), registration_store='Shop B')  # far from Silver
        MembershipSnapshot.objects.create(
            batch=self.batch, vip_id='T3', phone='PT3', grade='Diamond',
            annual_spend=Decimal('50000000'), registration_store='Shop A')  # no next tier

    def test_sort_ascending_amount_to_next_tier_diamond_last(self):
        rows, total_count = get_customer_tier_table(self.batch.id)
        vip_order = [r['vip_id'] for r in rows]
        self.assertEqual(vip_order, ['T1', 'T2', 'T3'])  # T1 closest, T3 (Diamond) last
        self.assertEqual(total_count, 3)

    def test_grade_filter(self):
        rows, total_count = get_customer_tier_table(self.batch.id, grade_filter='Diamond')
        self.assertEqual([r['vip_id'] for r in rows], ['T3'])
        self.assertEqual(total_count, 1)

    def test_shop_filter(self):
        rows, total_count = get_customer_tier_table(self.batch.id, shop_filter='Shop A')
        self.assertEqual(sorted(r['vip_id'] for r in rows), ['T1', 'T3'])
        self.assertEqual(total_count, 2)

    def test_shop_filter_is_partial_match(self):
        # icontains, not exact — matches the shop-filter convention used
        # elsewhere in the codebase; a user typing "Shop" (not the full
        # store name) must still get results.
        rows, total_count = get_customer_tier_table(self.batch.id, shop_filter='shop')
        self.assertEqual(sorted(r['vip_id'] for r in rows), ['T1', 'T2', 'T3'])
        self.assertEqual(total_count, 3)

    def test_no_grade_customer_still_visible_here_unlike_grade_breakdown(self):
        # Counterpart to CompareBatchesTest.test_no_grade_excluded_from_breakdown_and_comparison —
        # the grade-level summary excludes "No Grade", but a real "No Grade"
        # customer must still be reachable/filterable in the per-customer table
        # (they have a genuine upgrade path to Silver via next_tier_info()).
        MembershipSnapshot.objects.create(
            batch=self.batch, vip_id='T4', phone='PT4', grade='No Grade',
            annual_spend=Decimal('0'), registration_store='Shop A')
        rows, total_count = get_customer_tier_table(self.batch.id, grade_filter='No Grade')
        self.assertEqual([r['vip_id'] for r in rows], ['T4'])
        self.assertEqual(total_count, 1)
        self.assertEqual(rows[0]['next_grade'], 'Silver')

    def test_limit_caps_rows_but_total_count_reflects_full_set(self):
        for i in range(4, 10):  # 6 more customers beyond the 3 from setUp
            MembershipSnapshot.objects.create(
                batch=self.batch, vip_id=f'T{i}', phone=f'PT{i}', grade='Member',
                annual_spend=Decimal('1000000'))
        rows, total_count = get_customer_tier_table(self.batch.id, limit=2)
        self.assertEqual(len(rows), 2)
        self.assertEqual(total_count, 9)


# ---------------------------------------------------------------------------
# 8. Web smoke — permission gating
# ---------------------------------------------------------------------------

class MembershipWebSmokeTest(TestCase):
    def test_dashboard_200_for_superuser(self):
        user = User.objects.create_superuser("membadmin", password="pw")
        client = Client()
        client.force_login(user)
        r = client.get("/membership/", follow=True, SERVER_NAME="localhost")
        self.assertEqual(r.status_code, 200)

    def test_dashboard_blocked_for_anonymous(self):
        client = Client()
        r = client.get("/membership/", SERVER_NAME="localhost")
        self.assertEqual(r.status_code, 302)  # @login_required redirects to login

    def test_dashboard_blocked_without_permission(self):
        user = User.objects.create_user("noperm", password="pw")  # no role/perm assigned
        client = Client()
        client.force_login(user)
        r = client.get("/membership/", SERVER_NAME="localhost")
        self.assertEqual(r.status_code, 302)  # requires_perm redirects to "home"

    def test_table_partial_defaults_to_latest_batch_when_no_batch_param(self):
        MembershipSnapshotBatch.objects.create(snapshot_date=date(2026, 1, 1), source='auto')
        newest = MembershipSnapshotBatch.objects.create(snapshot_date=date(2026, 6, 1), source='auto')
        MembershipSnapshot.objects.create(batch=newest, vip_id='D1', phone='PD1', grade='Gold')

        user = User.objects.create_superuser("membadmin2", password="pw")
        client = Client()
        client.force_login(user)
        r = client.get("/membership/partial/table/", SERVER_NAME="localhost", HTTP_X_REQUESTED_WITH="XMLHttpRequest")
        self.assertEqual(r.status_code, 200)
        self.assertIn(b"D1", r.content)  # newest batch's customer shows up, not the older empty batch

    def test_table_partial_returns_empty_message_when_no_batches_exist(self):
        user = User.objects.create_superuser("membadmin3", password="pw")
        client = Client()
        client.force_login(user)
        r = client.get("/membership/partial/table/", SERVER_NAME="localhost", HTTP_X_REQUESTED_WITH="XMLHttpRequest")
        self.assertEqual(r.status_code, 200)
        self.assertIn(b"No snapshot", r.content)
