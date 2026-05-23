import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../api/bare_dio_provider.dart';
import '../../features/analytics/sales/sales_provider.dart';
import '../../features/analytics/customer/customer_provider.dart';
import '../../features/analytics/coupon/coupon_provider.dart';
import '../../features/analytics/shop_detail/shop_detail_provider.dart';
import '../../features/analytics/customer_detail/customer_detail_provider.dart';
import '../../features/charts/chart_provider.dart';
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
    // Invalidate all cached analytics data so the next user starts clean.
    ref.invalidate(salesAnalyticsProvider);
    ref.invalidate(salesTabProvider);
    ref.invalidate(customerAnalyticsProvider);
    ref.invalidate(couponAnalyticsProvider);
    ref.invalidate(couponTabProvider);
    ref.invalidate(shopsListProvider);
    ref.invalidate(shopDetailSalesProvider);
    ref.invalidate(shopCustomerProvider);
    ref.invalidate(shopCouponProvider);
    ref.invalidate(customerDetailProvider);
    ref.invalidate(salesChartProvider);
    ref.invalidate(customerChartProvider);
    ref.invalidate(couponChartProvider);
    // Reset UI filter state so the next user starts with default filters.
    ref.invalidate(salesFilterProvider);
    ref.invalidate(salesShopGroupProvider);
    ref.invalidate(customerFilterProvider);
    ref.invalidate(couponFilterProvider);
    ref.invalidate(couponShopGroupProvider);
    ref.invalidate(couponPrefixProvider);
    ref.invalidate(selectedShopProvider);
    ref.invalidate(shopDetailFilterProvider);
    ref.invalidate(chartFilterProvider);
    ref.invalidate(selectedSliceLabelProvider);
    ref.invalidate(customerSearchQueryProvider);
    state = const AsyncData(null);
  }

  void sessionExpired() {
    state = const AsyncData(null);
  }
}

final authProvider = AsyncNotifierProvider<AuthNotifier, UserSession?>(
  AuthNotifier.new,
);
