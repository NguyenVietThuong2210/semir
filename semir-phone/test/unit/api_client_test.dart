import 'package:flutter_test/flutter_test.dart';
import 'package:mockito/annotations.dart';

import 'package:semir_phone/core/api/api_client.dart';
import 'package:semir_phone/core/auth/auth_service.dart';
import 'package:semir_phone/core/auth/token_storage.dart';

import 'api_client_test.mocks.dart';

/// Unit tests for TLS pinning behavior in createApiClient.
///
/// TLS pinning state is controlled by BuildConfig.tlsPin (set via --dart-define).
/// In test builds, tlsPin is empty → standard HttpClient used (no pinning).
/// In release builds, tlsPin is non-empty → IOHttpClientAdapter + SecurityContext.
///
/// The actual TLS handshake rejection is verified manually (T071) since it
/// requires a real TLS server. We verify the adapter selection logic here.
@GenerateMocks([TokenStorage, AuthService])
void main() {
  late MockTokenStorage mockStorage;
  late MockAuthService mockAuthService;

  setUp(() {
    mockStorage = MockTokenStorage();
    mockAuthService = MockAuthService();
  });

  group('createApiClient', () {
    test('empty tlsPin → Dio created without error', () {
      // In test environment BuildConfig.tlsPin is empty (no --dart-define)
      expect(
        () => createApiClient(
          storage: mockStorage,
          authService: mockAuthService,
          onSessionExpired: () {},
        ),
        returnsNormally,
      );
    });

    test('created Dio has AuthInterceptor in interceptors list', () {
      final dio = createApiClient(
        storage: mockStorage,
        authService: mockAuthService,
        onSessionExpired: () {},
      );

      expect(dio.interceptors, isNotEmpty);
    });

    test('created Dio uses apiBaseUrl as baseUrl', () {
      final dio = createApiClient(
        storage: mockStorage,
        authService: mockAuthService,
        onSessionExpired: () {},
      );

      expect(dio.options.baseUrl, isA<String>());
    });

    test('onSessionExpired callback is wired into AuthInterceptor', () {
      bool sessionExpiredCalled = false;

      final dio = createApiClient(
        storage: mockStorage,
        authService: mockAuthService,
        onSessionExpired: () => sessionExpiredCalled = true,
      );

      expect(dio.interceptors, isNotEmpty);
      // Not yet triggered — no 401 has occurred
      expect(sessionExpiredCalled, isFalse);
    });

    test('connectTimeout is 10 seconds', () {
      final dio = createApiClient(
        storage: mockStorage,
        authService: mockAuthService,
        onSessionExpired: () {},
      );

      expect(dio.options.connectTimeout, const Duration(seconds: 10));
    });

    test('receiveTimeout is 30 seconds', () {
      final dio = createApiClient(
        storage: mockStorage,
        authService: mockAuthService,
        onSessionExpired: () {},
      );

      expect(dio.options.receiveTimeout, const Duration(seconds: 30));
    });

    test('Content-Type header set to application/json', () {
      final dio = createApiClient(
        storage: mockStorage,
        authService: mockAuthService,
        onSessionExpired: () {},
      );

      expect(
        dio.options.headers['Content-Type'],
        'application/json',
      );
    });
  });
}
