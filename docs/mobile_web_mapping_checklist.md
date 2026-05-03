# Mobile ↔ Web Mapping Checklist
**Tác giả:** Senior QA/PM Review  
**Ngày tạo:** 2026-05-01  
**Cập nhật lần cuối:** 2026-05-03 (full-sprint sign-off)  
**Mục tiêu:** Đảm bảo 8 Web pages có 1:1 parity với Mobile App về data, UI, và test coverage.

---

## Tổng quan trạng thái (Executive Summary)

| # | Web Page | Mobile Page | Data Parity | UI Parity | Widget Tests | Unit Tests | Status |
|---|----------|-------------|-------------|-----------|--------------|------------|--------|
| 1 | Sales Analytics | `SalesPage` | ✅ All tabs + allshops | ✅ All tabs + allshops section | ✅ 4 tests | ✅ | ✅ Done |
| 2 | Sales Charts | `SalesChartPage` | ✅ Verified | ✅ TrendLineChart + DateFilterBar | ✅ 7 tests | — | ✅ Done |
| 3 | Customer Analytics | `CustomerPage` | ✅ 5 tabs + Zalo tab | ✅ 5 breakdown + 4 comparison tabs | ✅ 8 tests | ✅ | ✅ Done |
| 4 | Customer Charts | `CustomerChartPage` | ✅ Verified | ✅ TrendLineChart + DateFilterBar | ✅ 4 tests | — | ✅ Done |
| 5 | Coupon Analytics | `CouponPage` | ✅ Key-lookup fix + empty state | ✅ | ✅ 7 tests | — | ✅ Done |
| 6 | Coupon Charts | `CouponChartPage` | ✅ Verified | ✅ TrendLineChart + DateFilterBar | ✅ 4 tests | — | ✅ Done |
| 7 | Shop Detail | `ShopDetailPage` | ✅ Zalo Active added | ✅ Zalo Active table in Customer section | ✅ 7 tests | — | ✅ Done |
| 8 | Customer Detail | `CustomerDetailPage` | ✅ Email added | ✅ Email shown when present | ✅ 15 tests | ✅ | ✅ Done |

**Flutter test suite: 226/226 passing** (2026-05-03)  
**Django API tests: 57/57 passing** (2026-05-03)

**Legend:** ✅ Done · ⚠️ Partial/Issue · ❌ Missing/Broken

---

## Fixes Applied This Sprint (2026-05-03 — full audit)

### P0 Fixes (Critical — Production Bugs)

| # | File | Bug | Fix |
|---|------|-----|-----|
| 1 | `customer_service.dart` | `json['comparison']` key mismatch — comparison tabs always empty | Changed to `json['customer_comparison']` |
| 2 | `customer_detail_service.dart` | `fromJson` read nested `json['customer']` that doesn't exist — all fields empty | Rewrote to read flat API response |
| 3 | `App/api/views.py` `CustomerDetailView` | `name` field not in API response | Added `'name': customer.name or ''` |

### P1 Fixes (Important — Feature Completeness)

| # | File | Change |
|---|------|--------|
| 4 | `App/api/views.py` `CustomerAnalyticsView` | Added `by_season` + `by_week` to `registration_breakdown` response |
| 5 | `customer_page.dart` | Expanded `_breakdownLabels` from 3 → 5 tabs: `By Store`, `By Season`, `By Month`, `By Week`, `By Grade` |
| 6 | `customer_detail_page.dart` `_CustomerProfile` | Added display of `registrationStore`, `registrationDate`, `cnvSyncStatus` |
| 7 | `customer_detail_service.dart` `CustomerDetailPayload` | Added fields: `registrationStore`, `registrationDate`, `cnvSyncStatus`; fixed `invoiceHeaders` to `['Date', 'Shop', 'Invoice', 'Amount']` |

### P2 Fixes (UI Polish — all resolved in this sprint)

