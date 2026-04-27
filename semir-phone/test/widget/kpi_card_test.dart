import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';

import 'package:semir_phone/core/theme/app_colors.dart';
import 'package:semir_phone/core/theme/app_theme.dart';
import 'package:semir_phone/shared/widgets/kpi_card.dart';

void main() {
  Widget buildSubject(KpiVariant variant) {
    return MaterialApp(
      theme: buildAppTheme(),
      home: Scaffold(
        body: KpiCard(
          label: 'Tổng doanh thu',
          value: '1,234,567,890',
          variant: variant,
        ),
      ),
    );
  }

  testWidgets('allTime variant has orange tint background', (tester) async {
    await tester.pumpWidget(buildSubject(KpiVariant.allTime));
    await tester.pumpAndSettle();

    final container = tester.widget<Container>(
      find.descendant(
        of: find.byType(KpiCard),
        matching: find.byType(Container),
      ).first,
    );
    final decoration = container.decoration as BoxDecoration?;
    expect(decoration?.color, AppColors.allTimeCardBg);
  });

  testWidgets('period variant has blue tint background', (tester) async {
    await tester.pumpWidget(buildSubject(KpiVariant.period));
    await tester.pumpAndSettle();

    final container = tester.widget<Container>(
      find.descendant(
        of: find.byType(KpiCard),
        matching: find.byType(Container),
      ).first,
    );
    final decoration = container.decoration as BoxDecoration?;
    expect(decoration?.color, AppColors.periodCardBg);
  });

  testWidgets('renders value and label text', (tester) async {
    await tester.pumpWidget(buildSubject(KpiVariant.allTime));
    await tester.pumpAndSettle();

    expect(find.text('1,234,567,890'), findsOneWidget);
    // label is uppercased in KpiCard
    expect(find.text('TỔNG DOANH THU'), findsOneWidget);
  });

  testWidgets('text color is AppColors.textDark (no hardcoded hex)', (tester) async {
    await tester.pumpWidget(buildSubject(KpiVariant.allTime));
    await tester.pumpAndSettle();

    final richTexts = tester.widgetList<Text>(find.byType(Text)).toList();
    for (final t in richTexts) {
      if (t.style?.color != null) {
        // Allow AppColors.textDark or textMuted but no hardcoded random colors
        expect(
          [AppColors.textDark, AppColors.textMuted, AppColors.white],
          contains(t.style?.color),
        );
      }
    }
  });
}
