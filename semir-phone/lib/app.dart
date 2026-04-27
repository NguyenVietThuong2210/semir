import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:go_router/go_router.dart';

import 'core/auth/auth_provider.dart';
import 'core/auth/auth_service.dart';
import 'core/theme/app_theme.dart';
import 'features/analytics/coupon/coupon_page.dart';
import 'features/analytics/customer/customer_page.dart';
import 'features/analytics/customer_detail/customer_detail_page.dart';
import 'features/analytics/sales/sales_page.dart';
import 'features/analytics/shop_detail/shop_detail_page.dart';
import 'features/charts/coupon_chart_page.dart';
import 'features/charts/customer_chart_page.dart';
import 'features/charts/sales_chart_page.dart';
import 'features/home/home_page.dart';
import 'features/login/login_page.dart';

// Route paths — no deep links (SC-009), back-stack only.
const String _pathLogin = '/login';
const String _pathHome = '/';

class SemirPhoneApp extends ConsumerStatefulWidget {
  const SemirPhoneApp({super.key});

  @override
  ConsumerState<SemirPhoneApp> createState() => _SemirPhoneAppState();
}

class _SemirPhoneAppState extends ConsumerState<SemirPhoneApp> {
  late final GoRouter _router;
  late final _AuthListenable _authListenable;

  @override
  void initState() {
    super.initState();
    _authListenable = _AuthListenable(ref);
    _router = GoRouter(
      initialLocation: _pathHome,
      refreshListenable: _authListenable,
      redirect: (context, state) async {
        final authState = ref.read(authProvider);
        final isAuthenticated = authState.valueOrNull != null;
        final isLoggingIn = state.matchedLocation == _pathLogin;

        if (!isAuthenticated && !isLoggingIn) return _pathLogin;
        if (isAuthenticated && isLoggingIn) return _pathHome;
        return null;
      },
      routes: [
        GoRoute(
          path: _pathLogin,
          builder: (context, state) => const LoginPage(),
        ),
        GoRoute(
          path: _pathHome,
          builder: (context, state) => const HomePage(),
          routes: [
            GoRoute(
              path: 'sales',
              redirect: (context, state) =>
                  _requirePerm('sales.view'),
              builder: (context, state) => const SalesPage(),
              routes: [
                GoRoute(
                  path: 'charts',
                  builder: (context, state) => const SalesChartPage(),
                ),
              ],
            ),
            GoRoute(
              path: 'customer',
              redirect: (context, state) =>
                  _requirePerm('customers.view'),
              builder: (context, state) => const CustomerPage(),
              routes: [
                GoRoute(
                  path: 'charts',
                  builder: (context, state) => const CustomerChartPage(),
                ),
              ],
            ),
            GoRoute(
              path: 'coupon',
              redirect: (context, state) =>
                  _requirePerm('coupons.view'),
              builder: (context, state) => const CouponPage(),
              routes: [
                GoRoute(
                  path: 'charts',
                  builder: (context, state) => const CouponChartPage(),
                ),
              ],
            ),
            GoRoute(
              path: 'shop-detail',
              redirect: (context, state) =>
                  _requirePerm('shop_detail.view'),
              builder: (context, state) => const ShopDetailPage(),
            ),
            GoRoute(
              path: 'customer-detail',
              redirect: (context, state) =>
                  _requirePerm('customer_detail.view'),
              builder: (context, state) => const CustomerDetailPage(),
            ),
          ],
        ),
      ],
    );
  }

  @override
  void dispose() {
    _authListenable.dispose();
    _router.dispose();
    super.dispose();
  }

  String? _requirePerm(String perm) {
    final session = ref.read(authProvider).valueOrNull;
    if (session == null || !session.hasPermission(perm)) return _pathHome;
    return null;
  }

  @override
  Widget build(BuildContext context) {
    return MaterialApp.router(
      title: 'S&B Dashboard',
      theme: buildAppTheme(),
      routerConfig: _router,
      debugShowCheckedModeBanner: false,
    );
  }
}

/// Bridges Riverpod auth state changes into GoRouter redirect evaluation.
/// Uses a managed [ProviderSubscription] so the listener is cleaned up when
/// the router is disposed — no orphaned subscriptions across rebuilds.
class _AuthListenable extends ChangeNotifier {
  _AuthListenable(WidgetRef ref) {
    _sub = ref.listenManual<AsyncValue<UserSession?>>(
      authProvider,
      (_, __) => notifyListeners(),
    );
  }

  late final ProviderSubscription<AsyncValue<UserSession?>> _sub;

  @override
  void dispose() {
    _sub.close();
    super.dispose();
  }
}
