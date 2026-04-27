# SemirPhone

Mobile analytics companion for SemirDashboard. Built with Flutter 3.x for iOS and Android.

## Prerequisites

| Tool | Version |
|------|---------|
| Flutter | 3.x stable (`flutter channel stable`) |
| Dart | 3.x (bundled with Flutter) |
| Xcode | 15+ (iOS builds — macOS only) |
| Android Studio | Flamingo+ with SDK 33+ |
| Fastlane | `gem install fastlane` |
| Ruby | 3.x (for Fastlane) |

Verify your setup:

```bash
flutter doctor -v
```

All checks must pass with no blocking issues before running the app.

## Quickstart

```bash
# From the repo root
cd semir-phone

# Install dependencies
flutter pub get

# Run on connected iOS device / Simulator
make run-ios

# Run on connected Android device / Emulator
make run-android

# Run all tests
make test
```

## Environment Variables

All secrets are injected at build time via `--dart-define`. Never committed.

```bash
export API_BASE_URL="https://analytics-customer-dashboard.com/api/v1/"
export SENTRY_DSN="https://xxx@sentry.io/yyy"
export ENVIRONMENT="production"
export TLS_PIN="sha256/<primary-pin>"
export TLS_BACKUP_PIN="sha256/<backup-pin>"
```

In development (debug builds), leave `TLS_PIN` empty to skip certificate pinning.

## Running Tests

```bash
# All unit + widget tests
make test
# or:
flutter test

# Single test file
flutter test test/unit/auth_service_test.dart

# Integration tests (requires running device + backend)
flutter test integration_test/login_flow_test.dart

# Regenerate golden snapshots (after UI changes)
make snapshot
# or:
flutter test --update-goldens test/golden/
```

## Project Structure

```
lib/
  core/
    api/           # Dio client, auth interceptor, endpoints
    auth/          # TokenStorage, AuthService, BiometricService, AuthProvider
    config/        # BuildConfig (dart-define flags)
    theme/         # AppColors, AppTheme
  features/
    login/         # Login page
    home/          # Home page, NavCard
    analytics/
      sales/       # Sales Analytics (page, service, provider)
      customer/    # Customer Analytics
      coupon/      # Coupon Analytics
      shop_detail/ # Shop Detail
      customer_detail/ # Customer Detail lookup
    charts/        # DonutCard, chart pages, chart provider
  shared/
    utils/         # VND formatter, date utils
    widgets/       # KpiCard, DataTableWidget, DarkTabs, SectionHeader, etc.
test/
  unit/            # Unit tests (no Flutter framework)
  widget/          # Widget tests
integration_test/  # E2E tests
```

## Architecture

- **State management**: Riverpod 2.x (`AsyncNotifierProvider` for async data, `StateProvider` for filters)
- **Navigation**: GoRouter with auth guard (`redirect` checks `authProvider` state)
- **HTTP**: Dio + `QueuedInterceptor` for serialized 401 → refresh → retry flow
- **Auth tokens**: `flutter_secure_storage` (Keychain on iOS, EncryptedSharedPreferences on Android)
- **Charts**: `fl_chart` PieChart (donut variant) with touch callbacks
- **Error reporting**: Sentry with PII scrubbing (`beforeSend` strips phone/vip_id/token fields)
- **TLS pinning**: CA/intermediate pinning via `SecurityContext` — active only when `TLS_PIN` env var is set

## Design Tokens

All colors come from `lib/core/theme/app_colors.dart` — never hardcode hex in widgets.

| Token | Usage |
|-------|-------|
| `AppColors.primary` | Action buttons, section headers, borders |
| `AppColors.navBg` | Dark tab bar background |
| `AppColors.allTimeCardBg` | All-time KPI card background (orange tint) |
| `AppColors.periodCardBg` | Period KPI card background (blue tint) |
| `AppColors.textDark` | Primary text |
| `AppColors.textMuted` | Secondary text, labels |

## Deployment

See [DEPLOYMENT.md](DEPLOYMENT.md) for the full 10-step release guide covering:
- Apple Developer setup and Fastlane Match cert sync
- TestFlight upload and internal testing checklist
- Google Play Console setup and AAB signing
- Production rollout strategy and rollback procedure
- TLS certificate rotation procedure

## Security Notes

- Phone numbers are **always** masked at the API layer (`09x-xxx-x567`) — the mobile app never receives raw numbers
- Sentry `beforeSend` hook strips any field containing `phone`, `vip_id`, `invoice`, or `token`
- Biometric authentication gates secure storage release — it is not a backend auth mechanism
- TLS certificate pinning rejects any connection not chaining to the pinned CA
- Refresh tokens are blacklisted server-side on rotation (`BLACKLIST_AFTER_ROTATION=True`)
