import 'dart:async';

import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:flutter_test/flutter_test.dart';

import 'package:semir_phone/core/theme/app_colors.dart';
import 'package:semir_phone/core/theme/app_theme.dart';
import 'package:semir_phone/features/analytics/shop_detail/shop_detail_page.dart';
import 'package:semir_phone/features/analytics/shop_detail/shop_detail_provider.dart';
import 'package:semir_phone/features/analytics/shop_detail/shop_detail_service.dart';
import 'package:semir_phone/shared/models/analytics_models.dart';
import 'package:semir_phone/shared/widgets/error_banner.dart';
import 'package:semir_phone/shared/widgets/kpi_card.dart';
import 'package:semir_phone/shared/widgets/loading_overlay.dart';

const _mockShops = ['HN01', 'HN02', 'HCM01'];

ShopSalesPayload _fixtureSalesPayload() {
  return ShopSalesPayload(
    allTimeKpis: const [
      KpiItem(label: 'Active', value: '1,234'),
      KpiItem(label: 'Returning', value: '890'),
      KpiItem(label: 'Return Rate', value: '72.12%'),
    ],
    periodKpis: const [
      KpiItem(label: 'Active', value: '400'),
    ],
    tabs: const [
      TableTab(
        tabKey: 'by_session',
        label: 'By Season',
        headers: ['Season', 'Active'],
        rows: [],
      ),
    ],
  );
}

Widget buildSubject({
  AsyncValue<List<String>> shopsState = const AsyncValue.data(_mockShops),
  AsyncValue<ShopSalesPayload?> salesState = const AsyncValue.data(null),
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
      shopDetailSalesProvider
          .overrideWith(() => _FakeSalesNotifier(salesState)),
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

    expect(find.text('No stores available'), findsOneWidget);
    expect(find.byType(DropdownButtonFormField<String>), findsNothing);
  });

  testWidgets('no shop selected → detail sections not shown', (tester) async {
    await tester.pumpWidget(buildSubject(salesState: const AsyncValue.data(null)));
    await tester.pumpAndSettle();

    expect(find.byType(KpiCard), findsNothing);
  });

  testWidgets('data loaded → section tab bar visible', (tester) async {
    await tester.pumpWidget(
      buildSubject(salesState: AsyncValue.data(_fixtureSalesPayload())),
    );
    await tester.pumpAndSettle();

    // Select a shop via the provider container (avoids HTTP call from notifier).
    final container = ProviderScope.containerOf(
      tester.element(find.byType(ShopDetailPage)),
    );
    container.read(selectedShopProvider.notifier).state = 'HN01';
    await tester.pumpAndSettle();

    // Section tab buttons should be visible
    expect(find.text('Sales'), findsWidgets);
    expect(find.text('Customers'), findsOneWidget);
    expect(find.text('Coupon'), findsOneWidget);
  });

  testWidgets('data loaded → KPI cards visible for sales section', (tester) async {
    await tester.pumpWidget(
      buildSubject(salesState: AsyncValue.data(_fixtureSalesPayload())),
    );
    await tester.pumpAndSettle();

    final container = ProviderScope.containerOf(
      tester.element(find.byType(ShopDetailPage)),
    );
    container.read(selectedShopProvider.notifier).state = 'HN01';
    await tester.pumpAndSettle();

    expect(find.byType(KpiCard), findsWidgets);
    // KpiCard uppercases its label — fixture label 'Active' renders as 'ACTIVE'.
    expect(find.text('ACTIVE'), findsWidgets);
  });

  testWidgets('loading state → LoadingOverlay visible', (tester) async {
    await tester.pumpWidget(
      buildSubject(salesState: const AsyncValue.loading()),
    );
    await tester.pump();

    expect(find.byType(LoadingOverlay), findsOneWidget);
  });

  testWidgets('error state → ErrorBanner visible when shop is selected',
      (tester) async {
    await tester.pumpWidget(
      buildSubject(
        salesState: AsyncValue.error('Network error', StackTrace.empty),
        selectedShop: 'HN01',
      ),
    );
    await tester.pumpAndSettle();

    expect(find.byType(ErrorBanner), findsOneWidget);
  });

  testWidgets('section card top-border uses AppColors.primary', (tester) async {
    await tester.pumpWidget(
      buildSubject(
        salesState: AsyncValue.data(_fixtureSalesPayload()),
        selectedShop: 'HN01',
      ),
    );
    await tester.pumpAndSettle();

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

class _FakeSalesNotifier extends ShopDetailSalesNotifier {
  _FakeSalesNotifier(this._state);
  final AsyncValue<ShopSalesPayload?> _state;

  @override
  Future<ShopSalesPayload?> build() {
    if (_state.isLoading) return Completer<ShopSalesPayload?>().future;
    if (_state.hasError) return Future.error(_state.error!, _state.stackTrace);
    return Future.value(_state.valueOrNull);
  }
}
