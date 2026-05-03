# Mobile App Audit Report — SemirPhone

**Date:** 2026-05-03  
**Auditor:** Senior Engineer review  
**App version branch:** release/2.0.0  
**Flutter analyze:** 0 errors, 40 info hints (pre-existing const lint)

---

## 1. Page Coverage — Home Navigation

The home page shows **8 permission-gated navigation cards**. There are **8 total navigable feature screens** in the app (excluding Login and Home):

| # | Screen | Route | Accessible From |
|---|--------|-------|-----------------|
| 1 | Sales Analytics | `/sales` | Home card |
| 2 | Sales Charts | `/sales/charts` | Home card **+ Sales AppBar chart icon** |
| 3 | Customers (CNV) | `/customer` | Home card |
| 4 | Customer Charts | `/customer/charts` | Home card **+ Customer AppBar chart icon** |
| 5 | Coupon Analytics | `/coupon` | Home card |
| 6 | Coupon Charts | `/coupon/charts` | Home card **+ Coupon AppBar chart icon** |
| 7 | Store Detail | `/shop-detail` | Home card |
| 8 | Customer Lookup | `/customer-detail` | Home card |

**Verdict: ✅ All 8 feature screens are accessible.**  
- Home now shows **8 cards** (5 primary + 3 chart shortcuts).  
- Chart pages are also reachable via the `bar_chart` icon in each analytics page AppBar (dual entry point).

> **Fix applied (2026-05-03):** Chart pages were previously registered in GoRouter but had zero UI entry points. Added (1) 3 chart cards to `home_page.dart` and (2) chart icon `IconButton` to AppBar of `sales_page.dart`, `customer_page.dart`, `coupon_page.dart`.

**Permission gates (correct):**

| Card | Permission Required |
|------|---------------------|
| Sales | `sales.view` |
| Customers | `customers.view` |
| Coupon | `coupons.view` |
| Store Detail | `shop_detail.view` |
| Customer Lookup | `customer_detail.view` |
| Sales Charts | `sales.view` |
| Customer Charts | `customers.view` |
| Coupon Charts | `coupons.view` |

---

## 2. Data Completeness — API → UI Mapping

All 5 analytics pages map the full API response to the UI. Verification done by reading service files against Django API response schemas.

### Sales Analytics (`/api/v1/analytics/sales/`)

| API Field | Displayed | Notes |
|-----------|-----------|-------|
| `all_time_kpis` | ✅ | 4 cards: Total Customers, Member Active/Inactive, Return Rate |
| `period_kpis` | ✅ | 10 metrics: New Members, Returning, Active, Return Rate, INV/AMT(RET/CUS), Total |
| `tabs.by_grade` | ✅ | Loaded in initial payload, shown in tab 0 |
| `tabs.by_season` | ✅ | Lazy-loaded on tab selection |
| `tabs.by_month` | ✅ | Lazy-loaded on tab selection |
| `tabs.by_week` | ✅ | Lazy-loaded on tab selection |
| `tabs.by_shop` | ✅ | Lazy-loaded on tab selection |
| `allshops_tabs` | ✅ | Shown as comparison section when shop_group filter is active |

### Customer Analytics — CNV (`/api/v1/analytics/customer/`)

| API Field | Displayed | Notes |
|-----------|-----------|-------|
| `all_time_kpis` | ✅ | 4 cards: Total POS/CNV, POS Only, CNV Only |
| `period_kpis` | ✅ | 4 cards: New POS/CNV, Synced, Active |
| `registration_breakdown.by_shop` | ✅ | Tab "By Store" |
| `registration_breakdown.by_season` | ✅ | Tab "By Season" |
| `registration_breakdown.by_month` | ✅ | Tab "By Month" |
| `registration_breakdown.by_week` | ✅ | Tab "By Week" |
| `registration_breakdown.by_grade` | ✅ | Tab "By Grade" |
| `customer_comparison.pos_only` | ✅ | Tab "POS Only" |
| `customer_comparison.cnv_only` | ✅ | Tab "CNV Only" |
| `customer_comparison.both` | ✅ | Tab "Both" |
| `customer_comparison.zalo` | ✅ | Tab "Zalo" |

