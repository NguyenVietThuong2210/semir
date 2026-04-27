import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:flutter_test/flutter_test.dart';

import 'package:semir_phone/core/auth/auth_provider.dart';
import 'package:semir_phone/core/auth/auth_service.dart';
import 'package:semir_phone/core/theme/app_theme.dart';
import 'package:semir_phone/features/analytics/coupon/coupon_page.dart';
import 'package:semir_phone/features/analytics/coupon/coupon_provider.dart';
import 'package:semir_phone/features/analytics/coupon/coupon_service.dart';
import 'package:semir_phone/features/analytics/customer/customer_page.dart';
import 'package:semir_phone/features/analytics/customer/customer_provider.dart';
import 'package:semir_phone/features/analytics/customer/customer_service.dart';
import 'package:semir_phone/features/analytics/sales/sales_page.dart';
import 'package:semir_phone/features/analytics/sales/sales_provider.dart';
import 'package:semir_phone/features/analytics/sales/sales_service.dart';
import 'package:semir_phone/shared/models/analytics_models.dart';
import 'package:semir_phone/features/charts/chart_provider.dart';
import 'package:semir_phone/features/charts/chart_service.dart';
import 'package:semir_phone/features/charts/sales_chart_page.dart';
import 'package:semir_phone/features/home/home_page.dart';
import 'package:semir_phone/features/login/login_page.dart';

// ---------------------------------------------------------------------------
// Fixtures
// ---------------------------------------------------------------------------

SalesAnalyticsPayload _salesPayload() => SalesAnalyticsPayload(
      allTimeKpis: const [
        KpiItem(label: 'Tổng doanh thu', value: '12,345,678,900'),
        KpiItem(label: 'Tổng đơn hàng', value: '45,678'),
        KpiItem(label: 'Khách hàng', value: '12,345'),
        KpiItem(label: 'Giá trị TB', value: '270,400'),
      ],
      periodKpis: const [
        KpiItem(label: 'Doanh thu kỳ', value: '5,678,900,000'),
        KpiItem(label: 'Đơn hàng kỳ', value: '21,000'),
        KpiItem(label: 'KH kỳ', value: '5,678'),
        KpiItem(label: 'Giá trị TB kỳ', value: '270,400'),
      ],
      tabs: const [
        TableTab(
          tabKey: 'grade',
          label: 'Theo Hạng',
          headers: ['Hạng', 'Doanh thu', 'Tỷ lệ', 'Đơn'],
          rows: [
            ['Diamond', '2,000,000,000', '35.2%', '5,678'],
            ['Gold', '1,500,000,000', '26.4%', '4,321'],
            ['Silver', '1,000,000,000', '17.6%', '3,000'],
            ['Member', '750,000,000', '13.2%', '2,000'],
            ['No Grade', '428,900,000', '7.6%', '1,000'],
          ],
        ),
      ],
    );

CustomerAnalyticsPayload _customerPayload() => CustomerAnalyticsPayload(
      allTimeKpis: const [
        KpiItem(label: 'Tổng KH', value: '15,678'),
        KpiItem(label: 'Tổng CNV', value: '8,234'),
      ],
      periodKpis: const [
        KpiItem(label: 'KH mới kỳ', value: '2,345'),
      ],
      registrationBreakdownTabs: const [
        TableTab(
          tabKey: 'by_shop',
          label: 'Theo Cửa hàng',
          headers: ['Cửa hàng', 'Số KH', 'Tỷ lệ'],
          rows: [
            ['HN01', '3,456', '22.0%'],
            ['HN02', '2,345', '14.9%'],
          ],
        ),
        TableTab(tabKey: 'by_month', label: 'Theo Tháng', headers: [], rows: []),
        TableTab(tabKey: 'by_grade', label: 'Theo Hạng', headers: [], rows: []),
      ],
      comparisonTabs: const [
        TableTab(tabKey: 'pos_only', label: 'POS Only', headers: [], rows: []),
        TableTab(tabKey: 'cnv_only', label: 'CNV Only', headers: [], rows: []),
        TableTab(tabKey: 'both', label: 'Cả hai', headers: [], rows: []),
      ],
    );

CouponAnalyticsPayload _couponPayload() => CouponAnalyticsPayload(
      allTimeKpis: const [
        KpiItem(label: 'Tổng coupon', value: '25,000'),
        KpiItem(label: 'Đã dùng', value: '18,750'),
      ],
      periodKpis: const [
        KpiItem(label: 'Coupon kỳ', value: '5,000'),
      ],
      tabs: const [
        TableTab(
          tabKey: 'by_shop',
          label: 'Theo Cửa hàng',
          headers: ['Cửa hàng', 'Tổng', 'Đã dùng'],
          rows: [
            ['HN01', '5,000', '3,750'],
            ['HN02', '4,000', '3,000'],
          ],
        ),
        TableTab(tabKey: 'detail', label: 'Chi tiết', headers: [], rows: []),
        TableTab(tabKey: 'duplicates', label: 'Trùng lặp', headers: [], rows: []),
      ],
    );