| # | File | Change |
|---|------|--------|
| 8 | `trend_line_chart.dart` | Created `TrendLineChart` widget using `fl_chart LineChart` (curved, tooltips, filled area) |
| 9 | `sales_chart_page.dart` | Added `DateFilterBar` + real `TrendLineChart` (replaced placeholder) |
| 10 | `customer_chart_page.dart` | Added `DateFilterBar` + `TrendLineChart` |
| 11 | `coupon_chart_page.dart` | Added `DateFilterBar` + `TrendLineChart` |
| 12 | `coupon_page.dart` | Fixed tab 0 bug: key lookup `tabKey == 'by_shop'` instead of `tabs.first` |
| 13 | `coupon_page.dart` | Added empty state: `Center(child: Text('No data'))` when `payload == null` |
| 14 | `App/api/views.py` `SalesAnalyticsView` | Added `allshops_tabs` key to response when `shop_group` is set |
| 15 | `sales_service.dart` `SalesAnalyticsPayload` | Added `allshopsTabs: TableTab.parseMap(...)` field |
| 16 | `sales_page.dart` | Added "All Shops (Comparison)" section with lazy-loaded tabs |
| 17 | `App/api/views.py` `CustomerAnalyticsView` | Added `'zalo'` key to `customer_comparison` with `_cnv_zalo_stats_table()` |
| 18 | `customer_page.dart` `_comparisonLabels` | Added `'Zalo'` as 4th comparison tab |
| 19 | `App/api/views.py` `_build_shop_customer` | Added `'zalo_active'` table (7-col CNV Zalo Active list) |
| 20 | `shop_detail_service.dart` `ShopCustomerPayload` | Added `zaloActiveTable` field parsed from `json['customer']['zalo_active']` |
| 21 | `shop_detail_page.dart` `_CustomerSection` | Added Zalo Active table rendering in Customer section |
| 22 | `App/api/views.py` `CustomerDetailView` | Added `'email': customer.email or ''` to response |
| 23 | `customer_detail_service.dart` `CustomerDetailPayload` | Added `email` field parsed from `json['email']` |
| 24 | `customer_detail_page.dart` `_CustomerProfile` | Added email row with `Icons.email_outlined` (shown only when non-empty) |

### Critical Chart Bugs Fixed (2026-05-03)

| # | Bug | Root Cause | Fix |
|---|-----|-----------|-----|
| C1 | Donuts always empty in production | API returns list, mobile parsed as map (`Map<String, dynamic>?`) | Changed `ChartPayload.fromJson` to `json['donuts'] as List?` + updated `DonutChart.fromJson` signature |
| C2 | Donut slice values always `""` in production | API returned `int`, mobile cast to `String?` returning null→`""` | API now calls `_fmt(count)` to return pre-formatted strings |
| C3 | All donut percentages 0.0 in production | API never computed or returned `percentage` field | API now computes `round(count/total*100, 1)` per slice |
| C4 | Trend always null in production | API returned nested dict `{metric, series:[{data_points:[]}]}`, mobile expected flat list | `_sales_trend` now returns `[{'label': date, 'value': float}]` flat list |
| C5 | `RangeError` on donut touch between slices | `fl_chart` returns `-1` for `touchedSectionIndex` when touching gaps | Added `idx >= 0` guard in `donut_card.dart:93` |

### Test Fixes

| # | File | Change |
|---|------|--------|
| T1 | `test/unit/customer_service_test.dart` | Updated fixture: `'comparison'` → `'customer_comparison'` key |
| T2 | `test/unit/customer_detail_service_test.dart` | Rewrote `_customerPayload()` to flat format; updated happy path assertions |
| T3 | `test/widget/chart_page_test.dart` | Added `CustomerChartPage` (4 tests) + `CouponChartPage` (4 tests) groups |
| T4 | `tests/snapshots/api_customer_shape.json` | Updated `registration_breakdown_keys` (3→5) and `customer_comparison_keys` (3→4 with `"zalo"`) |
| T5 | `test/unit/chart_service_test.dart` | Rewrote fixture: donuts as list (not map), value as string, percentage field; added 3 new tests |
| T6 | `test/widget/sales_page_test.dart` | Added null payload → "No data" test |
| T7 | `test/widget/customer_detail_page_test.dart` | Added 8 tests: loading, store/date, CNV synced/not_synced/null, invoice headers, email shown/hidden |
| T8 | `test/golden/golden_test.dart` | Regenerated `goldens/sales_charts.png` after DateFilterBar + TrendLineChart added |

