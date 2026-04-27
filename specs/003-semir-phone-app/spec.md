# Feature Specification: SemirPhone Mobile App

**Feature Branch**: `003-semir-phone-app`
**Created**: 2026-04-25
**Status**: Draft
**Input**: User description: "tôi muốn tạo 1 project mới là SemirPhone mục đich là sử dụng trên điện thoại ios/android, gồm chức năng login, page home và cụm chức năng Analytics & Reports như tong hình ... SemirPhone sẽ gọi đến server mà tôi deploy SemirDashboard và được upload lên app store/ google play, hãy sử dụng ngôn ngữ có thể adapt được cả 2, và đảm bảo về mặt security"

## Clarifications

### Session 2026-04-25

- Q: Does the backend use short-lived JWT access+refresh tokens or long-lived opaque session tokens? → A: JWT with short-lived access token (15min–1h) + long-lived refresh token (7–30 days). The backend JSON API layer (Sprint 0) must issue both. The mobile app handles transparent token refresh via an HTTP interceptor — the user is only re-routed to login when the refresh token itself expires or is revoked.
- Q: What are the permission strings for all 8 home cards? → A: `sales.view` (Sales Analytics + Sales Charts), `cnv.view` (Customer Analytics + Customer Charts), `coupons.view` (Coupon Analytics + Coupon Charts), `shop_detail.view` (Shop Detail), `customer_detail.view` (Customer Detail). Charts share the same gate as their data page — no separate permission needed.
- Q: How should SC-006 (crash-free rate) be measured given crash SDK is excluded? → A: Add a lightweight crash reporting SDK (Sentry free tier or Firebase Crashlytics) as in-scope for v1. Provides real-time, precise crash-free session rate. Removed from Out of Scope.
- Q: What is the maximum expected row count for the largest table (By Shop)? → A: ≤200 rows (50–150 shops in practice). Standard ScrollView with sticky header is sufficient; full virtualization is not required for v1.
- Q: Does the app support deep links (universal links / custom URL scheme)? → A: No deep links in v1. SC-009 guards against back-stack/navigator bypass only. No URL scheme, no AASA/assetlinks.json config required. Deep links are explicitly out of scope.

## User Scenarios & Testing *(mandatory)*

### User Story 1 - Secure Mobile Login (Priority: P1)

A SEMIR analytics user opens the SemirPhone app on their iOS or Android device, enters the same credentials they use on the SemirDashboard web app, and is granted access to the home page. Authentication tokens are stored securely on the device so the user remains signed in across app launches without re-entering credentials, until the session expires or the user signs out.

**Why this priority**: Without authentication the rest of the app is unreachable. This is the entry point and the security-critical foundation — every other feature depends on a valid session and identifies the actor for permission checks (the same role-based permissions that gate features in SemirDashboard apply here).

**Independent Test**: Install the app on a fresh device, launch it, sign in with valid analyst credentials → home page loads with the user's name and role badge. Re-launch the app → still signed in. Sign out → returned to login. Sign in with invalid credentials → clear error message, no token stored.

**Acceptance Scenarios**:

1. **Given** the app is installed and the user has valid SemirDashboard credentials, **When** they enter username and password and tap Sign In, **Then** they are taken to the home page within 3 seconds and their session is preserved across app restarts.
2. **Given** the user enters wrong credentials, **When** they submit, **Then** the app shows a clear error message (no specifics about which field was wrong) and does not store any token on the device.
3. **Given** the user is signed in, **When** they tap Sign Out from the user menu, **Then** all authentication tokens and cached personal data are removed from the device and they return to the login screen.
4. **Given** the user's JWT access token has expired and the app makes a data request that returns 401, **When** the app attempts a silent refresh using the stored refresh token, **Then** if the refresh succeeds the original request is retried automatically with no user-visible interruption; if the refresh token is also expired or revoked, the user is routed to the login screen with a "session expired" notice and their current page is saved as the post-login destination.
5. **Given** the device has biometric authentication available (Face ID / Touch ID / fingerprint), **When** the user opts into it during onboarding, **Then** subsequent app launches can re-authenticate via biometric in place of typing the password.

