import 'package:dio/dio.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../auth/auth_provider.dart';
import 'api_client.dart';
import 'bare_dio_provider.dart';

/// Provides the singleton Dio instance wired with auth interceptor.
final dioProvider = Provider<Dio>((ref) {
  final storage = ref.read(tokenStorageProvider);
  final authService = ref.read(authServiceProvider);

  return createApiClient(
    storage: storage,
    authService: authService,
    retryClient: ref.read(bareDioProvider),
    onSessionExpired: () {
      ref.read(authProvider.notifier).sessionExpired();
    },
  );
});
