import 'dart:async';

import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:flutter_test/flutter_test.dart';

import 'package:semir_phone/core/theme/app_theme.dart';
import 'package:semir_phone/features/charts/chart_provider.dart';
import 'package:semir_phone/features/charts/chart_service.dart';
import 'package:semir_phone/features/charts/coupon_chart_page.dart';
import 'package:semir_phone/features/charts/customer_chart_page.dart';
import 'package:semir_phone/features/charts/donut_card.dart';
import 'package:semir_phone/features/charts/sales_chart_page.dart';
import 'package:semir_phone/shared/widgets/error_banner.dart';
import 'package:semir_phone/shared/widgets/loading_overlay.dart';

ChartPayload _twoDonutPayload({bool withTrend = false}) {
  return ChartPayload(
    donuts: [
      const DonutChart(
        title: 'Theo Mùa',
        slices: [
          DonutSlice(
              label: 'M2-4 2025',
              value: '500,000,000',
              color: '#0D6EFD',
              percentage: 40.0),
          DonutSlice(
              label: 'M5-7 2025',
              value: '300,000,000',
              color: '#FF6B6B',
              percentage: 24.0),
        ],
      ),
      const DonutChart(
        title: 'Theo Hạng',
        slices: [
          DonutSlice(
              label: 'Diamond',
              value: '200,000,000',
              color: '#20C997',
              percentage: 16.0),
        ],
      ),
    ],
    trend: withTrend
        ? const [
            TrendPoint(label: 'T1/2025', value: 100000000),
            TrendPoint(label: 'T2/2025', value: 120000000),
          ]
        : null,
  );
}

Widget _buildSalesSubject(AsyncValue<ChartPayload?> state) {
  return ProviderScope(
    overrides: [
      salesChartProvider.overrideWith(() => _FakeSalesNotifier(state)),
    ],
    child: MaterialApp(theme: buildAppTheme(), home: const SalesChartPage()),
  );
}

Widget _buildCustomerSubject(AsyncValue<ChartPayload?> state) {
  return ProviderScope(
    overrides: [
      customerChartProvider.overrideWith(() => _FakeCustomerNotifier(state)),
    ],
    child: MaterialApp(theme: buildAppTheme(), home: const CustomerChartPage()),
  );
}

Widget _buildCouponSubject(AsyncValue<ChartPayload?> state) {
  return ProviderScope(
    overrides: [
      couponChartProvider.overrideWith(() => _FakeCouponNotifier(state)),
    ],
    child: MaterialApp(theme: buildAppTheme(), home: const CouponChartPage()),
  );
}

