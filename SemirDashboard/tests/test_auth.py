"""
tests/test_auth.py — API auth endpoint tests.

Covers:
  POST /api/v1/auth/token/        — login
  POST /api/v1/auth/token/refresh/ — silent refresh
  POST /api/v1/auth/logout/       — token revocation

No fixture data needed — these tests create their own users.
"""
import json
from django.contrib.auth.models import User
from django.test import override_settings
from rest_framework_simplejwt.tokens import RefreshToken

from tests.base import SnapshotTestCase

LOGIN_URL   = '/api/v1/auth/token/'
REFRESH_URL = '/api/v1/auth/token/refresh/'
LOGOUT_URL  = '/api/v1/auth/logout/'

# Disable throttling for all auth tests — throttle is tested separately
_NO_THROTTLE = override_settings(
    DEFAULT_THROTTLE_RATES={'anon': '10000/min', 'user': '10000/min', 'login': '10000/min'}
)


@_NO_THROTTLE
class LoginTest(SnapshotTestCase):
    @classmethod
    def setUpTestData(cls):
        cls.user = User.objects.create_user(
            username='test_login_user',
            password='StrongPass123!',
            is_active=True,
        )

    def setUp(self):
        super().setUp()
        from django.core.cache import cache
        cache.clear()

    def _post(self, url, data):
        return self.client.post(
            url,
            data=json.dumps(data),
            content_type='application/json',
        )

    # ── Happy path ────────────────────────────────────────────────────────────

    def test_login_success_returns_200(self):
        resp = self._post(LOGIN_URL, {'username': 'test_login_user', 'password': 'StrongPass123!'})
        self.assertEqual(resp.status_code, 200)

    def test_login_response_has_required_fields(self):
        resp = self._post(LOGIN_URL, {'username': 'test_login_user', 'password': 'StrongPass123!'})
        data = resp.json()
        for field in ('access', 'refresh', 'access_expires_in', 'username', 'permissions'):
            self.assertIn(field, data, f"Missing field: {field}")

    def test_login_returns_correct_username(self):
        resp = self._post(LOGIN_URL, {'username': 'test_login_user', 'password': 'StrongPass123!'})
        self.assertEqual(resp.json()['username'], 'test_login_user')

    def test_login_access_expires_in_is_positive(self):
        resp = self._post(LOGIN_URL, {'username': 'test_login_user', 'password': 'StrongPass123!'})
        self.assertGreater(resp.json()['access_expires_in'], 0)

    def test_login_permissions_is_list(self):
        resp = self._post(LOGIN_URL, {'username': 'test_login_user', 'password': 'StrongPass123!'})
        self.assertIsInstance(resp.json()['permissions'], list)

    # ── Wrong credentials ─────────────────────────────────────────────────────

    def test_login_wrong_password_returns_401(self):
        resp = self._post(LOGIN_URL, {'username': 'test_login_user', 'password': 'WrongPass!'})
        self.assertEqual(resp.status_code, 401)

    def test_login_nonexistent_user_returns_401(self):
        resp = self._post(LOGIN_URL, {'username': 'nobody', 'password': 'anything'})
        self.assertEqual(resp.status_code, 401)

    def test_login_empty_credentials_returns_401(self):
        resp = self._post(LOGIN_URL, {'username': '', 'password': ''})
        self.assertEqual(resp.status_code, 401)

    def test_login_missing_password_field_returns_401(self):
        resp = self._post(LOGIN_URL, {'username': 'test_login_user'})
        self.assertEqual(resp.status_code, 401)

    # ── Inactive user ─────────────────────────────────────────────────────────

    def test_login_inactive_user_returns_401(self):
        User.objects.create_user(
            username='inactive_user_auth',
            password='Pass123!',
            is_active=False,
        )
        resp = self._post(LOGIN_URL, {'username': 'inactive_user_auth', 'password': 'Pass123!'})
        self.assertEqual(resp.status_code, 401)

    # ── Method guard ─────────────────────────────────────────────────────────

    def test_login_get_method_not_allowed(self):
        resp = self.client.get(LOGIN_URL)
        self.assertEqual(resp.status_code, 405)


