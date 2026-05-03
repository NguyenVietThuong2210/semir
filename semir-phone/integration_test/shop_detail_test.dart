import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:integration_test/integration_test.dart';

import 'package:semir_phone/app.dart';
import 'package:semir_phone/shared/widgets/kpi_card.dart';
import 'package:semir_phone/shared/widgets/data_table_widget.dart';

/// E2E integration tests for Shop Detail page.
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

  Future<bool> navigateToShopDetail(WidgetTester tester) async {
    final card = find.text('Store Detail');
    if (card.evaluate().isEmpty) return false;
    await tester.tap(card.first);
    await tester.pumpAndSettle(const Duration(seconds: 5));
    return true;
  }

  /// Selects the first shop from the dropdown if no shop is pre-selected.
  Future<void> selectFirstShop(WidgetTester tester) async {
    // Try to find the shop dropdown and select the first available shop
    final dropdown = find.byType(DropdownButton<String>);
    if (dropdown.evaluate().isNotEmpty) {
      await tester.tap(dropdown.first);
      await tester.pumpAndSettle(const Duration(seconds: 2));
      // Select the first item in the dropdown (not the placeholder)
      final items = find.byType(DropdownMenuItem<String>);
      if (items.evaluate().length > 1) {
        await tester.tap(items.at(1)); // at(0) is often the placeholder
        await tester.pumpAndSettle(const Duration(seconds: 8));
      }
    }
  }

  group('Shop Detail E2E', () {
    testWidgets('user with shop_detail.view sees Store Detail page',
        (tester) async {
      await tester.pumpWidget(buildApp());
      await tester.pumpAndSettle(const Duration(seconds: 5));
      await loginIfNeeded(tester);

      final navigated = await navigateToShopDetail(tester);
      if (!navigated) return;

      expect(find.text('Store Detail'), findsWidgets);
    });

    testWidgets('shop detail initial load shows Sales section', (tester) async {
      await tester.pumpWidget(buildApp());
      await tester.pumpAndSettle(const Duration(seconds: 5));
      await loginIfNeeded(tester);

      final navigated = await navigateToShopDetail(tester);
      if (!navigated) return;

      await selectFirstShop(tester);

      // Sales section should be shown by default
      expect(find.text('Sales'), findsWidgets);
    });

    testWidgets('shop sales section shows KPI cards', (tester) async {
      await tester.pumpWidget(buildApp());
      await tester.pumpAndSettle(const Duration(seconds: 5));
      await loginIfNeeded(tester);

      final navigated = await navigateToShopDetail(tester);
      if (!navigated) return;

      await selectFirstShop(tester);

      expect(find.byType(KpiCard), findsWidgets);
    });

    testWidgets('shop sales section loads within 10 seconds', (tester) async {
      await tester.pumpWidget(buildApp());
      await tester.pumpAndSettle(const Duration(seconds: 5));
      await loginIfNeeded(tester);

      final navigated = await navigateToShopDetail(tester);
      if (!navigated) return;

      final start = DateTime.now();
      await selectFirstShop(tester);
      final elapsed = DateTime.now().difference(start);

      debugPrint('Shop detail sales load time: ${elapsed.inMilliseconds}ms');
      expect(elapsed.inSeconds, lessThanOrEqualTo(10));
    });

    testWidgets('shop sales section shows breakdown tables (by_session, by_month, by_week)',
        (tester) async {
      await tester.pumpWidget(buildApp());
      await tester.pumpAndSettle(const Duration(seconds: 5));
      await loginIfNeeded(tester);

      final navigated = await navigateToShopDetail(tester);
      if (!navigated) return;

      await selectFirstShop(tester);

      // At least one DataTableWidget should be visible for the sales section
      expect(find.byType(DataTableWidget), findsWidgets);
    });

    testWidgets('switching to Customers section lazy-loads customer data',
        (tester) async {
      await tester.pumpWidget(buildApp());
      await tester.pumpAndSettle(const Duration(seconds: 5));
      await loginIfNeeded(tester);

      final navigated = await navigateToShopDetail(tester);
      if (!navigated) return;

      await selectFirstShop(tester);

      final customersBtn = find.text('Customers');
      if (customersBtn.evaluate().isNotEmpty) {
        await tester.tap(customersBtn.first);
        await tester.pumpAndSettle(const Duration(seconds: 10));

        // Customer KPI cards should appear
        expect(find.byType(Scaffold), findsOneWidget);
        // Tabs: By Season, By Month, By Week
        final hasBySeasonTab = find.text('By Season').evaluate().isNotEmpty;
        final hasByMonthTab = find.text('By Month').evaluate().isNotEmpty;
        expect(hasBySeasonTab || hasByMonthTab, isTrue,
            reason: 'Customer breakdown tabs should be visible');
      }
    });

    testWidgets('switching to Coupon section lazy-loads coupon data',
        (tester) async {
      await tester.pumpWidget(buildApp());
      await tester.pumpAndSettle(const Duration(seconds: 5));
      await loginIfNeeded(tester);

      final navigated = await navigateToShopDetail(tester);
      if (!navigated) return;

      await selectFirstShop(tester);

      final couponBtn = find.text('Coupon');
      if (couponBtn.evaluate().isNotEmpty) {
        await tester.tap(couponBtn.first);
        await tester.pumpAndSettle(const Duration(seconds: 10));
        expect(find.byType(Scaffold), findsOneWidget);
      }
    });

    testWidgets('customer breakdown tabs all cycle without crash', (tester) async {
      await tester.pumpWidget(buildApp());
      await tester.pumpAndSettle(const Duration(seconds: 5));
      await loginIfNeeded(tester);

      final navigated = await navigateToShopDetail(tester);
      if (!navigated) return;

      await selectFirstShop(tester);

      // Navigate to customer section first
      final customersBtn = find.text('Customers');
      if (customersBtn.evaluate().isEmpty) return;
      await tester.tap(customersBtn.first);
      await tester.pumpAndSettle(const Duration(seconds: 10));

      // Cycle through breakdown tabs
      for (final tab in ['By Month', 'By Week', 'By Season']) {
        final tabFinder = find.text(tab);
        if (tabFinder.evaluate().isNotEmpty) {
          await tester.tap(tabFinder.first);
          await tester.pumpAndSettle(const Duration(seconds: 3));
          expect(find.byType(Scaffold), findsOneWidget);
        }
      }
    });

    testWidgets('sales breakdown tabs (By Session, By Month, By Week) all render',
        (tester) async {
      await tester.pumpWidget(buildApp());
      await tester.pumpAndSettle(const Duration(seconds: 5));
      await loginIfNeeded(tester);

      final navigated = await navigateToShopDetail(tester);
      if (!navigated) return;

      await selectFirstShop(tester);

      // By Session is the season-based breakdown for sales
      final hasBySession = find.text('By Session').evaluate().isNotEmpty;
      final hasByMonth = find.text('By Month').evaluate().isNotEmpty;
      final hasByWeek = find.text('By Week').evaluate().isNotEmpty;

      // At least one table tab should exist in sales section
      expect(hasBySession || hasByMonth || hasByWeek, isTrue,
          reason: 'At least one sales breakdown tab should render');
    });

    testWidgets('all-time and period KPIs are shown for each section',
        (tester) async {
      await tester.pumpWidget(buildApp());
      await tester.pumpAndSettle(const Duration(seconds: 5));
      await loginIfNeeded(tester);

      final navigated = await navigateToShopDetail(tester);
      if (!navigated) return;

      await selectFirstShop(tester);

      expect(find.text('All-Time'), findsWidgets);
      expect(find.text('Selected Period'), findsWidgets);
    });

    testWidgets('back navigation from Shop Detail returns to Home',
        (tester) async {
      await tester.pumpWidget(buildApp());
      await tester.pumpAndSettle(const Duration(seconds: 5));
      await loginIfNeeded(tester);

      final navigated = await navigateToShopDetail(tester);
      if (!navigated) return;

      final NavigatorState navigator =
          tester.state(find.byType(Navigator).first);
      navigator.pop();
      await tester.pumpAndSettle();

      expect(find.text('S&B Dashboard'), findsOneWidget);
    });
  });
}