void main() {
  group('SalesChartPage', () {
    testWidgets('loading state: LoadingOverlay visible', (tester) async {
      await tester.pumpWidget(_buildSalesSubject(const AsyncValue.loading()));
      await tester.pump();
      expect(find.byType(LoadingOverlay), findsOneWidget);
    });

    testWidgets('error state: ErrorBanner shown', (tester) async {
      await tester.pumpWidget(
        _buildSalesSubject(AsyncValue.error('Server error', StackTrace.empty)),
      );
      await tester.pumpAndSettle();
      expect(find.byType(ErrorBanner), findsOneWidget);
    });

    testWidgets('data state: correct donut card count rendered', (tester) async {
      await tester.pumpWidget(
          _buildSalesSubject(AsyncValue.data(_twoDonutPayload())));
      await tester.pumpAndSettle();
      expect(find.byType(DonutCard), findsNWidgets(2));
    });

    testWidgets('null trend → no trend section in widget tree', (tester) async {
      await tester.pumpWidget(
          _buildSalesSubject(
              AsyncValue.data(_twoDonutPayload(withTrend: false))));
      await tester.pumpAndSettle();
      expect(find.text('Trend'), findsNothing);
    });

    testWidgets('trend present → "Trend" section header shown', (tester) async {
      await tester.pumpWidget(
          _buildSalesSubject(
              AsyncValue.data(_twoDonutPayload(withTrend: true))));
      await tester.pumpAndSettle();
      await tester.drag(find.byType(ListView), const Offset(0, -600));
      await tester.pumpAndSettle();
      expect(find.text('Trend'), findsOneWidget);
    });

    testWidgets('legend visible for each slice', (tester) async {
      await tester.pumpWidget(
          _buildSalesSubject(AsyncValue.data(_twoDonutPayload())));
      await tester.pumpAndSettle();
      expect(find.textContaining('M2-4 2025'), findsOneWidget);
      expect(find.textContaining('Diamond'), findsOneWidget);
    });

    testWidgets('null payload → "No data" shown', (tester) async {
      await tester.pumpWidget(
          _buildSalesSubject(const AsyncValue.data(null)));
      await tester.pumpAndSettle();
      expect(find.text('No data'), findsOneWidget);
    });
  });

  group('CustomerChartPage', () {
    testWidgets('loading state: LoadingOverlay visible', (tester) async {
      await tester
          .pumpWidget(_buildCustomerSubject(const AsyncValue.loading()));
      await tester.pump();
      expect(find.byType(LoadingOverlay), findsOneWidget);
    });

    testWidgets('error state: ErrorBanner shown', (tester) async {
      await tester.pumpWidget(
        _buildCustomerSubject(
            AsyncValue.error('Network error', StackTrace.empty)),
      );
      await tester.pumpAndSettle();
      expect(find.byType(ErrorBanner), findsOneWidget);
    });

    testWidgets('null payload → "No data" shown', (tester) async {
      await tester.pumpWidget(
          _buildCustomerSubject(const AsyncValue.data(null)));
      await tester.pumpAndSettle();
      expect(find.text('No data'), findsOneWidget);
    });

    testWidgets('data state: donut cards and legend rendered', (tester) async {
      await tester.pumpWidget(
          _buildCustomerSubject(AsyncValue.data(_twoDonutPayload())));
      await tester.pumpAndSettle();
      expect(find.byType(DonutCard), findsNWidgets(2));
      expect(find.textContaining('Diamond'), findsOneWidget);
    });
  });

  group('CouponChartPage', () {
    testWidgets('loading state: LoadingOverlay visible', (tester) async {
      await tester.pumpWidget(_buildCouponSubject(const AsyncValue.loading()));
      await tester.pump();
      expect(find.byType(LoadingOverlay), findsOneWidget);
    });

    testWidgets('error state: ErrorBanner shown', (tester) async {
      await tester.pumpWidget(
        _buildCouponSubject(
            AsyncValue.error('Network error', StackTrace.empty)),
      );
      await tester.pumpAndSettle();
      expect(find.byType(ErrorBanner), findsOneWidget);
    });

    testWidgets('null payload → "No data" shown', (tester) async {
      await tester.pumpWidget(
          _buildCouponSubject(const AsyncValue.data(null)));
      await tester.pumpAndSettle();
      expect(find.text('No data'), findsOneWidget);
    });

    testWidgets('data state: donut cards and legend rendered', (tester) async {
      await tester.pumpWidget(
          _buildCouponSubject(AsyncValue.data(_twoDonutPayload())));
      await tester.pumpAndSettle();
      expect(find.byType(DonutCard), findsNWidgets(2));
      expect(find.textContaining('M2-4 2025'), findsOneWidget);
    });
  });
}

class _FakeSalesNotifier extends SalesChartNotifier {
  _FakeSalesNotifier(this._state);
  final AsyncValue<ChartPayload?> _state;

  @override
  Future<ChartPayload?> build() {
    if (_state.isLoading) return Completer<ChartPayload?>().future;
    if (_state.hasError) return Future.error(_state.error!, _state.stackTrace);
    return Future.value(_state.valueOrNull);
  }
}

class _FakeCustomerNotifier extends CustomerChartNotifier {
  _FakeCustomerNotifier(this._state);
  final AsyncValue<ChartPayload?> _state;

  @override
  Future<ChartPayload?> build() {
    if (_state.isLoading) return Completer<ChartPayload?>().future;
    if (_state.hasError) return Future.error(_state.error!, _state.stackTrace);
    return Future.value(_state.valueOrNull);
  }
}

class _FakeCouponNotifier extends CouponChartNotifier {
  _FakeCouponNotifier(this._state);
  final AsyncValue<ChartPayload?> _state;

  @override
  Future<ChartPayload?> build() {
    if (_state.isLoading) return Completer<ChartPayload?>().future;
    if (_state.hasError) return Future.error(_state.error!, _state.stackTrace);
    return Future.value(_state.valueOrNull);
  }
}
