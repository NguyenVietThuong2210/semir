import 'package:dio/dio.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:mockito/annotations.dart';
import 'package:mockito/mockito.dart';

import 'package:semir_phone/core/auth/auth_service.dart';
import 'package:semir_phone/core/auth/token_storage.dart';

import 'auth_service_test.mocks.dart';

@GenerateMocks([Dio, TokenStorage])
void main() {
  late MockDio mockDio;
  late MockTokenStorage mockStorage;
  late AuthService authService;

  setUp(() {
    mockDio = MockDio();
    mockStorage = MockTokenStorage();
    authService = AuthService(dio: mockDio, storage: mockStorage);
    when(mockStorage.saveTokens(
      access: anyNamed('access'),
      refresh: anyNamed('refresh'),
      expiry: anyNamed('expiry'),
      username: anyNamed('username'),
      permissions: anyNamed('permissions'),
    )).thenAnswer((_) async {});
    when(mockStorage.updateAccessToken(any, any)).thenAnswer((_) async {});
    when(mockStorage.deleteAll()).thenAnswer((_) async {});
  });

  group('AuthService.login', () {
    test('200 → UserSession with correct fields', () async {
      when(mockDio.post(
        any,
        data: anyNamed('data'),
        options: anyNamed('options'),
      )).thenAnswer((_) async => Response(
            requestOptions: RequestOptions(path: '/api/v1/auth/token/'),
            statusCode: 200,
            data: {
              'access': 'access_token_abc',
              'refresh': 'refresh_token_xyz',
              'username': 'testuser',
              'permissions': ['sales.view', 'shop_detail.view'],
              'access_expires_in': 3600,
            },
          ));

      final session = await authService.login('testuser', 'password');

      expect(session.username, 'testuser');
      expect(session.accessToken, 'access_token_abc');
      expect(session.refreshToken, 'refresh_token_xyz');
      expect(session.permissions, containsAll(['sales.view', 'shop_detail.view']));
    });

    test('401 → throws AuthException', () async {
      when(mockDio.post(
        any,
        data: anyNamed('data'),
        options: anyNamed('options'),
      )).thenThrow(DioException(
        requestOptions: RequestOptions(path: '/api/v1/auth/token/'),
        response: Response(
          requestOptions: RequestOptions(path: '/api/v1/auth/token/'),
          statusCode: 401,
          data: {'detail': 'No active account found with the given credentials'},
        ),
        type: DioExceptionType.badResponse,
      ));

      expect(() => authService.login('bad', 'creds'), throwsA(isA<AuthException>()));
    });

    test('network error → throws AuthException', () async {
      when(mockDio.post(
        any,
        data: anyNamed('data'),
        options: anyNamed('options'),
      )).thenThrow(DioException(
        requestOptions: RequestOptions(path: '/api/v1/auth/token/'),
        type: DioExceptionType.connectionError,
      ));

      expect(() => authService.login('user', 'pass'), throwsA(isA<AuthException>()));
    });
  });

  group('AuthService.logout', () {
    test('calls POST /api/v1/auth/logout/ with refresh token', () async {
      when(mockDio.post(
        any,
        data: anyNamed('data'),
        options: anyNamed('options'),
      )).thenAnswer((_) async => Response(
            requestOptions: RequestOptions(path: '/api/v1/auth/logout/'),
            statusCode: 205,
          ));

      await authService.logout('refresh_token_xyz');

      verify(mockDio.post(
        argThat(contains('logout')),
        data: {'refresh': 'refresh_token_xyz'},
        options: anyNamed('options'),
      )).called(1);
    });

    test('server error during logout does not throw (best-effort)', () async {
      when(mockDio.post(
        any,
        data: anyNamed('data'),
        options: anyNamed('options'),
      )).thenThrow(DioException(
        requestOptions: RequestOptions(path: '/api/v1/auth/logout/'),
        type: DioExceptionType.connectionError,
      ));

      // Should complete without throwing
      await expectLater(authService.logout('token'), completes);
    });
  });

  group('AuthService.refresh', () {
    test('200 → returns new access token', () async {
      when(mockDio.post(
        any,
        data: anyNamed('data'),
        options: anyNamed('options'),
      )).thenAnswer((_) async => Response(
            requestOptions: RequestOptions(path: '/api/v1/auth/token/refresh/'),
            statusCode: 200,
            data: {'access': 'new_access_token'},
          ));

      final newToken = await authService.refresh('valid_refresh_token');
      expect(newToken, 'new_access_token');
    });

    test('401 → throws SessionExpiredException', () async {
      when(mockDio.post(
        any,
        data: anyNamed('data'),
        options: anyNamed('options'),
      )).thenThrow(DioException(
        requestOptions: RequestOptions(path: '/api/v1/auth/token/refresh/'),
        response: Response(
          requestOptions: RequestOptions(path: '/api/v1/auth/token/refresh/'),
          statusCode: 401,
          data: {'detail': 'Token is blacklisted'},
        ),
        type: DioExceptionType.badResponse,
      ));

      expect(
        () => authService.refresh('expired_refresh_token'),
        throwsA(isA<SessionExpiredException>()),
      );
    });
  });
}
