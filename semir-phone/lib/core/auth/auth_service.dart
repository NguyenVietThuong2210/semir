import 'package:dio/dio.dart';

import '../api/endpoints.dart';
import 'token_storage.dart';

/// Raised when credentials are invalid (401 on login).
class AuthException implements Exception {
  final String message;
  const AuthException(this.message);
  @override
  String toString() => 'AuthException: $message';
}

/// Raised when the refresh token is expired/revoked.
class SessionExpiredException implements Exception {
  const SessionExpiredException();
  @override
  String toString() => 'SessionExpiredException';
}

class UserSession {
  final String username;
  final String accessToken;
  final String refreshToken;
  final DateTime accessTokenExpiry;
  final List<String> permissions;
  final bool biometricEnabled;

  const UserSession({
    required this.username,
    required this.accessToken,
    required this.refreshToken,
    required this.accessTokenExpiry,
    required this.permissions,
    this.biometricEnabled = false,
  });

  bool hasPermission(String perm) => permissions.contains(perm);
}

class AuthService {
  AuthService({required Dio dio, required TokenStorage storage})
      : _dio = dio,
        _storage = storage;

  final Dio _dio;
  final TokenStorage _storage;

  Future<UserSession> login(String username, String password) async {
    try {
      final resp = await _dio.post(
        Endpoints.login,
        data: {'username': username, 'password': password},
      );
      final data = resp.data as Map<String, dynamic>;
      final expiresIn = (data['access_expires_in'] as num).toInt();
      final expiry = DateTime.now().toUtc().add(Duration(seconds: expiresIn));

      final permissions = (data['permissions'] as List<dynamic>)
          .map((e) => e.toString())
          .toList();

      await _storage.saveTokens(
        access: data['access'] as String,
        refresh: data['refresh'] as String,
        expiry: expiry,
        username: data['username'] as String,
        permissions: permissions,
      );

      return UserSession(
        username: data['username'] as String,
        accessToken: data['access'] as String,
        refreshToken: data['refresh'] as String,
        accessTokenExpiry: expiry,
        permissions: permissions,
      );
    } on DioException catch (e) {
      if (e.response?.statusCode == 401) {
        throw const AuthException('Invalid username or password.');
      }
      throw AuthException(e.message ?? 'Network error during login.');
    }
  }

  Future<void> logout(String refreshToken) async {
    try {
      await _dio.post(Endpoints.logout, data: {'refresh': refreshToken});
    } catch (_) {
      // Ignore server errors on logout — tokens wiped locally regardless.
    } finally {
      await _storage.deleteAll();
    }
  }

  /// Silent token refresh. Returns the new access token.
  /// Throws [SessionExpiredException] if the refresh token is invalid/expired.
  Future<String> refresh(String refreshToken) async {
    try {
      final resp = await _dio.post(
        Endpoints.refresh,
        data: {'refresh': refreshToken},
      );
      final data = resp.data as Map<String, dynamic>;
      final expiresIn = (data['access_expires_in'] as num?)?.toInt() ?? 3600;
      final expiry = DateTime.now().toUtc().add(Duration(seconds: expiresIn));
      final newAccess = data['access'] as String;

      await _storage.updateAccessToken(newAccess, expiry);
      return newAccess;
    } on DioException catch (e) {
      if (e.response?.statusCode == 401) {
        await _storage.deleteAll();
        throw const SessionExpiredException();
      }
      rethrow;
    }
  }
}
