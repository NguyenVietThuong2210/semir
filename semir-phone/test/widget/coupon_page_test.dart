import 'dart:async';

import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:flutter_test/flutter_test.dart';

import 'package:semir_phone/core/theme/app_theme.dart';
import 'package:semir_phone/features/analytics/coupon/coupon_page.dart';
import 'package:semir_phone/features/analytics/coupon/coupon_provider.dart';
import 'package:semir_phone/features/analytics/coupon/coupon_service.dart';
import 'package:semir_phone/shared/models/analytics_models.dart';
import 'package:semir_phone/shared/widgets/error_banner.dart';
import 'package:semir_phone/shared/widgets/kpi_card.dart';
import 'package:semir_phone/shared/widgets/loading_overlay.dart';

CouponAnalyticsPayload _fixturePayload() {
  return CouponAnalyticsPayload(
    allTimeKpis: [
      const KpiItem(label: 'Tổng coupon', value: '10,000'),
      const KpiItem(label: 'Đã dùng', value: '6,500'),
    ],
    periodKpis: [
      const KpiItem(label: 'Coupon kỳ', value: '2,000'),
    ],
    tabs: [
      const TableTab(
        tabKey: 'by_shop',
        label: 'Theo Cửa hàng',
        headers: ['Cửa hàng', 'Số coupon'],
        rows: [['HN01', '500']],
      ),
      const TableTab(
        tabKey: 'detail',
        label: 'Chi tiết',
        headers: ['Coupon', 'Trạng thái'],
        rows: [],
      ),
      const TableTab(
        tabKey: 'duplicates',
        label: 'Trùng lặp',
        headers: ['Coupon', 'Lần dùng'],
        rows: [],
      ),
    ],
  );
}

void main() {
  Widget buildSubject(
    AsyncValue<CouponAnalyticsPayload?> state, {
    Map<Override, Override>? extras,
  }) {
    return ProviderScope(
      overrides: [
        couponAnalyticsProvider.overrideWith(() => _FakeNotifier(state)),
      ],
      child: MaterialApp(
        theme: buildAppTheme(),
        home: const CouponPage(),
      ),
    );
  }

  testWidgets('loading state: LoadingOverlay visible', (tester) async {
    await tester.pumpWidget(buildSubject(const AsyncValue.loading()));
    await tester.pump();

    expect(find.byType(LoadingOverlay), findsOneWidget);
  });

  testWidgets('error state: ErrorBanner visible with retry', (tester) async {
    await tester.pumpWidget(
      buildSubject(AsyncValue.error('Server error', StackTrace.empty)),
    );
    await tester.pumpAndSettle();

    expect(find.byType(ErrorBanner), findsOneWidget);
    expect(find.text('Retry'), findsOneWidget);
  });

  testWidgets('data state: KPI cards rendered', (tester) async {
    await tester.pumpWidget(buildSubject(AsyncValue.data(_fixturePayload())));
    await tester.pumpAndSettle();

    expect(find.byType(KpiCard), findsWidgets);
    expect(find.text('10,000'), findsOneWidget);
    expect(find.text('6,500'), findsOneWidget);
  });

  testWidgets('stat cards use only allTimeCardBg or periodCardBg backgrounds',
      (tester) async {
    await tester.pumpWidget(buildSubject(AsyncValue.data(_fixturePayload())));
    await tester.pumpAndSettle();

    final kpiCards = tester.widgetList<KpiCard>(find.byType(KpiCard)).toList();
    expect(kpiCards, isNotEmpty);

    // Every KpiCard must use allTimeCardBg or periodCardBg — no other colors
    for (final card in kpiCards) {
      expect(
        card.variant == KpiVariant.allTime || card.variant == KpiVariant.period,
        isTrue,
        reason: 'KpiCard "${card.label}" has unexpected variant',
      );
    }
  });

  testWidgets('no green/red/yellow background colors on any KPI card',
      (tester) async {
    await tester.pumpWidget(buildSubject(AsyncValue.data(_fixturePayload())));
    await tester.pumpAndSettle();

    // Verify AppColors.allTimeCardBg and periodCardBg are the only backgrounds
    // This ensures no status-color (green/red/yellow) semantics on coupon cards
    final forbiddenColors = [Colors.green, Colors.red, Colors.yellow, Colors.amber];

    // Find all Containers with decoration — none should use the forbidden colors
    final containers = tester.widgetList<Container>(find.byType(Container));
    for (final container in containers) {
      final decoration = container.decoration;
      if (decoration is BoxDecoration && decoration.color != null) {
        for (final forbidden in forbiddenColors) {
          expect(
            decoration.color!.toARGB32(),
            isNot(equals(forbidden.value)),
            reason: 'Found forbidden solid color background on a Container',
          );
        }
      }
    }
  });

  testWidgets('tab switch: switching to Detail tab works', (tester) async {
    await tester.pumpWidget(
      ProviderScope(
        overrides: [
          couponAnalyticsProvider
              .overrideWith(() => _FakeNotifier(AsyncValue.data(_fixturePayload()))),
          // Override the lazy tab provider so it resolves without HTTP calls.
          couponTabProvider.overrideWith((ref, key) async => const TableTab(
                tabKey: 'detail',
                label: 'Detail',
                headers: ['Coupon', 'Status'],
                rows: [],
              )),
        ],
        child: MaterialApp(
          theme: buildAppTheme(),
          home: const CouponPage(),
        ),
      ),
    );
    await tester.pumpAndSettle();

    expect(find.text('Detail'), findsWidgets);
    await tester.tap(find.text('Detail').first);
    await tester.pumpAndSettle();

    expect(find.byType(CouponPage), findsOneWidget);
  });

  testWidgets('tab labels: By Store / Detail / Duplicates all visible',
      (tester) async {
    await tester.pumpWidget(buildSubject(AsyncValue.data(_fixturePayload())));
    await tester.pumpAndSettle();

    expect(find.text('By Store'), findsWidgets);
    expect(find.text('Detail'), findsWidgets);
    expect(find.text('Duplicates'), findsWidgets);
  });
}

class _FakeNotifier extends CouponAnalyticsNotifier {
  _FakeNotifier(this._state);
  final AsyncValue<CouponAnalyticsPayload?> _state;

  @override
  Future<CouponAnalyticsPayload?> build() {
    if (_state.isLoading) return Completer<CouponAnalyticsPayload?>().future;
    if (_state.hasError) return Future.error(_state.error!, _state.stackTrace);
    return Future.value(_state.valueOrNull);
  }
}
