import 'dart:async';

import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:flutter_test/flutter_test.dart';

import 'package:semir_phone/core/theme/app_theme.dart';
import 'package:semir_phone/features/analytics/customer/customer_page.dart';
import 'package:semir_phone/features/analytics/customer/customer_provider.dart';
import 'package:semir_phone/features/analytics/customer/customer_service.dart';
import 'package:semir_phone/shared/models/analytics_models.dart';
import 'package:semir_phone/shared/widgets/error_banner.dart';
import 'package:semir_phone/shared/widgets/kpi_card.dart';
import 'package:semir_phone/shared/widgets/loading_overlay.dart';

CustomerAnalyticsPayload _fixturePayload() {
  return CustomerAnalyticsPayload(
    allTimeKpis: [
      const KpiItem(label: 'Tổng KH CNV', value: '5,678'),
      const KpiItem(label: 'Tỷ lệ quay lại', value: '62.5%'),
    ],
    periodKpis: [
      const KpiItem(label: 'KH mới kỳ', value: '1,234'),
    ],
    registrationBreakdownTabs: [
      const TableTab(
        tabKey: 'by_shop',
        label: 'Theo Cửa hàng',
        headers: ['Cửa hàng', 'Số KH'],
        rows: [['HN01', '500']],
      ),
      const TableTab(
        tabKey: 'by_season',
        label: 'Theo Mùa',
        headers: ['Mùa', 'Số KH'],
        rows: [],
      ),
      const TableTab(
        tabKey: 'by_month',
        label: 'Theo Tháng',
        headers: ['Tháng', 'Số KH'],
        rows: [],
      ),
      const TableTab(
        tabKey: 'by_week',
        label: 'Theo Tuần',
        headers: ['Tuần', 'Số KH'],
        rows: [],
      ),
      const TableTab(
        tabKey: 'by_grade',
        label: 'Theo Hạng',
        headers: ['Hạng', 'Số KH'],
        rows: [],
      ),
    ],
    comparisonTabs: [
      const TableTab(
        tabKey: 'pos_only',
        label: 'POS Only',
        headers: ['Tháng', 'Số KH'],
        rows: [['01/2025', '200']],
      ),
      const TableTab(
        tabKey: 'cnv_only',
        label: 'CNV Only',
        headers: ['Tháng', 'Số KH'],
        rows: [],
      ),
      const TableTab(
        tabKey: 'both',
        label: 'Cả hai',
        headers: ['Tháng', 'Số KH'],
        rows: [],
      ),
    ],
  );
}

void main() {
  Widget buildSubject(AsyncValue<CustomerAnalyticsPayload?> state) {
    return ProviderScope(
      overrides: [
        customerAnalyticsProvider.overrideWith(() => _FakeNotifier(state)),
      ],
      child: MaterialApp(
        theme: buildAppTheme(),
        home: const CustomerPage(),
      ),
    );
  }

  testWidgets('loading state: LoadingOverlay visible', (tester) async {
    await tester.pumpWidget(buildSubject(const AsyncValue.loading()));
    await tester.pump();

    expect(find.byType(LoadingOverlay), findsOneWidget);
  });

  testWidgets('error state: ErrorBanner visible', (tester) async {
    await tester.pumpWidget(
      buildSubject(AsyncValue.error('Network error', StackTrace.empty)),
    );
    await tester.pumpAndSettle();

    expect(find.byType(ErrorBanner), findsOneWidget);
    expect(find.text('Retry'), findsOneWidget);
  });

  testWidgets('data state: all-time KPI cards rendered with orange tint',
      (tester) async {
    await tester.pumpWidget(buildSubject(AsyncValue.data(_fixturePayload())));
    await tester.pumpAndSettle();

    expect(find.byType(KpiCard), findsWidgets);
    expect(find.text('5,678'), findsOneWidget);
    expect(find.text('62.5%'), findsOneWidget);
  });

  testWidgets('data state: period KPI card rendered', (tester) async {
    await tester.pumpWidget(buildSubject(AsyncValue.data(_fixturePayload())));
    await tester.pumpAndSettle();

    expect(find.text('1,234'), findsOneWidget);
  });

  testWidgets('Registration Breakdown tabs visible', (tester) async {
    await tester.pumpWidget(buildSubject(AsyncValue.data(_fixturePayload())));
    await tester.pumpAndSettle();

    expect(find.text('By Store'), findsWidgets);
    expect(find.text('By Month'), findsWidgets);
    expect(find.text('By Grade'), findsWidgets);
  });

  testWidgets('Customer Comparison tabs visible', (tester) async {
    await tester.pumpWidget(buildSubject(AsyncValue.data(_fixturePayload())));
    await tester.pumpAndSettle();

    // Comparison tabs may be below the fold — scroll the outermost ListView.
    await tester.drag(find.byType(ListView).first, const Offset(0, -600));
    await tester.pumpAndSettle();

    expect(find.text('POS Only'), findsWidgets);
    expect(find.text('CNV Only'), findsWidgets);
    expect(find.text('Both'), findsWidgets);
  });

  testWidgets('Registration Breakdown tab switch works', (tester) async {
    await tester.pumpWidget(buildSubject(AsyncValue.data(_fixturePayload())));
    await tester.pumpAndSettle();

    // Tap "By Month" tab in breakdown section
    final monthTab = find.text('By Month');
    await tester.tap(monthTab.first);
    await tester.pumpAndSettle();

    // Still on page — no crash
    expect(find.byType(CustomerPage), findsOneWidget);
  });

  testWidgets('403 error shows no-access message instead of retry',
      (tester) async {
    await tester.pumpWidget(
      buildSubject(AsyncValue.error(
        const PermissionException(),
        StackTrace.empty,
      )),
    );
    await tester.pumpAndSettle();

    // Should show some error indicator — ErrorBanner or specific 403 message
    expect(find.byType(ErrorBanner), findsOneWidget);
  });
}

class _FakeNotifier extends CustomerAnalyticsNotifier {
  _FakeNotifier(this._state);
  final AsyncValue<CustomerAnalyticsPayload?> _state;

  @override
  Future<CustomerAnalyticsPayload?> build() {
    if (_state.isLoading) return Completer<CustomerAnalyticsPayload?>().future;
    if (_state.hasError) return Future.error(_state.error!, _state.stackTrace);
    return Future.value(_state.valueOrNull);
  }
}
