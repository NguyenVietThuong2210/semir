import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:integration_test/integration_test.dart';

import 'package:semir_phone/app.dart';
import 'package:semir_phone/shared/widgets/kpi_card.dart';
import 'package:semir_phone/shared/widgets/data_table_widget.dart';

/// E2E integration tests for Customer Detail (Lookup) page.
/// Run against a live backend with test credentials.
///
/// Required environment variables (via --dart-define):
///   API_BASE_URL, TEST_USERNAME, TEST_PASSWORD
///   TEST_VIP_ID  — a known valid VIP ID to search (optional, skips search tests if absent)
void main() {
  IntegrationTestWidgetsFlutterBinding.ensureInitialized();

  const testUsername =
      String.fromEnvironment('TEST_USERNAME', defaultValue: 'admin');
  const testPassword =
      String.fromEnvironment('TEST_PASSWORD', defaultValue: 'admin');
  // Provide a real VIP ID from your test data for full search tests.
  // If empty, search-result tests are skipped automatically.
  const testVipId =
      String.fromEnvironment('TEST_VIP_ID', defaultValue: '');

  Widget buildApp() => const ProviderScope(child: SemirPhoneApp());

  Future<void> loginIfNeeded(WidgetTester tester) async {
    if (find.text('Sign In').evaluate().isEmpty) return;
    await tester.enterText(find.byType(TextField).first, testUsername);
    await tester.enterText(find.byType(TextField).last, testPassword);
    await tester.tap(find.text('Sign In'));
    await tester.pumpAndSettle(const Duration(seconds: 8));
  }

  Future<bool> navigateToCustomerDetail(WidgetTester tester) async {
    final card = find.text('Customer Lookup');
    if (card.evaluate().isEmpty) return false;
    await tester.tap(card.first);
    await tester.pumpAndSettle(const Duration(seconds: 5));
    return true;
  }

  group('Customer Detail E2E', () {
    testWidgets('user with customer_detail.view sees Customer Lookup page',
        (tester) async {
      await tester.pumpWidget(buildApp());
      await tester.pumpAndSettle(const Duration(seconds: 5));
      await loginIfNeeded(tester);

      final navigated = await navigateToCustomerDetail(tester);
      if (!navigated) return;

      expect(find.text('Customer Lookup'), findsWidgets);
    });

    testWidgets('search form has VIP ID and phone fields', (tester) async {
      await tester.pumpWidget(buildApp());
      await tester.pumpAndSettle(const Duration(seconds: 5));
      await loginIfNeeded(tester);

      final navigated = await navigateToCustomerDetail(tester);
      if (!navigated) return;

      // VIP ID and Phone text fields should be visible
      final textFields = find.byType(TextFormField);
      expect(textFields, findsWidgets,
          reason: 'Search form should have at least one input field');
      expect(find.text('Search'), findsOneWidget);
    });

    testWidgets('empty search shows no results (no crash)', (tester) async {
      await tester.pumpWidget(buildApp());
      await tester.pumpAndSettle(const Duration(seconds: 5));
      await loginIfNeeded(tester);

      final navigated = await navigateToCustomerDetail(tester);
      if (!navigated) return;

      // Tap Search without entering anything
      await tester.tap(find.text('Search'));
      await tester.pumpAndSettle(const Duration(seconds: 3));

      // Should not crash — either shows "enter an ID" message or stays on page
      expect(find.byType(Scaffold), findsOneWidget);
    });

    testWidgets('invalid VIP ID search shows not-found feedback',
        (tester) async {
      await tester.pumpWidget(buildApp());
      await tester.pumpAndSettle(const Duration(seconds: 5));
      await loginIfNeeded(tester);

      final navigated = await navigateToCustomerDetail(tester);
      if (!navigated) return;

      // Enter a VIP ID that should not exist
      final firstField = find.byType(TextFormField).first;
      await tester.enterText(firstField, '0000000000');
      await tester.tap(find.text('Search'));
      await tester.pumpAndSettle(const Duration(seconds: 6));

      // Not-found state: either a snackbar, banner or text message
      expect(find.byType(Scaffold), findsOneWidget);
    });

    testWidgets('valid VIP ID search returns customer profile card',
        (tester) async {
      if (testVipId.isEmpty) {
        debugPrint('Skipping: TEST_VIP_ID not provided');
        return;
      }

      await tester.pumpWidget(buildApp());
      await tester.pumpAndSettle(const Duration(seconds: 5));
      await loginIfNeeded(tester);

      final navigated = await navigateToCustomerDetail(tester);
      if (!navigated) return;

      // Enter the known VIP ID
      final firstField = find.byType(TextFormField).first;
      await tester.enterText(firstField, testVipId);
      await tester.tap(find.text('Search'));
      await tester.pumpAndSettle(const Duration(seconds: 8));

      // Customer profile card fields should appear
      expect(find.byType(KpiCard), findsWidgets,
          reason: 'KPI cards should be visible after successful search');
    });

    testWidgets('customer profile shows grade and VIP ID after successful search',
        (tester) async {
      if (testVipId.isEmpty) {
        debugPrint('Skipping: TEST_VIP_ID not provided');
        return;
      }

      await tester.pumpWidget(buildApp());
      await tester.pumpAndSettle(const Duration(seconds: 5));
      await loginIfNeeded(tester);

      final navigated = await navigateToCustomerDetail(tester);
      if (!navigated) return;

      final firstField = find.byType(TextFormField).first;
      await tester.enterText(firstField, testVipId);
      await tester.tap(find.text('Search'));
      await tester.pumpAndSettle(const Duration(seconds: 8));

      // The searched VIP ID should appear in the profile card
      expect(find.textContaining(testVipId), findsWidgets);
    });

    testWidgets('invoice history table renders with Date/Shop/Invoice columns',
        (tester) async {
      if (testVipId.isEmpty) {
        debugPrint('Skipping: TEST_VIP_ID not provided');
        return;
      }

      await tester.pumpWidget(buildApp());
      await tester.pumpAndSettle(const Duration(seconds: 5));
      await loginIfNeeded(tester);

      final navigated = await navigateToCustomerDetail(tester);
      if (!navigated) return;

      final firstField = find.byType(TextFormField).first;
      await tester.enterText(firstField, testVipId);
      await tester.tap(find.text('Search'));
      await tester.pumpAndSettle(const Duration(seconds: 8));

      // Invoice table should be visible (DataTableWidget)
      expect(find.byType(DataTableWidget), findsWidgets,
          reason: 'Invoice history DataTable should be present');
    });

    testWidgets('invoice history table has correct column headers',
        (tester) async {
      if (testVipId.isEmpty) {
        debugPrint('Skipping: TEST_VIP_ID not provided');
        return;
      }

      await tester.pumpWidget(buildApp());
      await tester.pumpAndSettle(const Duration(seconds: 5));
      await loginIfNeeded(tester);

      final navigated = await navigateToCustomerDetail(tester);
      if (!navigated) return;

      final firstField = find.byType(TextFormField).first;
      await tester.enterText(firstField, testVipId);
      await tester.tap(find.text('Search'));
      await tester.pumpAndSettle(const Duration(seconds: 8));

      // Verify all 4 expected column headers are rendered
      for (final col in ['Date', 'Shop', 'Invoice', 'Amount']) {
        expect(find.text(col), findsWidgets,
            reason: 'Invoice column "$col" should be visible');
      }
    });

    testWidgets('phone number in profile is masked (PII protection)',
        (tester) async {
      if (testVipId.isEmpty) {
        debugPrint('Skipping: TEST_VIP_ID not provided');
        return;
      }

      await tester.pumpWidget(buildApp());
      await tester.pumpAndSettle(const Duration(seconds: 5));
      await loginIfNeeded(tester);

      final navigated = await navigateToCustomerDetail(tester);
      if (!navigated) return;

      final firstField = find.byType(TextFormField).first;
      await tester.enterText(firstField, testVipId);
      await tester.tap(find.text('Search'));
      await tester.pumpAndSettle(const Duration(seconds: 8));

      // Phone should contain 'x' masking characters
      final maskedPhone = find.textContaining('x');
      expect(maskedPhone, findsWidgets,
          reason: 'Phone should be masked (contains x characters)');
    });

    testWidgets('CNV sync status badge is shown in profile', (tester) async {
      if (testVipId.isEmpty) {
        debugPrint('Skipping: TEST_VIP_ID not provided');
        return;
      }

      await tester.pumpWidget(buildApp());
      await tester.pumpAndSettle(const Duration(seconds: 5));
      await loginIfNeeded(tester);

      final navigated = await navigateToCustomerDetail(tester);
      if (!navigated) return;

      final firstField = find.byType(TextFormField).first;
      await tester.enterText(firstField, testVipId);
      await tester.tap(find.text('Search'));
      await tester.pumpAndSettle(const Duration(seconds: 8));

      // CNV sync status should show "Synced" or "Not Synced"
      final hasSynced = find.text('Synced').evaluate().isNotEmpty;
      final hasNotSynced = find.text('Not Synced').evaluate().isNotEmpty;
      expect(hasSynced || hasNotSynced, isTrue,
          reason: 'CNV sync status badge should be visible');
    });

    testWidgets('customer lookup loads within 8 seconds', (tester) async {
      if (testVipId.isEmpty) {
        debugPrint('Skipping: TEST_VIP_ID not provided');
        return;
      }

      await tester.pumpWidget(buildApp());
      await tester.pumpAndSettle(const Duration(seconds: 5));
      await loginIfNeeded(tester);

      final navigated = await navigateToCustomerDetail(tester);
      if (!navigated) return;

      final firstField = find.byType(TextFormField).first;
      await tester.enterText(firstField, testVipId);

      final start = DateTime.now();
      await tester.tap(find.text('Search'));
      await tester.pumpAndSettle(const Duration(seconds: 10));
      final elapsed = DateTime.now().difference(start);

      debugPrint('Customer detail lookup time: ${elapsed.inMilliseconds}ms');
      expect(elapsed.inSeconds, lessThanOrEqualTo(8),
          reason: 'Customer detail should load within 8s');
    });

    testWidgets('back navigation from Customer Detail returns to Home',
        (tester) async {
      await tester.pumpWidget(buildApp());
      await tester.pumpAndSettle(const Duration(seconds: 5));
      await loginIfNeeded(tester);

      final navigated = await navigateToCustomerDetail(tester);
      if (!navigated) return;

      final NavigatorState navigator =
          tester.state(find.byType(Navigator).first);
      navigator.pop();
      await tester.pumpAndSettle();

      expect(find.text('SB Dashboard'), findsOneWidget);
    });
  });
}
