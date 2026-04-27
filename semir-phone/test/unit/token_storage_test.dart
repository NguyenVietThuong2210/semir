import 'package:flutter_test/flutter_test.dart';
import 'package:flutter_secure_storage/flutter_secure_storage.dart';
import 'package:mockito/annotations.dart';
import 'package:mockito/mockito.dart';
import 'package:semir_phone/core/auth/token_storage.dart';

import 'token_storage_test.mocks.dart';

@GenerateMocks([FlutterSecureStorage])
void main() {
  late MockFlutterSecureStorage mockStorage;
  late TokenStorage tokenStorage;

  setUp(() {
    mockStorage = MockFlutterSecureStorage();
    tokenStorage = TokenStorage(storage: mockStorage);
  });

  group('TokenStorage', () {
    test('saveTokens stores all fields', () async {
      when(mockStorage.write(key: anyNamed('key'), value: anyNamed('value')))
          .thenAnswer((_) async {});

      final expiry = DateTime(2026, 1, 1, 12, 0, 0).toUtc();
      await tokenStorage.saveTokens(
        access: 'access_token_123',
        refresh: 'refresh_token_456',
        expiry: expiry,
        username: 'testuser',
        permissions: ['sales.view', 'cnv.view'],
      );

      verify(mockStorage.write(key: 'access_token', value: 'access_token_123'))
          .called(1);
      verify(mockStorage.write(key: 'refresh_token', value: 'refresh_token_456'))
          .called(1);
      verify(mockStorage.write(key: 'username', value: 'testuser')).called(1);
      verify(mockStorage.write(
        key: 'permissions',
        value: '["sales.view","cnv.view"]',
      )).called(1);
    });

    test('readAccessToken returns stored value', () async {
      when(mockStorage.read(key: 'access_token'))
          .thenAnswer((_) async => 'stored_access');
      expect(await tokenStorage.readAccessToken(), 'stored_access');
    });

    test('readRefreshToken returns stored value', () async {
      when(mockStorage.read(key: 'refresh_token'))
          .thenAnswer((_) async => 'stored_refresh');
      expect(await tokenStorage.readRefreshToken(), 'stored_refresh');
    });

    test('readAccessToken returns null when not stored', () async {
      when(mockStorage.read(key: 'access_token')).thenAnswer((_) async => null);
      expect(await tokenStorage.readAccessToken(), isNull);
    });

    test('readRefreshToken returns null when not stored', () async {
      when(mockStorage.read(key: 'refresh_token'))
          .thenAnswer((_) async => null);
      expect(await tokenStorage.readRefreshToken(), isNull);
    });

    test('both tokens stored independently', () async {
      when(mockStorage.read(key: 'access_token'))
          .thenAnswer((_) async => 'access_value');
      when(mockStorage.read(key: 'refresh_token'))
          .thenAnswer((_) async => 'refresh_value');

      expect(await tokenStorage.readAccessToken(), 'access_value');
      expect(await tokenStorage.readRefreshToken(), 'refresh_value');
    });

    test('biometric flag persists', () async {
      when(mockStorage.write(key: anyNamed('key'), value: anyNamed('value')))
          .thenAnswer((_) async {});
      when(mockStorage.read(key: 'biometric_enabled'))
          .thenAnswer((_) async => 'true');

      await tokenStorage.saveBiometricEnabled(true);
      expect(await tokenStorage.readBiometricEnabled(), isTrue);
    });

    test('biometric disabled by default when not stored', () async {
      when(mockStorage.read(key: 'biometric_enabled'))
          .thenAnswer((_) async => null);
      expect(await tokenStorage.readBiometricEnabled(), isFalse);
    });

    test('deleteAll clears storage', () async {
      when(mockStorage.deleteAll()).thenAnswer((_) async {});
      await tokenStorage.deleteAll();
      verify(mockStorage.deleteAll()).called(1);
    });

    test('readPermissions returns parsed list', () async {
      when(mockStorage.read(key: 'permissions'))
          .thenAnswer((_) async => '["sales.view","cnv.view","coupons.view"]');
      final perms = await tokenStorage.readPermissions();
      expect(perms, ['sales.view', 'cnv.view', 'coupons.view']);
    });

    test('readPermissions returns empty list when null', () async {
      when(mockStorage.read(key: 'permissions')).thenAnswer((_) async => null);
      final perms = await tokenStorage.readPermissions();
      expect(perms, isEmpty);
    });
  });
}
