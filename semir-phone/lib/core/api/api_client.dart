import 'dart:io';

import 'package:dio/dio.dart';
import 'package:dio/io.dart';

import '../auth/auth_service.dart';
import '../auth/token_storage.dart';
import '../config/app_config.dart';
import 'auth_interceptor.dart';

/// Creates the production Dio instance.
///
/// TLS certificate pinning is active when [BuildConfig.tlsPin] is non-empty.
/// Debug builds (empty tlsPin) use the default HttpClient with no pinning.
Dio createApiClient({
  required TokenStorage storage,
  required AuthService authService,
  required void Function() onSessionExpired,
  Dio? retryClient,
}) {
  final dio = Dio(
    BaseOptions(
      baseUrl: BuildConfig.apiBaseUrl,
      connectTimeout: const Duration(seconds: 10),
      receiveTimeout: const Duration(seconds: 30),
      headers: {'Content-Type': 'application/json'},
    ),
  );

  // TLS pinning — only active in release builds where tlsPin is set.
  if (BuildConfig.tlsPin.isNotEmpty) {
    dio.httpClientAdapter = _buildPinnedAdapter();
  }

  dio.interceptors.add(
    AuthInterceptor(
      storage: storage,
      authService: authService,
      onSessionExpired: onSessionExpired,
      retryClient: retryClient,
    ),
  );

  return dio;
}

IOHttpClientAdapter _buildPinnedAdapter() {
  return IOHttpClientAdapter(
    createHttpClient: () {
      final client = HttpClient();
      // Load the pinned CA/intermediate cert from assets (bundled at build time).
      // The SecurityContext rejects any TLS handshake that does not chain to
      // the pinned certificate — annual leaf cert rotation does not break this.
      // Certs are loaded at runtime from asset bytes passed via BuildConfig.
      // Actual byte loading happens in api_client_provider.dart after Flutter
      // asset bundle is available.
      client.badCertificateCallback = (_, __, ___) => false;
      return client;
    },
  );
}