---

### User Story 2 - Home Page Navigation (Priority: P1)

After signing in, the user lands on a home page that mirrors the SemirDashboard web home: a header greeting + section group headers ("Analytics & Reports") + a grid of feature cards. Each card has the same icon, title, description, and call-to-action button as the web version, but laid out for a phone screen (single column or 2-column grid depending on device width). Cards a user does not have permission for are hidden, exactly as on web.

**Why this priority**: The home page is the navigation hub. Without it the analytics features have no entry point and the user can't tell what the app is for at a glance.

**Independent Test**: Sign in as a user with full permissions → see all 8 cards (Sales Analytics, Sales Analytics Charts, Customer Analytics, Customer Charts, Coupon Analytics, Coupon Analytics Charts, Shop Detail, Customer Detail). Sign in as a user with restricted permissions → only the cards they can access are visible. Tap each card → navigate to the corresponding page.

**Acceptance Scenarios**:

1. **Given** a signed-in user with full permissions, **When** the home page loads, **Then** the user sees the "Analytics & Reports" section group header and 8 feature cards with the same titles, icons, and descriptions as the web version.
2. **Given** a signed-in user without `coupons.view` permission, **When** the home page loads, **Then** the Coupon Analytics card is not displayed and the layout reflows cleanly with no empty slots.
3. **Given** the user taps any feature card, **When** the tap is registered, **Then** the app navigates to the corresponding analytics page within 1 second.
4. **Given** the user is on a small phone (≤375pt width), **When** the home page renders, **Then** cards stack in a single column with full-width touch targets ≥44pt tall, no horizontal scrolling, no text truncation.
5. **Given** the user is on a tablet or large phone (≥768pt width), **When** the home page renders, **Then** cards display in a 2-column or 3-column grid using the same uniform blue top-border style as the web home.

---

### User Story 3 - View Sales Analytics on Mobile (Priority: P1)

The user opens the Sales Analytics page from the home grid and sees the same KPI cards (Period Metrics + All-Time Metrics) and breakdown tables (By Season / By Month / By Week / By Shop / By Grade) that appear on the web. The page supports the same date-range filter (start/end date + quick presets) and shop-group filter. Tables are scrollable horizontally on small screens to preserve the column structure rather than wrap and break the data shape.

**Why this priority**: Sales Analytics is the primary analytical workflow — it is the most-used feature in SemirDashboard. Delivering this on mobile is the core value proposition: managers can check return-visit rates and revenue while away from a desk.

**Independent Test**: Sign in → tap Sales Analytics → see Period + All-Time KPI cards (uniform style: orange tint = all-time, blue tint = period) → switch date filter to "Last 30 Days" → values refresh. Switch tabs (By Season → By Month → By Shop) → tables update. All numbers shown match what the web shows for the same filters.

**Acceptance Scenarios**:

1. **Given** the user has `sales.view` permission and selects Sales Analytics from home, **When** the page loads, **Then** they see the same 8 Period KPI cards and 4 All-Time KPI cards as the web with identical metric values, formatted identically (numbers, %, VND).
2. **Given** the user changes the date range filter to a custom period, **When** they tap Apply, **Then** all KPIs and the active tab refresh with the period-scoped data within 4 seconds.
3. **Given** the user switches between breakdown tabs (Season / Month / Week / Shop / Grade), **When** they tap a tab, **Then** the corresponding table loads and is fully scrollable (vertical and horizontal) with sticky header row.
4. **Given** the user is on a phone in portrait orientation, **When** a table has more columns than fit the screen, **Then** the table allows horizontal scroll while keeping the first column (label) sticky on the left.
5. **Given** the user pulls down on the page, **When** the pull-to-refresh gesture completes, **Then** data is re-fetched from the server.

---

### User Story 4 - View Customer Analytics on Mobile (Priority: P2)