---

## PAGE 1 — Sales Analytics

**Web:** `GET /analytics/` → `analytics/dashboard.html`  
**Mobile:** `SalesPage` → `GET /analytics/sales/`  
**File:** `semir-phone/lib/features/analytics/sales/sales_page.dart`

### [PAGE-EXISTS] ✅

### [DATA] ✅ All tabs match

| Data Field | Web renders | Mobile API field | Match? |
|-----------|-------------|-----------------|--------|
| All-Time KPI cards | 4 cards | `all_time_kpis.*` | ✅ |
| Period KPI cards | same | `period_kpis.*` | ✅ |
| Tab By Grade | `by_grade[]` | `tabs.by_grade` | ✅ |
| Tab By Season | `by_season[]` | `tabs.by_season` | ✅ |
| Tab By Month | `by_month[]` | `tabs.by_month` | ✅ |
| Tab By Week | `by_week[]` | `tabs.by_week` | ✅ |
| Tab By Shop | `by_shop[]` | `tabs.by_shop` | ✅ |
| Allshops tabs (Grade/Season/Month/Week) | `periods_by_grade[]` etc. | `allshops_tabs.*` (lazy loaded) | ✅ **Fixed** |

### [UI] ✅

| UI Element | Web | Mobile | Status |
|-----------|-----|--------|--------|
| Date range filter | ✅ | ✅ DateFilterBar | ✅ |
| Shop group filter | ✅ | ✅ ShopGroupFilter | ✅ |
| All-Time KPI cards | 4 cards | ✅ | ✅ |
| Period KPI cards | same | ✅ | ✅ |
| Tab: By Grade/Season/Month/Week/Shop | ✅ | ✅ DataTableWidget | ✅ |
| Allshops comparison section | ✅ 4 cross-tabs | ✅ **Fixed** — shown when shopGroup ≠ 'All' | ✅ |
| Pull-to-refresh | ✅ | ✅ PullToRefresh | ✅ |
| Loading overlay | ✅ | ✅ LoadingOverlay | ✅ |
| Error state | ✅ | ✅ ErrorBanner | ✅ |

### [TEST] ✅ 4 widget tests + golden

### Open Action Items
None.

---

## PAGE 2 — Sales Charts

**Web:** `GET /analytics/chart/` → `analytics/chart.html`  
**Mobile:** `SalesChartPage` → `GET /charts/sales/`  
**File:** `semir-phone/lib/features/charts/sales_chart_page.dart`

### [PAGE-EXISTS] ✅

### [DATA] ✅ Verified
- `/charts/sales/` Django view returns `ChartPayload` with `donuts[]` + optional `trend`
- Donut charts (By Grade, By Shop distribution) match web donut structure

### [UI] ✅

| UI Element | Web | Mobile | Status |
|-----------|-----|--------|--------|
| Donut charts | Multiple donuts | ✅ `DonutCard` widgets | ✅ |
| Legend per slice | ✅ | ✅ | ✅ |
| Trend line chart | Interactive line chart | ✅ **Fixed** — `TrendLineChart` (fl_chart) | ✅ |
| Date filter | ✅ | ✅ **Fixed** — `DateFilterBar` added | ✅ |

### [EMPTY-STATE] ✅ `payload == null` → `Center(child: Text('No data'))`

### [TEST] ✅ 7 tests (loading, error, null payload, donut count, no trend, trend visible, legend) + golden updated

### Open Action Items
None.

---

## PAGE 3 — Customer Analytics

**Web:** `GET /cnv/` → `cnv/customer_analytics.html`  
**Mobile:** `CustomerPage` → `GET /analytics/customer/`  
**File:** `semir-phone/lib/features/analytics/customer/customer_page.dart`

