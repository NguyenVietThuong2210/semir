# Data Model: SemirPhone Mobile App

**Phase**: 1 — Design  
**Date**: 2026-04-25  
**Feature**: [spec.md](spec.md) | **Research**: [research.md](research.md)

All entities below exist in the **mobile app layer** (Dart). The backend computes all analytics values — the app stores and displays them. There is no local database; all persistent state is either in device secure storage (tokens) or in-memory (page cache).

---

## Entity 1: UserSession

Represents the authenticated user's identity and session tokens. Persisted in device secure storage (Keychain on iOS, EncryptedSharedPreferences on Android via `flutter_secure_storage`).

| Field | Type | Notes |
|-------|------|-------|
| `username` | `String` | Display name |
| `accessToken` | `String` | JWT, short-lived (15min–1h). Written to secure storage. |
| `refreshToken` | `String` | JWT, long-lived (7–30 days). Written to secure storage. |
| `accessTokenExpiry` | `DateTime` | UTC expiry of access token. App checks this before each request. |
| `permissions` | `List<String>` | e.g. `["sales.view", "cnv.view"]`. Returned in login response, cached in memory. |
| `biometricEnabled` | `bool` | Whether user has opted into biometric unlock. Stored in secure storage. |

**Lifecycle:**
- Created on successful login (`POST /api/v1/auth/token/`)
- `accessToken` updated on successful refresh (`POST /api/v1/auth/token/refresh/`)
- Wiped entirely on Sign Out or refresh token rejection

**Validation rules:**
- `accessToken` and `refreshToken` MUST NOT be empty strings — treat as "not authenticated"
- `accessTokenExpiry` in the past → attempt refresh before next request
- `permissions` empty list → user has no feature access (show empty home, not crash)

---

## Entity 2: Permission

A single string identifier gating access to one feature area. Evaluated client-side from the `UserSession.permissions` list.

| Permission | Guards |
|------------|--------|
| `sales.view` | Sales Analytics page + Sales Charts page |
| `cnv.view` | Customer Analytics page + Customer Charts page |
| `coupons.view` | Coupon Analytics page + Coupon Charts page |
| `shop_detail.view` | Shop Detail page |
| `customer_detail.view` | Customer Detail page |

**Rules:**
- Evaluated entirely from `UserSession.permissions` — no additional API calls needed
- If a 403 is returned by any endpoint, the corresponding page must show "no access" regardless of local permission state (server is authoritative)
- Chart pages share the gate of their data page (no separate permission string)

---

## Entity 3: BuildConfig

Environment-specific configuration. Exists as a compile-time constant object (Dart `const`), injected via `--dart-define` flags at build time. Never loaded from files or network at runtime.

| Field | Type | Debug Value | Release Value |
|-------|------|-------------|---------------|
| `apiBaseUrl` | `String` | `http://localhost:8000/api/v1` | `https://analytics-customer-dashboard.com/api/v1` |
| `tlsPinSha256` | `String` | (empty — pinning disabled in debug) | CA/intermediate cert SHA-256 |
| `tlsBackupPinSha256` | `String` | (empty) | Backup CA cert SHA-256 |
| `sentryDsn` | `String` | (empty — Sentry disabled in debug) | Sentry project DSN |
| `environment` | `String` | `"debug"` | `"production"` |

**Rules:**
- `apiBaseUrl` MUST end without `/` (all endpoint paths start with `/`)
- Pinning is only active when `tlsPinSha256` is non-empty — debug builds skip pinning
- Sentry only initializes when `sentryDsn` is non-empty

---

## Entity 4: DateRangeFilter

User-selected date range applied to all analytics pages. Held in-memory per page as Riverpod state.

| Field | Type | Notes |
|-------|------|-------|
| `dateFrom` | `DateTime?` | null = all-time (no lower bound) |
| `dateTo` | `DateTime?` | null = today |
| `preset` | `DatePreset?` | Enum: Last7Days, Last30Days, Last90Days, LastMonth, ThisMonth, LastYear, ThisYear, Year2024, Year2025 |

**Rules:**
- `dateFrom` ≤ `dateTo` always (UI enforces this)
- When a preset is selected, `dateFrom` and `dateTo` are computed from the preset — the preset field is stored for UI display only
- Passed to API as `date_from=YYYY-MM-DD&date_to=YYYY-MM-DD` query parameters

---

## Entity 5: AnalyticsPageCache

In-memory store of the last successfully loaded data for each analytics page. Enables FR-026 (show previous data while background refresh runs). Implemented as a `Map<String, AnalyticsPayload>` in a Riverpod provider; cleared on Sign Out.

| Field | Type | Notes |
|-------|------|-------|
| `pageKey` | `String` | e.g. `"sales"`, `"customer"`, `"coupon"` |
| `filter` | `DateRangeFilter` | The filter that produced this data |
| `payload` | `AnalyticsPayload` | Typed union — see below |
| `fetchedAt` | `DateTime` | For stale detection (not used in v1; prep for v2 offline) |

---

## Entity 6: SalesAnalyticsPayload

Deserialized response from `GET /api/v1/analytics/sales/`. All numeric values are pre-computed server-side.

