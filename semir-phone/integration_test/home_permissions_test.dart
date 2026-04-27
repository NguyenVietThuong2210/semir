import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:integration_test/integration_test.dart';
import 'package:mockito/mockito.dart';

import 'package:semir_phone/app.dart';
import 'package:semir_phone/core/auth/auth_provider.dart';
import 'package:semir_phone/features/home/nav_card.dart';

import 'home_permissions_test.mocks.dart';

void main() {
  IntegrationTestWidgetsFlutterBinding.ensureInitialized();

  late MockTokenStorage mockStorage;
  late MockAuthService mockAuthService;

  Widget buildApp(List<String> permissions, String username) {
    when(mockStorage.readAccessToken()).thenAnswer((_) async => 'access');
    when(mockStorage.readRefreshToken()).thenAnswer((_) async => 'refresh');
    when(mockStorage.readAccessTokenExpiry()).thenAnswer(
        (_) async => DateTime.now().toUtc().add(const Duration(hours: 1)));
    when(mockStorage.readPermissions()).thenAnswer((_) async => permissions);
    when(mockStorage.readUsername()).thenAnswer((_) async => username);

    return ProviderScope(
      overrides: [
        tokenStorageProvider.overrideWithValue(mockStorage),
        authServiceProvider.overrideWithValue(mockAuthService),
      ],
      child: const SemirPhoneApp(),
    );
  }

  setUp(() {
    mockStorage = MockTokenStorage();
    mockAuthService = MockAuthService();
  });

  testWidgets('full permission user sees all 5 cards accessible', (tester) async {
    await tester.pumpWidget(buildApp([
      'sales.view',
      'customers.view',
      'coupons.view',
      'shop_detail.view',
      'customer_detail.view',
    ], 'admin'));
    await tester.pumpAndSettle();

    expect(find.byType(NavCard), findsNWidgets(5));
    expect(find.text('No access'), findsNothing);
  });

  testWidgets('sales-only user: Sales card is tappable', (tester) async {
    await tester.pumpWidget(buildApp(['sales.view'], 'salesuser'));
    await tester.pumpAndSettle();

    await tester.tap(find.text('Sales'));
    await tester.pumpAndSettle();

    expect(find.text('Sales Analytics'), findsOneWidget);
  });

  testWidgets('no-permission card tap does not navigate', (tester) async {
    await tester.pumpWidget(buildApp(['sales.view'], 'salesuser'));
    await tester.pumpAndSettle();

    await tester.tap(find.text('Coupon'));
    await tester.pumpAndSettle();

    // Still on home page
    expect(find.text('S&B Dashboard'), findsOneWidget);
    expect(find.text('Hello, salesuser'), findsOneWidget);
  });
}