### [PAGE-EXISTS] ✅

### [DATA] ✅ All tabs match

| Data Field | Web | Mobile | Status |
|-----------|-----|--------|--------|
| All-Time KPIs | Total POS, CNV, POS Only, CNV Only, etc. | `all_time_kpis.*` | ✅ |
| Period KPIs | same | `period_kpis.*` | ✅ |
| BD: by_shop | ✅ | ✅ Tab "By Store" | ✅ |
| BD: by_season | ✅ | ✅ Tab "By Season" | ✅ |
| BD: by_month | ✅ | ✅ Tab "By Month" | ✅ |
| BD: by_week | ✅ | ✅ Tab "By Week" | ✅ |
| BD: by_grade | ✅ | ✅ Tab "By Grade" | ✅ |
| Comparison: POS Only | ✅ | ✅ Tab "POS Only" | ✅ |
| Comparison: CNV Only | ✅ | ✅ Tab "CNV Only" | ✅ |
| Comparison: Both | ✅ | ✅ Tab "Both" | ✅ |
| Comparison: Zalo Stats | ✅ | ✅ **Fixed** — Tab "Zalo" (Shop/NewCNV/ZaloApp/%App/ZaloOA/%OA) | ✅ |

### [UI] ✅

| UI Element | Web | Mobile | Status |
|-----------|-----|--------|--------|
| Date filter | ✅ | ✅ DateFilterBar | ✅ |
| All-Time KPI cards | ✅ | ✅ | ✅ |
| Period KPI cards | ✅ | ✅ | ✅ |
| BD 5-tab structure | ✅ | ✅ | ✅ |
| Comparison 4-tab structure (incl. Zalo) | ✅ | ✅ **Fixed** | ✅ |

### [TEST] ✅ 8 widget tests

### Open Action Items
None.

---

## PAGE 4 — Customer Charts

**Web:** `GET /cnv/customer-chart/` → `cnv/customer_chart.html`  
**Mobile:** `CustomerChartPage` → `GET /charts/customer/`  
**File:** `semir-phone/lib/features/charts/customer_chart_page.dart`

### [PAGE-EXISTS] ✅

### [DATA] ✅ Verified — `/charts/customer/` Django view exists

### [UI] ✅

| UI Element | Web | Mobile | Status |
|-----------|-----|--------|--------|
| Donut charts | Multiple donuts | ✅ `DonutCard` widgets | ✅ |
| Legend per slice | ✅ | ✅ | ✅ |
| Trend line chart | Interactive line chart | ✅ **Fixed** — `TrendLineChart` (fl_chart) | ✅ |
| Date filter | ✅ | ✅ **Fixed** — `DateFilterBar` added | ✅ |

### [EMPTY-STATE] ✅

### [TEST] ✅ 4 tests (loading, error, null payload, data — donut cards + legend)

### Open Action Items
None.

---

## PAGE 5 — Coupon Analytics

**Web:** `GET /coupon/` → `coupon/dashboard.html`  
**Mobile:** `CouponPage` → `GET /analytics/coupon/`  
**File:** `semir-phone/lib/features/analytics/coupon/coupon_page.dart`

### [PAGE-EXISTS] ✅

### [DATA] ✅

| Data Field | Web | Mobile | Status |
|-----------|-----|--------|--------|
| All-Time KPIs | Total, Used, Unused, Rate | `all_time_kpis.*` | ✅ |
| Period KPIs | same | `period_kpis.*` | ✅ |
| Tab By Shop | shop_name, total, used, unused, rate, amount | `tabs.by_shop` | ✅ |
| Tab Detail | Coupon ID, Status, Amount (VND), Shop, Date | `tabs.detail` | ✅ (mobile API columns) |
| Tab Duplicates | Invoice, Count, Coupons | `tabs.duplicates` | ✅ (mobile API columns) |
| Coupon prefix filter | ✅ | ✅ TextField → `couponPrefixProvider` | ✅ |
| Tab 0 key-safety | — | ✅ **Fixed** — key lookup `tabKey == 'by_shop'` | ✅ |

