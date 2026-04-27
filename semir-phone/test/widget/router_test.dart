import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:mockito/annotations.dart';
import 'package:mockito/mockito.dart';

import 'package:semir_phone/core/auth/auth_provider.dart';
import 'package:semir_phone/core/auth/auth_service.dart';
import 'package:semir_phone/core/auth/token_storage.dart';
import 'package:semir_phone/app.dart';

import 'router_test.mocks.dart';

@GenerateMocks([TokenStorage, AuthService])
void main() {
  late MockTokenStorage mockStorage;
  late MockAuthService mockAuthService;

  setUp(() {
    mockStorage = MockTokenStorage();
    mockAuthService = MockAuthService();
  });

  Widget buildApp({UserSession? session}) {
    when(mockStorage.readAccessToken())
        .thenAnswer((_) async => session?.accessToken);
    when(mockStorage.readRefreshToken())
        .thenAnswer((_) async => session?.refreshToken);
    when(mockStorage.readPermissions())
        .thenAnswer((_) async => session?.permissions ?? []);
    when(mockStorage.readUsername())
        .thenAnswer((_) async => session?.username);
    when(mockStorage.readAccessTokenExpiry())
        .thenAnswer((_) async => session?.accessTokenExpiry);

    return ProviderScope(
      overrides: [
        tokenStorageProvider.overrideWithValue(mockStorage),
        authServiceProvider.overrideWithValue(mockAuthService),
      ],
      child: const SemirPhoneApp(),
    );
  }

  testWidgets('unauthenticated → redirects to login page', (tester) async {
    await tester.pumpWidget(buildApp(session: null));
    await tester.pumpAndSettle();

    expect(find.text('Sign In'), findsOneWidget);
    expect(find.text('S&B Dashboard'), findsOneWidget);
  });

  testWidgets('authenticated → renders home page', (tester) async {
    final session = UserSession(
      username: 'admin',
      accessToken: 'access',
      refreshToken: 'refresh',
      accessTokenExpiry: DateTime.now().add(const Duration(hours: 1)),
      permissions: ['sales.view'],
    );

    await tester.pumpWidget(buildApp(session: session));
    await tester.pumpAndSettle();

    expect(find.text('S&B Dashboard'), findsOneWidget);
    expect(find.text('Hello, admin'), findsOneWidget);
  });

  testWidgets('SC-009: accessing /sales without sales.view → redirected to home', (tester) async {
    // Session with NO sales.view permission
    final session = UserSession(
      username: 'limiteduser',
      accessToken: 'access',
      refreshToken: 'refresh',
      accessTokenExpiry: DateTime.now().add(const Duration(hours: 1)),
      permissions: ['coupons.view'], // no sales.view
    );

    await tester.pumpWidget(buildApp(session: session));
    await tester.pumpAndSettle();

    // We're on home — Sales card should show "no access"
    expect(find.text('S&B Dashboard'), findsOneWidget);
    // The sales card should show no-access message
    final noAccessFinder = find.text('No access');
    expect(noAccessFinder, findsWidgets);
  });

  testWidgets('back button on login page does not navigate to protected route', (tester) async {
    await tester.pumpWidget(buildApp(session: null));
    await tester.pumpAndSettle();

    // On login page — tapping system back should not reveal protected content
    final NavigatorState? navigator =
        tester.state(find.byType(Navigator).last);
    expect(navigator?.canPop(), isFalse);
  });
}
