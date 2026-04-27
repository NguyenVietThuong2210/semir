import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:mockito/annotations.dart';
import 'package:mockito/mockito.dart';

import 'package:semir_phone/core/auth/auth_service.dart';
import 'package:semir_phone/core/auth/auth_provider.dart';
import 'package:semir_phone/core/auth/token_storage.dart';

import 'auth_provider_test.mocks.dart';

@GenerateMocks([TokenStorage, AuthService])
void main() {
  late MockTokenStorage mockStorage;
  late MockAuthService mockAuthService;

  ProviderContainer buildContainer() {
    return ProviderContainer(
      overrides: [
        tokenStorageProvider.overrideWithValue(mockStorage),
        authServiceProvider.overrideWithValue(mockAuthService),
      ],
    );
  }

  setUp(() {
    mockStorage = MockTokenStorage();
    mockAuthService = MockAuthService();
    // Default: no stored session
    when(mockStorage.readAccessToken()).thenAnswer((_) async => null);
    when(mockStorage.readRefreshToken()).thenAnswer((_) async => null);
    when(mockStorage.readPermissions()).thenAnswer((_) async => []);
    when(mockStorage.readUsername()).thenAnswer((_) async => null);
    when(mockStorage.readAccessTokenExpiry()).thenAnswer((_) async => null);
  });

  group('AuthNotifier', () {
    test('initial state is null (no stored tokens)', () async {
      final container = buildContainer();
      addTearDown(container.dispose);

      final state = await container.read(authProvider.future);
      expect(state, isNull);
    });

    test('login → UserSession with correct permissions and username', () async {
      final session = UserSession(
        username: 'admin',
        accessToken: 'access_abc',
        refreshToken: 'refresh_xyz',
        accessTokenExpiry: DateTime.now().add(const Duration(hours: 1)),
        permissions: ['sales.view', 'customer_detail.view'],
      );
      when(mockAuthService.login('admin', 'pass123'))
          .thenAnswer((_) async => session);
      when(mockStorage.saveTokens(
        access: anyNamed('access'),
        refresh: anyNamed('refresh'),
        expiry: anyNamed('expiry'),
        username: anyNamed('username'),
        permissions: anyNamed('permissions'),
      )).thenAnswer((_) async {});

      final container = buildContainer();
      addTearDown(container.dispose);

      // Wait for initial build
      await container.read(authProvider.future);

      final notifier = container.read(authProvider.notifier);
      await notifier.login('admin', 'pass123');

      final state = await container.read(authProvider.future);
      expect(state, isNotNull);
      expect(state!.username, 'admin');
      expect(state.permissions, containsAll(['sales.view', 'customer_detail.view']));
    });

    test('logout → state becomes null', () async {
      // Seed stored tokens
      when(mockStorage.readAccessToken()).thenAnswer((_) async => 'stored_access');
      when(mockStorage.readRefreshToken()).thenAnswer((_) async => 'stored_refresh');
      when(mockStorage.readPermissions()).thenAnswer((_) async => ['sales.view']);
      when(mockStorage.readUsername()).thenAnswer((_) async => 'admin');
      when(mockAuthService.logout(any)).thenAnswer((_) async {});
      when(mockStorage.deleteAll()).thenAnswer((_) async {});

      final container = buildContainer();
      addTearDown(container.dispose);

      // Restore session
      await container.read(authProvider.future);

      final notifier = container.read(authProvider.notifier);
      await notifier.logout();

      final state = await container.read(authProvider.future);
      expect(state, isNull);
    });

    test('restoreSession with stored valid tokens → UserSession', () async {
      when(mockStorage.readAccessToken()).thenAnswer((_) async => 'valid_access');
      when(mockStorage.readRefreshToken()).thenAnswer((_) async => 'valid_refresh');
      when(mockStorage.readPermissions()).thenAnswer((_) async => ['sales.view']);
      when(mockStorage.readUsername()).thenAnswer((_) async => 'storemanager');

      final container = buildContainer();
      addTearDown(container.dispose);

      final state = await container.read(authProvider.future);
      expect(state, isNotNull);
      expect(state!.username, 'storemanager');
      expect(state.hasPermission('sales.view'), isTrue);
    });

    test('hasPermission returns false for unlisted permission', () async {
      when(mockStorage.readAccessToken()).thenAnswer((_) async => 'access');
      when(mockStorage.readRefreshToken()).thenAnswer((_) async => 'refresh');
      when(mockStorage.readPermissions()).thenAnswer((_) async => ['sales.view']);
      when(mockStorage.readUsername()).thenAnswer((_) async => 'user');

      final container = buildContainer();
      addTearDown(container.dispose);

      final state = await container.read(authProvider.future);
      expect(state!.hasPermission('admin.access'), isFalse);
    });
  });
}
