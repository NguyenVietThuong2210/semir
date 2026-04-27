import 'package:flutter_test/flutter_test.dart';
import 'package:local_auth/local_auth.dart';
import 'package:mockito/annotations.dart';
import 'package:mockito/mockito.dart';

import 'package:semir_phone/core/auth/biometric_service.dart';

import 'biometric_service_test.mocks.dart';

@GenerateMocks([LocalAuthentication])
void main() {
  late MockLocalAuthentication mockLocalAuth;
  late BiometricService service;

  setUp(() {
    mockLocalAuth = MockLocalAuthentication();
    service = BiometricService(auth: mockLocalAuth);
  });

  group('BiometricService.isAvailable', () {
    test('true when device supports biometrics and has enrolled biometrics', () async {
      when(mockLocalAuth.isDeviceSupported()).thenAnswer((_) async => true);
      when(mockLocalAuth.canCheckBiometrics).thenAnswer((_) async => true);

      expect(await service.isAvailable(), isTrue);
    });

    test('false when device does not support biometrics', () async {
      when(mockLocalAuth.isDeviceSupported()).thenAnswer((_) async => false);
      when(mockLocalAuth.canCheckBiometrics).thenAnswer((_) async => false);

      expect(await service.isAvailable(), isFalse);
    });

    test('false when no enrolled biometrics (device supported but canCheck false)', () async {
      when(mockLocalAuth.isDeviceSupported()).thenAnswer((_) async => true);
      when(mockLocalAuth.canCheckBiometrics).thenAnswer((_) async => false);

      expect(await service.isAvailable(), isFalse);
    });

    test('false on exception', () async {
      when(mockLocalAuth.isDeviceSupported()).thenThrow(Exception('platform error'));

      expect(await service.isAvailable(), isFalse);
    });
  });

  group('BiometricService.authenticate', () {
    test('returns true on successful authentication', () async {
      when(mockLocalAuth.authenticate(
        localizedReason: anyNamed('localizedReason'),
        options: anyNamed('options'),
      )).thenAnswer((_) async => true);

      expect(await service.authenticate(), isTrue);
    });

    test('returns false when user cancels', () async {
      when(mockLocalAuth.authenticate(
        localizedReason: anyNamed('localizedReason'),
        options: anyNamed('options'),
      )).thenAnswer((_) async => false);

      expect(await service.authenticate(), isFalse);
    });

    test('returns false on exception (e.g. biometric lockout)', () async {
      when(mockLocalAuth.authenticate(
        localizedReason: anyNamed('localizedReason'),
        options: anyNamed('options'),
      )).thenThrow(Exception('biometric lockout'));

      expect(await service.authenticate(), isFalse);
    });
  });
}
