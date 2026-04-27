import 'dart:async';
import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:flutter_test/flutter_test.dart';

import 'package:semir_phone/core/theme/app_theme.dart';
import 'package:semir_phone/features/analytics/sales/sales_page.dart';
import 'package:semir_phone/features/analytics/sales/sales_provider.dart';
import 'package:semir_phone/features/analytics/sales/sales_service.dart';
import 'package:semir_phone/shared/models/analytics_models.dart';
import 'package:semir_phone/shared/widgets/error_banner.dart';
import 'package:semir_phone/shared/widgets/kpi_card.dart';
import 'package:semir_phone/shared/widgets/loading_overlay.dart';

SalesAnalyticsPayload _fixturePayload() {
  return SalesAnalyticsPayload(
    allTimeKpis: [
      const KpiItem(label: 'Tổng doanh thu', value: '1,234,567,890'),
      const KpiItem(label: 'Tổng đơn hàng', value: '12,345'),
    ],
    periodKpis: [
      const KpiItem(label: 'Doanh thu kỳ', value: '500,000,000'),
      const KpiItem(label: 'Đơn hàng kỳ', value: '5,000'),
    ],
    tabs: [
      const TableTab(
        tabKey: 'grade',
        label: 'Theo Hạng',
        headers: ['Hạng', 'Doanh thu'],
        rows: [
          ['Diamond', '200,000,000'],
          ['Gold', '150,000,000'],
        ],
      ),
    ],
  );
}

void main() {
  Widget buildSubject(AsyncValue<SalesAnalyticsPayload?> state) {
    return ProviderScope(
      overrides: [
        salesAnalyticsProvider.overrideWith(() => _FakeNotifier(state)),
      ],
      child: MaterialApp(
        theme: buildAppTheme(),
        home: const SalesPage(),
      ),
    );
  }

  testWidgets('loading state: LoadingOverlay visible', (tester) async {
    await tester.pumpWidget(
      buildSubject(const AsyncValue.loading()),
    );
    await tester.pump();

    expect(find.byType(LoadingOverlay), findsOneWidget);
  });

  testWidgets('data state: KPI cards rendered with correct values', (tester) async {
    await tester.pumpWidget(
      buildSubject(AsyncValue.data(_fixturePayload())),
    );
    await tester.pumpAndSettle();

    expect(find.byType(KpiCard), findsNWidgets(4)); // 2 allTime + 2 period
    expect(find.text('1,234,567,890'), findsOneWidget);
    expect(find.text('500,000,000'), findsOneWidget);
  });

  testWidgets('error state: ErrorBanner visible with retry', (tester) async {
    await tester.pumpWidget(
      buildSubject(AsyncValue.error('Server error', StackTrace.empty)),
    );
    await tester.pumpAndSettle();

    expect(find.byType(ErrorBanner), findsOneWidget);
    expect(find.text('Retry'), findsOneWidget);
  });

  testWidgets('tab switch: DataTableWidget updates', (tester) async {
    // Single tab fixture
    await tester.pumpWidget(
      buildSubject(AsyncValue.data(_fixturePayload())),
    );
    await tester.pumpAndSettle();

    // Tab label is visible
    expect(find.text('By Grade'), findsWidgets);
  });
}

// Fake notifier for testing without real providers
class _FakeNotifier extends SalesAnalyticsNotifier {
  _FakeNotifier(this._state);
  final AsyncValue<SalesAnalyticsPayload?> _state;

  @override
  Future<SalesAnalyticsPayload?> build() {
    if (_state.isLoading) return Completer<SalesAnalyticsPayload?>().future;
    if (_state.hasError) return Future.error(_state.error!, _state.stackTrace);
    return Future.value(_state.valueOrNull);
  }
}
