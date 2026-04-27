import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:integration_test/integration_test.dart';
import 'package:mockito/mockito.dart';

import 'package:semir_phone/app.dart';
import 'package:semir_phone/core/auth/auth_provider.dart';
import 'package:semir_phone/core/auth/auth_service.dart';

import 'login_flow_test.mocks.dart';

void main() {
  IntegrationTestWidgetsFlutterBinding.ensureInitialized();

  late MockTokenStorage mockStorage;
  late MockAuthService mockAuthService;

  setUp(() {
    mockStorage = MockTokenStorage();
    mockAuthService = MockAuthService();
    when(mockStorage.readAccessToken()).thenAnswer((_) async => null);
    when(mockStorage.readRefreshToken()).thenAnswer((_) async => null);
    when(mockStorage.readAccessTokenExpiry()).thenAnswer((_) async => null);
    when(mockStorage.readPermissions()).thenAnswer((_) async => []);
    when(mockStorage.readUsername()).thenAnswer((_) async => null);
  });

  Widget buildApp() {
    return ProviderScope(
      overrides: [
        tokenStorageProvider.overrideWithValue(mockStorage),
        authServiceProvider.overrideWithValue(mockAuthService),
      ],
      child: const SemirPhoneApp(),
    );
  }

  testWidgets('E2E: sign in → home renders', (tester) async {
    final session = UserSession(
      username: 'manager',
      accessToken: 'access_e2e',
      refreshToken: 'refresh_e2e',
      accessTokenExpiry: DateTime.now().toUtc().add(const Duration(hours: 1)),
      permissions: ['sales.view', 'shop_detail.view'],
    );
    when(mockAuthService.login('manager', 'secure123'))
        .thenAnswer((_) async => session);

    await tester.pumpWidget(buildApp());
    await tester.pumpAndSettle();

    // Login page
    expect(find.text('S&B Dashboard'), findsOneWidget);

    await tester.enterText(
        find.widgetWithText(TextFormField, 'Username'), 'manager');
    await tester.enterText(
        find.widgetWithText(TextFormField, 'Password'), 'secure123');
    await tester.tap(find.text('Sign In'));
    await tester.pumpAndSettle();

    // Home page
    expect(find.text('S&B Dashboard'), findsOneWidget);
    expect(find.text('Hello, manager'), findsOneWidget);
  });

  testWidgets('E2E: session restored on re-launch → still on home', (tester) async {
    when(mockStorage.readAccessToken()).thenAnswer((_) async => 'stored_access');
    when(mockStorage.readRefreshToken()).thenAnswer((_) async => 'stored_refresh');
    when(mockStorage.readAccessTokenExpiry()).thenAnswer(
        (_) async => DateTime.now().toUtc().add(const Duration(hours: 1)));
    when(mockStorage.readPermissions()).thenAnswer((_) async => ['sales.view']);
    when(mockStorage.readUsername()).thenAnswer((_) async => 'manager');

    await tester.pumpWidget(buildApp());
    await tester.pumpAndSettle();

    expect(find.text('S&B Dashboard'), findsOneWidget);
    expect(find.text('Hello, manager'), findsOneWidget);
  });

  testWidgets('E2E: sign out → login screen shown', (tester) async {
    when(mockStorage.readAccessToken()).thenAnswer((_) async => 'stored_access');
    when(mockStorage.readRefreshToken()).thenAnswer((_) async => 'stored_refresh');
    when(mockStorage.readAccessTokenExpiry()).thenAnswer(
        (_) async => DateTime.now().toUtc().add(const Duration(hours: 1)));
    when(mockStorage.readPermissions()).thenAnswer((_) async => ['sales.view']);
    when(mockStorage.readUsername()).thenAnswer((_) async => 'manager');
    when(mockAuthService.logout(any)).thenAnswer((_) async {});
    when(mockStorage.deleteAll()).thenAnswer((_) async {});

    await tester.pumpWidget(buildApp());
    await tester.pumpAndSettle();

    await tester.tap(find.byIcon(Icons.logout));
    await tester.pumpAndSettle();

    // Back on login page
    expect(find.text('S&B Dashboard'), findsOneWidget);
    expect(find.text('Sign In'), findsOneWidget);
  });

  testWidgets('E2E: wrong password → error banner, no token stored', (tester) async {
    when(mockAuthService.login('user', 'wrongpass'))
        .thenThrow(const AuthException('invalid credentials'));

    await tester.pumpWidget(buildApp());
    await tester.pumpAndSettle();

    await tester.enterText(
        find.widgetWithText(TextFormField, 'Username'), 'user');
    await tester.enterText(
        find.widgetWithText(TextFormField, 'Password'), 'wrongpass');
    await tester.tap(find.text('Sign In'));
    await tester.pumpAndSettle();

    expect(
      find.text('Incorrect username or password.'),
      findsOneWidget,
    );
    verifyNever(mockStorage.saveTokens(
      access: anyNamed('access'),
      refresh: anyNamed('refresh'),
      expiry: anyNamed('expiry'),
      username: anyNamed('username'),
      permissions: anyNamed('permissions'),
    ));
  });
}
