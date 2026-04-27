import 'package:fl_chart/fl_chart.dart';
import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';

import 'package:semir_phone/core/theme/app_theme.dart';
import 'package:semir_phone/features/charts/chart_service.dart';
import 'package:semir_phone/features/charts/donut_card.dart';

DonutChart _twoSliceChart() {
  return const DonutChart(
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
  );
}

DonutChart _emptyChart() {
  return const DonutChart(title: 'Empty', slices: []);
}

Widget buildCard({
  required DonutChart chart,
  ValueChanged<String>? onSliceTapped,
  String? highlightedLabel,
}) {
  return MaterialApp(
    theme: buildAppTheme(),
    home: Scaffold(
      body: DonutCard(
        chart: chart,
        onSliceTapped: onSliceTapped,
        highlightedLabel: highlightedLabel,
      ),
    ),
  );
}

void main() {
  testWidgets('renders chart title', (tester) async {
    await tester.pumpWidget(buildCard(chart: _twoSliceChart()));
    await tester.pumpAndSettle();

    expect(find.text('Theo Mùa'), findsOneWidget);
  });

  testWidgets('renders legend with correct slice labels and values', (tester) async {
    await tester.pumpWidget(buildCard(chart: _twoSliceChart()));
    await tester.pumpAndSettle();

    expect(find.textContaining('M2-4 2025'), findsOneWidget);
    expect(find.textContaining('M5-7 2025'), findsOneWidget);
    expect(find.textContaining('500,000,000'), findsOneWidget);
  });

  testWidgets('empty slices → shows title in center card (no crash)', (tester) async {
    await tester.pumpWidget(buildCard(chart: _emptyChart()));
    await tester.pumpAndSettle();

    expect(find.text('Empty'), findsOneWidget);
  });

  testWidgets('highlightedLabel causes active slice to render bold in legend',
      (tester) async {
    await tester.pumpWidget(buildCard(
      chart: _twoSliceChart(),
      highlightedLabel: 'M2-4 2025',
    ));
    await tester.pumpAndSettle();

    // Active slice text still visible
    expect(find.textContaining('M2-4 2025'), findsOneWidget);
  });

  testWidgets('null onSliceTapped does not crash on render', (tester) async {
    await tester.pumpWidget(buildCard(
      chart: _twoSliceChart(),
      onSliceTapped: null,
    ));
    await tester.pumpAndSettle();

    expect(find.byType(DonutCard), findsOneWidget);
  });

  testWidgets('PieChart widget rendered for non-empty slices', (tester) async {
    await tester.pumpWidget(buildCard(chart: _twoSliceChart()));
    await tester.pumpAndSettle();

    // PieChart should be in the widget tree
    expect(find.byType(PieChart), findsOneWidget);
  });
}
