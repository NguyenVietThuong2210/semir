import 'dart:async';

import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:mockito/annotations.dart';
import 'package:mockito/mockito.dart';

import 'package:semir_phone/core/auth/auth_provider.dart';
import 'package:semir_phone/core/auth/auth_service.dart';
import 'package:semir_phone/core/auth/token_storage.dart';
import 'package:semir_phone/core/theme/app_theme.dart';
import 'package:semir_phone/features/login/login_page.dart';

import 'login_page_test.mocks.dart';

@GenerateMocks([TokenStorage, AuthService])
void main() {
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

  Widget buildSubject() {
    return ProviderScope(
      overrides: [
        tokenStorageProvider.overrideWithValue(mockStorage),
        authServiceProvider.overrideWithValue(mockAuthService),
      ],
      child: MaterialApp(
        theme: buildAppTheme(),
        home: const LoginPage(),
      ),
    );
  }

  testWidgets('renders username and password fields with sign-in button', (tester) async {
    await tester.pumpWidget(buildSubject());
    await tester.pumpAndSettle();

    expect(find.byType(TextFormField), findsNWidgets(2));
    expect(find.text('Sign In'), findsOneWidget);
  });

  testWidgets('valid credentials → calls login on notifier', (tester) async {
    final session = UserSession(
      username: 'admin',
      accessToken: 'access',
      refreshToken: 'refresh',
      accessTokenExpiry: DateTime.now().add(const Duration(hours: 1)),
      permissions: ['sales.view'],
    );
    when(mockAuthService.login('admin', 'pass123'))
        .thenAnswer((_) async => session);
    when(mockStorage.saveTokens(
      access: anyNamed('access'),
      refresh: anyNamed('refresh'),
      expiry: anyNamed('expiry'),
      username: anyNamed('username'),
      permissions: anyNamed('permissions'),
    )).thenAnswer((_) async {});

    await tester.pumpWidget(buildSubject());
    await tester.pumpAndSettle();

    await tester.enterText(
        find.widgetWithText(TextFormField, 'Username'), 'admin');
    await tester.enterText(
        find.widgetWithText(TextFormField, 'Password'), 'pass123');
    await tester.tap(find.text('Sign In'));
    await tester.pump();

    verify(mockAuthService.login('admin', 'pass123')).called(1);
  });

  testWidgets('invalid credentials 401 → shows generic error, no token saved', (tester) async {
    when(mockAuthService.login(any, any)).thenThrow(
      const AuthException('Invalid credentials'),
    );

    await tester.pumpWidget(buildSubject());
    await tester.pumpAndSettle();

    await tester.enterText(
        find.widgetWithText(TextFormField, 'Username'), 'bad');
    await tester.enterText(
        find.widgetWithText(TextFormField, 'Password'), 'wrong');
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

  testWidgets('empty form submission shows validation errors', (tester) async {
    await tester.pumpWidget(buildSubject());
    await tester.pumpAndSettle();

    await tester.tap(find.text('Sign In'));
    await tester.pumpAndSettle();

    expect(find.text('Please enter your username'), findsOneWidget);
    expect(find.text('Please enter your password'), findsOneWidget);
    verifyNever(mockAuthService.login(any, any));
  });

  testWidgets('loading state shows progress inside button', (tester) async {
    // Use a Completer so we control exactly when the login future resolves.
    final loginCompleter = Completer<UserSession>();
    when(mockAuthService.login(any, any))
        .thenAnswer((_) => loginCompleter.future);

    await tester.pumpWidget(buildSubject());
    await tester.pumpAndSettle();

    await tester.enterText(
        find.widgetWithText(TextFormField, 'Username'), 'user');
    await tester.enterText(
        find.widgetWithText(TextFormField, 'Password'), 'pass');
    await tester.tap(find.text('Sign In'));
    await tester.pump(); // one frame — login future still pending

    // Both button and LoadingOverlay show a spinner during loading.
    expect(find.byType(CircularProgressIndicator), findsWidgets);

    // Resolve the completer so there are no pending timers at teardown.
    loginCompleter.completeError(const AuthException('cancelled'));
    await tester.pumpAndSettle();
  });
}
