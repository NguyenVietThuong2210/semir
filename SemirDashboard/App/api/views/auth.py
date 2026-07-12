"""App/api/views/auth.py — JWT login / refresh / logout
Split from api/views.py (R4, 2026-07-12).
"""
import logging
from datetime import datetime, timedelta

from django.db.models import Count, Q, Sum
from rest_framework import status
from rest_framework.exceptions import APIException
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.response import Response
from rest_framework.throttling import AnonRateThrottle
from rest_framework.views import APIView
from rest_framework_simplejwt.tokens import RefreshToken
from rest_framework_simplejwt.exceptions import TokenError, InvalidToken

from App.permissions import user_has_perm, PERMISSION_DEFS
from App.api.permissions import make_perm_class

logger = logging.getLogger('App')
from .helpers import _get_user_permissions, _LoginThrottle

class LoginView(APIView):
    """POST /api/v1/auth/token/ — Login, returns JWT pair + permissions."""
    permission_classes = [AllowAny]
    throttle_classes = [_LoginThrottle]

    def post(self, request):
        from django.contrib.auth import authenticate
        username = request.data.get('username', '')
        password = request.data.get('password', '')

        user = authenticate(request, username=username, password=password)
        if user is None or not user.is_active:
            return Response(
                {'detail': 'No active account found with the given credentials'},
                status=status.HTTP_401_UNAUTHORIZED,
            )

        refresh = RefreshToken.for_user(user)
        access = refresh.access_token
        expires_in = int(
            (access.payload['exp'] - access.payload['iat'])
        )

        return Response({
            'access': str(access),
            'refresh': str(refresh),
            'access_expires_in': expires_in,
            'username': user.username,
            'permissions': _get_user_permissions(user),
        })


class TokenRefreshView(APIView):
    """POST /api/v1/auth/token/refresh/ — Silent JWT refresh."""
    permission_classes = [AllowAny]

    def post(self, request):
        refresh_token = request.data.get('refresh', '')
        if not refresh_token:
            return Response(
                {'detail': 'Refresh token is required'},
                status=status.HTTP_400_BAD_REQUEST,
            )
        try:
            refresh = RefreshToken(refresh_token)
            # C-04 phase 1: issue a rotated refresh token alongside the access token.
            # The old refresh token is NOT blacklisted yet — mobile clients that do not
            # store the new token keep working. Blacklisting is enabled in phase 2
            # once the mobile app persists the rotated token.
            refresh.set_jti()
            refresh.set_exp()
            access = refresh.access_token
            expires_in = int(access.payload['exp'] - access.payload['iat'])
            return Response({
                'access': str(access),
                'refresh': str(refresh),
                'access_expires_in': expires_in,
            })
        except (TokenError, InvalidToken):
            return Response(
                {'detail': 'Token is invalid or expired'},
                status=status.HTTP_401_UNAUTHORIZED,
            )


class LogoutView(APIView):
    """POST /api/v1/auth/logout/ — Revoke refresh token. Idempotent."""
    permission_classes = [IsAuthenticated]

    def post(self, request):
        refresh_token = request.data.get('refresh', '')
        try:
            token = RefreshToken(refresh_token)
            token.blacklist()
        except (TokenError, InvalidToken):
            pass  # Already blacklisted or invalid — still return 205
        return Response(status=status.HTTP_205_RESET_CONTENT)


# ═══════════════════════════════════════════════════════════════════════════════
# ANALYTICS ENDPOINTS
# ═══════════════════════════════════════════════════════════════════════════════