### [UI] ✅

| UI Element | Web | Mobile | Status |
|-----------|-----|--------|--------|
| All-Time KPI row | ✅ | ✅ | ✅ |
| Period KPI row | ✅ | ✅ | ✅ |
| Prefix filter | ✅ | ✅ | ✅ |
| Shop group filter | ✅ | ✅ | ✅ |
| By Shop / Detail / Duplicates tabs | ✅ | ✅ DataTableWidget | ✅ |
| Download button | ✅ Excel | N/A on mobile | (expected — mobile-only skip) |

### [EMPTY-STATE] ✅ **Fixed** — `Center(child: Text('No data'))` when `payload == null`

### [TEST] ✅ 7 widget tests

### Open Action Items
None.

---

## PAGE 6 — Coupon Charts

**Web:** `GET /coupon/chart/` → `coupon/chart.html`  
**Mobile:** `CouponChartPage` → `GET /charts/coupon/`  
**File:** `semir-phone/lib/features/charts/coupon_chart_page.dart`

### [PAGE-EXISTS] ✅

### [DATA] ✅ Verified — `/charts/coupon/` Django view exists

### [UI] ✅

| UI Element | Web | Mobile | Status |
|-----------|-----|--------|--------|
| Donut charts | Multiple donuts | ✅ `DonutCard` widgets | ✅ |
| Legend per slice | ✅ | ✅ | ✅ |
| Trend line chart | Interactive line chart | ✅ **Fixed** — `TrendLineChart` (fl_chart) | ✅ |
| Date filter | ✅ | ✅ **Fixed** — `DateFilterBar` added | ✅ |

### [EMPTY-STATE] ✅

### [TEST] ✅ 4 tests (loading, error, null payload, data — donut cards + legend)

### Open Action Items
None.

---

## PAGE 7 — Shop Detail

**Web:** `GET /shop-detail/` → `shop_detail.html`  
**Mobile:** `ShopDetailPage` → `GET /analytics/shop-detail/`  
**File:** `semir-phone/lib/features/analytics/shop_detail/shop_detail_page.dart`

### [PAGE-EXISTS] ✅

### [DATA] ✅

| Data Field | Web | Mobile | Status |
|-----------|-----|--------|--------|
| Sales: All-Time + Period KPIs | 5 KPIs each | `allTimeKpis` + `periodKpis` | ✅ |
| Sales: By Season/Month/Week tables | 8 cols each | ✅ via tabs | ✅ |
| Customer: All-Time + Period KPIs | 7 KPIs | ✅ | ✅ |
| Customer: By Season/Month/Week tables | 11 cols each | ✅ via tabs | ✅ |
| Customer: Zalo Active list | CNV table 7 cols | ✅ **Fixed** — `zaloActiveTable` (CNV ID/Phone/Name/Level/Zalo App/OA/Date) | ✅ |
| Coupon: KPIs | 4 KPIs | ✅ | ✅ |
| Coupon: Detail table | Coupon ID/Status/Amount/Shop/Date | ✅ `detailTable` | ✅ |

### [UI] ✅

| UI Element | Web | Mobile | Status |
|-----------|-----|--------|--------|
| Shop dropdown | 3 separate dropdowns | ✅ 1 unified dropdown (accepted design simplification) | ✅ |
| Date filter | ✅ | ✅ DateFilterBar | ✅ |
| Section tabs (Sales/Customer/Coupon) | ✅ | ✅ | ✅ |
| Sales KPI cards + tables | ✅ | ✅ | ✅ |
| Customer KPI cards + tables | ✅ | ✅ | ✅ |
| Customer: Zalo Active list | ✅ 7-col table | ✅ **Fixed** — `_CustomerSection` renders Zalo Active table | ✅ |
| Coupon KPI cards + detail table | ✅ | ✅ | ✅ |
| Section card top-border primary color | ✅ | ✅ `AppColors.primary` | ✅ |

