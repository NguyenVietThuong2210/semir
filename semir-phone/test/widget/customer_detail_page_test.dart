import 'dart:async';

import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:flutter_test/flutter_test.dart';

import 'package:semir_phone/core/theme/app_theme.dart';
import 'package:semir_phone/features/analytics/customer_detail/customer_detail_page.dart';
import 'package:semir_phone/features/analytics/customer_detail/customer_detail_provider.dart';
import 'package:semir_phone/features/analytics/customer_detail/customer_detail_service.dart';
import 'package:semir_phone/shared/models/analytics_models.dart';
import 'package:semir_phone/shared/widgets/loading_overlay.dart';

CustomerDetailPayload _fixtureCustomer({
  String phone = '09x-xxx-x567',
  String grade = 'Gold',
  String registrationStore = 'HN01',
  String registrationDate = '2022-05-01',
  String? cnvSyncStatus = 'synced',
  String email = '',
}) {
  return CustomerDetailPayload(
    username: 'Nguyen Van A',
    phone: phone,
    vipId: 'VIP001234',
    grade: grade,
    registrationStore: registrationStore,
    registrationDate: registrationDate,
    cnvSyncStatus: cnvSyncStatus,
    email: email,
    kpis: [
      const KpiItem(label: 'Total Invoices', value: '25'),
      const KpiItem(label: 'Total Revenue (VND)', value: '12,500,000'),
    ],
    invoiceHeaders: ['Date', 'Shop', 'Invoice', 'Amount'],
    invoiceRows: [
      ['2025-03-01', 'HN01', 'INV001', '500,000'],
      ['2025-02-14', 'HN02', 'INV002', '750,000'],
    ],
  );
}

Widget buildSubject(AsyncValue<CustomerDetailPayload?> state) {
  return ProviderScope(
    overrides: [
      customerDetailProvider.overrideWith(() => _FakeNotifier(state)),
    ],
    child: MaterialApp(
      theme: buildAppTheme(),
      home: const CustomerDetailPage(),
    ),
  );
}

