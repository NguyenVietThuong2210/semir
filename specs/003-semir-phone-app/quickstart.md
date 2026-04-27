# Quickstart: SemirPhone Integration Scenarios

**Phase**: 1 — Design  
**Date**: 2026-04-25  
**For**: Developers setting up the project and QA validating each user story.

---

## Prerequisites

| Tool | Version | Install |
|------|---------|---------|
| Flutter SDK | ≥ 3.x (stable) | https://docs.flutter.dev/get-started/install |
| Dart | ≥ 3.x (bundled with Flutter) | — |
| Xcode | ≥ 15 (macOS only, for iOS builds) | Mac App Store |
| Android Studio | ≥ Flamingo | https://developer.android.com/studio |
| Fastlane | ≥ 2.x | `gem install fastlane` |
| Ruby | ≥ 3.x (for Fastlane) | `rbenv install 3.x` |

**Verify setup:**
```bash
flutter doctor -v          # All green except unrelated tools
flutter --version          # Must show 3.x stable
fastlane --version         # Must show 2.x
```

---

## First-Time Setup

```bash
# 1. Clone the repo (SemirPhone is at semir-phone/ inside the main repo)
git clone <repo-url> && cd semir-phone

# 2. Install Flutter dependencies
flutter pub get

# 3. Create local env file (copy template, fill in values)
cp .env.example .env.debug
# Edit .env.debug: set API_BASE_URL=http://localhost:8000/api/v1

# 4. Run the backend locally (in a separate terminal)
cd ../SemirDashboard && python manage.py runserver

# 5. Verify the backend API is up
curl http://localhost:8000/api/v1/auth/token/ \
  -X POST -H "Content-Type: application/json" \
  -d '{"username":"admin","password":"<password>"}' | python -m json.tool
# Should return access + refresh + permissions JSON
```

---

## Daily Development Commands

All commands run from the `semir-phone/` directory:

```bash
make run-ios          # Launch on iOS Simulator (requires macOS + Xcode)
make run-android      # Launch on Android Emulator
make test             # Run all unit + widget tests
make snapshot         # Regenerate visual PNG snapshots → render/ folder
make build-ios        # Build signed IPA (requires Fastlane configured)
make build-android    # Build signed AAB (requires keystore configured)
```

**Manual equivalents (if Make is not available):**
```bash
flutter run -d "iPhone 15 Pro"   # iOS
flutter run -d "Pixel 7"         # Android
flutter test                      # All tests
flutter test --update-goldens    # Regenerate golden snapshots
```

---

## Integration Scenario 1: Login Flow (US1)

**Goal**: Verify that login, token storage, biometric opt-in, and session persistence all work end-to-end.

**Setup**: Backend running locally. Use superuser account (has all permissions).

```
1. Launch app (make run-ios or make run-android)
2. Enter valid username + password → tap Sign In
   Expected: Home page loads within 3 seconds, username shown in header
3. Kill the app (don't swipe away — force-quit from app switcher)
4. Relaunch app
   Expected: Already signed in — home page loads without login prompt
5. Go to Settings → tap Sign Out
   Expected: Returned to login screen, no tokens in Keychain/Keystore
6. Enter wrong credentials → tap Sign In
   Expected: Generic error message, no token stored
7. Sign in again, go to Settings → enable biometric
8. Kill and relaunch app
   Expected: Biometric prompt appears before home page
```

**Snapshot to generate:** `make snapshot` → verify `render/login.png` and `render/home.png`

---

## Integration Scenario 2: Home Permission Filtering (US2)

**Goal**: Verify that cards are shown/hidden based on `UserSession.permissions`.

**Setup**: Create two test accounts on the backend:
- `analyst_full`: all 5 permissions
- `analyst_sales`: only `sales.view`

```
1. Sign in as analyst_full → verify all 8 cards visible
2. Sign out → sign in as analyst_sales
   Expected: Only "Sales Analytics" and "Sales Analytics Charts" cards visible
   Layout must reflow cleanly (no empty gaps)
3. Try navigating directly to the customer page via Flutter devtools route injection
   Expected: Navigator auth guard blocks navigation, shows "no access"
```

---

## Integration Scenario 3: Sales Analytics Data (US3)

**Goal**: Verify data parity with the web for the same filter inputs.

**Setup**: Backend running. Open both the mobile app and the SemirDashboard web app in a browser at the same time.