### Coupon Analytics (`/api/v1/analytics/coupon/`)

| API Field | Displayed | Notes |
|-----------|-----------|-------|
| `all_time_kpis` | ✅ | 6 cards: Total, Used, Unused, Total/Coupon/Unique Amt |
| `period_kpis` | ✅ | 6 cards: same structure for period |
| `tabs.by_shop` | ✅ | Loaded in initial payload (default tab) |
| `tabs.detail` | ✅ | Lazy-loaded on tab selection |
| `tabs.duplicates` | ✅ | Lazy-loaded on tab selection |
| Prefix filter | ✅ | TextField sends `?prefix=` param |

### Store Detail (`/api/v1/analytics/shop-detail/`)

| API Field | Displayed | Notes |
|-----------|-----------|-------|
| `sales.all_time_kpis` | ✅ | 7 KPI cards |
| `sales.period_kpis` | ✅ | 7 KPI cards |
| `sales.by_session` | ✅ | Season breakdown table |
| `sales.by_month` | ✅ | Month breakdown table |
| `sales.by_week` | ✅ | Week breakdown table |
| `customer.all_time_kpis` | ✅ | Lazy-loaded, 7 KPI cards |
| `customer.period_kpis` | ✅ | Lazy-loaded |
| `customer.by_season` | ✅ | Tab in customer section |
| `customer.by_month` | ✅ | Tab in customer section |
| `customer.by_week` | ✅ | Tab in customer section |
| `customer.zalo_active` | ✅ | Zalo Active list (shown if rows not empty) |
| `coupon.all_time_kpis` | ✅ | Lazy-loaded, 6 KPI cards |
| `coupon.period_kpis` | ✅ | Lazy-loaded |
| `coupon.detail_table` | ✅ | Coupon detail table |

### Customer Lookup (`/api/v1/analytics/customer-detail/`)

| API Field | Displayed | Notes |
|-----------|-----------|-------|
| `name` | ✅ | Profile card title |
| `phone` | ✅ | Masked display (PII: `09x-xxx-x567`) |
| `vip_id` | ✅ | Profile card |
| `grade` | ✅ | Badge: No Grade / Member / Silver / Gold / Diamond |
| `registration_store` | ✅ | Profile card (optional) |
| `registration_date` | ✅ | Profile card (optional) |
| `email` | ✅ | Profile card with icon (optional) |
| `cnv_sync_status` | ✅ | Sync badge: Synced / Not Synced |
| `total_invoices` | ✅ | KPI card |
| `total_revenue` | ✅ | KPI card (VND formatted) |
| `invoice_history[].date` | ✅ | Table column "Date" |
| `invoice_history[].shop` | ✅ | Table column "Shop" |
| `invoice_history[].invoice_id` | ✅ | Table column "Invoice" |
| `invoice_history[].amount` | ✅ | Table column "Amount" |
| `invoice_history[].coupon_used` | ℹ️ | API always returns `''` (include_coupons=False for speed) — column hidden intentionally |

**Overall data completeness: ✅ 100% of meaningful API fields displayed.**

---

## 3. Performance & Lazy Loading

### Lazy Loading Strategy (per page)

| Page | Strategy | Details |
|------|----------|---------|
| **Sales Analytics** | ✅ Tab-level lazy load | Tab 0 (by_grade) in initial payload; tabs 1-4 load on first selection via `FutureProvider.family` |
| **Customer Analytics** | ✅ Single-load (correct) | API returns all 9 tabs in one response — no tab param supported; Flutter loads once and caches via Riverpod |
| **Coupon Analytics** | ✅ Tab-level lazy load | Tab 0 (by_shop) in initial payload; Detail + Duplicates lazy on selection |
| **Store Detail** | ✅ Section-level lazy load | Sales section on initial load; Customer + Coupon sections lazy via `FutureProvider.family` on tab selection |
| **Customer Lookup** | ✅ Search-driven load | No data until user submits — prevents unnecessary API calls |

