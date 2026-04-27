import 'dart:async';
import 'package:dio/dio.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:mockito/annotations.dart';
import 'package:mockito/mockito.dart';

import 'package:semir_phone/core/auth/auth_service.dart';
import 'package:semir_phone/core/auth/token_storage.dart';
import 'package:semir_phone/core/api/auth_interceptor.dart';

import 'auth_interceptor_test.mocks.dart';

/// Subclass that no-ops next/resolve to prevent Dio's internal completer from
/// completing with an error when called in test isolation (no Dio chain).
class _SilentErrorHandler extends ErrorInterceptorHandler {
  @override
  void next(DioException err) {}
  @override
  void resolve(Response response) {}
  @override
  void reject(DioException err, [bool callFollowingErrorInterceptors = false]) {}
}

@GenerateMocks([TokenStorage, AuthService, Dio])
void main() {
  late MockTokenStorage mockStorage;
  late MockAuthService mockAuthService;
  late MockDio mockRetryDio;
  late int sessionExpiredCallCount;
  late AuthInterceptor interceptor;

  setUp(() {
    mockStorage = MockTokenStorage();
    mockAuthService = MockAuthService();
    mockRetryDio = MockDio();
    sessionExpiredCallCount = 0;
    // Stub retry requests to succeed immediately — avoids real HTTP calls.
    when(mockRetryDio.fetch(any)).thenAnswer((_) async => Response(
          requestOptions: RequestOptions(path: '/'),
          statusCode: 200,
          data: <String, dynamic>{},
        ));
    interceptor = AuthInterceptor(
      storage: mockStorage,
      authService: mockAuthService,
      onSessionExpired: () => sessionExpiredCallCount++,
      retryClient: mockRetryDio,
    );
  });

  group('AuthInterceptor', () {
    test('onRequest injects Bearer token from storage', () async {
      when(mockStorage.readAccessToken())
          .thenAnswer((_) async => 'injected_token');

      final options = RequestOptions(path: '/analytics/sales/');
      final handler = RequestInterceptorHandler();

      await interceptor.onRequest(options, handler);
      expect(options.headers['Authorization'], 'Bearer injected_token');
    });

    test('single 401 triggers exactly 1 refresh call', () async {
      var refreshCallCount = 0;
      when(mockStorage.readRefreshToken())
          .thenAnswer((_) async => 'refresh_token');
      when(mockAuthService.refresh('refresh_token')).thenAnswer((_) async {
        refreshCallCount++;
        return 'new_access_token';
      });

      final err = DioException(
        requestOptions: RequestOptions(path: '/analytics/sales/'),
        response: Response(
          requestOptions: RequestOptions(path: '/analytics/sales/'),
          statusCode: 401,
        ),
        type: DioExceptionType.badResponse,
      );

      await interceptor.onError(err, _SilentErrorHandler());

      expect(refreshCallCount, 1,
          reason: 'Exactly 1 refresh call for a single 401');
      expect(sessionExpiredCallCount, 0);
    });

    test('refresh failure triggers session expiry and clears queue', () async {
      when(mockStorage.readRefreshToken())
          .thenAnswer((_) async => 'expired_refresh');
      when(mockAuthService.refresh('expired_refresh'))
          .thenThrow(const SessionExpiredException());

      final err = DioException(
        requestOptions: RequestOptions(path: '/analytics/sales/'),
        response: Response(
          requestOptions: RequestOptions(path: '/analytics/sales/'),
          statusCode: 401,
        ),
        type: DioExceptionType.badResponse,
      );

      await interceptor.onError(err, _SilentErrorHandler());

      expect(sessionExpiredCallCount, 1,
          reason: 'Session expiry callback fired once');
    });

    test('no refresh token → session expired immediately', () async {
      when(mockStorage.readRefreshToken()).thenAnswer((_) async => null);

      final err = DioException(
        requestOptions: RequestOptions(path: '/analytics/sales/'),
        response: Response(
          requestOptions: RequestOptions(path: '/analytics/sales/'),
          statusCode: 401,
        ),
        type: DioExceptionType.badResponse,
      );

      await interceptor.onError(err, _SilentErrorHandler());

      verifyNever(mockAuthService.refresh(any));
      expect(sessionExpiredCallCount, 1);
    });

    test('non-401 errors are passed through without refresh', () async {
      final err = DioException(
        requestOptions: RequestOptions(path: '/analytics/sales/'),
        response: Response(
          requestOptions: RequestOptions(path: '/analytics/sales/'),
          statusCode: 500,
        ),
        type: DioExceptionType.badResponse,
      );

      await interceptor.onError(err, _SilentErrorHandler());

      verifyNever(mockAuthService.refresh(any));
      expect(sessionExpiredCallCount, 0);
    });

    test('concurrent 401s: exactly 1 refresh call, all requests retried', () async {
      // SC-003: concurrent 401s must serialise to exactly 1 refresh call.
      var refreshCallCount = 0;
      when(mockStorage.readRefreshToken())
          .thenAnswer((_) async => 'refresh_token');
      when(mockAuthService.refresh('refresh_token')).thenAnswer((_) async {
        await Future.delayed(const Duration(milliseconds: 50));
        refreshCallCount++;
        return 'new_access_token';
      });

      final errors = List.generate(
        3,
        (i) => DioException(
          requestOptions: RequestOptions(path: '/analytics/sales/$i'),
          response: Response(
            requestOptions: RequestOptions(path: '/analytics/sales/$i'),
            statusCode: 401,
          ),
          type: DioExceptionType.badResponse,
        ),
      );

      await Future.wait(
        errors.map((err) => interceptor.onError(err, _SilentErrorHandler())),
      );

      expect(refreshCallCount, 1,
          reason: 'Concurrent 401s must trigger exactly 1 refresh call');
      expect(sessionExpiredCallCount, 0);
    });
  });
}
