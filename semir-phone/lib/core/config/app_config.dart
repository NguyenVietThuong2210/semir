/// Compile-time configuration injected via --dart-define flags.
/// Never load from files or network at runtime.
///
/// Debug build: flutter run --dart-define=API_BASE_URL=http://localhost:8000/api/v1
/// Release build: all values set in CI / Fastlane build command.
abstract final class BuildConfig {
  static const String apiBaseUrl = String.fromEnvironment(
    'API_BASE_URL',
    defaultValue: 'http://localhost:8000/api/v1',
  );

  static const String tlsPin = String.fromEnvironment(
    'TLS_PIN',
    defaultValue: '', // empty = pinning disabled (debug)
  );

  static const String tlsBackupPin = String.fromEnvironment(
    'TLS_BACKUP_PIN',
    defaultValue: '',
  );

  static const String sentryDsn = String.fromEnvironment(
    'SENTRY_DSN',
    defaultValue: '', // empty = Sentry disabled (debug)
  );

  static const String environment = String.fromEnvironment(
    'ENVIRONMENT',
    defaultValue: 'debug',
  );
}