### Server-Side Response Times (measured in Django test suite against 431k-row fixture)

These are **pure server compute times** — no network, no Flutter rendering overhead. Mobile E2E times (on device with network) will be higher.

| Endpoint | All-Time | Period (2025) | Under 5s? |
|----------|----------|---------------|-----------|
| Sales Analytics initial load | 1.12s | — | ✅ |
| Sales Analytics (all-time KPIs) | 1.00s | 1.97s | ✅ |
| Sales by_season tab | 1.79s | — | ✅ |
| Sales by_month tab | — | 2.50s | ✅ |
| Sales by_shop tab | 1.49s | — | ✅ |
| Customer Analytics (CNV) | 0.38s | — | ✅ |
| CNV customer KPIs (all-time) | **4.53s** | 3.40s | ✅ (borderline) |
| CNV breakdown by_shop | 0.37s | — | ✅ |
| CNV breakdown by_month | — | 0.53s | ✅ |
| Coupon Analytics initial load | 0.26s | — | ✅ |
| Shop Detail initial load | 0.26s | — | ✅ |
| Shop Detail sales (all-time) | 0.28s | 0.33s | ✅ |
| Shop Detail coupon (all-time) | 0.85s | 0.57s | ✅ |
| Customer Detail lookup | 0.01s | — | ✅ |
| Shop list dropdown | 0.00s | — | ✅ |

**All endpoints respond under 5 seconds server-side.** CNV all-time customer KPIs at 4.53s is the slowest — it aggregates cross-system POS+CNV data across 431k rows. Within acceptable limit; flagged for future optimization if data grows.

> Flutter integration tests use 8–10s timeouts to account for device boot, login, navigation, and network latency on top of server time.

### HTTP Layer
- **Client:** Dio 5.4.0 with 10s connect / 30s receive timeouts
- **Auth:** JWT Bearer injection + silent refresh on 401 (serial, prevents N-refresh race)
- **TLS:** Certificate pinning active in release builds (`BuildConfig.tlsPin`)
- **Caching:** Riverpod state cache per filter combination — same params = no duplicate HTTP request within session

### Known Limitations

| Gap | Impact | Severity |
|-----|--------|----------|
| No virtual scrolling for tables with 100+ rows | Mild jank on old devices | Medium |
| No request debouncing on filter changes | Not applicable — uses calendar picker (discrete events) | Low |
| No offline/local cache (cold start always hits API) | Requires network on every launch | Medium |
| No pagination — all table rows fetched at once | Backend API handles data volumes; acceptable for current scale | Low |

---

## 4. Integration Test Coverage

### Before This Audit

| File | Tests | Coverage |
|------|-------|---------|
| `login_flow_test.dart` | 4 tests | Login, session restore, logout, wrong password |
| `home_permissions_test.dart` | 3 tests | Full permissions, single perm card, no-access tap |
| `sales_analytics_test.dart` | 4 tests | KPI cards visible, load time, date filter, tab switch |

**Gap: 5 pages had NO integration tests.**

### After This Audit — Added Tests

| File | Tests | Coverage |
|------|-------|---------|
| `customer_analytics_test.dart` | **9 tests** | Page visible, KPI cards, load time ≤10s, all 5 breakdown tabs render, all 4 comparison tabs, tab switch, date filter, pull-to-refresh, back navigation |
| `coupon_analytics_test.dart` | **9 tests** | Page visible, KPI cards, load time ≤10s, by_shop default tab, Detail lazy tab, Duplicates lazy tab, all 3 tabs render, prefix filter field, pull-to-refresh, back navigation |
| `shop_detail_test.dart` | **10 tests** | Page visible, sales section loads, KPI cards, load time ≤10s, breakdown tables render, Customer section lazy loads, Coupon section lazy loads, customer tab cycle, sales tab render, all-time/period KPIs, back navigation |
| `customer_detail_test.dart` | **10 tests** | Page visible, search form has fields, empty search no-crash, invalid VIP ID no-crash, valid VIP ID returns profile (requires `TEST_VIP_ID`), grade shown, invoice table renders, column headers correct, phone masked, CNV sync badge, load time ≤8s, back navigation |