| Field | Type | Notes |
|-------|------|-------|
| `allTimeKpis` | `SalesKpis` | 4 all-time KPI values |
| `periodKpis` | `SalesKpis` | 8 period KPI values |
| `activeTab` | `SalesTab` | Enum: BySeason, ByMonth, ByWeek, ByShop, ByGrade |
| `tabData` | `Map<SalesTab, TableData>` | One TableData per tab |

**SalesKpis fields:** `totalInvoices`, `totalRevenue`, `avgInvoice`, `totalCustomers`, `returningCustomers`, `returnRate`, `newCustomers`, `avgVisitsPerCustomer` (all `num`; formatted to VND or % in the UI layer).

**TableData:** `headers: List<String>` + `rows: List<List<String>>` — all values pre-formatted as strings by the backend (VND, %, counts). The app renders strings; it does not reformat numbers.

---

## Entity 7: CustomerAnalyticsPayload

Deserialized response from `GET /api/v1/analytics/customer/`.

| Field | Type | Notes |
|-------|------|-------|
| `allTimeKpis` | `CustomerKpis` | POS + CNV totals (all-time) |
| `periodKpis` | `CustomerKpis` | POS + CNV totals (period) |
| `registrationBreakdown` | `Map<RegTab, TableData>` | Tabs: ByShop, ByMonth, ByGrade |
| `customerComparison` | `Map<CompTab, TableData>` | Tabs: PosOnly, CnvOnly, Both |

---

## Entity 8: CouponAnalyticsPayload

Deserialized response from `GET /api/v1/analytics/coupon/`.

| Field | Type | Notes |
|-------|------|-------|
| `allTimeKpis` | `CouponKpis` | Used, Unused, Amount (all-time) |
| `periodKpis` | `CouponKpis` | Used, Unused, Amount (period) |
| `tabData` | `Map<CouponTab, TableData>` | Tabs: ByShop, Detail, Duplicates |

---

## Entity 9: ShopDetailPayload

Deserialized response from `GET /api/v1/analytics/shop-detail/`.

| Field | Type | Notes |
|-------|------|-------|
| `shopName` | `String` | Selected shop display name |
| `salesSection` | `ShopSalesData` | KPIs (all-time + period) + by_session + by_month + by_week |
| `customerSection` | `ShopCustomerData` | CNV breakdown for this shop |
| `couponSection` | `ShopCouponData` | Coupon stats for this shop |

---

## Entity 10: CustomerDetailPayload

Deserialized response from `GET /api/v1/analytics/customer-detail/`.

| Field | Type | Notes |
|-------|------|-------|
| `vipId` | `String` | Customer VIP ID |
| `phone` | `String` | Phone number (masked for display, e.g. `"09x-xxx-xx89"`) |
| `grade` | `String` | No Grade / Member / Silver / Gold / Diamond |
| `registrationStore` | `String` | Shop name |
| `registrationDate` | `String` | ISO date |
| `totalInvoices` | `int` | |
| `totalRevenue` | `String` | Pre-formatted VND |
| `cnvSyncStatus` | `String?` | "synced" / "not_synced" / null |
| `invoiceHistory` | `List<InvoiceRow>` | Recent invoices |

**Note on PII display:** Phone numbers must be masked in the UI (middle digits replaced with `x`). VIP IDs are internal codes — not personal data by Vietnamese PDPA definition, but invoice history tied to a VIP ID is sensitive. FR-006 prohibits logging any of this.

---

## Entity 11: ChartPayload

Deserialized response from `GET /api/v1/charts/{sales|customer|coupon}/`.

| Field | Type | Notes |
|-------|------|-------|
| `donuts` | `List<DonutData>` | One per donut card (up to 8 for sales charts) |
| `trend` | `TrendData?` | Line chart data; null if page has no trend chart |

**DonutData:** `title: String`, `slices: List<{label, value, color}>`.  
**TrendData:** `series: List<{shopName, dataPoints: List<{date, value}>}>`.  
Colors in chart payloads are hex strings — the backend controls the palette to match the web.

---

## Entity 12: SnapshotArtifact

Output of the `make snapshot` command (FR-032/033). Not a runtime entity — exists on the filesystem only.

| Field | Value |
|-------|-------|
| Location | `render/` directory (`.gitignore`d except `render/README.md`) |
| Naming | `<screen_label>.png` e.g. `login.png`, `home.png`, `sales_analytics.png` |
| Source | Flutter golden test runner (`flutter test --update-goldens`) |
| Format | PNG, rendered at 390×844pt (iPhone 14 Pro logical resolution) |
| QA gate | Senior QA must open and visually review each PNG before marking a UI task done |

---

## State Transitions: UserSession

```
[Not Authenticated]
      │
      │ login success (POST /api/v1/auth/token/)
      ▼
[Authenticated]
      │                            │
      │ 401 → refresh fails        │ Sign Out
      │ (or refresh token expired) │ (DELETE tokens)
      ▼                            ▼
[Session Expired]          [Not Authenticated]
      │
      │ User re-logs in
      ▼
[Authenticated]
```

**Biometric gate (when enabled):**
```
[App Launched] → [Biometric Prompt]
                        │                    │
                  success                  failure/cancel
                        │                    │
               [Authenticated]        [Not Authenticated]
               (uses stored           (clears app state,
                refresh token)         shows login)
```
