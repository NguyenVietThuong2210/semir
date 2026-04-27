import 'dart:async';

import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:flutter_test/flutter_test.dart';

import 'package:semir_phone/core/theme/app_theme.dart';
import 'package:semir_phone/features/charts/chart_provider.dart';
import 'package:semir_phone/features/charts/chart_service.dart';
import 'package:semir_phone/features/charts/donut_card.dart';
import 'package:semir_phone/features/charts/sales_chart_page.dart';

ChartPayload _interactionPayload() {
  return const ChartPayload(
    donuts: [
      DonutChart(
        title: 'Theo Mùa',
        slices: [
          DonutSlice(
            label: 'M2-4 2025',
            value: '500,000,000',
            color: '#0D6EFD',
            percentage: 40.0,
          ),
          DonutSlice(
            label: 'M5-7 2025',
            value: '300,000,000',
            color: '#FF6B6B',
            percentage: 24.0,
          ),
        ],
      ),
    ],
    trend: null,
  );
}

Widget buildSubject() {
  return ProviderScope(
    overrides: [
      salesChartProvider.overrideWith(
        () => _FakeNotifier(AsyncValue.data(_interactionPayload())),
      ),
    ],
    child: MaterialApp(
      theme: buildAppTheme(),
      home: const SalesChartPage(),
    ),
  );
}

void main() {
  testWidgets('selectedSliceLabelProvider starts null', (tester) async {
    late WidgetRef capturedRef;

    await tester.pumpWidget(ProviderScope(
      overrides: [
        salesChartProvider.overrideWith(
          () => _FakeNotifier(AsyncValue.data(_interactionPayload())),
        ),
      ],
      child: MaterialApp(
        theme: buildAppTheme(),
        home: Consumer(
          builder: (context, ref, _) {
            capturedRef = ref;
            return const SalesChartPage();
          },
        ),
      ),
    ));
    await tester.pumpAndSettle();

    expect(capturedRef.read(selectedSliceLabelProvider), isNull);
  });

  testWidgets('DonutCard renders with correct slice count', (tester) async {
    await tester.pumpWidget(buildSubject());
    await tester.pumpAndSettle();

    expect(find.byType(DonutCard), findsOneWidget);
    // 2 slices in legend
    expect(find.textContaining('M2-4 2025'), findsOneWidget);
    expect(find.textContaining('M5-7 2025'), findsOneWidget);
  });

  testWidgets(
      'selectedSliceLabelProvider update causes DonutCard to highlight that slice',
      (tester) async {
    late WidgetRef capturedRef;

    await tester.pumpWidget(ProviderScope(
      overrides: [
        salesChartProvider.overrideWith(
          () => _FakeNotifier(AsyncValue.data(_interactionPayload())),
        ),
      ],
      child: MaterialApp(
        theme: buildAppTheme(),
        home: Consumer(
          builder: (context, ref, _) {
            capturedRef = ref;
            return const SalesChartPage();
          },
        ),
      ),
    ));
    await tester.pumpAndSettle();

    // Programmatically set the selected slice
    capturedRef.read(selectedSliceLabelProvider.notifier).state = 'M2-4 2025';
    await tester.pump();

    // The DonutCard should receive the new highlightedLabel and re-render
    final donutCard = tester.widget<DonutCard>(find.byType(DonutCard));
    expect(donutCard.highlightedLabel, 'M2-4 2025');
  });

  testWidgets('DonutCard passes onSliceTapped callback that updates provider',
      (tester) async {
    late WidgetRef capturedRef;

    await tester.pumpWidget(ProviderScope(
      overrides: [
        salesChartProvider.overrideWith(
          () => _FakeNotifier(AsyncValue.data(_interactionPayload())),
        ),
      ],
      child: MaterialApp(
        theme: buildAppTheme(),
        home: Consumer(
          builder: (context, ref, _) {
            capturedRef = ref;
            return const SalesChartPage();
          },
        ),
      ),
    ));
    await tester.pumpAndSettle();

    // Verify callback is wired — simulate calling it directly
    final donutCard = tester.widget<DonutCard>(find.byType(DonutCard));
    expect(donutCard.onSliceTapped, isNotNull);

    // Call the callback directly with a label
    donutCard.onSliceTapped!('M5-7 2025');
    await tester.pump();

    expect(capturedRef.read(selectedSliceLabelProvider), 'M5-7 2025');
  });
}

class _FakeNotifier extends SalesChartNotifier {
  _FakeNotifier(this._state);
  final AsyncValue<ChartPayload?> _state;

  @override
  Future<ChartPayload?> build() {
    if (_state.isLoading) return Completer<ChartPayload?>().future;
    if (_state.hasError) return Future.error(_state.error!, _state.stackTrace);
    return Future.value(_state.valueOrNull);
  }
}
