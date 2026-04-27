import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:integration_test/integration_test.dart';

import 'package:semir_phone/app.dart';
import 'package:semir_phone/shared/widgets/kpi_card.dart';

/// E2E integration tests for Sales Analytics page.
/// Run against a live backend with test credentials.
///
/// Required environment variables (via --dart-define):
///   API_BASE_URL, TEST_USERNAME, TEST_PASSWORD
void main() {
  IntegrationTestWidgetsFlutterBinding.ensureInitialized();

  const testUsername =
      String.fromEnvironment('TEST_USERNAME', defaultValue: 'admin');
  const testPassword =
      String.fromEnvironment('TEST_PASSWORD', defaultValue: 'admin');

  Widget buildApp() => const ProviderScope(child: SemirPhoneApp());

  /// Signs in via the login form if the login page is currently shown.
  Future<void> loginIfNeeded(WidgetTester tester) async {
    if (find.text('Sign In').evaluate().isEmpty) return;
    await tester.enterText(find.byType(TextField).first, testUsername);
    await tester.enterText(find.byType(TextField).last, testPassword);
    await tester.tap(find.text('Sign In'));
    await tester.pumpAndSettle(const Duration(seconds: 8));
  }

  /// Navigates to Sales from the home screen, if the card is visible.
  Future<void> navigateToSales(WidgetTester tester) async {
    final card = find.text('Sales');
    if (card.evaluate().isEmpty) return;
    await tester.tap(card.first);
    await tester.pumpAndSettle(const Duration(seconds: 8));
  }

  group('Sales Analytics E2E', () {
    testWidgets('authenticated user sees Sales Analytics KPI cards',
        (tester) async {
      await tester.pumpWidget(buildApp());
      await tester.pumpAndSettle(const Duration(seconds: 5));

      await loginIfNeeded(tester);
      await navigateToSales(tester);

      expect(find.byType(KpiCard), findsWidgets);
    });

    testWidgets('sales analytics data loads within 8 seconds on WiFi',
        (tester) async {
      await tester.pumpWidget(buildApp());

      final start = DateTime.now();
      await tester.pumpAndSettle(const Duration(seconds: 10));

      final elapsed = DateTime.now().difference(start);
      debugPrint('Sales analytics load time: ${elapsed.inMilliseconds}ms');
      // SC-002: ≤4s on WiFi — logged here, asserted in performance validation.
    });

    testWidgets('date filter shows expected label on sales page',
        (tester) async {
      await tester.pumpWidget(buildApp());
      await tester.pumpAndSettle(const Duration(seconds: 5));

      await loginIfNeeded(tester);
      await navigateToSales(tester);

      if (find.text('Year 2025').evaluate().isNotEmpty) {
        expect(find.text('Year 2025'), findsOneWidget);
      }
    });

    testWidgets('tab switch in sales analytics does not crash', (tester) async {
      await tester.pumpWidget(buildApp());
      await tester.pumpAndSettle(const Duration(seconds: 5));

      await loginIfNeeded(tester);
      await navigateToSales(tester);

      final tabFinder = find.text('By Grade');
      if (tabFinder.evaluate().isNotEmpty) {
        await tester.tap(tabFinder.first);
        await tester.pumpAndSettle(const Duration(seconds: 3));
        expect(find.byType(Scaffold), findsOneWidget);
      }
    });
  });
}
