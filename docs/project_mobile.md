---
name: SemirPhone Mobile App
description: Flutter iOS/Android companion app — architecture, auth, navigation, API, testing
type: project
---

# SemirPhone — Mobile App

**Last Updated:** 2026-04-27

Flutter iOS/Android companion to SemirDashboard. Connects to the same Django backend via a versioned REST API (`/api/v1/`).

---

## Paths

| Location | Path |
|----------|------|
| Project root | `semir-phone/` |
| Entry point | `semir-phone/lib/main.dart` |
| App shell / router | `semir-phone/lib/app.dart` |
| Tests | `semir-phone/test/` (unit / widget / golden) |
| Golden images | `semir-phone/test/goldens/` |
| Assets | `semir-phone/assets/icons/`, `semir-phone/assets/certs/` |

---

## Build Commands

```bash
# Debug (local backend)
flutter run --dart-define=API_BASE_URL=http://localhost:8000/api/v1

# Release (production)
flutter build apk \
  --dart-define=API_BASE_URL=https://analytics-customer-dashboard.com/api/v1 \
  --dart-define=TLS_PIN=<sha256-base64> \
  --dart-define=TLS_BACKUP_PIN=<sha256-base64-backup> \
  --dart-define=SENTRY_DSN=<dsn> \
  --dart-define=ENVIRONMENT=production

# Run all tests
flutter test

# Update stale golden images (after widget/theme changes)
flutter test test/golden/golden_test.dart --update-goldens

# Regenerate Riverpod boilerplate
dart run build_runner build --delete-conflicting-outputs
```

---

## Key Dependencies

| Package | Purpose |
|---------|---------|
| `go_router ^13` | Declarative navigation + auth redirect |
| `flutter_riverpod ^2` | State management |
| `riverpod_annotation` + `build_runner` | Code generation for providers |
| `dio ^5` | HTTP client |
| `flutter_secure_storage ^9` | Encrypted token storage |
| `local_auth ^2` | Biometric (Face ID / fingerprint) |
| `fl_chart ^0.67` | Donut + line charts |
| `sentry_flutter ^8` | Crash reporting + PII scrubbing |
| `intl ^0.19` | VND number formatting |
| `mockito ^5` | Unit test mocking |
| `golden_toolkit ^0.15` | Visual golden snapshot tests |

---

## Architecture

### Layer structure

```
lib/
  main.dart                   # Sentry init, ProviderScope, runApp
  app.dart                    # SemirPhoneApp (router + auth listenable)
  core/
    api/
      api_client.dart         # Dio instance with auth interceptor
      api_client_provider.dart
      auth_interceptor.dart   # JWT 401 handler (concurrent-safe)
      bare_dio_provider.dart  # Dio without auth interceptor (for token refresh)
      endpoints.dart          # All API path constants
    auth/
      auth_provider.dart      # AsyncNotifierProvider<UserSession?>
      auth_service.dart       # login / logout / refresh calls
      biometric_service.dart  # local_auth wrapper
      token_storage.dart      # flutter_secure_storage wrapper
    config/
      app_config.dart         # BuildConfig — dart-define compile-time constants
    theme/
      app_colors.dart
      app_theme.dart
  features/
    login/                    # LoginPage + LoginNotifier
    home/                     # HomePage + NavCard
    analytics/
      sales/                  # SalesPage, SalesProvider, SalesService
      customer/               # CustomerPage, CustomerProvider, CustomerService
      coupon/                 # CouponPage, CouponProvider, CouponService
      shop_detail/            # ShopDetailPage, ShopDetailProvider, ShopDetailService
      customer_detail/        # CustomerDetailPage, provider, service
    charts/                   # SalesChartPage, CustomerChartPage, CouponChartPage, DonutCard
  shared/
    models/
      analytics_models.dart   # KpiItem, TableTab, ApiException, PermissionException, ParseException
    utils/
      date_utils.dart         # DatePreset enum + DateRange, date helpers
      vnd_formatter.dart      # VND number formatting
    widgets/                  # Shared: KpiCard, DarkTabs, DataTableWidget, DateFilterBar,
                              #         ErrorBanner, LoadingOverlay, PullToRefresh,
                              #         SectionHeader, ShopGroupFilter
```