ChartPayload _chartPayload() => const ChartPayload(
      donuts: [
        DonutChart(
          title: 'Theo Mùa',
          slices: [
            DonutSlice(label: 'M2-4 2025', value: '5,000,000,000', color: '#0D6EFD', percentage: 40.0),
            DonutSlice(label: 'M5-7 2025', value: '3,000,000,000', color: '#FF6B6B', percentage: 24.0),
            DonutSlice(label: 'M8-10 2025', value: '2,500,000,000', color: '#20C997', percentage: 20.0),
            DonutSlice(label: 'M11-1 2024-2025', value: '2,000,000,000', color: '#FFC107', percentage: 16.0),
          ],
        ),
        DonutChart(
          title: 'Theo Hạng',
          slices: [
            DonutSlice(label: 'Diamond', value: '2,000,000,000', color: '#6610F2', percentage: 35.0),
            DonutSlice(label: 'Gold', value: '1,500,000,000', color: '#FD7E14', percentage: 26.0),
            DonutSlice(label: 'Silver', value: '1,000,000,000', color: '#6C757D', percentage: 18.0),
          ],
        ),
      ],
      trend: [
        TrendPoint(label: 'T1/2025', value: 800000000),
        TrendPoint(label: 'T2/2025', value: 950000000),
        TrendPoint(label: 'T3/2025', value: 1200000000),
      ],
    );

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

Widget _wrap(Widget child, {List<Override> overrides = const []}) {
  return ProviderScope(
    overrides: overrides,
    child: MaterialApp(
      theme: buildAppTheme(),
      debugShowCheckedModeBanner: false,
      home: child,
    ),
  );
}

const _phone390 = Size(390, 844); // iPhone 14

// ---------------------------------------------------------------------------
// Golden tests
// ---------------------------------------------------------------------------