User opens Customer Analytics, sees POS vs CNV comparison KPIs (orange tint for All-Time, blue tint for Period), Registration Breakdown tabs, and Customer Comparison breakdown tabs with the same data structure as the web.

**Why this priority**: Important secondary workflow — used by managers tracking loyalty program adoption. Depends on the same patterns established by Sales Analytics so it can ship soon after.

**Independent Test**: Sign in → tap Customer Analytics → see the 8 KPI cards → switch between Registration Breakdown and Customer Comparison sections → switch tabs within each section → numbers match web for same date filter.

**Acceptance Scenarios**:

1. **Given** a user with `cnv.view` permission, **When** they open Customer Analytics, **Then** the same KPI cards (Total Customers POS, Total CNV Customers, POS Only, CNV Only, plus 4 period equivalents) appear with identical layout and tints as the web version.
2. **Given** the user selects a date range, **When** they apply the filter, **Then** the period KPI section and all comparison tables refresh with period-scoped data.

---

### User Story 5 - View Coupon Analytics on Mobile (Priority: P2)

User opens Coupon Analytics, sees Used/Unused coupon stats and Coupon Amount data with the same uniform card style (no green/red tinted cards — orange for all-time, blue for period). By Shop and Detail tables are scrollable.

**Why this priority**: Same priority tier as Customer Analytics — operational data that supports campaign decisions but is not the core workflow.

**Independent Test**: Sign in → Coupon Analytics → see all stat cards in uniform style → switch By Shop / Detail / Duplicates tabs → tables render with sticky headers and horizontal scroll.

**Acceptance Scenarios**:

1. **Given** a user with `coupons.view` permission opens Coupon Analytics, **When** the page loads, **Then** stat cards use the same orange-tint (all-time) and blue-tint (period) style as Sales/Customer pages — no green/red/yellow cards.
2. **Given** the user filters by Coupon ID Prefix or Campaign, **When** they apply, **Then** the by-shop breakdown updates to reflect the filter.

---

### User Story 6 - View Shop Detail and Customer Detail (Priority: P2)

User opens Shop Detail to drill into a single shop's sales/customer/coupon stats with date filters. User opens Customer Detail to look up an individual customer by VIP ID or phone and see their purchase history + CNV sync status.

**Why this priority**: Detail/lookup pages are common but used by fewer users than aggregate dashboards. They depend on patterns established by the dashboards.

**Independent Test**: Sign in → Shop Detail → pick a shop from dropdown → load → 3 sections appear (Sales / Customer / Coupon by Shop). Customer Detail → enter a VIP ID → customer profile loads with invoice history table.

**Acceptance Scenarios**:

1. **Given** the user opens Shop Detail and selects a shop, **When** they tap Load, **Then** the 3 section cards (Sales Analytics by Shop, Customer Analytics by Shop, Coupon Analytics by Shop) appear with uniform blue top borders and dark-blue section headers.
2. **Given** the user opens Customer Detail and searches by VIP ID, **When** the lookup returns a result, **Then** the customer info, statistics, and invoice history table are displayed.

---

### User Story 7 - View Charts on Mobile (Priority: P3)

User opens Sales Analytics Charts, Customer Charts, or Coupon Analytics Charts. Donut charts and trend charts render at a phone-appropriate size, are touch-interactive (tap a slice or data point to highlight the corresponding row in the data table below), and the underlying tables remain scrollable.

**Why this priority**: Charts are valuable for visual storytelling but consumption-only — users primarily make decisions from the dashboard tables. Implementing chart pages last keeps the MVP tight.

**Independent Test**: Sign in → Sales Analytics Charts → see 8 donut cards in a 2x4 grid → tap a donut → highlights related row. Switch to trend chart → see line chart → toggle shop visibility from the legend.

**Acceptance Scenarios**:

1. **Given** the user opens any of the 3 chart pages, **When** the page loads, **Then** donut and trend charts render correctly at phone-appropriate dimensions and use the same color palette as the web charts.
2. **Given** the user taps a donut slice or trend data point, **When** the tap registers, **Then** the corresponding row in the data table below highlights and scrolls into view.

---

