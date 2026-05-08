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