void main() {
  // Use consistent font rendering across platforms
  setUp(() {
    // Set surface size for all tests
  });

  // T046 — Login & Home
  group('T046 login + home goldens', () {
    testWidgets('login page — 390pt', (tester) async {
      tester.view.physicalSize = _phone390 * tester.view.devicePixelRatio;
      tester.view.devicePixelRatio = 1.0;
      addTearDown(tester.view.reset);

      await tester.pumpWidget(_wrap(const LoginPage()));
      await tester.pumpAndSettle();

      await expectLater(
        find.byType(MaterialApp),
        matchesGoldenFile('goldens/login.png'),
      );
    });

    testWidgets('home — full permissions — 390pt', (tester) async {
      tester.view.physicalSize = _phone390 * tester.view.devicePixelRatio;
      tester.view.devicePixelRatio = 1.0;
      addTearDown(tester.view.reset);

      final fullSession = UserSession(
        username: 'admin',
        accessToken: 'tok',
        refreshToken: 'ref',
        accessTokenExpiry: DateTime.now().add(const Duration(hours: 1)),
        permissions: const [
          'sales.view', 'customers.view', 'coupons.view',
          'shop_detail.view', 'customer_detail.view',
        ],
      );

      await tester.pumpWidget(_wrap(
        const HomePage(),
        overrides: [
          authProvider.overrideWith(() => _FakeAuthNotifier(AsyncValue.data(fullSession))),
        ],
      ));
      await tester.pumpAndSettle();

      await expectLater(
        find.byType(MaterialApp),
        matchesGoldenFile('goldens/home_full_permissions.png'),
      );
    });

    testWidgets('home — sales only — 390pt', (tester) async {
      tester.view.physicalSize = _phone390 * tester.view.devicePixelRatio;
      tester.view.devicePixelRatio = 1.0;
      addTearDown(tester.view.reset);

      final salesOnlySession = UserSession(
        username: 'staff',
        accessToken: 'tok',
        refreshToken: 'ref',
        accessTokenExpiry: DateTime.now().add(const Duration(hours: 1)),
        permissions: const ['sales.view'],
      );

      await tester.pumpWidget(_wrap(
        const HomePage(),
        overrides: [
          authProvider.overrideWith(() => _FakeAuthNotifier(AsyncValue.data(salesOnlySession))),
        ],
      ));
      await tester.pumpAndSettle();

      await expectLater(
        find.byType(MaterialApp),
        matchesGoldenFile('goldens/home_sales_only.png'),
      );
    });
  });

  // T066 — Sales Analytics
  group('T066 sales analytics goldens', () {
    testWidgets('sales analytics — data — 390pt', (tester) async {
      tester.view.physicalSize = _phone390 * tester.view.devicePixelRatio;
      tester.view.devicePixelRatio = 1.0;
      addTearDown(tester.view.reset);

      await tester.pumpWidget(_wrap(
        const SalesPage(),
        overrides: [
          salesAnalyticsProvider.overrideWith(() => _FakeSalesNotifier(AsyncValue.data(_salesPayload()))),
        ],
      ));
      await tester.pumpAndSettle();

      await expectLater(
        find.byType(MaterialApp),
        matchesGoldenFile('goldens/sales_analytics.png'),
      );
    });

    testWidgets('sales analytics — loading — 390pt', (tester) async {
      tester.view.physicalSize = _phone390 * tester.view.devicePixelRatio;
      tester.view.devicePixelRatio = 1.0;
      addTearDown(tester.view.reset);

      await tester.pumpWidget(_wrap(
        const SalesPage(),
        overrides: [
          salesAnalyticsProvider.overrideWith(() => _FakeSalesNotifier(const AsyncValue.loading())),
        ],
      ));
      await tester.pump(); // don't settle — capture loading state

      await expectLater(
        find.byType(MaterialApp),
        matchesGoldenFile('goldens/sales_loading.png'),
      );
    });

    testWidgets('sales analytics — error — 390pt', (tester) async {
      tester.view.physicalSize = _phone390 * tester.view.devicePixelRatio;
      tester.view.devicePixelRatio = 1.0;
      addTearDown(tester.view.reset);

      await tester.pumpWidget(_wrap(
        const SalesPage(),
        overrides: [
          salesAnalyticsProvider.overrideWith(() => _FakeSalesNotifier(
            AsyncValue.error('Không thể kết nối đến máy chủ', StackTrace.empty),
          )),
        ],
      ));
      await tester.pumpAndSettle();

      await expectLater(
        find.byType(MaterialApp),
        matchesGoldenFile('goldens/sales_error.png'),
      );
    });
  });

  // T077 — Customer Analytics
  group('T077 customer analytics golden', () {
    testWidgets('customer analytics — data — 390pt', (tester) async {
      tester.view.physicalSize = _phone390 * tester.view.devicePixelRatio;
      tester.view.devicePixelRatio = 1.0;
      addTearDown(tester.view.reset);

      await tester.pumpWidget(_wrap(
        const CustomerPage(),
        overrides: [
          customerAnalyticsProvider.overrideWith(() => _FakeCustomerNotifier(AsyncValue.data(_customerPayload()))),
        ],
      ));
      await tester.pumpAndSettle();

      await expectLater(
        find.byType(MaterialApp),
        matchesGoldenFile('goldens/customer_analytics.png'),
      );
    });
  });

  // T083 — Coupon Analytics
  group('T083 coupon analytics golden', () {
    testWidgets('coupon analytics — data — 390pt', (tester) async {
      tester.view.physicalSize = _phone390 * tester.view.devicePixelRatio;
      tester.view.devicePixelRatio = 1.0;
      addTearDown(tester.view.reset);

      await tester.pumpWidget(_wrap(
        const CouponPage(),
        overrides: [
          couponAnalyticsProvider.overrideWith(() => _FakeCouponNotifier(AsyncValue.data(_couponPayload()))),
        ],
      ));
      await tester.pumpAndSettle();

      await expectLater(
        find.byType(MaterialApp),
        matchesGoldenFile('goldens/coupon_analytics.png'),
      );
    });
  });

  // T106 — Charts
  group('T106 chart goldens', () {
    testWidgets('sales charts — data — 390pt', (tester) async {
      tester.view.physicalSize = _phone390 * tester.view.devicePixelRatio;
      tester.view.devicePixelRatio = 1.0;
      addTearDown(tester.view.reset);

      await tester.pumpWidget(_wrap(
        const SalesChartPage(),
        overrides: [
          salesChartProvider.overrideWith(() => _FakeSalesChartNotifier(AsyncValue.data(_chartPayload()))),
        ],
      ));
      await tester.pumpAndSettle();

      await expectLater(
        find.byType(MaterialApp),
        matchesGoldenFile('goldens/sales_charts.png'),
      );
    });
  });
}

// ---------------------------------------------------------------------------
// Fake notifiers
// ---------------------------------------------------------------------------

class _FakeAuthNotifier extends AuthNotifier {
  _FakeAuthNotifier(this._state);
  final AsyncValue<UserSession?> _state;
  @override
  Future<UserSession?> build() async {
    state = _state;
    return _state.valueOrNull;
  }
}

class _FakeSalesNotifier extends SalesAnalyticsNotifier {
  _FakeSalesNotifier(this._state);
  final AsyncValue<SalesAnalyticsPayload?> _state;
  @override
  Future<SalesAnalyticsPayload?> build() async {
    state = _state;
    return _state.valueOrNull;
  }
}

class _FakeCustomerNotifier extends CustomerAnalyticsNotifier {
  _FakeCustomerNotifier(this._state);
  final AsyncValue<CustomerAnalyticsPayload?> _state;
  @override
  Future<CustomerAnalyticsPayload?> build() async {
    state = _state;
    return _state.valueOrNull;
  }
}

class _FakeCouponNotifier extends CouponAnalyticsNotifier {
  _FakeCouponNotifier(this._state);
  final AsyncValue<CouponAnalyticsPayload?> _state;
  @override
  Future<CouponAnalyticsPayload?> build() async {
    state = _state;
    return _state.valueOrNull;
  }
}

class _FakeSalesChartNotifier extends SalesChartNotifier {
  _FakeSalesChartNotifier(this._state);
  final AsyncValue<ChartPayload?> _state;
  @override
  Future<ChartPayload?> build() async {
    state = _state;
    return _state.valueOrNull;
  }
}
