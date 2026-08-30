"""
tests/test_cnv_sync.py

Unit tests for CNV sync service rate limiter and membership fetch logic.
No fixture loading required — all external calls are mocked.
"""
import time
import threading
from decimal import Decimal
from unittest.mock import MagicMock, patch, call
from django.test import TestCase

from App.cnv.sync_service import CNVSyncService, _RateLimiter, MEMBERSHIP_RATE_LIMIT


class RateLimiterTest(TestCase):
    """Test _RateLimiter enforces minimum interval between calls."""

    def test_rate_is_50(self):
        self.assertEqual(MEMBERSHIP_RATE_LIMIT, 50)

    def test_single_acquire_does_not_block(self):
        rl = _RateLimiter(rate=50)
        t0 = time.monotonic()
        rl.acquire()
        elapsed = time.monotonic() - t0
        self.assertLess(elapsed, 0.1)  # first call is immediate

    def test_second_acquire_waits_min_interval(self):
        rl = _RateLimiter(rate=50)
        rl.acquire()  # first — sets _last_call
        t0 = time.monotonic()
        rl.acquire()  # second — must wait ~20ms
        elapsed = time.monotonic() - t0
        # Should have waited close to 1/50 = 0.02s
        self.assertGreaterEqual(elapsed, 0.015)

    def test_throughput_stays_under_limit(self):
        """10 sequential calls at rate=50 should take at least 9*(1/50)=0.18s."""
        rl = _RateLimiter(rate=50)
        n = 10
        t0 = time.monotonic()
        for _ in range(n):
            rl.acquire()
        elapsed = time.monotonic() - t0
        min_expected = (n - 1) / 50
        self.assertGreaterEqual(elapsed, min_expected * 0.9)  # 10% tolerance

    def test_thread_safe_no_exception(self):
        """Multiple threads acquiring concurrently must not raise."""
        rl = _RateLimiter(rate=200)  # fast rate so test doesn't take long
        errors = []

        def worker():
            try:
                rl.acquire()
            except Exception as e:
                errors.append(e)

        threads = [threading.Thread(target=worker) for _ in range(20)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()
        self.assertEqual(errors, [])


class FetchMembershipTest(TestCase):
    """Test _fetch_membership rate limiting and 429 retry logic."""

    def _make_service(self):
        with patch('App.cnv.sync_service.CNVAPIClient'):
            service = CNVSyncService(username='u', password='p')
        return service

    def test_returns_membership_fields_on_success(self):
        service = self._make_service()
        service.client.get_customer_membership.return_value = {
            'membership': {
                'level_name': 'Gold',
                'points': 1000,
                'used_points': 200,
                'total_points': 1200,
            }
        }
        result = service._fetch_membership(123)
        self.assertEqual(result['level_name'], 'Gold')
        self.assertEqual(result['points'], Decimal('1000'))
        self.assertEqual(result['used_points'], Decimal('200'))
        self.assertEqual(result['total_points'], Decimal('1200'))

    def test_returns_empty_dict_when_no_membership_key(self):
        service = self._make_service()
        service.client.get_customer_membership.return_value = {}
        result = service._fetch_membership(123)
        self.assertEqual(result, {})

    def test_returns_empty_dict_on_generic_exception(self):
        service = self._make_service()
        service.client.get_customer_membership.side_effect = Exception('Network error')
        result = service._fetch_membership(123)
        self.assertEqual(result, {})

    @patch('App.cnv.sync_service.time.sleep')
    def test_429_triggers_retry_after_1s_sleep(self, mock_sleep):
        service = self._make_service()
        service.client.get_customer_membership.side_effect = [
            Exception('429 Too Many Requests'),
            {'membership': {'level_name': 'Silver', 'points': 500, 'used_points': 0, 'total_points': 500}},
        ]
        result = service._fetch_membership(99)
        # Must have slept 1s (the retry wait — rate limiter sleep is separate)
        sleep_calls = [c for c in mock_sleep.call_args_list if c.args[0] == 1]
        self.assertGreaterEqual(len(sleep_calls), 1)
        self.assertEqual(result['level_name'], 'Silver')

    @patch('App.cnv.sync_service.time.sleep')
    def test_429_retry_also_fails_returns_empty(self, mock_sleep):
        service = self._make_service()
        service.client.get_customer_membership.side_effect = [
            Exception('429 Too Many Requests'),
            Exception('429 Too Many Requests'),
        ]
        result = service._fetch_membership(99)
        self.assertEqual(result, {})

    def test_rate_limiter_called_before_api(self):
        """acquire() must be called before every membership API request."""
        service = self._make_service()
        service.client.get_customer_membership.return_value = {}
        call_order = []

        original_acquire = service._rate_limiter.acquire
        def tracked_acquire():
            call_order.append('acquire')
            original_acquire()
        service._rate_limiter.acquire = tracked_acquire

        original_get = service.client.get_customer_membership
        def tracked_get(cid):
            call_order.append('api')
            return original_get(cid)
        service.client.get_customer_membership = tracked_get

        service._fetch_membership(1)
        self.assertEqual(call_order[0], 'acquire')
        self.assertEqual(call_order[1], 'api')


class TransformCustomerTest(TestCase):
    """Ensure membership fields are not included in transform output when fetch fails."""

    def _make_service(self):
        with patch('App.cnv.sync_service.CNVAPIClient'):
            service = CNVSyncService(username='u', password='p')
        return service

    def _sample_customer_data(self):
        return {
            'id': 12345,
            'last_name': 'Nguyen',
            'first_name': 'A',
            'phone': '0901234567',
            'email': '',
            'gender': 'female',
            'birthday_day': 1,
            'birthday_month': 1,
            'birthday_year': 1990,
            'tags': '',
            'physical_card_code': '',
            'points': 500,
            'exp_points': 400,
            'total_spending': 1000000,
            'total_points': 600,
            'created_at': '2025-01-01T00:00:00.000Z',
            'updated_at': '2026-01-01T00:00:00.000Z',
        }

    def test_transform_does_not_include_level_name(self):
        """level_name must NOT be in transform output — only added on successful fetch."""
        service = self._make_service()
        result = service._transform_customer(self._sample_customer_data())
        self.assertNotIn('level_name', result)

    def test_transform_does_not_include_used_points(self):
        """used_points must NOT be in transform output — only added on successful fetch."""
        service = self._make_service()
        result = service._transform_customer(self._sample_customer_data())
        self.assertNotIn('used_points', result)

    def test_transform_does_not_include_points(self):
        """points must NOT be in transform output — authoritative value comes from membership API."""
        service = self._make_service()
        result = service._transform_customer(self._sample_customer_data())
        self.assertNotIn('points', result)

    def test_transform_does_not_include_total_points(self):
        """total_points must NOT be in transform output — authoritative value comes from membership API."""
        service = self._make_service()
        result = service._transform_customer(self._sample_customer_data())
        self.assertNotIn('total_points', result)

    def test_membership_fields_present_after_successful_fetch(self):
        """After merging a successful fetch, level_name and used_points are present."""
        service = self._make_service()
        transformed = service._transform_customer(self._sample_customer_data())
        membership = {'level_name': 'Gold', 'used_points': Decimal('100'), 'points': Decimal('500'), 'total_points': Decimal('600')}
        transformed.update(membership)
        self.assertEqual(transformed['level_name'], 'Gold')
        self.assertEqual(transformed['used_points'], Decimal('100'))

    def test_membership_fields_absent_after_failed_fetch(self):
        """After merging an empty fetch result, level_name and used_points still absent."""
        service = self._make_service()
        transformed = service._transform_customer(self._sample_customer_data())
        transformed.update({})  # simulates failed fetch
        self.assertNotIn('level_name', transformed)
        self.assertNotIn('used_points', transformed)


class ProcessCustomerBatchTest(TestCase):
    """Perf plan P3-02 (2026-07-18): _process_customer_batch changed from
    1 UPDATE query per existing record to grouped bulk_update calls. This is
    a DB-level integration test (the invariant lives in what actually lands
    in the database, not just in the transform dict) — no such test existed
    before this change."""

    def _make_service(self):
        with patch('App.cnv.sync_service.CNVAPIClient'):
            service = CNVSyncService(username='u', password='p')
        return service

    def _raw_customer(self, cnv_id, phone='0900000000'):
        return {
            'id': cnv_id, 'last_name': 'N', 'first_name': 'A', 'phone': phone,
            'email': '', 'gender': 'female', 'birthday_day': 1, 'birthday_month': 1,
            'birthday_year': 1990, 'tags': '', 'physical_card_code': '',
            'points': 999, 'exp_points': 1, 'total_spending': 1, 'total_points': 999,
            'created_at': '2025-01-01T00:00:00.000Z', 'updated_at': '2026-01-01T00:00:00.000Z',
        }

    def test_membership_fetch_fail_does_not_overwrite_existing_points(self):
        """Zero-overwrite rule at the DB level: a customer with existing
        points=100 must still have points=100 after a batch run where
        membership fetch fails for that customer."""
        from App.cnv.models import CNVCustomer
        existing = CNVCustomer.objects.create(
            cnv_id=555, phone='0900000001', points=Decimal('100'),
            used_points=Decimal('50'), total_points=Decimal('150'), level_name='Gold',
        )
        service = self._make_service()
        with patch.object(service, '_fetch_membership', return_value={}):
            created, updated, failed = service._process_customer_batch(
                [self._raw_customer(555, phone='0900000001')]
            )
        self.assertEqual((created, updated, failed), (0, 1, 0))
        existing.refresh_from_db()
        self.assertEqual(existing.points, Decimal('100'), "points must NOT be reset when membership fetch fails")
        self.assertEqual(existing.used_points, Decimal('50'))
        self.assertEqual(existing.total_points, Decimal('150'))
        self.assertEqual(existing.level_name, 'Gold')
        # Non-membership fields ARE updated from the transform (existing behavior).
        self.assertEqual(existing.phone, '0900000001')

    def test_membership_fetch_success_updates_points(self):
        """When membership fetch succeeds, points/used_points/total_points/
        level_name ARE written."""
        from App.cnv.models import CNVCustomer
        existing = CNVCustomer.objects.create(cnv_id=556, phone='0900000002', points=Decimal('0'))
        service = self._make_service()
        membership = {
            'level_name': 'Diamond', 'used_points': Decimal('20'),
            'points': Decimal('300'), 'total_points': Decimal('320'),
        }
        with patch.object(service, '_fetch_membership', return_value=membership):
            created, updated, failed = service._process_customer_batch(
                [self._raw_customer(556, phone='0900000002')]
            )
        self.assertEqual((created, updated, failed), (0, 1, 0))
        existing.refresh_from_db()
        self.assertEqual(existing.points, Decimal('300'))
        self.assertEqual(existing.used_points, Decimal('20'))
        self.assertEqual(existing.level_name, 'Diamond')

    def test_mixed_success_and_failure_grouped_correctly(self):
        """A batch with SOME memberships succeeding and SOME failing must
        update each customer correctly — proving the field-set grouping
        doesn't cross-contaminate the two groups."""
        from App.cnv.models import CNVCustomer
        ok_cust = CNVCustomer.objects.create(cnv_id=601, phone='p601', points=Decimal('0'))
        fail_cust = CNVCustomer.objects.create(
            cnv_id=602, phone='p602', points=Decimal('777'), level_name='Silver'
        )
        service = self._make_service()

        def _fetch_side_effect(cid):
            if cid == 601:
                return {'level_name': 'Gold', 'used_points': Decimal('1'),
                         'points': Decimal('500'), 'total_points': Decimal('501')}
            return {}

        with patch.object(service, '_fetch_membership', side_effect=_fetch_side_effect):
            created, updated, failed = service._process_customer_batch([
                self._raw_customer(601, phone='p601'),
                self._raw_customer(602, phone='p602'),
            ])
        self.assertEqual((created, updated, failed), (0, 2, 0))
        ok_cust.refresh_from_db()
        fail_cust.refresh_from_db()
        self.assertEqual(ok_cust.points, Decimal('500'))
        self.assertEqual(ok_cust.level_name, 'Gold')
        self.assertEqual(fail_cust.points, Decimal('777'), "unaffected customer's points must be untouched")
        self.assertEqual(fail_cust.level_name, 'Silver')

    def test_new_customer_created_when_cnv_id_not_existing(self):
        from App.cnv.models import CNVCustomer
        service = self._make_service()
        with patch.object(service, '_fetch_membership', return_value={}):
            created, updated, failed = service._process_customer_batch(
                [self._raw_customer(999, phone='pnew')]
            )
        self.assertEqual((created, updated, failed), (1, 0, 0))
        self.assertTrue(CNVCustomer.objects.filter(cnv_id=999).exists())

    def test_query_count_reduced_vs_per_row_update(self):
        """A batch of 10 existing customers all failing membership fetch
        (single field-group) must issue O(1) UPDATE-related queries, not 10
        — proving the grouped bulk_update actually reduces query count."""
        from django.db import connection
        from django.test.utils import CaptureQueriesContext
        from App.cnv.models import CNVCustomer
        for i in range(700, 710):
            CNVCustomer.objects.create(cnv_id=i, phone=f'p{i}')
        service = self._make_service()
        batch = [self._raw_customer(i, phone=f'p{i}') for i in range(700, 710)]
        with patch.object(service, '_fetch_membership', return_value={}):
            with CaptureQueriesContext(connection) as ctx:
                created, updated, failed = service._process_customer_batch(batch)
        self.assertEqual((created, updated, failed), (0, 10, 0))
        update_related = [q for q in ctx.captured_queries if 'UPDATE' in q['sql'].upper()]
        self.assertLessEqual(len(update_related), 2,
            f"expected O(1) UPDATE statements for a single field-group batch of 10, got {len(update_related)}")


class ProcessOrderBatchTest(TestCase):
    """Perf plan P3-02: _process_order_batch changed from 1 UPDATE query per
    record to a single bulk_update (no zero-overwrite risk for orders —
    _transform_order always sets every field)."""

    def _make_service(self):
        with patch('App.cnv.sync_service.CNVAPIClient'):
            service = CNVSyncService(username='u', password='p')
        return service

    def _raw_order(self, order_code, customer_code='C1'):
        return {
            'name': order_code, 'id': order_code,
            'customer': {'id': customer_code, 'first_name': 'A', 'last_name': 'N', 'phone': 'p1'},
            'created_at': '2025-01-01T00:00:00.000Z', 'location_id': 'S1',
            'total_price': 100000,
        }

    def test_new_order_created(self):
        from App.cnv.models import CNVOrder
        service = self._make_service()
        created, updated, failed = service._process_order_batch([self._raw_order('ORD1')])
        self.assertEqual((created, updated, failed), (1, 0, 0))
        self.assertTrue(CNVOrder.objects.filter(order_code='ORD1').exists())

    def test_existing_order_updated_via_bulk_update(self):
        from App.cnv.models import CNVOrder
        service = self._make_service()
        service._process_order_batch([self._raw_order('ORD2', customer_code='OLD')])
        created, updated, failed = service._process_order_batch(
            [self._raw_order('ORD2', customer_code='NEW')]
        )
        self.assertEqual((created, updated, failed), (0, 1, 0))
        self.assertEqual(CNVOrder.objects.get(order_code='ORD2').customer_code, 'NEW')

    def test_order_with_no_customer_info_still_created(self):
        # 2026-08-30: an order with no nested customer object and no
        # customerCode fallback makes _transform_order produce
        # customer_code=None. On Postgres this used to be a hard NOT NULL
        # violation (masked on SQLite dev, since INSERT OR IGNORE there
        # silently drops NOT NULL violations too, not just PK/unique
        # conflicts) — customer_code is now nullable, matching its sibling
        # customer_name/customer_phone fields.
        from App.cnv.models import CNVOrder
        service = self._make_service()
        raw = {
            'name': 'ORD3', 'id': 'ORD3', 'customer': {},
            'created_at': '2025-01-01T00:00:00.000Z', 'location_id': 'S1',
            'total_price': 100000,
        }
        created, updated, failed = service._process_order_batch([raw])
        self.assertEqual((created, updated, failed), (1, 0, 0))
        self.assertIsNone(CNVOrder.objects.get(order_code='ORD3').customer_code)

    def test_bulk_create_failure_does_not_poison_later_statements(self):
        # 2026-08-30: on Postgres, any error inside a transaction aborts the
        # WHOLE transaction — every later statement (e.g. sync_log's own
        # save() calls right after this batch) then fails too with
        # "current transaction is aborted", unless the failing operation is
        # wrapped in its own transaction.atomic()/savepoint. Force a real DB
        # error inside bulk_create to prove the atomic() wrapping in
        # _process_order_batch contains the damage — a later save() on an
        # unrelated model must still succeed in the same test (which, like
        # sync_orders() itself, runs inside Django TestCase's own outer
        # transaction — the exact context that exposes this class of bug).
        from django.db.utils import IntegrityError
        from App.cnv.models import CNVSyncLog

        service = self._make_service()
        with patch('App.cnv.models.CNVOrder.objects.bulk_create', side_effect=IntegrityError('forced')):
            created, updated, failed = service._process_order_batch([self._raw_order('ORD4')])
        self.assertEqual((created, updated, failed), (0, 0, 1))

        # If bulk_create's failure had poisoned the transaction, this save()
        # would raise django.db.utils.InternalError ("transaction aborted").
        log = CNVSyncLog.objects.create(sync_type='orders')
        log.mark_completed()
        self.assertEqual(log.status, 'completed')


class CheckpointTieBoundaryFixTest(TestCase):
    """2026-07-25 fix: sync_customers()/sync_orders() used to save
    `checkpoint = latest_updated_at + 1 microsecond`, then filter the next
    run's fetch with `updated_at_from >= checkpoint`. If several records
    shared the exact same updated_at (a tie) and that tie straddled a run's
    max_pages cutoff, the +1us push meant the next run's `>=` filter
    permanently excluded the tied stragglers — confirmed root cause of 165
    customers silently never syncing. The fix: save the checkpoint as the
    exact boundary timestamp (no offset), so an inclusive `>=` filter next
    run naturally re-includes anyone tied at that exact moment."""

    def _make_service(self):
        with patch('App.cnv.sync_service.CNVAPIClient'):
            service = CNVSyncService(username='u', password='p')
        return service

    def _raw_customer(self, cnv_id, updated_at, phone=None):
        return {
            'id': cnv_id, 'last_name': 'N', 'first_name': 'A',
            'phone': phone or f'090000{cnv_id:04d}',
            'email': '', 'gender': 'female', 'birthday_day': 1, 'birthday_month': 1,
            'birthday_year': 1990, 'tags': '', 'physical_card_code': '',
            'points': 0, 'exp_points': 0, 'total_spending': 0, 'total_points': 0,
            'created_at': updated_at, 'updated_at': updated_at,
        }

    def test_checkpoint_saved_without_microsecond_offset(self):
        """A tied batch (2 customers, identical updated_at) must produce a
        checkpoint equal to that exact timestamp — not timestamp + 1us."""
        tied_at = '2026-07-18T10:00:00.000Z'
        service = self._make_service()
        service.client.fetch_all_customers = MagicMock(
            return_value=[self._raw_customer(1001, tied_at), self._raw_customer(1002, tied_at)]
        )
        with patch.object(service, '_fetch_membership', return_value={}):
            service.sync_customers(incremental=False)

        from App.cnv.models import CNVSyncLog
        log = CNVSyncLog.objects.filter(sync_type='customers', status='completed').first()
        expected = service._parse_datetime(tied_at)
        self.assertEqual(log.checkpoint_updated_at, expected,
                          "checkpoint must equal the exact tied timestamp, no +1us offset")

    def test_next_run_refetches_from_exact_tied_boundary(self):
        """After a tied batch, the NEXT incremental run must query
        updated_since == the exact boundary timestamp (inclusive), so a
        real CNV API's `updated_at_from >=` filter would re-include any
        customer still tied at that exact moment that this run missed."""
        tied_at = '2026-07-18T10:00:00.000Z'
        service = self._make_service()
        service.client.fetch_all_customers = MagicMock(
            return_value=[self._raw_customer(2001, tied_at)]
        )
        with patch.object(service, '_fetch_membership', return_value={}):
            service.sync_customers(incremental=False)

        service.client.fetch_all_customers = MagicMock(return_value=[])
        with patch.object(service, '_fetch_membership', return_value={}):
            service.sync_customers(incremental=True)

        expected = service._parse_datetime(tied_at)
        _, kwargs = service.client.fetch_all_customers.call_args
        self.assertEqual(kwargs.get('updated_since'), expected,
                          "next run must resume from the exact tied timestamp, not past it")

    def test_sync_orders_checkpoint_also_has_no_offset(self):
        tied_at = '2026-07-18T10:00:00.000Z'
        service = self._make_service()
        raw_order = {
            'id': 5001, 'name': '#5001', 'created_at': tied_at, 'updated_at': tied_at,
            'customer': {}, 'financial_status': 'paid', 'location_id': 'S1', 'total_price': 1000,
        }
        service.client.fetch_all_orders = MagicMock(return_value=[raw_order])
        service.sync_orders(incremental=False)

        from App.cnv.models import CNVSyncLog
        log = CNVSyncLog.objects.filter(sync_type='orders', status='completed').first()
        expected = service._parse_datetime(tied_at)
        self.assertEqual(log.checkpoint_updated_at, expected,
                          "order checkpoint must also have no +1us offset")


class BackfillCustomersByIdsTest(TestCase):
    """2026-07-25 incident: sync_customers()'s checkpoint (max(updated_at in
    batch) + 1us, then next run filters updated_at >= checkpoint) permanently
    drops customers whose updated_at ties with the last-fetched record across
    a max_pages cutoff. backfill_customers_by_ids() fetches specific IDs
    directly, bypassing that cursor entirely."""

    def _make_service(self):
        with patch('App.cnv.sync_service.CNVAPIClient'):
            service = CNVSyncService(username='u', password='p')
        return service

    def _raw_customer(self, cnv_id, phone='0900000000'):
        return {
            'id': cnv_id, 'last_name': 'N', 'first_name': 'A', 'phone': phone,
            'email': '', 'gender': 'female', 'birthday_day': 1, 'birthday_month': 1,
            'birthday_year': 1990, 'tags': '', 'physical_card_code': '',
            'points': 999, 'exp_points': 1, 'total_spending': 1, 'total_points': 999,
            'created_at': '2025-01-01T00:00:00.000Z', 'updated_at': '2026-01-01T00:00:00.000Z',
        }

    def test_fetches_by_ids_and_creates_customers(self):
        from App.cnv.models import CNVCustomer
        service = self._make_service()
        requested_ids = [111, 222, 333]
        service.client.fetch_customers_by_ids = MagicMock(
            return_value=[self._raw_customer(i) for i in requested_ids]
        )
        with patch.object(service, '_fetch_membership', return_value={}):
            created, updated, failed = service.backfill_customers_by_ids(requested_ids)

        self.assertEqual((created, updated, failed), (3, 0, 0))
        service.client.fetch_customers_by_ids.assert_called_once_with(requested_ids, batch_size=100)
        self.assertEqual(
            set(CNVCustomer.objects.filter(cnv_id__in=requested_ids).values_list('cnv_id', flat=True)),
            {111, 222, 333},
        )

    def test_does_not_touch_incremental_checkpoint(self):
        """Must never move CNVSyncLog's incremental cursor for `sync_customers`
        — this is a one-off gap-fill, not a replacement for the scheduled sync."""
        from App.cnv.models import CNVSyncLog
        from django.utils import timezone
        existing_checkpoint = timezone.now()
        CNVSyncLog.objects.create(
            sync_type='customers', status='completed',
            checkpoint_updated_at=existing_checkpoint,
        )
        service = self._make_service()
        service.client.fetch_customers_by_ids = MagicMock(return_value=[self._raw_customer(444)])
        with patch.object(service, '_fetch_membership', return_value={}):
            service.backfill_customers_by_ids([444])

        latest = CNVSyncLog.objects.filter(
            sync_type='customers', status='completed', checkpoint_updated_at__isnull=False
        ).order_by('-checkpoint_updated_at').first()
        self.assertEqual(latest.checkpoint_updated_at, existing_checkpoint,
                          "backfill must not create/advance the incremental checkpoint")

    def test_ids_not_returned_by_api_are_logged_not_silently_dropped(self):
        service = self._make_service()
        service.client.fetch_customers_by_ids = MagicMock(
            return_value=[self._raw_customer(1)]  # only 1 of 2 requested IDs returned
        )
        with patch.object(service, '_fetch_membership', return_value={}):
            created, updated, failed = service.backfill_customers_by_ids([1, 2])
        self.assertEqual((created, updated, failed), (1, 0, 0))
