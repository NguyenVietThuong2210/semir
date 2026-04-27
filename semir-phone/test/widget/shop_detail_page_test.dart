import 'dart:async';

import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:flutter_test/flutter_test.dart';

import 'package:semir_phone/core/theme/app_colors.dart';
import 'package:semir_phone/core/theme/app_theme.dart';
import 'package:semir_phone/features/analytics/shop_detail/shop_detail_page.dart';
import 'package:semir_phone/shared/models/analytics_models.dart';
import 'package:semir_phone/features/analytics/shop_detail/shop_detail_provider.dart';
import 'package:semir_phone/features/analytics/shop_detail/shop_detail_service.dart';
import 'package:semir_phone/shared/widgets/error_banner.dart';
import 'package:semir_phone/shared/widgets/kpi_card.dart';
import 'package:semir_phone/shared/widgets/loading_overlay.dart';

const _mockShops = ['HN01', 'HN02', 'HCM01'];

ShopDetailPayload _fixturePayload() {
  return ShopDetailPayload(
    salesAllTimeKpis: [
      const KpiItem(label: 'Tổng doanh thu', value: '5,000,000,000'),
    ],
    salesPeriodKpis: [
      const KpiItem(label: 'Doanh thu kỳ', value: '1,200,000,000'),
    ],
    salesTabs: [
      const TableTab(
        tabKey: 'by_session',
        label: 'Theo Phiên',
        headers: ['Phiên', 'Doanh thu'],
        rows: [],
      ),
    ],
    customerKpis: [
      const KpiItem(label: 'Tổng KH', value: '1,234'),
    ],
    customerTabs: [
      const TableTab(
        tabKey: 'breakdown',
        label: 'Breakdown',
        headers: ['Hạng', 'Số KH'],
        rows: [],
      ),
    ],
    couponKpis: [
      const KpiItem(label: 'Tổng coupon', value: '500'),
    ],
    couponTabs: [
      const TableTab(
        tabKey: 'detail',
        label: 'Chi tiết',
        headers: ['Coupon', 'Trạng thái'],
        rows: [],
      ),
    ],
  );
}

Widget buildSubject({
  AsyncValue<List<String>> shopsState = const AsyncValue.data(_mockShops),
  AsyncValue<ShopDetailPayload?> detailState = const AsyncValue.data(null),
  String? selectedShop,
}) {
  return ProviderScope(
    overrides: [
      shopsListProvider.overrideWith((ref) async {
        if (shopsState is AsyncLoading) {
          await Future.delayed(const Duration(days: 365));
        }
        if (shopsState is AsyncError) {
          throw (shopsState as AsyncError).error;
        }
        return (shopsState as AsyncData<List<String>>).value;
      }),
      shopDetailProvider.overrideWith(() => _FakeDetailNotifier(detailState)),
      if (selectedShop != null)
        selectedShopProvider.overrideWith((ref) => selectedShop),
    ],
    child: MaterialApp(
      theme: buildAppTheme(),
      home: const ShopDetailPage(),
    ),
  );
}

void main() {
  testWidgets('dropdown populated from shops list', (tester) async {
    await tester.pumpWidget(buildSubject());
    await tester.pumpAndSettle();

    // Open the dropdown
    await tester.tap(find.byType(DropdownButtonFormField<String>));
    await tester.pumpAndSettle();

    expect(find.text('HN01'), findsWidgets);
    expect(find.text('HN02'), findsWidgets);
    expect(find.text('HCM01'), findsWidgets);
  });

  testWidgets('empty shops list → "no shops" message shown', (tester) async {
    await tester.pumpWidget(
      buildSubject(shopsState: const AsyncValue.data([])),
    );
    await tester.pumpAndSettle();

    // With empty list the page renders a Text notice instead of a dropdown.
    expect(find.text('No stores available'), findsOneWidget);
    expect(find.byType(DropdownButtonFormField<String>), findsNothing);
  });

  testWidgets('no shop selected → detail sections not shown', (tester) async {
    await tester.pumpWidget(buildSubject(detailState: const AsyncValue.data(null)));
    await tester.pumpAndSettle();

    expect(find.byType(KpiCard), findsNothing);
  });

  testWidgets('data loaded → 3 section headers visible', (tester) async {
    await tester.pumpWidget(
      buildSubject(
        detailState: AsyncValue.data(_fixturePayload()),
        selectedShop: 'HN01',
      ),
    );
    await tester.pumpAndSettle();

    // All 3 sections: Sales, Customer, Coupon
    expect(find.text('Sales'), findsWidgets);
    expect(find.text('Customers'), findsWidgets);
    expect(find.text('Coupon'), findsWidgets);
  });

  testWidgets('loading state → LoadingOverlay visible', (tester) async {
    await tester.pumpWidget(
      buildSubject(detailState: const AsyncValue.loading()),
    );
    await tester.pump();

    expect(find.byType(LoadingOverlay), findsOneWidget);
  });

  testWidgets('error state → ErrorBanner visible', (tester) async {
    await tester.pumpWidget(
      buildSubject(
        detailState: AsyncValue.error('Network error', StackTrace.empty),
        selectedShop: 'HN01',
      ),
    );
    await tester.pumpAndSettle();

    expect(find.byType(ErrorBanner), findsOneWidget);
  });

  testWidgets('section card top-border uses AppColors.primary', (tester) async {
    await tester.pumpWidget(
      buildSubject(
        detailState: AsyncValue.data(_fixturePayload()),
        selectedShop: 'HN01',
      ),
    );
    await tester.pumpAndSettle();

    // Find containers with top-border decoration using primary color
    final containers = tester.widgetList<Container>(find.byType(Container));
    bool foundPrimaryBorder = false;
    for (final container in containers) {
      final decoration = container.decoration;
      if (decoration is BoxDecoration && decoration.border != null) {
        final border = decoration.border as Border;
        if (border.top.color == AppColors.primary && border.top.width == 4.0) {
          foundPrimaryBorder = true;
          break;
        }
      }
    }
    expect(foundPrimaryBorder, isTrue,
        reason: 'No section card with 4pt primary top-border found');
  });
}

class _FakeDetailNotifier extends ShopDetailNotifier {
  _FakeDetailNotifier(this._state);
  final AsyncValue<ShopDetailPayload?> _state;

  @override
  Future<ShopDetailPayload?> build() {
    if (_state.isLoading) return Completer<ShopDetailPayload?>().future;
    if (_state.hasError) return Future.error(_state.error!, _state.stackTrace);
    return Future.value(_state.valueOrNull);
  }
}