### Feature pattern (per-feature)

Every analytics feature follows the same 3-file pattern:

| File | Responsibility |
|------|---------------|
| `*_service.dart` | HTTP call → parse → return typed payload |
| `*_provider.dart` | `AsyncNotifierProvider` wrapping the service; exposes `refresh()` |
| `*_page.dart` | `ConsumerWidget` watching the provider; renders loading / error / data |

---

## Authentication

### Token storage (`core/auth/token_storage.dart`)

All tokens stored in `flutter_secure_storage` (AES on Android `encryptedSharedPreferences`, Keychain on iOS):

| Key | Value |
|-----|-------|
| `access_token` | JWT access token string |
| `refresh_token` | JWT refresh token string |
| `token_expiry` | ISO-8601 UTC string |
| `username` | logged-in username |
| `permissions` | `jsonEncode(List<String>)` |
| `biometric_enabled` | `'true'` / `'false'` |

### JWT interceptor (`core/api/auth_interceptor.dart`)

Concurrent-401 serialisation pattern — when N requests get a 401 simultaneously:
- Exactly **1** refresh call is made
- All other requests queue and retry with the new token
- If refresh fails → `onSessionExpired()` callback clears state and redirects to `/login`

The interceptor's retry Dio is injected via `bareDioProvider` (a plain Dio with no auth interceptor, preventing infinite retry loops).

### Auth flow

```
cold start
  └─ authProvider.build() reads tokens from storage
  └─ if access token present → UserSession loaded (no network call)
  └─ expiry missing → assumes 1h from now (avoids needless refresh round-trip)

login
  └─ AuthService.login(username, password) → POST /auth/token/
  └─ tokens saved to secure storage
  └─ UserSession built from response

logout
  └─ POST /auth/logout/ (best-effort)
  └─ deleteAll() clears secure storage
  └─ GoRouter redirects to /login

401 during any request
  └─ AuthInterceptor queues request, refreshes token once
  └─ retry all queued requests with new access token
  └─ if refresh fails → onSessionExpired() → /login
```

---

## Navigation (`app.dart`)

GoRouter with `refreshListenable: _AuthListenable(ref)`:

| Route | Perm required | Page |
|-------|--------------|------|
| `/login` | none | `LoginPage` |
| `/` | authenticated | `HomePage` |
| `/sales` | `sales.view` | `SalesPage` |
| `/sales/charts` | `sales.view` | `SalesChartPage` |
| `/customer` | `customers.view` | `CustomerPage` |
| `/customer/charts` | `customers.view` | `CustomerChartPage` |
| `/coupon` | `coupons.view` | `CouponPage` |
| `/coupon/charts` | `coupons.view` | `CouponChartPage` |
| `/shop-detail` | `shop_detail.view` | `ShopDetailPage` |
| `/customer-detail` | `customer_detail.view` | `CustomerDetailPage` |

`_AuthListenable` uses `ref.listenManual` (returns `ProviderSubscription`) — the subscription is closed in `dispose()` to avoid orphaned listeners. Do **not** use `ref.listen` here (returns `void`, not closeable outside a widget context).

Permission redirect: `_requirePerm(perm)` returns `'/'` (home) when the session lacks the permission, or `null` to allow navigation.

---

## API Client (`core/api/`)

`BuildConfig.apiBaseUrl` is injected at compile time via `--dart-define=API_BASE_URL=...`. Never loaded from files or network.

**TLS certificate pinning** (production only):
- `BuildConfig.tlsPin` and `tlsBackupPin` hold SHA-256 SPKI fingerprints
- Applied via `IOHttpClientAdapter` in `api_client.dart`
- Empty string in debug → pinning disabled

All API base paths are in `endpoints.dart` — do not hardcode URLs in service files.

---

## Shared Models (`shared/models/analytics_models.dart`)

Single source of truth for shared types across all features:

| Type | Purpose |
|------|---------|
| `KpiItem` | `{label, value}` for a stat card |
| `TableTab` | `{tabKey, label, headers, rows}` for a data table |
| `ApiException` | Non-2xx HTTP error (carries `statusCode` + `message`) |
| `PermissionException` | 403 response — user lacks permission |
| `ParseException` | JSON decode / shape mismatch failure |

**Do not re-define these in individual service files.** All services import from here.

---

## Date Utilities (`shared/utils/date_utils.dart`)

`DatePreset` enum with 8 values: `last7Days`, `last30Days`, `last90Days`, `lastMonth`, `thisMonth`, `thisYear`, `currentYear`, `previousYear`.

`currentYear` and `previousYear` are computed dynamically from `DateTime.now().year` — no hardcoded year constants.

---

## Shared Widgets

| Widget | Usage |
|--------|-------|
| `KpiCard` | Stat card with `KpiVariant.allTime` (orange tint) or `KpiVariant.period` (blue tint) |
| `DarkTabs` | Tab bar with dark background (matches web dark-tabs pattern) |
| `DataTableWidget` | Horizontally scrollable table with sticky first column |
| `DateFilterBar` | Date preset picker + custom range |
| `ErrorBanner` | Error message + optional Retry button |
| `LoadingOverlay` | Full-screen loading indicator |
| `PullToRefresh` | Wraps a `ListView` with pull-to-refresh |
| `SectionHeader` | Solid primary-color section header |
| `ShopGroupFilter` | `InputDecorator + DropdownButton<String>` — **controlled widget**, `value:` drives selection |

`ShopGroupFilter` uses `DropdownButton` (not `DropdownButtonFormField`) so it responds correctly to externally-driven state resets. Do **not** switch it back to `DropdownButtonFormField(initialValue:)`.

---

## Test Structure

```
test/
  unit/
    api_client_test.dart          # AuthInterceptor + Dio mock tests
    chart_service_test.dart
    coupon_service_test.dart
    customer_detail_service_test.dart
    customer_service_test.dart
    sales_service_test.dart
    shop_detail_service_test.dart
    token_storage_test.dart
    log_scrub_test.dart           # Sentry PII scrubbing
  widget/
    coupon_page_test.dart
    customer_detail_page_test.dart
    customer_page_test.dart
    sales_page_test.dart
    shop_detail_page_test.dart
    home_page_test.dart
    login_page_test.dart
    router_test.dart
    chart_page_test.dart
    chart_interaction_test.dart
    donut_card_test.dart
    nav_card_test.dart
    date_filter_bar_test.dart
  golden/
    golden_test.dart              # Visual pixel-comparison tests (198 total)
    goldens/                      # Reference PNG images
```

Golden images must be regenerated with `--update-goldens` whenever any visual component changes (theme, widget layout, colors). All 198 tests must pass before release.

---

## Security

| Concern | Implementation |
|---------|---------------|
| Token storage | `flutter_secure_storage` with `encryptedSharedPreferences: true` (Android) |
| TLS pinning | SHA-256 SPKI pinning via `IOHttpClientAdapter` (prod only) |
| Compile-time secrets | All config via `--dart-define` (no files, no `.env`) |
| Crash reporting PII | Sentry `beforeSend` callback scrubs tokens, phone numbers, usernames |
| 401 race condition | Single-refresh serialisation in `AuthInterceptor` |
| Permissions | `UserSession.hasPermission()` checked at both router redirect and UI card level |

---

## Release Checklist

- [ ] All 198 tests pass (`flutter test`)
- [ ] Golden images up to date (no pixel diffs without `--update-goldens`)
- [ ] `--dart-define=API_BASE_URL`, `TLS_PIN`, `TLS_BACKUP_PIN`, `SENTRY_DSN`, `ENVIRONMENT=production` set in build
- [ ] TLS pin fingerprints match current server certificate
- [ ] Biometric login tested on a real device (not simulator)
- [ ] App icon + splash screen generated (`flutter pub run flutter_launcher_icons`, `flutter pub run flutter_native_splash:create`)