class TokenRefreshTest(SnapshotTestCase):
    @classmethod
    def setUpTestData(cls):
        cls.user = User.objects.create_user(
            username='test_refresh_user',
            password='StrongPass123!',
        )

    def _get_tokens(self):
        refresh = RefreshToken.for_user(self.user)
        return str(refresh), str(refresh.access_token)

    def _post(self, url, data):
        return self.client.post(
            url,
            data=json.dumps(data),
            content_type='application/json',
        )

    # ── Happy path ────────────────────────────────────────────────────────────

    def test_refresh_returns_200(self):
        refresh_token, _ = self._get_tokens()
        resp = self._post(REFRESH_URL, {'refresh': refresh_token})
        self.assertEqual(resp.status_code, 200)

    def test_refresh_response_has_access_and_expires_in(self):
        refresh_token, _ = self._get_tokens()
        resp = self._post(REFRESH_URL, {'refresh': refresh_token})
        data = resp.json()
        self.assertIn('access', data)
        self.assertIn('access_expires_in', data)

    def test_refresh_new_access_token_is_different_from_original(self):
        refresh_token, original_access = self._get_tokens()
        resp = self._post(REFRESH_URL, {'refresh': refresh_token})
        new_access = resp.json()['access']
        # Tokens are JWTs with different iat — they must differ
        self.assertNotEqual(new_access, original_access)

    def test_refresh_expires_in_positive(self):
        refresh_token, _ = self._get_tokens()
        resp = self._post(REFRESH_URL, {'refresh': refresh_token})
        self.assertGreater(resp.json()['access_expires_in'], 0)

    # ── Invalid / missing token ───────────────────────────────────────────────

    def test_refresh_invalid_token_returns_401(self):
        resp = self._post(REFRESH_URL, {'refresh': 'not.a.real.jwt'})
        self.assertEqual(resp.status_code, 401)

    def test_refresh_empty_token_returns_400(self):
        resp = self._post(REFRESH_URL, {'refresh': ''})
        self.assertEqual(resp.status_code, 400)

    def test_refresh_missing_field_returns_400(self):
        resp = self._post(REFRESH_URL, {})
        self.assertEqual(resp.status_code, 400)

    def test_refresh_blacklisted_token_returns_401(self):
        """Token blacklisted via logout must not refresh."""
        refresh = RefreshToken.for_user(self.user)
        refresh_str = str(refresh)
        refresh.blacklist()
        resp = self._post(REFRESH_URL, {'refresh': refresh_str})
        self.assertEqual(resp.status_code, 401)


class LogoutTest(SnapshotTestCase):
    @classmethod
    def setUpTestData(cls):
        cls.user = User.objects.create_user(
            username='test_logout_user',
            password='StrongPass123!',
        )

    def _get_tokens(self):
        refresh = RefreshToken.for_user(self.user)
        return str(refresh), str(refresh.access_token)

    def _post(self, url, data, access_token=None):
        headers = {}
        if access_token:
            headers['HTTP_AUTHORIZATION'] = f'Bearer {access_token}'
        return self.client.post(
            url,
            data=json.dumps(data),
            content_type='application/json',
            **headers,
        )

    # ── Happy path ────────────────────────────────────────────────────────────

    def test_logout_returns_205(self):
        refresh_token, access_token = self._get_tokens()
        resp = self._post(LOGOUT_URL, {'refresh': refresh_token}, access_token=access_token)
        self.assertEqual(resp.status_code, 205)

    def test_logout_blacklists_refresh_token(self):
        """After logout, the refresh token must be rejected."""
        refresh_token, access_token = self._get_tokens()
        self._post(LOGOUT_URL, {'refresh': refresh_token}, access_token=access_token)

        # Now try to use the refresh token — must be 401
        resp = self.client.post(
            REFRESH_URL,
            data=json.dumps({'refresh': refresh_token}),
            content_type='application/json',
        )
        self.assertEqual(resp.status_code, 401)

    def test_logout_idempotent_double_call_returns_205(self):
        """Logging out twice must still return 205 (idempotent)."""
        refresh_token, access_token = self._get_tokens()
        self._post(LOGOUT_URL, {'refresh': refresh_token}, access_token=access_token)
        # Second call — token already blacklisted
        refresh_token2, access_token2 = self._get_tokens()
        resp = self._post(LOGOUT_URL, {'refresh': 'already.blacklisted.token'}, access_token=access_token2)
        self.assertEqual(resp.status_code, 205)

    # ── Auth required ─────────────────────────────────────────────────────────

    def test_logout_without_bearer_returns_401(self):
        refresh_token, _ = self._get_tokens()
        resp = self._post(LOGOUT_URL, {'refresh': refresh_token})
        self.assertEqual(resp.status_code, 401)

    def test_logout_with_invalid_bearer_returns_401(self):
        resp = self._post(LOGOUT_URL, {'refresh': 'token'}, access_token='bad.access.token')
        self.assertEqual(resp.status_code, 401)