```
1. In web: go to Sales Analytics, set date filter to 2025-01-01 → 2025-12-31
   Note the Period KPI values (total invoices, return rate, etc.)
2. In mobile: open Sales Analytics, set same date filter → tap Apply
   Expected: Same values displayed (SC-003)
3. Mobile: switch through all tabs (By Season → By Month → By Week → By Shop → By Grade)
   Expected: Each tab table renders with sticky first column, horizontal scroll works
4. Mobile: pull down on the page
   Expected: Loading indicator appears, data refreshes
5. Mobile: switch to airplane mode, try to change filter
   Expected: "No connection" error banner with retry button
```

---

## Integration Scenario 4: JWT Refresh (Concurrent 401)

**Goal**: Verify the token refresh interceptor handles concurrent 401s correctly.

**Setup**: Set access token expiry to 5 seconds in Django simplejwt config for this test.

```
1. Sign in → navigate to Sales Analytics
2. Wait 6 seconds (access token expires)
3. Rapidly switch 3 tabs at once (triggers 3 parallel API calls)
   Expected: Exactly 1 refresh call hits POST /api/v1/auth/token/refresh/
             All 3 data requests succeed after the single refresh
             No "session expired" screen appears
4. Check Django logs: should show exactly 1 token refresh request, not 3
```

---

## Integration Scenario 5: Visual Snapshot QA (FR-032/033)

**Goal**: Verify that snapshots match web concept and pass QA review.

```bash
# Generate all snapshots
make snapshot

# Output: render/ folder contains:
#   render/login.png
#   render/home.png
#   render/sales_analytics.png
#   render/customer_analytics.png
#   render/coupon_analytics.png
#   render/shop_detail.png
#   render/customer_detail.png
#   render/sales_charts.png
#   render/customer_charts.png
#   render/coupon_charts.png
```

**QA checklist per PNG (senior QA review gate):**
- [ ] Section card-headers: solid primary blue (#0d6efd), white text
- [ ] All-Time KPI cards: orange tint background, dark text
- [ ] Period KPI cards: blue tint background, dark text
- [ ] Table headers: solid primary blue, white text, no per-column accent colors
- [ ] Home cards: uniform blue top-border (4pt), no mixed accent colors
- [ ] No text truncation on 390pt width (iPhone 14 Pro logical)
- [ ] Currency values formatted as "1,234,567 VND" (Vietnamese grouping)
- [ ] Compare against `../SemirDashboard/render/png/` web snapshots — same block structure

---

## Integration Scenario 6: Store Build & Submission (FR-043–FR-045)

**Goal**: Produce a signed IPA and AAB ready for TestFlight and Play Internal Testing.

```bash
# iOS — requires macOS, Xcode, Fastlane Match configured
fastlane ios beta          # Builds, signs, uploads to TestFlight

# Android — requires keystore env vars set
export KEYSTORE_PASSWORD=<>
export KEY_ALIAS=<>
export KEY_PASSWORD=<>
fastlane android beta      # Builds signed AAB, uploads to Play Internal Testing
```

**Pre-submission checklist (from DEPLOYMENT.md):**
- [ ] App icon in `assets/icons/` (1024×1024 iOS, adaptive Android)
- [ ] Splash screen configured in `flutter_native_splash` config
- [ ] Privacy policy URL set in `BuildConfig.privacyPolicyUrl` and store listing
- [ ] `store-assets/` screenshots generated for all required device sizes
- [ ] Sentry DSN set in `--dart-define=SENTRY_DSN=<dsn>` for release build
- [ ] TLS pin SHA-256 set in `--dart-define=TLS_PIN=<sha256>` for release build
- [ ] Version number incremented in `pubspec.yaml` (both `version` and build number)

---

## Environment Variables Reference

| Variable | Used in | Example |
|----------|---------|---------|
| `API_BASE_URL` | Debug builds | `http://localhost:8000/api/v1` |
| `TLS_PIN` | Release builds | `sha256/<base64>` |
| `TLS_BACKUP_PIN` | Release builds | `sha256/<base64>` |
| `SENTRY_DSN` | Release builds | `https://xxx@sentry.io/yyy` |
| `KEYSTORE_PASSWORD` | Android release | (secret) |
| `KEY_ALIAS` | Android release | `semirphone-key` |
| `KEY_PASSWORD` | Android release | (secret) |

All secrets MUST be set as environment variables — never committed to the repo.