**Design Note:** Web has 3 separate shop dropdowns (sales_shop / customer_shop / coupon_shop) because each queries a different model field. Mobile uses 1 unified dropdown from `/analytics/shops/`. This is an accepted simplification — confirmed with team.

### [EMPTY-STATE] ✅ "Please select a store to view details"

### [TEST] ✅ 7 widget tests

### Open Action Items
None.

---

## PAGE 8 — Customer Detail

**Web:** `GET /customer/detail/` → `customer/detail.html`  
**Mobile:** `CustomerDetailPage` → `GET /analytics/customer-detail/`  
**File:** `semir-phone/lib/features/analytics/customer_detail/customer_detail_page.dart`

### [PAGE-EXISTS] ✅

### [DATA] ✅ All fields match

| Data Field | Web | Mobile | Status |
|-----------|-----|--------|--------|
| Name | ✅ | ✅ `json['name']` → `username` | ✅ |
| Phone masked | ✅ | ✅ `09x-xxx-x567` format | ✅ |
| VIP ID | ✅ | ✅ `json['vip_id']` | ✅ |
| Grade | ✅ | ✅ `json['grade']` | ✅ |
| Registration Store | ✅ | ✅ `json['registration_store']` | ✅ |
| Registration Date | ✅ | ✅ `json['registration_date']` | ✅ |
| CNV Sync status | ✅ | ✅ `json['cnv_sync_status']` | ✅ |
| Email | ✅ | ✅ **Fixed** — `json['email']`, shown when non-empty | ✅ |
| Stats KPIs (Total Invoices, Total Revenue) | ✅ | ✅ built from `total_invoices` + `total_revenue` | ✅ |
| Invoice history | Date, Shop, Invoice#, Amount | ✅ `invoice_history[{date, shop, invoice_id, amount}]` | ✅ |

### [UI] ✅

| UI Element | Web | Mobile | Status |
|-----------|-----|--------|--------|
| Search by VIP ID | ✅ | ✅ TextField | ✅ |
| Search by Phone | ✅ | ✅ TextField | ✅ |
| Profile card (name, phone, VIP ID, grade) | ✅ | ✅ | ✅ |
| Registration Store + Date | ✅ | ✅ shown as joined text line | ✅ |
| CNV sync icon + label | ✅ | ✅ `Icons.link`/`Icons.link_off` | ✅ |
| Email field | ✅ | ✅ **Fixed** — `Icons.email_outlined` row (hidden when empty) | ✅ |
| KPI stats (invoices, revenue) | ✅ | ✅ 2 KpiCards | ✅ |
| Invoice history table | ✅ | ✅ DataTableWidget (4 cols) | ✅ |
| Not found state | ✅ | ✅ `_NotFoundBanner` | ✅ |

### [EMPTY-STATE] ✅
- Initial: null → empty
- Not found: `NotFoundException` → `_NotFoundBanner`

### [TEST] ✅ 15 widget tests (initial state, data state, phone masked, 404, invoice table, grade badge, KPI cards, loading, store/date, CNV synced/not_synced/null, invoice headers, email shown, email hidden)

### Open Action Items
None.

---

## Rollout Status

### Phase 1 — Critical Fixes (P0) ✅ COMPLETE
- [x] Fix Customer `comparison` key bug → `customer_comparison`
- [x] Fix CustomerDetail `fromJson` flat response parsing + add `name` to API
- [x] Fix `registrationStore`, `registrationDate`, `cnvSyncStatus` fields

### Phase 2 — Feature Completeness (P1) ✅ COMPLETE
- [x] Add `by_season` + `by_week` to CustomerAnalytics API + Mobile tabs (5 tabs now)
- [x] Show registration store, date, CNV sync in CustomerDetail profile card
- [x] Fix all broken unit test fixtures to match corrected API format