### Edge Cases

- **Offline / no network**: All data pages show a clear "no connection" message with a retry button. The login screen disables the Sign In button when offline. The app does not crash.
- **Server unreachable / 5xx error**: Retry-able views show an error banner with retry button. The user remains signed in (token not invalidated).
- **Token expired mid-session**: Any data request that returns 401 triggers a transparent redirect to the login screen with "session expired" notice; the page they were on is preserved as the post-login destination.
- **Large data response (By Shop table up to 200 rows)**: Maximum expected table size is ≤200 rows (50–150 shops in practice). Standard ScrollView with sticky header is sufficient — full row virtualization is not required. The page must remain responsive at ≥50fps scroll on a mid-tier device with 200 rows rendered.
- **Permission revoked while user is signed in**: When the user navigates to a card whose permission was just removed server-side, the server returns 403 and the app shows "you don't have access to this page" without crashing.
- **App backgrounded for long time**: When user returns, the app checks the JWT access token expiry. If expired but refresh token is still valid, the app silently exchanges it for a new access token before refreshing the page. If both are expired, the user is routed to login with a "session expired" notice. State of the current page is preserved as the post-login destination.
- **Concurrent 401 responses**: If multiple in-flight API requests all receive 401 simultaneously (e.g. user opens a page that fires 3 parallel requests), the app MUST trigger only a single token-refresh attempt and queue the other retries behind it. Parallel refresh attempts against the same refresh token will result in token invalidation on most backends — the refresh must be serialized.
- **Different device sizes / orientations**: Layout adapts from 320pt-wide phones up through tablet sizes; landscape orientation works on tablets, portrait on phones; rotation does not lose state.
- **Visual consistency check on every UI change**: A visual snapshot mechanism captures rendered screens (per-page) so reviewers can verify the mobile UI matches the web concept and does not break layout. Snapshots regenerate after every UI change.
- **Locale & VND formatting**: All currency values render in VND with Vietnamese-style grouping (e.g. "1,234,567,890 VND") matching what the web shows.
- **Self-signed / dev server certificates**: In production builds, only certificates signed by trusted authorities are accepted (no MITM via self-signed certs).

## Requirements *(mandatory)*

### Functional Requirements

#### Authentication & Session

- **FR-001**: The app MUST authenticate users against the existing SemirDashboard backend using the same credential scheme (username + password) used on the web.
- **FR-002**: The app MUST store both the JWT access token and the refresh token in the device's secure storage (Keychain on iOS, encrypted Keystore-backed storage on Android) — never in plain files, plain preferences, or local DB.
- **FR-003**: The app MUST attach the JWT access token to every backend request via the `Authorization: Bearer <token>` header. When a request receives a 401 response, the app MUST silently attempt to exchange the stored refresh token for a new access token via the token-refresh endpoint. If the refresh succeeds, the original request MUST be retried automatically. If the refresh fails (refresh token expired or revoked), the app MUST route the user to the login screen with a "session expired" notice.
- **FR-004**: The app MUST support a Sign Out action that wipes both the JWT access token and refresh token, plus any cached user-identifying data, from the device's secure storage.
- **FR-005**: The app MUST offer optional biometric unlock (Face ID / Touch ID / Android biometric) as a device-level gate on accessing the secure storage that holds the refresh token. Biometric authentication does NOT involve the backend — it gates whether the OS releases the stored refresh token to the app. When the user enables biometric during onboarding, subsequent cold launches require a successful biometric prompt before the app attempts token refresh. Biometric failure or cancellation returns the user to the login screen.
- **FR-006**: The app MUST never log credentials, tokens, or personally identifiable customer data (phones, VIP IDs, invoice numbers) to device logs or crash reports.
- **FR-007**: The app MUST display a clear, generic error message on failed login that does not reveal whether it was the username or password that was wrong.

#### Permissions & Access Control

- **FR-008**: The app MUST respect the same role-based permission system as SemirDashboard — feature cards on home and routes within the app MUST be hidden or blocked based on the signed-in user's permissions.
- **FR-009**: The app MUST treat any 403 server response as a permission denial and show the user a friendly "no access" message rather than crashing or looping.

