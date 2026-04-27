import 'dart:async';

import 'package:dio/dio.dart';

import '../auth/auth_service.dart';
import '../auth/token_storage.dart';

/// JWT refresh interceptor with concurrent-401 serialisation.
///
/// When multiple requests get a 401 simultaneously:
///   - Exactly 1 token refresh call is made
///   - All pending requests are queued and retried with the new token
///   - If the refresh fails, all pending requests fail with SessionExpiredException
///
/// This prevents the N-parallel-401 → N-refresh-calls race condition.
class AuthInterceptor extends Interceptor {
  AuthInterceptor({
    required TokenStorage storage,
    required AuthService authService,
    required void Function() onSessionExpired,
    /// Dio for token-refreshed retries. Injected via bareDioProvider in
    /// production (fully configured, no auth interceptor). In tests, inject
    /// a MockDio to avoid real HTTP calls.
    Dio? retryClient,
  })  : _storage = storage,
        _authService = authService,
        _onSessionExpired = onSessionExpired,
        _retryClient = retryClient;

  final TokenStorage _storage;
  final AuthService _authService;
  final void Function() _onSessionExpired;
  final Dio? _retryClient;

  bool _isRefreshing = false;
  final List<_PendingRequest> _pendingRequests = [];

  @override
  Future<void> onRequest(
    RequestOptions options,
    RequestInterceptorHandler handler,
  ) async {
    final token = await _storage.readAccessToken();
    if (token != null) {
      options.headers['Authorization'] = 'Bearer $token';
    }
    handler.next(options);
  }

  @override
  Future<void> onError(
    DioException err,
    ErrorInterceptorHandler handler,
  ) async {
    if (err.response?.statusCode != 401) {
      handler.next(err);
      return;
    }

    // Skip refresh if this request itself is the refresh call (avoids loop).
    if (err.requestOptions.path.contains('/auth/token/refresh/')) {
      _onSessionExpired();
      handler.next(err);
      return;
    }

    final refreshToken = await _storage.readRefreshToken();
    if (refreshToken == null) {
      _onSessionExpired();
      handler.next(err);
      return;
    }

    if (_isRefreshing) {
      // Queue this request — the in-flight refresh will retry it.
      final completer = Completer<Response<dynamic>>();
      _pendingRequests.add(_PendingRequest(err.requestOptions, completer));
      try {
        final response = await completer.future;
        handler.resolve(response);
      } catch (e) {
        handler.next(err);
      }
      return;
    }

    _isRefreshing = true;
    try {
      final newToken = await _authService.refresh(refreshToken);
      // Drain the queue with new token (fire-and-forget each pending retry).
      for (final pending in _pendingRequests) {
        _retryRequest(pending.options, newToken)
            .then(pending.completer.complete)
            .catchError(pending.completer.completeError);
      }
      _pendingRequests.clear();
      // Retry the original request.
      try {
        final retried = await _retryRequest(err.requestOptions, newToken);
        handler.resolve(retried);
      } catch (retryErr) {
        handler.next(err);
      }
    } on SessionExpiredException {
      for (final pending in _pendingRequests) {
        pending.completer.completeError(const SessionExpiredException());
      }
      _pendingRequests.clear();
      _onSessionExpired();
      handler.next(err);
    } catch (_) {
      // Unexpected error during refresh — drain queue and propagate.
      for (final pending in _pendingRequests) {
        pending.completer.completeError(_);
      }
      _pendingRequests.clear();
      handler.next(err);
    } finally {
      _isRefreshing = false;
    }
  }

  Future<Response<dynamic>> _retryRequest(
    RequestOptions options,
    String newToken,
  ) {
    assert(_retryClient != null, 'retryClient must be injected via bareDioProvider');
    final dio = _retryClient!;
    return dio.fetch(
      options.copyWith(
        headers: {...options.headers, 'Authorization': 'Bearer $newToken'},
      ),
    );
  }
}

class _PendingRequest {
  _PendingRequest(this.options, this.completer);
  final RequestOptions options;
  final Completer<Response<dynamic>> completer;
}
