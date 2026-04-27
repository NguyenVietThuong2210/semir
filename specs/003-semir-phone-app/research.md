# Research: SemirPhone Mobile App

**Phase**: 0 — Pre-planning research  
**Date**: 2026-04-25  
**Feature**: [spec.md](spec.md)

---

## Decision 1: Cross-Platform Framework

**Decision:** Flutter (Dart 3.x / Flutter 3.x)

**Rationale:** The spec mandates pixel-perfect UI parity with the web (FR-017–FR-023): exact primary blue `#0d6efd`, orange tint backgrounds, precise 4pt top-border accents, identical table column header colors. Flutter renders every pixel directly via its own Impeller/Skia GPU canvas — no native widget delegation. This eliminates cross-platform rendering differences that React Native cannot avoid (native UIKit on iOS vs ViewGroups on Android produce subtle color, shadow, and border differences). Flutter golden tests also produce PNG output natively, directly satisfying FR-032/033 (visual snapshot mechanism).

**Alternatives considered:**
- **React Native**: Bridges to native widgets. Easier ecosystem access but cannot guarantee identical pixel rendering across platforms. Achieving exact design token parity would require per-platform style shims on every component — ongoing maintenance debt.
- **Native (Swift + Kotlin)**: Maximum platform fidelity, but two separate codebases violates FR-027 (single shared codebase).

---

## Decision 2: HTTP Client + JWT Refresh

**Decision:** Dio + `QueuedInterceptor` with flag-and-queue concurrent 401 handling

**Rationale:** Dio is Flutter's standard HTTP client with first-class interceptor support. The concurrent-401 race condition (multiple in-flight requests all receiving 401 simultaneously) is prevented by the flag-and-queue pattern: an `isRefreshing` boolean gates the refresh call, and a `pendingRequests` list accumulates failed requests while refresh is in progress. When the single refresh call succeeds, all pending requests are retried with the new access token. `QueuedInterceptor` (included in Dio) serializes interceptor execution automatically. This directly implements the edge case in the spec ("Concurrent 401 responses").

**Alternatives considered:**
- **`http` package**: No interceptor support — requires custom wrapper for JWT refresh, leading to boilerplate.
- **Regular `Interceptor` without flag**: Multiple 401s trigger parallel refresh calls, corrupting the refresh token on most backends.

---

## Decision 3: State Management

**Decision:** Riverpod 2.x (with code generation via `riverpod_generator`)

**Rationale:** SemirPhone is a read-only analytics app (~10 screens, all async data fetch → display). Riverpod provides compile-time safety, context-free provider access, built-in `AsyncValue` for loading/error/data states (eliminates manual loading flag boilerplate), and straightforward testability (override providers in tests with mock data). For this scope, Riverpod's `AsyncNotifierProvider` maps directly to each analytics page's data lifecycle.

**Alternatives considered:**
- **BLoC**: Strict event → state architecture suited for large teams. Too much boilerplate for 10 screens with no write operations.
- **Provider**: Predecessor to Riverpod; less type-safe, no compile-time checks.
- **GetX**: Simple but sacrifices type safety; not recommended for production apps with strict testing requirements.

---

## Decision 4: Visual Snapshots (FR-032/033)

**Decision:** Flutter golden tests (`flutter_test` built-in) + `golden_toolkit` package

**Rationale:** Flutter golden tests render a widget tree to a PNG and compare pixel-by-pixel against stored baselines. Command: `flutter test --update-goldens` regenerates all golden files. Files stored in `test/golden/` (committed) and symlinked / copied to `render/` on generation (fulfills FR-033: single `make snapshot` command). `golden_toolkit` adds device frame helpers and multi-device rendering in a single test run. Failed tests auto-produce a `_isolatedDiff.png` showing expected vs actual — directly enabling the QA review gate (FR-033: "senior QA review before marking done").

**Alternatives considered:**
- **Detox (E2E simulator screenshots)**: Real device rendering but slow, flaky, and requires a running simulator in CI.
- **Manual screenshots**: Not automatable; violates FR-039 (single `make snapshot` command).

---

## Decision 5: TLS Certificate Pinning

**Decision:** Pin intermediate CA certificate public key via Dio + `SecurityContext.setTrustedCertificatesBytes()`