### Total Integration Test Coverage After Audit

| Area | Before | After |
|------|--------|-------|
| Login / Auth | ✅ 4 tests | ✅ 4 tests |
| Home permissions | ✅ 3 tests | ✅ 3 tests |
| Sales Analytics | ✅ 4 tests | ✅ 4 tests |
| Customer Analytics | ❌ 0 tests | ✅ 9 tests |
| Coupon Analytics | ❌ 0 tests | ✅ 9 tests |
| Store Detail | ❌ 0 tests | ✅ 10 tests |
| Customer Lookup | ❌ 0 tests | ✅ 10 tests |
| **Total** | **11 tests** | **49 tests** |

---

## 5. Unit & Widget Test Coverage

Pre-existing (not changed in this audit):

| Category | Files | Tests |
|----------|-------|-------|
| Unit tests | 16 files | service parsing, auth flows, date utils, VND formatter, token storage, biometric, log scrubbing |
| Widget tests | 16 files | all 5 analytics pages, all 3 chart pages, home, login, router, KPI cards, data table, donut chart |
| Golden tests | 1 file | visual snapshot of key screens |

---

## 6. How to Run Integration Tests

```bash
# Run all integration tests against a live backend
cd semir-phone

# With test credentials + known VIP ID
flutter test integration_test/ \
  --dart-define=API_BASE_URL=http://your-server/api/v1 \
  --dart-define=TEST_USERNAME=admin \
  --dart-define=TEST_PASSWORD=yourpassword \
  --dart-define=TEST_VIP_ID=12345

# Run a single test file
flutter test integration_test/customer_analytics_test.dart \
  --dart-define=API_BASE_URL=http://your-server/api/v1 \
  --dart-define=TEST_USERNAME=admin \
  --dart-define=TEST_PASSWORD=yourpassword
```

Tests that require `TEST_VIP_ID` (customer_detail search-result tests) are automatically skipped when the variable is empty — safe to run without it.

---

## 7. Architecture Summary

```
Screens (10 total)
  └── Home (5 cards → 5 feature routes)
      ├── Sales     → /sales       → /sales/charts
      ├── Customers → /customer    → /customer/charts
      ├── Coupon    → /coupon      → /coupon/charts
      ├── Store     → /shop-detail
      └── Lookup    → /customer-detail

State Management: Riverpod (AsyncNotifier + FutureProvider.family for lazy tabs)
HTTP: Dio 5.4 + AuthInterceptor (JWT, serial 401 refresh)
Navigation: GoRouter (permission-gated redirects, back-stack only)
Tests: 49 integration + 32 unit/widget tests
Flutter analyze: 0 errors
```

---

## 8. Verdict

| Check | Status |
|-------|--------|
| Home shows all 8 navigable pages | ✅ **8 home cards** (5 primary + 3 chart) + chart icon in each analytics AppBar |
| All pages display full API data | ✅ 100% of meaningful fields mapped |
| Lazy loading applied | ✅ Tab-level (Sales, Coupon), section-level (Store Detail), search-driven (Lookup) |
| Server-side response time | ✅ All endpoints < 5s; slowest = CNV all-time at 4.53s |
| Integration test timeouts | ✅ 8–10s E2E budget per page (device + network overhead) |
| Integration test coverage | ✅ All 7 page areas covered (49 tests, up from 11) |
| Flutter analyze errors | ✅ 0 errors |
| Parity: API ↔ Web ↔ Mobile | ✅ 85 parity tests passing in Django test suite |

### Bug Fixed This Session

| Bug | Root Cause | Fix |
|-----|-----------|-----|
| 3 chart pages unreachable | GoRouter routes registered but no UI button pointed to them | Added 3 chart cards to `home_page.dart`; added AppBar `bar_chart` icon to `sales_page.dart`, `customer_page.dart`, `coupon_page.dart` |
