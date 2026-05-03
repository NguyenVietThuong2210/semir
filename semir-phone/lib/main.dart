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

  bool isSensitive(String key) =>
      sensitiveKeys.any((k) => key.toLowerCase().contains(k));

  // Recursively scrub a map, replacing sensitive values with '[REDACTED]'.
  Map<String, dynamic> scrubMap(Map<String, dynamic> map) {
    return Map<String, dynamic>.fromEntries(map.entries.map((e) {
      if (isSensitive(e.key)) return MapEntry(e.key, '[REDACTED]');
      if (e.value is Map<String, dynamic>) {
        return MapEntry(e.key, scrubMap(e.value as Map<String, dynamic>));
      }
      return e;
    }));
  }

  final tags = event.tags;
  // ignore: deprecated_member_use
  final extra = event.extra;
  final needsScrub = (tags != null) || (extra != null);
  if (!needsScrub) return event;

  final scrubbedTags = tags == null
      ? null
      : Map<String, String>.fromEntries(tags.entries.map((e) =>
          MapEntry(e.key, isSensitive(e.key) ? '[REDACTED]' : e.value)));

  final scrubbedExtra = extra == null ? null : scrubMap(extra);

  return SentryEvent(
    eventId: event.eventId,
    timestamp: event.timestamp,
    platform: event.platform,
    logger: event.logger,
    serverName: event.serverName,
    release: event.release,
    dist: event.dist,
    environment: event.environment,
    message: event.message,
    transaction: event.transaction,
    throwable: event.throwable,
    level: event.level,
    culprit: event.culprit,
    tags: scrubbedTags,
    extra: scrubbedExtra,
    modules: event.modules,
    breadcrumbs: event.breadcrumbs,
    sdk: event.sdk,
    request: event.request,
    contexts: event.contexts,
    user: event.user,
    fingerprint: event.fingerprint,
    exceptions: event.exceptions,
    threads: event.threads,
    debugMeta: event.debugMeta,
    type: event.type,
  );
}