**Rationale:** The spec (FR-031) explicitly requires pinning the CA/intermediate (not the leaf cert) with a backup pin to avoid forced updates on annual cert renewal. `SecurityContext` in Dart's `dart:io` allows loading a PEM-formatted intermediate CA certificate as the only trusted issuer. On iOS this overrides ATS; on Android it overrides the system trust store. The backup pin is implemented as a second PEM certificate in the same `SecurityContext`. Both are embedded in the app bundle as assets.

**Alternatives considered:**
- **Leaf cert pinning**: Requires app update every 90 days (Let's Encrypt) or annually — violates the spec's operational constraint.
- **No pinning**: HTTPS only (FR-030) is enforced, but rogue CA MITM attacks remain possible. FR-031 says SHOULD pin — we treat this as MUST for a production analytics app handling sensitive retail data.

---

## Decision 6: Build & Release Automation

**Decision:** Fastlane + GitHub Actions (or local Fastlane CLI for manual releases)

**Rationale:** Fastlane abstracts iOS code-signing complexity (certificates, provisioning profiles via Fastlane Match) and automates both IPA upload to TestFlight and AAB upload to Google Play Internal Testing. The `Makefile` targets (`build-ios`, `build-android`) call Fastlane lanes internally — the developer runs one command, Fastlane handles signing and upload. GitHub Actions triggers the same lanes on tagged commits for CI/CD.

**Alternatives considered:**
- **Manual `flutter build ipa/apk`**: Works for one-off builds but requires manual Xcode archive steps for App Store submission. Not auditable or reproducible across machines.
- **Xcode Cloud**: iOS-only; no Android equivalent.

---

## Resolved: Backend JSON API (Sprint 0 Blocker)

**Decision:** Django REST Framework (DRF) API layer added to SemirDashboard

**Rationale:** The existing SemirDashboard serves HTML via Django template views. The mobile app needs JSON. Rather than a separate API server, DRF endpoints are added to the existing Django project under `/api/v1/`. This reuses existing analytics functions (`get_sales_tab`, `compute_cnv_breakdown`, etc.) as the data source — no analytics logic is duplicated. JWT tokens are issued via `djangorestframework-simplejwt`.

**API surface** (to be fully specified in `contracts/api-contract.md`):
- `POST /api/v1/auth/token/` — login, returns access + refresh + permissions
- `POST /api/v1/auth/token/refresh/` — exchange refresh → new access token
- `POST /api/v1/auth/logout/` — revoke refresh token
- `GET /api/v1/analytics/sales/` — Sales Analytics data
- `GET /api/v1/analytics/customer/` — Customer Analytics data
- `GET /api/v1/analytics/coupon/` — Coupon Analytics data
- `GET /api/v1/charts/sales/` — Sales chart data
- `GET /api/v1/charts/customer/` — Customer chart data
- `GET /api/v1/charts/coupon/` — Coupon chart data
- `GET /api/v1/analytics/shop-detail/` — Shop Detail data
- `GET /api/v1/analytics/customer-detail/` — Customer Detail data

**Versioning strategy:** `/api/v1/` prefix allows future breaking changes via `/api/v2/` without forcing simultaneous app updates. Old app versions continue to work until explicitly deprecated.

---

## Tech Stack Summary

| Layer | Choice | Version |
|-------|--------|---------|
| Language | Dart | 3.x |
| Framework | Flutter | 3.x (stable channel) |
| HTTP client | Dio | 5.x |
| State management | Riverpod | 2.x |
| Secure storage | flutter_secure_storage | 9.x |
| Biometric | local_auth | 2.x |
| Charts | fl_chart | 0.x |
| Crash reporting | Sentry Flutter SDK | latest |
| Visual snapshots | flutter_test goldens + golden_toolkit | — |
| Build automation | Fastlane | 2.x |
| Backend API | Django REST Framework + simplejwt | — |
| Min iOS | 14.0 | — |
| Min Android | API 26 (Android 8.0) | — |

**Crash reporting choice (Sentry over Firebase Crashlytics):** Sentry provides finer-grained PII scrubbing configuration (before-send hooks) making FR-046's PII exclusion rule easier to enforce. Sentry free tier supports 5,000 errors/month, sufficient for an internal analytics app.
