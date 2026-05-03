import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:mockito/annotations.dart';
import 'package:mockito/mockito.dart';

import 'package:semir_phone/core/auth/auth_provider.dart';
import 'package:semir_phone/core/auth/auth_service.dart';
import 'package:semir_phone/core/auth/token_storage.dart';
import 'package:semir_phone/core/theme/app_theme.dart';
import 'package:semir_phone/features/home/home_page.dart';
import 'package:semir_phone/features/home/nav_card.dart';

import 'home_page_test.mocks.dart';

@GenerateMocks([TokenStorage, AuthService])
void main() {
  late MockTokenStorage mockStorage;
  late MockAuthService mockAuthService;

  setUp(() {
    mockStorage = MockTokenStorage();
    mockAuthService = MockAuthService();
    when(mockStorage.readAccessTokenExpiry()).thenAnswer((_) async => null);
  });

  Widget buildSubject(List<String> permissions, {double screenWidth = 390}) {
    when(mockStorage.readAccessToken()).thenAnswer((_) async => 'access');
    when(mockStorage.readRefreshToken()).thenAnswer((_) async => 'refresh');
    when(mockStorage.readPermissions()).thenAnswer((_) async => permissions);
    when(mockStorage.readUsername()).thenAnswer((_) async => 'testuser');

    return ProviderScope(
      overrides: [
        tokenStorageProvider.overrideWithValue(mockStorage),
        authServiceProvider.overrideWithValue(mockAuthService),
      ],
      child: MaterialApp(
        theme: buildAppTheme(),
        home: MediaQuery(
          data: MediaQueryData(size: Size(screenWidth, 800)),
          child: const HomePage(),
        ),
      ),
    );
  }

  testWidgets('full permissions → all 8 cards rendered', (tester) async {
    await tester.pumpWidget(buildSubject([
      'sales.view',
      'customers.view',
      'coupons.view',
      'shop_detail.view',
      'customer_detail.view',
    ]));
    await tester.pumpAndSettle();

    // 5 primary cards + 3 chart cards (Sales Charts, Customer Charts, Coupon Charts)
    expect(find.byType(NavCard), findsNWidgets(8));
  });

  testWidgets('sales.view only → 2 accessible cards, others show no-access', (tester) async {
    await tester.pumpWidget(buildSubject(['sales.view']));
    await tester.pumpAndSettle();

    // All 8 cards rendered — Sales + Sales Charts accessible, 6 no-access
    expect(find.byType(NavCard), findsNWidgets(8));
    expect(find.text('No access'), findsNWidgets(6));
  });

  testWidgets('coupons.view absent → Coupon + Coupon Charts cards show no-access', (tester) async {
    await tester.pumpWidget(buildSubject([
      'sales.view',
      'customers.view',
      'shop_detail.view',
      'customer_detail.view',
    ]));
    await tester.pumpAndSettle();

    // Coupon and Coupon Charts both show no-access (2 no-access cards)
    expect(find.text('Coupon'), findsOneWidget);
    expect(find.text('No access'), findsNWidgets(2));
  });

  testWidgets('375pt width → single column (no Row widgets for grid)', (tester) async {
    await tester.pumpWidget(buildSubject(['sales.view'], screenWidth: 375));
    await tester.pumpAndSettle();

    // At 375pt, no 2-col Row should exist (only AppBar rows etc)
    // All NavCards are in a Column, not side-by-side
    final navCards = tester.widgetList<NavCard>(find.byType(NavCard)).toList();
    expect(navCards.length, 8);
  });

  testWidgets('768pt width → uses 2-column grid (Row widgets present)', (tester) async {
    await tester.pumpWidget(buildSubject([
      'sales.view',
      'customers.view',
      'coupons.view',
    ], screenWidth: 768));
    await tester.pumpAndSettle();

    // At 768pt, _CardGrid renders Row widgets for all 8 cards
    expect(find.byType(NavCard), findsNWidgets(8));
  });

  testWidgets('username shown in greeting', (tester) async {
    await tester.pumpWidget(buildSubject(['sales.view']));
    await tester.pumpAndSettle();

    expect(find.text('Hello, testuser'), findsOneWidget);
  });
}