### Phase 3 — Test Coverage (P1) ✅ COMPLETE
- [x] CustomerChartPage: 4 widget tests added
- [x] CouponChartPage: 4 widget tests added
- [x] SalesPage: null payload test added
- [x] CustomerDetailPage: loading, store/date/CNV, invoice headers, email — 8 tests added
- [x] ChartService: percentage assertion, list-format fixture, empty-donuts test — 3 tests added
- [x] `flutter test`: **226/226 passing**
- [x] `python manage.py test tests.test_api`: **57/57 passing**

### Phase 4 — UI Polish (P2) ✅ COMPLETE
- [x] Implement trend line chart (pages 2, 4, 6) — `TrendLineChart` using fl_chart
- [x] Add date filter to chart pages (pages 2, 4, 6) — `DateFilterBar` added
- [x] Coupon tab 0 key-lookup fix — `tabKey == 'by_shop'` instead of `tabs.first`
- [x] Coupon empty state when `payload == null`
- [x] Allshops tabs for Sales — `allshops_tabs` API key + "All Shops (Comparison)" section
- [x] Zalo Stats tab in Customer Analytics comparison section
- [x] Zalo Active list in Shop Detail Customer section
- [x] Add email field to Customer Detail (API + mobile UI)

### Phase 5 — Sign-off ✅ COMPLETE
- [x] Flutter test: 226/226 green
- [x] Django API test: 57/57 green
- [x] Flutter analyze: 0 errors
- [x] Golden snapshots regenerated after UI changes
- [x] `donut_card.dart` RangeError fix (fl_chart `-1` guard)

---

## Appendix — File Reference

### Mobile
| Page | Dart file | Provider | Service |
|------|-----------|----------|---------|
| SalesPage | `features/analytics/sales/sales_page.dart` | `sales_provider.dart` | `sales_service.dart` |
| SalesChartPage | `features/charts/sales_chart_page.dart` | `chart_provider.dart` | `chart_service.dart` |
| CustomerPage | `features/analytics/customer/customer_page.dart` | `customer_provider.dart` | `customer_service.dart` |
| CustomerChartPage | `features/charts/customer_chart_page.dart` | `chart_provider.dart` | `chart_service.dart` |
| CouponPage | `features/analytics/coupon/coupon_page.dart` | `coupon_provider.dart` | `coupon_service.dart` |
| CouponChartPage | `features/charts/coupon_chart_page.dart` | `chart_provider.dart` | `chart_service.dart` |
| ShopDetailPage | `features/analytics/shop_detail/shop_detail_page.dart` | `shop_detail_provider.dart` | `shop_detail_service.dart` |
| CustomerDetailPage | `features/analytics/customer_detail/customer_detail_page.dart` | `customer_detail_provider.dart` | `customer_detail_service.dart` |

### Web
| Page | View | Template |
|------|------|----------|
| Sales Analytics | `App/views/analytics.py` | `analytics/dashboard.html` |
| Sales Charts | `App/views/analytics.py` | `analytics/chart.html` |
| Customer Analytics | `App/cnv/views.py` | `cnv/customer_analytics.html` |
| Customer Charts | `App/cnv/views.py` | `cnv/customer_chart.html` |
| Coupon Analytics | `App/views/coupon.py` | `coupon/dashboard.html` |
| Coupon Charts | `App/views/coupon.py` | `coupon/chart.html` |
| Shop Detail | `App/views/shop_detail.py` | `shop_detail.html` |
| Customer Detail | `App/views/customer.py` | `customer/detail.html` |

### API Endpoints
| Mobile calls | Django view | Status |
|-------------|-------------|--------|
| `GET /analytics/sales/` | `SalesAnalyticsView` | ✅ |
| `GET /analytics/customer/` | `CustomerAnalyticsView` | ✅ |
| `GET /analytics/coupon/` | `CouponAnalyticsView` | ✅ |
| `GET /analytics/customer-detail/` | `CustomerDetailView` | ✅ |
| `GET /analytics/shop-detail/` | `ShopDetailView` | ✅ |
| `GET /charts/sales/` | `SalesChartView` | ✅ |
| `GET /charts/customer/` | `CustomerChartView` | ✅ |
| `GET /charts/coupon/` | `CouponChartView` | ✅ |
