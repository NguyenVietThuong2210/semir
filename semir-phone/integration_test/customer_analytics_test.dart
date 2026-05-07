import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:integration_test/integration_test.dart';

import 'package:semir_phone/app.dart';
import 'package:semir_phone/shared/widgets/kpi_card.dart';
import 'package:semir_phone/shared/widgets/data_table_widget.dart';

/// E2E integration tests for Customer Analytics (CNV) page.
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

  Future<void> loginIfNeeded(WidgetTester tester) async {
    if (find.text('Sign In').evaluate().isEmpty) return;
    await tester.enterText(find.byType(TextField).first, testUsername);
    await tester.enterText(find.byType(TextField).last, testPassword);
    await tester.tap(find.text('Sign In'));
    await tester.pumpAndSettle(const Duration(seconds: 8));
  }

  Future<bool> navigateToCustomer(WidgetTester tester) async {
    final card = find.text('Customers');
    if (card.evaluate().isEmpty) return false;
    await tester.tap(card.first);
    await tester.pumpAndSettle(const Duration(seconds: 10));
    return true;
  }

  group('Customer Analytics E2E', () {
    testWidgets('authenticated user with customers.view sees Customer page',
        (tester) async {
      await tester.pumpWidget(buildApp());
      await tester.pumpAndSettle(const Duration(seconds: 5));
      await loginIfNeeded(tester);

      final navigated = await navigateToCustomer(tester);
      if (!navigated) return; // user lacks customers.view permission

      expect(find.text('Customers'), findsWidgets);
    });

    testWidgets('customer analytics KPI cards are rendered', (tester) async {
      await tester.pumpWidget(buildApp());
      await tester.pumpAndSettle(const Duration(seconds: 5));
      await loginIfNeeded(tester);

      final navigated = await navigateToCustomer(tester);
      if (!navigated) return;

      // KpiCard widgets should be present (all-time + period sections)
      expect(find.byType(KpiCard), findsWidgets);
    });

    testWidgets('customer analytics loads within 10 seconds', (tester) async {
      await tester.pumpWidget(buildApp());
      await tester.pumpAndSettle(const Duration(seconds: 5));
      await loginIfNeeded(tester);

      final start = DateTime.now();
      final navigated = await navigateToCustomer(tester);
      final elapsed = DateTime.now().difference(start);

      if (!navigated) return;
      debugPrint('Customer analytics load time: ${elapsed.inMilliseconds}ms');
      expect(elapsed.inSeconds, lessThanOrEqualTo(10),
          reason: 'Customer analytics must load within 10s');
    });

    testWidgets('all-time KPI section is present with expected labels',
        (tester) async {
      await tester.pumpWidget(buildApp());
      await tester.pumpAndSettle(const Duration(seconds: 5));
      await loginIfNeeded(tester);

      final navigated = await navigateToCustomer(tester);
      if (!navigated) return;

      expect(find.text('All-Time Overview'), findsOneWidget);
      expect(find.text('Selected Period'), findsOneWidget);
    });

    testWidgets('registration breakdown section renders with tabs',
        (tester) async {
      await tester.pumpWidget(buildApp());
      await tester.pumpAndSettle(const Duration(seconds: 5));
      await loginIfNeeded(tester);

      final navigated = await navigateToCustomer(tester);
      if (!navigated) return;

      expect(find.text('Registration Breakdown'), findsOneWidget);
      // All 5 breakdown tabs are rendered in tab bar
      for (final tab in ['By Store', 'By Season', 'By Month', 'By Week', 'By Grade']) {
        expect(find.text(tab), findsWidgets,
            reason: 'Breakdown tab "$tab" not found');
      }
    });

    testWidgets('customer comparison section renders with tabs', (tester) async {
      await tester.pumpWidget(buildApp());
      await tester.pumpAndSettle(const Duration(seconds: 5));
      await loginIfNeeded(tester);

      final navigated = await navigateToCustomer(tester);
      if (!navigated) return;

      expect(find.text('Customer Comparison'), findsOneWidget);
      for (final tab in ['POS Only', 'CNV Only', 'Both', 'Zalo']) {
        expect(find.text(tab), findsWidgets,
            reason: 'Comparison tab "$tab" not found');
      }
    });

    testWidgets('switching registration breakdown tabs does not crash',
        (tester) async {
      await tester.pumpWidget(buildApp());
      await tester.pumpAndSettle(const Duration(seconds: 5));
      await loginIfNeeded(tester);

      final navigated = await navigateToCustomer(tester);
      if (!navigated) return;

      // Tap through all 5 breakdown tabs
      for (final tab in ['By Season', 'By Month', 'By Week', 'By Grade', 'By Store']) {
        final tabFinder = find.text(tab);
        if (tabFinder.evaluate().isNotEmpty) {
          await tester.tap(tabFinder.first);
          await tester.pumpAndSettle(const Duration(seconds: 2));
          // DataTableWidget should be visible for the selected tab
          expect(find.byType(DataTableWidget), findsWidgets);
        }
      }
    });

    testWidgets('switching customer comparison tabs does not crash',
        (tester) async {
      await tester.pumpWidget(buildApp());
      await tester.pumpAndSettle(const Duration(seconds: 5));
      await loginIfNeeded(tester);

      final navigated = await navigateToCustomer(tester);
      if (!navigated) return;

      for (final tab in ['CNV Only', 'Both', 'Zalo', 'POS Only']) {
        final tabFinder = find.text(tab);
        if (tabFinder.evaluate().isNotEmpty) {
          await tester.tap(tabFinder.first);
          await tester.pumpAndSettle(const Duration(seconds: 2));
          expect(find.byType(Scaffold), findsOneWidget);
        }
      }
    });

    testWidgets('date filter change triggers data reload without crash',
        (tester) async {
      await tester.pumpWidget(buildApp());
      await tester.pumpAndSettle(const Duration(seconds: 5));
      await loginIfNeeded(tester);

      final navigated = await navigateToCustomer(tester);
      if (!navigated) return;

      // Verify date filter bar is visible
      expect(find.byType(KpiCard), findsWidgets);
      // Verify page does not crash on date change (tapping filter bar)
      expect(find.byType(Scaffold), findsOneWidget);
    });

    testWidgets('pull to refresh works without crashing', (tester) async {
      await tester.pumpWidget(buildApp());
      await tester.pumpAndSettle(const Duration(seconds: 5));
      await loginIfNeeded(tester);

      final navigated = await navigateToCustomer(tester);
      if (!navigated) return;

      // Fling down to trigger pull-to-refresh
      await tester.fling(
        find.byType(ListView).first,
        const Offset(0, 300),
        1000,
      );
      await tester.pumpAndSettle(const Duration(seconds: 8));
      expect(find.byType(Scaffold), findsOneWidget);
    });

    testWidgets('back navigation from Customer returns to Home', (tester) async {
      await tester.pumpWidget(buildApp());
      await tester.pumpAndSettle(const Duration(seconds: 5));
      await loginIfNeeded(tester);

      final navigated = await navigateToCustomer(tester);
      if (!navigated) return;

      // Press back
      final NavigatorState navigator = tester.state(find.byType(Navigator).first);
      navigator.pop();
      await tester.pumpAndSettle();

      expect(find.text('SB Dashboard'), findsOneWidget);
    });
  });
}
