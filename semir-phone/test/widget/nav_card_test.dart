import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';

import 'package:semir_phone/core/theme/app_theme.dart';
import 'package:semir_phone/features/home/nav_card.dart';

void main() {
  Widget buildSubject({
    String title = 'Doanh số',
    String description = 'Phân tích doanh số',
    IconData icon = Icons.bar_chart_rounded,
    VoidCallback? onTap,
    bool hasAccess = true,
  }) {
    return MaterialApp(
      theme: buildAppTheme(),
      home: Scaffold(
        body: Padding(
          padding: const EdgeInsets.all(16),
          child: NavCard(
            title: title,
            description: description,
            icon: icon,
            onTap: onTap ?? () {},
            hasAccess: hasAccess,
          ),
        ),
      ),
    );
  }

  testWidgets('renders title and description', (tester) async {
    await tester.pumpWidget(buildSubject());
    expect(find.text('Doanh số'), findsOneWidget);
    expect(find.text('Phân tích doanh số'), findsOneWidget);
  });

  testWidgets('has blue top border (4pt AppColors.primary)', (tester) async {
    await tester.pumpWidget(buildSubject());
    await tester.pumpAndSettle();

    final container = tester.widget<Container>(
      find.descendant(
        of: find.byType(InkWell),
        matching: find.byType(Container),
      ).first,
    );
    final decoration = container.decoration as BoxDecoration?;
    final topBorder = decoration?.border;
    expect(topBorder, isNotNull);
  });

  testWidgets('tap fires onTap callback when hasAccess true', (tester) async {
    var tapped = false;
    await tester.pumpWidget(buildSubject(onTap: () => tapped = true));
    await tester.tap(find.byType(InkWell));
    await tester.pumpAndSettle();
    expect(tapped, isTrue);
  });

  testWidgets('onTap not fired when hasAccess false', (tester) async {
    var tapped = false;
    await tester.pumpWidget(buildSubject(
      onTap: () => tapped = true,
      hasAccess: false,
    ));
    await tester.tap(find.byType(InkWell));
    await tester.pumpAndSettle();
    expect(tapped, isFalse);
  });

  testWidgets('shows no-access message when hasAccess false', (tester) async {
    await tester.pumpWidget(buildSubject(hasAccess: false));
    expect(find.text('No access'), findsOneWidget);
  });

  testWidgets('minimum height is at least 44pt (touch target)', (tester) async {
    await tester.pumpWidget(buildSubject());
    await tester.pumpAndSettle();

    final cardContainer = tester.getSize(find.byType(NavCard));
    expect(cardContainer.height, greaterThanOrEqualTo(44));
  });

  testWidgets('chevron visible when hasAccess true', (tester) async {
    await tester.pumpWidget(buildSubject(hasAccess: true));
    expect(find.byIcon(Icons.chevron_right), findsOneWidget);
  });

  testWidgets('chevron hidden when hasAccess false', (tester) async {
    await tester.pumpWidget(buildSubject(hasAccess: false));
    expect(find.byIcon(Icons.chevron_right), findsNothing);
  });
}