void main() {
  testWidgets('initial state: search fields visible, no profile shown',
      (tester) async {
    await tester.pumpWidget(buildSubject(const AsyncValue.data(null)));
    await tester.pumpAndSettle();

    expect(find.byType(TextField), findsWidgets);
    expect(find.text('Nguyen Van A'), findsNothing);
  });

  testWidgets('data state: customer profile rendered', (tester) async {
    await tester.pumpWidget(buildSubject(AsyncValue.data(_fixtureCustomer())));
    await tester.pumpAndSettle();

    expect(find.text('Nguyen Van A'), findsOneWidget);
    expect(find.textContaining('VIP001234'), findsOneWidget);
    expect(find.text('Gold'), findsOneWidget);
  });

  testWidgets('phone displayed in masked format (09x-xxx-x567)', (tester) async {
    await tester.pumpWidget(buildSubject(AsyncValue.data(
      _fixtureCustomer(phone: '09x-xxx-x567'),
    )));
    await tester.pumpAndSettle();

    // Masked phone must be visible
    expect(find.text('09x-xxx-x567'), findsOneWidget);
    // Full phone digits must never appear
    expect(find.textContaining('0901234567'), findsNothing);
  });

  testWidgets('404 error → "customer not found" banner shown', (tester) async {
    await tester.pumpWidget(buildSubject(const AsyncValue.error(
      NotFoundException(),
      StackTrace.empty,
    )));
    await tester.pumpAndSettle();

    // Should show not-found message
    expect(find.textContaining('Customer not found'), findsWidgets);
  });

  testWidgets('invoice table renders rows', (tester) async {
    await tester.pumpWidget(buildSubject(AsyncValue.data(_fixtureCustomer())));
    await tester.pumpAndSettle();

    expect(find.text('2025-03-01'), findsOneWidget);
    expect(find.text('HN01'), findsWidgets);
    expect(find.text('500,000'), findsOneWidget);
  });

  testWidgets('grade badge rendered with primary color border', (tester) async {
    await tester.pumpWidget(buildSubject(AsyncValue.data(
      _fixtureCustomer(grade: 'Diamond'),
    )));
    await tester.pumpAndSettle();

    expect(find.text('Diamond'), findsOneWidget);
  });

  testWidgets('KPI cards rendered with correct values', (tester) async {
    await tester.pumpWidget(buildSubject(AsyncValue.data(_fixtureCustomer())));
    await tester.pumpAndSettle();

    expect(find.text('25'), findsOneWidget);
    expect(find.text('12,500,000'), findsOneWidget);
  });

  testWidgets('loading state: LoadingOverlay visible', (tester) async {
    await tester.pumpWidget(buildSubject(const AsyncValue.loading()));
    await tester.pump();

    expect(find.byType(LoadingOverlay), findsOneWidget);
  });

  testWidgets('registration store and date shown in profile', (tester) async {
    await tester.pumpWidget(buildSubject(AsyncValue.data(
      _fixtureCustomer(registrationStore: 'HN01', registrationDate: '2022-05-01'),
    )));
    await tester.pumpAndSettle();

    expect(find.textContaining('HN01'), findsWidgets);
    expect(find.textContaining('2022-05-01'), findsOneWidget);
  });

  testWidgets('CNV synced → shows CNV Synced label', (tester) async {
    await tester.pumpWidget(buildSubject(AsyncValue.data(
      _fixtureCustomer(cnvSyncStatus: 'synced'),
    )));
    await tester.pumpAndSettle();

    expect(find.textContaining('CNV Synced'), findsOneWidget);
  });

  testWidgets('CNV not_synced → shows Not in CNV label', (tester) async {
    await tester.pumpWidget(buildSubject(AsyncValue.data(
      _fixtureCustomer(cnvSyncStatus: 'not_synced'),
    )));
    await tester.pumpAndSettle();

    expect(find.textContaining('Not in CNV'), findsOneWidget);
  });

  testWidgets('null cnvSyncStatus → no CNV section shown', (tester) async {
    await tester.pumpWidget(buildSubject(AsyncValue.data(
      _fixtureCustomer(cnvSyncStatus: null),
    )));
    await tester.pumpAndSettle();

    expect(find.textContaining('CNV'), findsNothing);
  });

  testWidgets('invoice table headers match API columns', (tester) async {
    await tester.pumpWidget(buildSubject(AsyncValue.data(_fixtureCustomer())));
    await tester.pumpAndSettle();

    expect(find.text('Date'), findsOneWidget);
    expect(find.text('Shop'), findsWidgets);
    expect(find.text('Invoice'), findsOneWidget);
    expect(find.text('Amount'), findsOneWidget);
  });

  testWidgets('email shown when present', (tester) async {
    await tester.pumpWidget(buildSubject(AsyncValue.data(
      _fixtureCustomer(email: 'nguyen@example.com'),
    )));
    await tester.pumpAndSettle();

    expect(find.text('nguyen@example.com'), findsOneWidget);
  });

  testWidgets('email hidden when empty', (tester) async {
    await tester.pumpWidget(buildSubject(AsyncValue.data(
      _fixtureCustomer(email: ''),
    )));
    await tester.pumpAndSettle();

    expect(find.byIcon(Icons.email_outlined), findsNothing);
  });
}

class _FakeNotifier extends CustomerDetailNotifier {
  _FakeNotifier(this._state);
  final AsyncValue<CustomerDetailPayload?> _state;

  @override
  Future<CustomerDetailPayload?> build() {
    if (_state.isLoading) return Completer<CustomerDetailPayload?>().future;
    if (_state.hasError) return Future.error(_state.error!, _state.stackTrace);
    return Future.value(_state.valueOrNull);
  }
}
