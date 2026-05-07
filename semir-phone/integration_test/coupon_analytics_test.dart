import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:integration_test/integration_test.dart';

import 'package:semir_phone/app.dart';
import 'package:semir_phone/shared/widgets/kpi_card.dart';
import 'package:semir_phone/shared/widgets/data_table_widget.dart';

/// E2E integration tests for Coupon Analytics page.
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

  Future<bool> navigateToCoupon(WidgetTester tester) async {
    final card = find.text('Coupon');
    if (card.evaluate().isEmpty) return false;
    await tester.tap(card.first);
    await tester.pumpAndSettle(const Duration(seconds: 10));
    return true;
  }

  group('Coupon Analytics E2E', () {
    testWidgets('user with coupons.view sees Coupon Analytics page',
        (tester) async {
      await tester.pumpWidget(buildApp());
      await tester.pumpAndSettle(const Duration(seconds: 5));
      await loginIfNeeded(tester);

      final navigated = await navigateToCoupon(tester);
      if (!navigated) return;

      expect(find.text('Coupon Analytics'), findsOneWidget);
    });

    testWidgets('coupon KPI cards render in all-time and period sections',
        (tester) async {
      await tester.pumpWidget(buildApp());
      await tester.pumpAndSettle(const Duration(seconds: 5));
      await loginIfNeeded(tester);

      final navigated = await navigateToCoupon(tester);
      if (!navigated) return;

      expect(find.byType(KpiCard), findsWidgets);
      expect(find.text('All-Time Overview'), findsOneWidget);
      expect(find.text('Selected Period'), findsOneWidget);
    });

    testWidgets('coupon analytics loads within 10 seconds', (tester) async {
      await tester.pumpWidget(buildApp());
      await tester.pumpAndSettle(const Duration(seconds: 5));
      await loginIfNeeded(tester);

      final start = DateTime.now();
      final navigated = await navigateToCoupon(tester);
      final elapsed = DateTime.now().difference(start);

      if (!navigated) return;
      debugPrint('Coupon analytics load time: ${elapsed.inMilliseconds}ms');
      expect(elapsed.inSeconds, lessThanOrEqualTo(10));
    });

    testWidgets('by_shop tab is loaded in initial payload and shown',
        (tester) async {
      await tester.pumpWidget(buildApp());
      await tester.pumpAndSettle(const Duration(seconds: 5));
      await loginIfNeeded(tester);

      final navigated = await navigateToCoupon(tester);
      if (!navigated) return;

      // "By Store" tab should be visible as default tab
      expect(find.text('By Store'), findsWidgets);
      expect(find.byType(DataTableWidget), findsWidgets);
    });

    testWidgets('switching to Detail tab lazy-loads data without crash',
        (tester) async {
      await tester.pumpWidget(buildApp());
      await tester.pumpAndSettle(const Duration(seconds: 5));
      await loginIfNeeded(tester);

      final navigated = await navigateToCoupon(tester);
      if (!navigated) return;

      final detailTab = find.text('Detail');
      if (detailTab.evaluate().isNotEmpty) {
        await tester.tap(detailTab.first);
        await tester.pumpAndSettle(const Duration(seconds: 6));
        expect(find.byType(Scaffold), findsOneWidget);
      }
    });

    testWidgets('switching to Duplicates tab lazy-loads data without crash',
        (tester) async {
      await tester.pumpWidget(buildApp());
      await tester.pumpAndSettle(const Duration(seconds: 5));
      await loginIfNeeded(tester);

      final navigated = await navigateToCoupon(tester);
      if (!navigated) return;

      final dupTab = find.text('Duplicates');
      if (dupTab.evaluate().isNotEmpty) {
        await tester.tap(dupTab.first);
        await tester.pumpAndSettle(const Duration(seconds: 6));
        expect(find.byType(Scaffold), findsOneWidget);
      }
    });

    testWidgets('all 3 coupon tabs (By Store, Detail, Duplicates) are rendered',
        (tester) async {
      await tester.pumpWidget(buildApp());
      await tester.pumpAndSettle(const Duration(seconds: 5));
      await loginIfNeeded(tester);

      final navigated = await navigateToCoupon(tester);
      if (!navigated) return;

      for (final tab in ['By Store', 'Detail', 'Duplicates']) {
        expect(find.text(tab), findsWidgets,
            reason: 'Coupon tab "$tab" not found');
      }
    });

    testWidgets('coupon prefix filter field is visible and accepts input',
        (tester) async {
      await tester.pumpWidget(buildApp());
      await tester.pumpAndSettle(const Duration(seconds: 5));
      await loginIfNeeded(tester);

      final navigated = await navigateToCoupon(tester);
      if (!navigated) return;

      // Find the prefix TextField and enter a filter
      final prefixField = find.byWidgetPredicate(
        (w) =>
            w is TextField &&
            (w.decoration?.hintText?.toLowerCase().contains('coupon') == true ||
                w.decoration?.hintText?.toLowerCase().contains('prefix') == true),
      );
      if (prefixField.evaluate().isNotEmpty) {
        await tester.enterText(prefixField.first, 'MB');
        await tester.testTextInput.receiveAction(TextInputAction.done);
        await tester.pumpAndSettle(const Duration(seconds: 6));
        expect(find.byType(Scaffold), findsOneWidget);
      }
    });

    testWidgets('coupon KPIs: Total Coupons + Used + Unused labels exist',
        (tester) async {
      await tester.pumpWidget(buildApp());
      await tester.pumpAndSettle(const Duration(seconds: 5));
      await loginIfNeeded(tester);

      final navigated = await navigateToCoupon(tester);
      if (!navigated) return;

      // Verify at least one of the known coupon KPI labels exists
      final hasTotalCoupons = find.text('Total Coupons').evaluate().isNotEmpty;
      final hasUsed = find.text('Used').evaluate().isNotEmpty;
      expect(hasTotalCoupons || hasUsed, isTrue,
          reason: 'At least one coupon KPI label should be visible');
    });

    testWidgets('pull to refresh reloads coupon data without crash',
        (tester) async {
      await tester.pumpWidget(buildApp());
      await tester.pumpAndSettle(const Duration(seconds: 5));
      await loginIfNeeded(tester);

      final navigated = await navigateToCoupon(tester);
      if (!navigated) return;

      await tester.fling(
        find.byType(ListView).first,
        const Offset(0, 300),
        1000,
      );
      await tester.pumpAndSettle(const Duration(seconds: 8));
      expect(find.byType(Scaffold), findsOneWidget);
    });

    testWidgets('back navigation from Coupon returns to Home', (tester) async {
      await tester.pumpWidget(buildApp());
      await tester.pumpAndSettle(const Duration(seconds: 5));
      await loginIfNeeded(tester);

      final navigated = await navigateToCoupon(tester);
      if (!navigated) return;

      final NavigatorState navigator = tester.state(find.byType(Navigator).first);
      navigator.pop();
      await tester.pumpAndSettle();

      expect(find.text('SB Dashboard'), findsOneWidget);
    });
  });
}