#### Home Page & Navigation

- **FR-010**: The app MUST display a home page after login containing a section group header "Analytics & Reports" and the 8 feature cards gated by the following permissions: Sales Analytics (`sales.view`), Sales Analytics Charts (`sales.view`), Customer Analytics (`cnv.view`), Customer Charts (`cnv.view`), Coupon Analytics (`coupons.view`), Coupon Analytics Charts (`coupons.view`), Shop Detail (`shop_detail.view`), Customer Detail (`customer_detail.view`). The auth response MUST include the user's full permission set so the app can evaluate all gates client-side without additional requests.
- **FR-011**: Each home card MUST display the same icon, title, and description as the corresponding web card.
- **FR-012**: The app MUST hide cards the user does not have permission for and reflow the layout cleanly with no empty slots.
- **FR-013**: The app MUST provide a primary navigation mechanism (back button, drawer, or tab bar) to return to home from any analytics page.

#### Analytics Pages — Data & Layout Parity

- **FR-014**: For each analytics page implemented, the displayed numeric values MUST match the web equivalent for the same filter inputs (same period, same shop group, same prefix, etc.).
- **FR-015**: All analytics pages MUST support the same date-range filter (start date, end date, quick presets like Last 7/30/90 Days, Last/This Month, Last/This Year, fixed years) used on the web.
- **FR-016**: All analytics pages MUST support the same shop-group filter used on the web (where applicable).
- **FR-017**: KPI / stat cards MUST follow the established UI rule: All-Time = orange tint background, Period = blue tint background, all text in dark/black on light background.
- **FR-018**: All section card-headers MUST use the primary brand blue (the same blue used for the web's `--primary` token, hex `#0d6efd` or the nearest platform design-token equivalent) as a solid background with white text — no tinted/semi-transparent headers, no per-section accent colors.
- **FR-019**: Tabs (Registration Breakdown, Customer Comparison, etc.) MUST follow the dark-tabs pattern when placed on a dark container background: inactive tabs are white with reduced opacity (~30%), active tab has a white background with dark (nav-blue) text.
- **FR-020**: Data tables MUST preserve their column structure on small screens via horizontal scroll with a sticky first column (the label/key column) — never reflow columns into a stacked layout that breaks the data shape.
- **FR-021**: Tables MUST use the primary brand blue (`#0d6efd` equivalent) as a solid background with white text for all column headers — no per-column accent colors.
- **FR-022**: All currency values MUST render in VND with thousands grouping matching the web format.
- **FR-023**: All cards on Home and section cards on Shop Detail MUST have a uniform blue top-border accent (4pt blue line at the top).

#### Data Refresh & Performance

- **FR-024**: Each analytics page MUST support pull-to-refresh to re-fetch data from the server.
- **FR-025**: The app MUST display a loading indicator while fetching data and MUST never leave the user staring at an empty screen for more than 1 second without feedback.
- **FR-026**: The app MUST cache the last successfully loaded data per page so that switching between pages and returning shows the previous data immediately while a refresh runs in the background.

#### Cross-Platform & Distribution

- **FR-027**: The app MUST run on iOS 14+ and Android 8 (API 26)+ from a single shared codebase to keep iOS and Android UI/behavior in lock-step.
- **FR-028**: The app MUST be packaged for distribution to Apple App Store and Google Play Store, including the privacy nutrition label, store listing, and screenshots (rendered from real screens).
- **FR-029**: The app MUST point at the production SemirDashboard backend URL by default in release builds, and a separate dev/staging URL in debug/internal builds — never mix.

#### Network Security

- **FR-030**: The app MUST communicate with the backend over HTTPS only — plain HTTP requests MUST be blocked by platform configuration (App Transport Security on iOS, network security config on Android).
- **FR-031**: The app SHOULD pin or validate the backend's TLS certificate against an expected issuer chain to mitigate MITM attacks via rogue CAs. The implementation MUST pin the CA/intermediate certificate (not the leaf cert) and include a backup pin, so that routine annual certificate renewal on the backend does not require an emergency app update.

#### Visual Render & Review Mechanism

- **FR-032**: The project MUST provide a visual snapshot mechanism that renders each app screen with realistic sample data and captures it as an image (PNG) for human review and visual regression detection. The exact technical approach (simulator screenshot, golden-file test, component-isolation render) is determined by the chosen framework during planning — the output must be a viewable PNG per page.
- **FR-033**: The visual snapshot mechanism MUST be triggerable by a single command (e.g. `make snapshot`) and snapshots MUST be stored under `render/` with one PNG per screen label, regenerated after every UI change. A senior QA review of the generated PNGs is required before any UI task is marked done.
- **FR-034**: The reviewer MUST be able to compare the mobile snapshot for any page side-by-side with the web `render/png/` snapshot for the same page to confirm concept parity (same blocks, same colors, same data shape, no broken layout).

#### Prompt History Note

- **FR-035**: The project MUST maintain a note file inside the project that records the history of user prompts driving the project, in the order they were given, with a timestamp per entry.

#### Testing & Quality

- **FR-036**: The project MUST include automated tests covering the login flow (valid + invalid credentials, biometric opt-in), the home permission filtering, and at least one analytics page's data fetching + rendering.
- **FR-037**: The project MUST include a CI-runnable smoke test that launches each implemented page with a mocked backend response and asserts no crashes and that the visual snapshot is generated.
- **FR-046**: The app MUST integrate a lightweight crash reporting SDK (Sentry free tier or Firebase Crashlytics) in release builds. The SDK MUST capture uncaught exceptions and report crash-free session rate. Crash reports MUST NOT include authentication tokens, customer phone numbers, VIP IDs, or invoice numbers — PII scrubbing rules must be configured before the SDK is enabled.

#### Build Environment & Developer Onboarding

- **FR-038**: The project MUST include a `README.md` that covers, in order: (1) prerequisite tools and exact versions required (e.g. Flutter/Node, Xcode, Android Studio, JDK), (2) first-time environment setup steps, (3) running the app on iOS simulator and Android emulator, (4) running all tests and generating snapshots, (5) building a release IPA and AAB, (6) a reference to `DEPLOYMENT.md` for store submission. A developer with zero prior context MUST be able to follow this document to a running simulator within 2 hours on a clean machine.
- **FR-039**: The project MUST include a task-runner file (Makefile or equivalent) exposing named targets: `run-ios`, `run-android`, `test`, `snapshot`, `build-ios`, `build-android`. Each target must be a single command with no manual steps inside.

#### App Identity & Store Assets

- **FR-040**: The project MUST include a production-ready app icon (1024×1024 px, no alpha channel for iOS; adaptive foreground + background layers for Android) and a splash/launch screen that displays while the app initialises. Both are required by App Store and Play Store review.
- **FR-041**: The project MUST include a `store-assets/` folder containing: app name, subtitle (iOS) / short description (Android), full store description, keyword list, and at least 3 screenshots per required device size. Screenshots must be rendered from the running app on a simulator or emulator at the required resolution — iPhone 6.7" (1290×2796 pt) and iPhone 5.5" (1242×2208 pt) for iOS; 1080×1920 or 1080×2340 for Android. These are distinct from the `render/` QA snapshots (which are for regression testing) — store screenshots must match store dimension requirements exactly.
- **FR-042**: The app MUST reference a hosted privacy policy URL in both the App Store listing and the in-app settings/about screen. The privacy policy must be live before first submission — both stores reject submissions without it.

#### Code Signing & Release Pipeline

- **FR-043**: iOS release builds MUST be signed with a Distribution certificate and a matching App Store provisioning profile linked to the correct Bundle ID. The `DEPLOYMENT.md` guide MUST document how to obtain, install, and rotate these credentials without re-submitting the app.
- **FR-044**: Android release builds MUST be signed with a keystore file. The keystore password, key alias, and key password MUST be stored as environment variables (never committed to version control). `DEPLOYMENT.md` MUST document keystore creation, backup, and the consequence of losing the key (cannot update the app on Play Store).
- **FR-045**: The project MUST include a `DEPLOYMENT.md` file covering the complete end-to-end process: (1) Apple Developer account setup and certificate issuance, (2) App Store Connect app record creation (Bundle ID, app name, pricing, distribution), (3) building and uploading an IPA via Xcode / CLI, (4) TestFlight internal testing before public submission, (5) App Store review submission checklist, (6) Google Play Console app creation (package name, release track), (7) building a signed AAB, (8) uploading to Internal Testing track, (9) promoting to Production, (10) how to submit updates for both stores after the initial launch.

### Key Entities

- **User Session**: Represents an authenticated user. Attributes: username, role, permission set, JWT access token (short-lived, 15min–1h), refresh token (long-lived, 7–30 days), access token expiry timestamp. Both tokens stored in device secure storage. Cleared on Sign Out or refresh token rejection.
- **Permission**: Single string identifier from the set `{sales.view, cnv.view, coupons.view, shop_detail.view, customer_detail.view}` — same vocabulary used by SemirDashboard. Returned in the JWT auth response as a list. Determines which home cards and routes are accessible. Charts share the gate of their data page (no separate permission).
- **Date-Range Filter**: Pair of start/end dates plus optional quick-preset selection. Applied to all analytics pages.
- **Shop Group Filter**: Optional shop-group key. Applied where supported (Sales, Coupon).
- **Analytics Page Data**: A typed payload per page — KPI scalars, breakdown tables (rows × columns), tab variants. Returned by the backend as JSON; displayed by the corresponding page.
- **Snapshot Artifact**: A PNG image of a rendered page captured by the visual snapshot mechanism, stored under `render/` with a per-page label and saved alongside an HTML/JSON dump of the data used for the render.
- **Prompt History Entry**: Ordered record of `{timestamp, prompt_text}` appended to the project's prompt-history note file each time the user issues a prompt that drives the project.
- **Build Configuration**: The set of environment-specific values (API base URL, TLS pin hash, log level, feature flags) that distinguish debug, staging, and production builds. Stored as environment variables or build-flavor config files — never hardcoded in source and never committed in plain text.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: From a cold app launch (session already valid), the home page renders within 3 seconds and the user reaches any analytics page within 1 additional second of tapping its card — verified on a mid-tier Android device (Snapdragon 6xx class or equivalent) with a Wi-Fi connection.
- **SC-002**: ≥95% of analytics page data loads complete and render within 4 seconds on a throttled network simulating 10 Mbps download / 5 Mbps upload (representative of median 4G speed in urban Vietnam) — measured in integration tests using network throttling.
- **SC-003**: For any (page, date-range, shop-group) input, the mobile display of KPI values MUST match the web display when both are given the same backend API response payload — verified by unit/integration tests that feed identical fixture JSON to both the mobile and web rendering layers and assert identical formatted output. Live server cache timing differences are explicitly excluded from this criterion.
- **SC-004**: The app passes Apple App Store and Google Play review on first submission with no security or policy rejections.
- **SC-005**: Visual snapshot regression catches ≥90% of unintended UI changes — measured by injecting deliberate UI breakages during QA and confirming the snapshot diff flags them.
- **SC-006**: Crash-free session rate ≥99.5% in the first 30 days post-launch — measured via the integrated crash reporting SDK (Sentry or Firebase Crashlytics) dashboard, not store-reported metrics.
- **SC-007**: Data tables on screens as narrow as 320pt remain fully readable (no truncation, no broken column alignment) and scroll horizontally with sticky first column at ≥50fps with up to 200 rows rendered (the maximum expected table size).
- **SC-008**: Authentication tokens are never present in any device log, crash report, or analytics event — verified by automated log-scrubbing test.
- **SC-009**: A user whose role lacks a permission cannot reach the corresponding page via back-button manipulation or direct navigator state injection. Deep links are not supported in v1 — the navigator's auth guard is the sole enforcement mechanism.
- **SC-010**: A new developer with the required tools already installed can follow the README from first checkout to a running simulator, passing test suite, and generated snapshots within 2 hours — verified by having a team member who was not involved in setup follow the README cold.

## Assumptions

- The existing SemirDashboard backend already exposes (or will be extended to expose) JSON endpoints for each analytics page; this project consumes those endpoints rather than reimplementing analytics on the device.
- The backend supports a token-based authentication endpoint that returns a token and the signed-in user's permission set; the same role/permission vocabulary used by the web is reused on mobile.
- The same business rules locked in SemirDashboard (return-visit formula, season labels M2-4 / M5-7 / M8-10 / M11-1, grade hierarchy No Grade < Member < Silver < Gold < Diamond, VIP ID = "0" exclusion) are computed server-side and the app simply displays the results — the app does not re-implement these rules.
- The mobile app initially supports the same languages/locales as the web app (English UI labels, Vietnamese formatted currency).
- Push notifications, offline editing, and write/upload features (uploading customers/sales/coupons, managing campaigns, triggering CNV sync) are explicitly OUT OF SCOPE for v1 — the mobile app is read-only for analytics. Upload and admin functions remain web-only.
- The app uses a single shared codebase for iOS and Android (cross-platform UI framework) — exact framework choice is a planning-phase decision, not a spec-phase decision.
- Visual snapshots are generated using the chosen framework's native testing/screenshot tooling (e.g. Flutter golden tests on a simulator, or Detox screenshots via emulator). The mechanism differs from the web's Chrome-headless approach but produces equivalent per-page PNG output.
- The user has stable enough connectivity to hit the backend on demand; offline-first sync is not required.
- The backend production URL and TLS certificate chain are stable. TLS certificate pinning will target the CA/intermediate issuer certificate (not the leaf) with a backup pin embedded, so annual certificate renewal on the backend does not break existing app installs.
- A hosted privacy policy URL will be available before first store submission. Both App Store and Google Play require this URL at review time.
- The Apple Developer Program and Google Play Developer accounts are already registered or will be registered before the build/submission phase.

## Dependencies

- **[HARD BLOCKER — Sprint 0] SemirDashboard JSON API layer**: The existing SemirDashboard backend serves analytics via Django template views that return HTML pages — not JSON. A JSON API layer must be designed, built, and deployed on the backend before any mobile data-fetching code can be written or tested against a real server. This is the single largest risk to the project timeline and must be the first deliverable in Sprint 0. The API contract (endpoints, request params, response shapes for all 8 analytics pages + auth + permissions) must be defined and agreed upon before mobile development starts.
- **Existing SemirDashboard backend** (https://analytics-customer-dashboard.com): once the JSON API is live, provides authentication, permission resolution, and all analytics data. Must remain available at app runtime.
- **Apple Developer Program account** ($99/year): required for code-signing, TestFlight, and App Store submission. Must be enrolled before the build phase.
- **Google Play Developer account** ($25 one-time): required for Play Store submission and signing key registration. Must be enrolled before the build phase.
- **Hosted privacy policy URL**: both stores require a publicly accessible privacy policy URL at submission time. Must be live before submitting for review.
- **iOS Distribution Certificate + App Store Provisioning Profile**: issued through Apple Developer portal, tied to the app's Bundle ID. Required to produce a signed IPA for App Store.
- **Android release keystore**: generated once, backed up securely. Loss of the keystore means the app can never be updated on Play Store — treat as a critical secret.

## Out of Scope (v1)

- Data upload (customers, sales, coupons)
- Campaign management
- User management / admin features
- Manual CNV sync triggering
- Push notifications
- Offline data editing / offline-first sync
- Excel/PDF export from the device
- Web-only debug pages (admin logs, sync status detail)
- In-app update / force-update mechanism (v2)
- In-app analytics / user behaviour tracking SDK (v2)
- Multi-language UI (English labels + VND currency is v1 scope; full i18n is v2)
- Deep links / universal links / custom URL scheme (v2)
