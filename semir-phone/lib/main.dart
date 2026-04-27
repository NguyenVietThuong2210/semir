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

  // Scrub sensitive keys from event tags (string map, safe to filter).
  final tags = event.tags;
  if (tags != null) {
    final scrubbedTags = Map<String, String>.fromEntries(
      tags.entries.map((e) {
        final isSensitive = sensitiveKeys.any((k) => e.key.toLowerCase().contains(k));
        return MapEntry(e.key, isSensitive ? '[REDACTED]' : e.value);
      }),
    );
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
  return event;
}
