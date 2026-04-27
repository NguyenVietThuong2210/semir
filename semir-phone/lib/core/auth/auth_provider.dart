import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../api/bare_dio_provider.dart';
import 'auth_service.dart';
import 'token_storage.dart';

final tokenStorageProvider = Provider<TokenStorage>((ref) => TokenStorage());

/// AuthService uses the bare Dio (no interceptor) so that token refresh calls
/// and login calls do not go through the auth interceptor — avoids the
/// circular dependency: dioProvider → authServiceProvider → dioProvider.
final authServiceProvider = Provider<AuthService>((ref) {
  return AuthService(
    dio: ref.read(bareDioProvider),
    storage: ref.read(tokenStorageProvider),
  );
});

/// Holds the current [UserSession] (null = not authenticated).
class AuthNotifier extends AsyncNotifier<UserSession?> {
  @override
  Future<UserSession?> build() async {
    return _restoreSession();
  }

  /// Attempt to restore an existing session from secure storage.
  Future<UserSession?> _restoreSession() async {
    final storage = ref.read(tokenStorageProvider);
    final access = await storage.readAccessToken();
    final refresh = await storage.readRefreshToken();
    if (access == null || access.isEmpty || refresh == null || refresh.isEmpty) {
      return null;
    }
    final username = await storage.readUsername() ?? '';
    final expiry = await storage.readAccessTokenExpiry();
    final permissions = await storage.readPermissions();
    return UserSession(
      username: username,
      accessToken: access,
      refreshToken: refresh,
      // If expiry is missing from storage, assume 1 hour from now rather than
      // "already expired" — avoids a needless refresh round-trip on cold start.
      accessTokenExpiry: expiry ?? DateTime.now().toUtc().add(const Duration(hours: 1)),
      permissions: permissions,
    );
  }

  Future<void> login(String username, String password) async {
    state = const AsyncLoading();
    final authService = ref.read(authServiceProvider);
    try {
      final session = await authService.login(username, password);
      state = AsyncData(session);
    } catch (err, stack) {
      state = AsyncError(err, stack);
      rethrow;
    }
  }

  Future<void> logout() async {
    final session = state.valueOrNull;
    if (session != null) {
      final authService = ref.read(authServiceProvider);
      await authService.logout(session.refreshToken);
    }
    state = const AsyncData(null);
  }

  void sessionExpired() {
    state = const AsyncData(null);
  }
}

final authProvider = AsyncNotifierProvider<AuthNotifier, UserSession?>(
  AuthNotifier.new,
);
