import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:sentry_flutter/sentry_flutter.dart';

import 'app.dart';
import 'core/config/app_config.dart';

Future<void> main() async {
  WidgetsFlutterBinding.ensureInitialized();

  if (BuildConfig.sentryDsn.isNotEmpty) {
    await SentryFlutter.init(
      (options) {
        options.dsn = BuildConfig.sentryDsn;
        options.environment = BuildConfig.environment;
        options.tracesSampleRate = 0.2;
        options.beforeSend = _scrubPii;
      },
      appRunner: () => _runApp(),
    );
  } else {
    _runApp();
  }
}

void _runApp() {
  runApp(const ProviderScope(child: SemirPhoneApp()));
}

/// Strip PII fields before any event reaches Sentry (FR-006, FR-046, SC-008).
/// Exposed as [scrubPiiForTest] for unit testing (SC-008 gate).
SentryEvent? scrubPiiForTest(SentryEvent event, Hint hint) => _scrubPii(event, hint);

SentryEvent? _scrubPii(SentryEvent event, Hint hint) {
  const sensitiveKeys = ['phone', 'vip_id', 'invoice', 'token', 'password'];
  Map<String, dynamic> scrub(Map<String, dynamic> map) {
    return map.map((key, value) {
      final lowerKey = key.toLowerCase();
      final isSensitive =
          sensitiveKeys.any((k) => lowerKey.contains(k));
      if (isSensitive) return MapEntry(key, '[REDACTED]');
      if (value is Map<String, dynamic>) return MapEntry(key, scrub(value));
      return MapEntry(key, value);
    });
  }

  final extra = event.extra;
  if (extra != null) {
    return event.copyWith(extra: scrub(extra.cast<String, dynamic>()));
  }
  return event;
}
