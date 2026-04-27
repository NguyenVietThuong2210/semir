import 'package:dio/dio.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../config/app_config.dart';

/// Bare Dio with no auth interceptor.
/// Used by AuthService (refresh calls) and AuthInterceptor (retry calls)
/// to break the circular dependency: dioProvider → authServiceProvider → dioProvider.
final bareDioProvider = Provider<Dio>((ref) {
  return Dio(
    BaseOptions(
      baseUrl: BuildConfig.apiBaseUrl,
      connectTimeout: const Duration(seconds: 10),
      receiveTimeout: const Duration(seconds: 30),
      headers: {'Content-Type': 'application/json'},
    ),
  );
});
