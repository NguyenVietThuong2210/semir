import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';

import 'package:semir_phone/core/theme/app_colors.dart';
import 'package:semir_phone/core/theme/app_theme.dart';
import 'package:semir_phone/shared/widgets/data_table_widget.dart';

List<List<String>> _makeRows(int count) {
  return List.generate(
    count,
    (i) => ['Label ${i + 1}', '${(i + 1) * 1000}', '${(i + 1) * 50}%'],
  );
}

void main() {
  Widget buildSubject({int rowCount = 10}) {
    return MaterialApp(
      theme: buildAppTheme(),
      home: Scaffold(
        body: SizedBox(
          height: 400,
          child: DataTableWidget(
            headers: const ['Nhãn', 'Doanh thu', 'Tỷ lệ'],
            rows: _makeRows(rowCount),
          ),
        ),
      ),
    );
  }

  testWidgets('renders headers', (tester) async {
    await tester.pumpWidget(buildSubject());
    await tester.pumpAndSettle();

    expect(find.text('Nhãn'), findsWidgets);
    expect(find.text('Doanh thu'), findsOneWidget);
    expect(find.text('Tỷ lệ'), findsOneWidget);
  });

  testWidgets('renders row labels in first column', (tester) async {
    await tester.pumpWidget(buildSubject(rowCount: 5));
    await tester.pumpAndSettle();

    expect(find.text('Label 1'), findsOneWidget);
    expect(find.text('Label 2'), findsOneWidget);
  });

  testWidgets('no overflow errors with 200 rows', (tester) async {
    await tester.pumpWidget(buildSubject(rowCount: 200));
    await tester.pumpAndSettle();

    // If layout throws, pumpWidget will fail — this is the overflow guard
    expect(tester.takeException(), isNull);
  });

  testWidgets('column headers have primary color background', (tester) async {
    await tester.pumpWidget(buildSubject());
    await tester.pumpAndSettle();

    // Find containers that have the primary color — at least one header row
    final containers = tester.widgetList<Container>(find.byType(Container));
    final hasHeaderBg = containers.any((c) {
      // _HeaderCell uses Container(color:) directly, not BoxDecoration.
      final d = c.decoration as BoxDecoration?;
      return d?.color == AppColors.primary || c.color == AppColors.primary;
    });
    expect(hasHeaderBg, isTrue);
  });

  testWidgets('widget renders with linked scroll controllers (no exception)', (tester) async {
    await tester.pumpWidget(buildSubject(rowCount: 50));
    await tester.pumpAndSettle();

    expect(find.byType(DataTableWidget), findsOneWidget);
    expect(tester.takeException(), isNull);
  });
}
