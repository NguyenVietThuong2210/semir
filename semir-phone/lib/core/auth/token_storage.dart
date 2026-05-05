import 'dart:convert';

import 'package:flutter_secure_storage/flutter_secure_storage.dart';

/// Thin wrapper over flutter_secure_storage.
/// Keychain (iOS) / EncryptedSharedPreferences (Android).
/// All token I/O goes through this class — never write tokens elsewhere.
class TokenStorage {
  TokenStorage({FlutterSecureStorage? storage})
      : _storage = storage ??
            const FlutterSecureStorage(
              aOptions: AndroidOptions(encryptedSharedPreferences: true),
            );

  final FlutterSecureStorage _storage;

  static const _kAccess = 'access_token';
  static const _kRefresh = 'refresh_token';
  static const _kExpiry = 'access_token_expiry';
  static const _kUsername = 'username';
  static const _kBiometric = 'biometric_enabled';
  static const _kPermissions = 'permissions';

  Future<void> saveTokens({
    required String access,
    required String refresh,
    required DateTime expiry,
    required String username,
    required List<String> permissions,
  }) async {
    await Future.wait([
      _storage.write(key: _kAccess, value: access),
      _storage.write(key: _kRefresh, value: refresh),
      _storage.write(key: _kExpiry, value: expiry.toIso8601String()),
      _storage.write(key: _kUsername, value: username),
      _storage.write(key: _kPermissions, value: jsonEncode(permissions)),
    ]);
  }

  Future<void> updateAccessToken(String access, DateTime expiry) async {
    await Future.wait([
      _storage.write(key: _kAccess, value: access),
      _storage.write(key: _kExpiry, value: expiry.toIso8601String()),
    ]);
  }

  Future<String?> readAccessToken() => _storage.read(key: _kAccess);
  Future<String?> readRefreshToken() => _storage.read(key: _kRefresh);
  Future<String?> readUsername() => _storage.read(key: _kUsername);

  Future<DateTime?> readAccessTokenExpiry() async {
    final raw = await _storage.read(key: _kExpiry);
    return raw != null ? DateTime.parse(raw) : null;
  }

  Future<List<String>> readPermissions() async {
    final raw = await _storage.read(key: _kPermissions);
    if (raw == null || raw.isEmpty) return [];
    return (jsonDecode(raw) as List).whereType<String>().toList();
  }

  Future<void> saveBiometricEnabled(bool enabled) =>
      _storage.write(key: _kBiometric, value: enabled.toString());

  Future<bool> readBiometricEnabled() async {
    final raw = await _storage.read(key: _kBiometric);
    return raw == 'true';
  }

  Future<void> deleteAll() => _storage.deleteAll();
}
