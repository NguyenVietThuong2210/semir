import 'package:local_auth/local_auth.dart';

/// Wraps local_auth for biometric authentication.
///
/// Biometric = device-level gate on Keychain/Keystore access.
/// It is NOT a backend auth call — the JWT tokens remain in secure storage
/// and are accessed after biometric confirms device owner identity.
class BiometricService {
  BiometricService({LocalAuthentication? auth})
      : _auth = auth ?? LocalAuthentication();

  final LocalAuthentication _auth;

  Future<bool> isAvailable() async {
    try {
      final canCheck = await _auth.canCheckBiometrics;
      final isDeviceSupported = await _auth.isDeviceSupported();
      return canCheck && isDeviceSupported;
    } catch (_) {
      return false;
    }
  }

  /// Returns true if the user successfully authenticates biometrically.
  /// Returns false on failure, cancel, or if biometrics are unavailable.
  Future<bool> authenticate() async {
    try {
      return await _auth.authenticate(
        localizedReason: 'Authenticate to open S&B Dashboard',
        options: const AuthenticationOptions(
          biometricOnly: false, // allow PIN fallback
          stickyAuth: true,
        ),
      );
    } catch (_) {
      return false;
    }
  }
}
