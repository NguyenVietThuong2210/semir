# Mobile ↔ Web Mapping Checklist
**Tác giả:** Senior QA/PM Review  
**Ngày tạo:** 2026-05-01  
**Cập nhật lần cuối:** 2026-05-06 (Sprint 2 — deep 5-layer audit)  
**Mục tiêu:** Đảm bảo 8 Web pages có 1:1 parity với Mobile App về data, UI, và test coverage.

---

## Tổng quan trạng thái (Executive Summary)

| # | Web Page | Mobile Page | Data Parity | UI Parity | Widget Tests | Unit Tests | Status |
|---|----------|-------------|-------------|-----------|--------------|------------|--------|
| 1 | Sales Analytics | `SalesPage` | ⚠️ 2 sections missing | ⚠️ No Buyer w/o Info, No CusDetail | ✅ 4 tests | ✅ | ⚠️ Gaps |
| 2 | Sales Charts | `SalesChartPage` | ⚠️ API returns 2-3 donuts vs 8 on web | ⚠️ No multi-series trend, bar, tables | ✅ 7 tests | — | ⚠️ Gaps |
| 3 | Customer Analytics | `CustomerPage` | ⚠️ Missing all-shops BD tabs, Points Analysis | ⚠️ | ✅ 8 tests | ✅ | ⚠️ Partial |
| 4 | Customer Charts | `CustomerChartPage` | ⚠️ Same chart gaps as Page 2 | ⚠️ | ✅ 4 tests | — | ⚠️ Gaps |
| 5 | Coupon Analytics | `CouponPage` | ✅ | ✅ | ✅ 7 tests | — | ✅ Done |
| 6 | Coupon Charts | `CouponChartPage` | ⚠️ Same chart gaps as Page 2 | ⚠️ | ✅ 4 tests | — | ⚠️ Gaps |
| 7 | Shop Detail | `ShopDetailPage` | ✅ | ✅ | ✅ 7 tests | — | ✅ Done |
| 8 | Customer Detail | `CustomerDetailPage` | ⚠️ Missing Zalo date, points, last purchase, 3 invoice cols | ⚠️ | ✅ 15 tests | ✅ | ⚠️ Partial |

**Flutter test suite: 226/226 passing** (2026-05-03)  
**Django API tests: 57/57 passing** (2026-05-03)

**Legend:** ✅ Done · ⚠️ Partial/Issue · ❌ Missing/Broken

---

## ══════════════════════════════════════════
## SPRINT 2 — 2026-05-06 — Fix Plan & Checklist
## (Deep 5-Layer Audit: Web Template → View → API → Service → Widget)
## ══════════════════════════════════════════

### Fix Plan

| # | Priority | Page | Dimension | Gap description | Proposed fix |
|---|----------|------|-----------|-----------------|--------------|
| 1 | P1 | SalesPage | DATA+UI | "Buyer Without Info" section (period KPIs + all-time KPIs + by-shop table) absent from API and mobile | API: add `buyer_without_info_stats` to `SalesAnalyticsView`; Mobile: add to `SalesAnalyticsPayload.fromJson` + render in `sales_page.dart` |
| 2 | P1 | SalesPage | DATA+UI | "Customer Details" table (top-100 VIP customers: VIP ID, Name, Grade, Reg Date, Purchases, Return Visits, Total Spent) absent from API and mobile | API: add `customer_details` list to `SalesAnalyticsView`; Mobile: parse in service + render table in `sales_page.dart` |
| 3 | P1 | SalesChartPage | DATA+UI | Web has 8 donut charts (2 rows × 4: customer metrics + invoice/amount metrics); mobile API returns only 2-3 donuts | API: expand `SalesChartView` to return all 8 donut definitions with `percentage` field; mobile renders via existing `payload.donuts.map(...)` |
| 4 | P1 | SalesChartPage | UI | Period Overview collapsible data table below donuts — absent from mobile | API: add `overview_table` to chart response; Mobile: render `DataTableWidget` below donuts |
| 5 | P1 | SalesChartPage | UI | Shop Trends multi-series line chart (per-shop, AVG all, AVG selected, metric selector, time-axis selector) — mobile only has single return_rate trend line | API: add per-shop time-series data to chart response; Mobile: add multi-series chart widget |
| 6 | P1 | SalesChartPage | UI | Shop Trends collapsible data table — absent from mobile | API: include shop trend table data; Mobile: add collapsible `DataTableWidget` |
| 7 | P1 | SalesChartPage | UI | Period Totals bar chart (shop selector, metric selector, time axis) — absent from mobile | API: add period totals bar data; Mobile: add bar chart widget |
| 8 | P1 | SalesChartPage | UI | Period Totals collapsible data table — absent from mobile | API: include period totals table; Mobile: add collapsible `DataTableWidget` |
| 9 | P1 | CustomerChartPage | DATA+UI | Same chart structural gaps as items 3–8 (donuts count, trend, bar chart, data tables) | Same approach as items 3–8 applied to `CustomerChartView` and `customer_chart_page.dart` |
| 10 | P1 | CouponChartPage | DATA+UI | Same chart structural gaps as items 3–8 applied to coupon chart page | Same approach applied to `CouponChartView` and `coupon_chart_page.dart` |
| 11 | P2 | CustomerPage | DATA+UI | Registration Breakdown missing "All Shops" tab variants (by_season_allshops, by_month_allshops, by_week_allshops) — web has 7 tabs, mobile has 5 | API: add all-shops breakdown tabs to `CustomerAnalyticsView`; Mobile: update `_breakdownLabels` and add 3 tabs |
| 12 | P2 | CustomerPage | DATA+UI | "Points Analysis" tab (CNV loyalty points breakdown) — absent from mobile comparison section | API: add `points_analysis` key to `customer_comparison`; Mobile: add tab label + parse + render |
| 13 | P2 | CustomerDetailPage | DATA+UI | Zalo Active Date (`cnv_customer.zalo_app_created_at`) — web shows in profile card; not in API or mobile | API: add `zalo_active_date` to `CustomerDetailView`; Mobile: parse + show in profile card |
| 14 | P2 | CustomerDetailPage | DATA+UI | Loyalty Points (POS) and Loyalty Points (CNV) — web shows both; not in API or mobile | API: add `pos_points`, `cnv_points` to `CustomerDetailView`; Mobile: parse + show as KPI cards |
| 15 | P2 | CustomerDetailPage | DATA+UI | Last Purchase Date — web shows in Purchase Statistics; mobile only has Total Invoices + Total Revenue | API: add `last_purchase_date` to response; Mobile: parse + add to `kpis` list |
| 16 | P2 | CustomerDetailPage | DATA+UI | Invoice table missing 3 columns: Coupon ID, Face Value, Coupon Amount — web shows 7 cols, mobile shows 4 | API: add `coupon_id`, `face_value_display`, `coupon_amount` per invoice row; Mobile: update headers + row mapping |
| 17 | P2 | CouponPage | UI | Campaign selector filter on web — mobile has prefix TextField but no campaign dropdown | Mobile: add `DropdownButton<String>` for campaign filter fed from API `available_campaigns` list |

---

### Sprint 2 Checklist

#### P1 — Missing Features (fix first)

- [ ] [SalesPage] [DATA] Add `buyer_without_info_stats` to `SalesAnalyticsView` API response (period KPIs + all-time KPIs + by_shop table)
- [ ] [SalesPage] [DATA] Add `customer_details` list (top-100) to `SalesAnalyticsView` API response
- [ ] [SalesPage] [DATA] Parse `buyer_without_info_stats` in `sales_service.dart` `SalesAnalyticsPayload.fromJson`
- [ ] [SalesPage] [DATA] Parse `customer_details` in `sales_service.dart`
- [ ] [SalesPage] [UI] Render "Buyer Without Info" section in `sales_page.dart` (Period summary card + All-Time summary card + By Shop breakdown table)
- [ ] [SalesPage] [UI] Render "Customer Details" table in `sales_page.dart` (VIP ID, Name, Grade, Reg Date, Purchases, Return Visits, Total Spent)
- [ ] [SalesChartPage] [DATA] Expand `SalesChartView` to return all 8 donuts (customer metrics + invoice/amount metrics rows)
- [ ] [SalesChartPage] [DATA] Add `overview_table` (period overview data table) to chart API response
- [ ] [SalesChartPage] [DATA] Add per-shop time-series data (`shop_trend`) to chart API response
- [ ] [SalesChartPage] [DATA] Add period totals bar data (`period_totals`) to chart API response
- [ ] [SalesChartPage] [UI] Render Period Overview data table below donuts in `sales_chart_page.dart`
- [ ] [SalesChartPage] [UI] Render Shop Trends multi-series line chart with shop selector in `sales_chart_page.dart`
- [ ] [SalesChartPage] [UI] Render Shop Trends data table in `sales_chart_page.dart`
- [ ] [SalesChartPage] [UI] Render Period Totals bar chart in `sales_chart_page.dart`
- [ ] [SalesChartPage] [UI] Render Period Totals data table in `sales_chart_page.dart`
- [ ] [CustomerChartPage] [DATA] Same API expansions applied to `CustomerChartView`
- [ ] [CustomerChartPage] [UI] Same chart widgets added to `customer_chart_page.dart`
- [ ] [CouponChartPage] [DATA] Same API expansions applied to `CouponChartView`
- [ ] [CouponChartPage] [UI] Same chart widgets added to `coupon_chart_page.dart`

#### P2 — Partial Parity Gaps (fix after P1)

- [ ] [CustomerPage] [DATA] Add `by_season_allshops`, `by_month_allshops`, `by_week_allshops` tabs to `CustomerAnalyticsView` API `registration_breakdown`
- [ ] [CustomerPage] [DATA] Parse 3 new tabs in `customer_service.dart`
- [ ] [CustomerPage] [UI] Add 3 new tabs to `_breakdownLabels` in `customer_page.dart`
- [ ] [CustomerPage] [DATA] Add `points_analysis` key to `customer_comparison` in API
- [ ] [CustomerPage] [UI] Add "Points Analysis" comparison tab in `customer_page.dart`
- [ ] [CustomerDetailPage] [DATA] Add `zalo_active_date` to `CustomerDetailView` API response
- [ ] [CustomerDetailPage] [DATA] Add `pos_points`, `cnv_points` to API response
- [ ] [CustomerDetailPage] [DATA] Add `last_purchase_date` to API response
- [ ] [CustomerDetailPage] [DATA] Add `coupon_id`, `face_value_display`, `coupon_amount` per invoice row to API response
- [ ] [CustomerDetailPage] [DATA] Parse all new fields in `customer_detail_service.dart`
- [ ] [CustomerDetailPage] [UI] Render Zalo Active Date in profile card (`customer_detail_page.dart`)
- [ ] [CustomerDetailPage] [UI] Render POS + CNV loyalty points as KPI cards
- [ ] [CustomerDetailPage] [UI] Add Last Purchase Date to KPI section
- [ ] [CustomerDetailPage] [UI] Update invoice table to 7 columns (add Coupon, Face Value, Coupon Amount)
- [ ] [CouponPage] [UI] Add campaign selector dropdown to coupon filter section in `coupon_page.dart`

#### Tests to add / update

- [ ] [SalesPage] Add widget test: "Buyer Without Info" section visible with data
- [ ] [SalesPage] Add widget test: "Customer Details" table visible with data
- [ ] [SalesPage] Add unit test: `SalesAnalyticsPayload.fromJson` parses `buyer_without_info_stats` and `customer_details`
- [ ] [SalesChartPage] Update widget tests: verify 8 donut cards rendered
- [ ] [SalesChartPage] Add widget test: Shop Trends chart visible
- [ ] [SalesChartPage] Add widget test: Period Totals bar chart visible
- [ ] [CustomerChartPage] Update tests for new chart widgets
- [ ] [CouponChartPage] Update tests for new chart widgets
- [ ] [CustomerDetailPage] Add tests: Zalo date shown, POS/CNV points shown, invoice 7-col headers, last purchase date shown
- [ ] [CustomerPage] Add tests: 8-tab breakdown (3 new all-shops tabs), Points Analysis comparison tab

**Total gaps:** 17 (P0: 0, P1: 10, P2: 7)  
**Estimated test delta:** +15 to +20 tests

---

## Fixes Applied — Sprint 1 (2026-05-03 — full audit)

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

### P2 Fixes (UI Polish — all resolved Sprint 1)

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
| 17 | `App/api/views.py` `CustomerAnalyticsView` | Added `'zalo'` key to `customer_comparison` |
| 18 | `customer_page.dart` `_comparisonLabels` | Added `'Zalo'` as 4th comparison tab |
| 19 | `App/api/views.py` `_build_shop_customer` | Added `'zalo_active'` table (7-col CNV Zalo Active list) |
| 20 | `shop_detail_service.dart` `ShopCustomerPayload` | Added `zaloActiveTable` field |
| 21 | `shop_detail_page.dart` `_CustomerSection` | Added Zalo Active table rendering |
| 22 | `App/api/views.py` `CustomerDetailView` | Added `'email': customer.email or ''` |
| 23 | `customer_detail_service.dart` `CustomerDetailPayload` | Added `email` field |
| 24 | `customer_detail_page.dart` `_CustomerProfile` | Added email row (shown only when non-empty) |

### Critical Chart Bugs Fixed (Sprint 1)

| # | Bug | Root Cause | Fix |
|---|-----|-----------|-----|
| C1 | Donuts always empty | API returns list, mobile parsed as map | Changed `ChartPayload.fromJson` to `json['donuts'] as List?` |
| C2 | Donut slice values always `""` | API returned `int`, mobile cast to `String?` → null | API now calls `_fmt(count)` pre-formatted strings |
| C3 | All donut percentages 0.0 | API never computed `percentage` field | API now computes `round(count/total*100, 1)` per slice |
| C4 | Trend always null | API returned nested dict, mobile expected flat list | `_sales_trend` now returns flat `[{'label': date, 'value': float}]` |
| C5 | `RangeError` on donut gap touch | `fl_chart` returns `-1` for `touchedSectionIndex` | Added `idx >= 0` guard in `donut_card.dart:93` |

---

## PAGE 1 — Sales Analytics

**Web:** `GET /analytics/` → `analytics/dashboard.html`  
**Mobile:** `SalesPage` → `GET /analytics/sales/`  
**File:** `semir-phone/lib/features/analytics/sales/sales_page.dart`

### [PAGE-EXISTS] ✅

### [DATA] ⚠️ 2 sections missing from API + mobile

| Data Field | Web template renders | API returns | Mobile parses | Mobile widget renders | Status |
|-----------|---------------------|-------------|---------------|----------------------|--------|
| All-Time KPI cards (4) | ✅ | ✅ `all_time_kpis.*` | ✅ | ✅ | ✅ |
| Period KPI cards (4) | ✅ | ✅ `period_kpis.*` | ✅ | ✅ | ✅ |
| Tab By Grade | ✅ | ✅ `tabs.by_grade` | ✅ | ✅ | ✅ |
| Tab By Season | ✅ | ✅ `tabs.by_season` | ✅ | ✅ | ✅ |
| Tab By Month | ✅ | ✅ `tabs.by_month` | ✅ | ✅ | ✅ |
| Tab By Week | ✅ | ✅ `tabs.by_week` | ✅ | ✅ | ✅ |
| Tab By Shop | ✅ | ✅ `tabs.by_shop` | ✅ | ✅ | ✅ |
| Allshops tabs (4) | ✅ always shown | ✅ `allshops_tabs` when `shop_group` set | ✅ | ✅ when filter active | ⚠️ web always visible, mobile only when filtered |
| **Buyer Without Info** — Period KPIs | ✅ dashboard.html:570–610 | ❌ Not in API | ❌ | ❌ | **❌ Gap #1** |
| **Buyer Without Info** — All-Time KPIs | ✅ dashboard.html:611–640 | ❌ Not in API | ❌ | ❌ | **❌ Gap #1** |
| **Buyer Without Info** — By Shop table | ✅ dashboard.html:641–664 | ❌ Not in API | ❌ | ❌ | **❌ Gap #1** |
| **Customer Details** table (top-100) | ✅ dashboard.html:666–715 | ❌ Not in API | ❌ | ❌ | **❌ Gap #2** |

### [UI] ⚠️

| UI Element | Web | Mobile | Status |
|-----------|-----|--------|--------|
| Date range filter | ✅ | ✅ `DateFilterBar` | ✅ |
| Shop group filter | ✅ | ✅ `ShopGroupFilter` | ✅ |
| All-Time KPI cards | 4 cards | ✅ | ✅ |
| Period KPI cards | 4 cards | ✅ | ✅ |
| Tabs By Grade/Season/Month/Week/Shop | ✅ | ✅ `DataTableWidget` | ✅ |
| Allshops comparison section | ✅ always | ✅ shown when `shopGroup ≠ 'All'` | ⚠️ |
| **Buyer Without Info** section | ✅ full section | ❌ No widget | **❌ Gap #1** |
| **Customer Details** table | ✅ full table | ❌ No widget | **❌ Gap #2** |
| Pull-to-refresh | ✅ | ✅ `PullToRefresh` | ✅ |
| Loading overlay | ✅ | ✅ `LoadingOverlay` | ✅ |
| Error state | ✅ | ✅ `ErrorBanner` | ✅ |

### [TEST] ✅ 4 widget tests + golden
### [EMPTY-STATE] ✅ `payload == null` → `Center(child: Text('No data'))`

### Open Action Items
- ❌ **Gap #1:** Add `buyer_without_info_stats` to API + mobile (P1)
- ❌ **Gap #2:** Add `customer_details` to API + mobile (P1)

---

## PAGE 2 — Sales Charts

**Web:** `GET /analytics/chart/` → `analytics/chart.html`  
**Mobile:** `SalesChartPage` → `GET /charts/sales/`  
**File:** `semir-phone/lib/features/charts/sales_chart_page.dart`

### [PAGE-EXISTS] ✅

### [DATA] ⚠️ API returns subset of web chart data

| Data Field | Web template renders | API returns | Mobile renders | Status |
|-----------|---------------------|-------------|----------------|--------|
| 8 donuts (2 rows × 4) | ✅ chart.html:233–371 | ⚠️ API returns 2-3 donuts | ✅ renders all API donuts | **⚠️ Gap #3** |
| Period Overview data table | ✅ chart.html:376–391 | ❌ Not in API | ❌ | **❌ Gap #4** |
| Shop Trends multi-series chart | ✅ chart.html:393–505 | ❌ Not in API | ❌ | **❌ Gap #5** |
| Shop Trends data table | ✅ chart.html:507–523 | ❌ Not in API | ❌ | **❌ Gap #6** |
| Period Totals bar chart | ✅ chart.html:525–616 | ❌ Not in API | ❌ | **❌ Gap #7** |
| Period Totals data table | ✅ chart.html:618+ | ❌ Not in API | ❌ | **❌ Gap #8** |
| Single return_rate trend line | ✅ | ✅ `trend` flat list | ✅ `TrendLineChart` | ✅ |

### [UI] ⚠️

| UI Element | Web | Mobile | Status |
|-----------|-----|--------|--------|
| Date filter | ✅ | ✅ `DateFilterBar` | ✅ |
| 8 donut cards | ✅ | ⚠️ Only API-provided count | **⚠️ Gap #3** |
| Period Overview data table | ✅ collapsible | ❌ Missing | **❌ Gap #4** |
| Shop Trends chart (multi-series, shop selector) | ✅ interactive | ❌ Missing | **❌ Gap #5** |
| Shop Trends data table | ✅ collapsible | ❌ Missing | **❌ Gap #6** |
| Period Totals bar chart | ✅ interactive | ❌ Missing | **❌ Gap #7** |
| Period Totals data table | ✅ collapsible | ❌ Missing | **❌ Gap #8** |
| Single return_rate trend line | ✅ | ✅ `TrendLineChart` | ✅ |

### [TEST] ✅ 7 tests
### [EMPTY-STATE] ✅

### Open Action Items
- ⚠️ **Gap #3:** Expand API to return all 8 donuts (P1)
- ❌ **Gaps #4–8:** Add overview table, shop trend chart, bar chart, data tables to API + mobile (P1)

---

## PAGE 3 — Customer Analytics

**Web:** `GET /cnv/customer-analytics/` → `cnv/customer_analytics.html`  
**Mobile:** `CustomerPage` → `GET /analytics/customer/`  
**File:** `semir-phone/lib/features/analytics/customer/customer_page.dart`

### [PAGE-EXISTS] ✅

### [DATA] ⚠️ Missing all-shops breakdown tabs + Points Analysis

| Data Field | Web template renders | Mobile | Status |
|-----------|---------------------|--------|--------|
| All-Time KPIs (4 cards) | ✅ | ✅ `all_time_kpis.*` | ✅ |
| Period KPIs (4 cards) | ✅ | ✅ `period_kpis.*` | ✅ |
| BD: by_shop | ✅ | ✅ Tab "By Store" | ✅ |
| BD: by_season | ✅ | ✅ Tab "By Season" | ✅ |
| BD: by_month | ✅ | ✅ Tab "By Month" | ✅ |
| BD: by_week | ✅ | ✅ Tab "By Week" | ✅ |
| BD: by_grade | ✅ (sales page concept) | ✅ Tab "By Grade" (extra) | ✅ |
| BD: by_season_allshops | ✅ | ❌ Not in API or mobile | **❌ Gap #11** |
| BD: by_month_allshops | ✅ | ❌ Not in API or mobile | **❌ Gap #11** |
| BD: by_week_allshops | ✅ | ❌ Not in API or mobile | **❌ Gap #11** |
| Comparison: POS Only | ✅ | ✅ Tab "POS Only" | ✅ |
| Comparison: CNV Only | ✅ | ✅ Tab "CNV Only" | ✅ |
| Comparison: Both | ✅ | ✅ Tab "Both" | ✅ |
| Comparison: Zalo Stats | ✅ | ✅ Tab "Zalo" | ✅ |
| Points Analysis (CNV loyalty points) | ✅ lazy tab `ca_points` | ❌ Not in API or mobile | **❌ Gap #12** |

### [UI] ⚠️

| UI Element | Web | Mobile | Status |
|-----------|-----|--------|--------|
| Date filter | ✅ | ✅ `DateFilterBar` | ✅ |
| All-Time + Period KPI cards | ✅ | ✅ | ✅ |
| BD 5-tab structure (basic) | ✅ | ✅ | ✅ |
| BD all-shops tabs (3) | ✅ | ❌ Missing | **❌ Gap #11** |
| Comparison 4-tab structure (incl. Zalo) | ✅ | ✅ | ✅ |
| Points Analysis tab | ✅ | ❌ Missing | **❌ Gap #12** |

### [TEST] ✅ 8 widget tests
### [EMPTY-STATE] ✅

### Open Action Items
- ❌ **Gap #11:** Add `by_season_allshops`, `by_month_allshops`, `by_week_allshops` breakdown tabs (P2)
- ❌ **Gap #12:** Add Points Analysis comparison tab (P2)

---

## PAGE 4 — Customer Charts

**Web:** `GET /cnv/customer-chart/` → `cnv/customer_chart.html`  
**Mobile:** `CustomerChartPage` → `GET /charts/customer/`  
**File:** `semir-phone/lib/features/charts/customer_chart_page.dart`

### [PAGE-EXISTS] ✅

### [DATA/UI] ⚠️ Same structural gaps as SalesChartPage

- Web `customer_chart.html` has same structure: Overview donuts + Period Overview table + Shop Trends multi-series chart + Shop Trends table + Period Totals bar chart + Period Totals table
- Mobile `customer_chart_page.dart`: only donuts + single trend line (same pattern as SalesChartPage)
- **Gaps #9:** All items from Gap #3–8 apply here for CustomerChartView / customer_chart_page.dart

### [TEST] ✅ 4 tests
### [EMPTY-STATE] ✅

### Open Action Items
- ❌ **Gap #9:** Expand API + mobile for all chart sections (P1)

---

## PAGE 5 — Coupon Analytics

**Web:** `GET /coupons/` → `coupon/dashboard.html`  
**Mobile:** `CouponPage` → `GET /analytics/coupon/`  
**File:** `semir-phone/lib/features/analytics/coupon/coupon_page.dart`

### [PAGE-EXISTS] ✅

### [DATA] ✅

| Data Field | Web | Mobile | Status |
|-----------|-----|--------|--------|
| All-Time KPIs (6 cards) | Total, Used, Unused, Total Amt, Coupon Amt, Unique Inv Amt | `all_time_kpis.*` | ✅ |
| Period KPIs (6 cards) | same | `period_kpis.*` | ✅ |
| Tab By Shop | shop_name, used, pct, coupon_amount, total_amount | `tabs.by_shop` | ✅ |
| Tab Detail | Coupon ID, Status, Amount, Shop, Date | `tabs.detail` | ✅ |
| Tab Duplicates | Invoice, Count, Coupons | `tabs.duplicates` | ✅ |
| Coupon prefix filter | ✅ | ✅ `couponPrefixProvider` | ✅ |
| Shop group filter | ✅ | ✅ `ShopGroupFilter` | ✅ |
| Tab 0 key-safety | — | ✅ **Fixed** Sprint 1 | ✅ |

### [UI] ✅ — minor gap: no campaign selector

| UI Element | Web | Mobile | Status |
|-----------|-----|--------|--------|
| All-Time + Period KPI rows | ✅ | ✅ | ✅ |
| Prefix filter | ✅ | ✅ `TextField` | ✅ |
| Shop group filter | ✅ | ✅ `ShopGroupFilter` | ✅ |
| Campaign selector | ✅ dropdown | ❌ Missing | **⚠️ Gap #17** |
| By Shop / Detail / Duplicates tabs | ✅ | ✅ `DataTableWidget` | ✅ |

### [EMPTY-STATE] ✅
### [TEST] ✅ 7 widget tests

### Open Action Items
- ⚠️ **Gap #17:** Add campaign selector dropdown (P2)

---

## PAGE 6 — Coupon Charts

**Web:** `GET /coupons/chart/` → `coupon/chart.html`  
**Mobile:** `CouponChartPage` → `GET /charts/coupon/`  
**File:** `semir-phone/lib/features/charts/coupon_chart_page.dart`

### [PAGE-EXISTS] ✅

### [DATA/UI] ⚠️ Same structural gaps as SalesChartPage

- Web `coupon/chart.html` has same structure: Overview donuts + Shop Trends multi-series chart + data tables
- Mobile `coupon_chart_page.dart`: only donuts + single trend line
- **Gap #10:** All chart structural gaps apply

### [TEST] ✅ 4 tests
### [EMPTY-STATE] ✅

### Open Action Items
- ❌ **Gap #10:** Expand API + mobile for all chart sections (P1)

---

## PAGE 7 — Shop Detail

**Web:** `GET /shop-detail/` → `shop_detail.html`  
**Mobile:** `ShopDetailPage` → `GET /analytics/shop-detail/`  
**File:** `semir-phone/lib/features/analytics/shop_detail/shop_detail_page.dart`

### [PAGE-EXISTS] ✅

### [DATA] ✅

| Data Field | Web | Mobile | Status |
|-----------|-----|--------|--------|
| Sales: All-Time + Period KPIs | ✅ | ✅ `ShopSalesPayload` | ✅ |
| Sales: by_session/by_month/by_week tabs | ✅ | ✅ via `tabs` | ✅ |
| Customer: All-Time + Period KPIs | ✅ | ✅ `ShopCustomerPayload` | ✅ |
| Customer: by_season/by_month/by_week tabs | ✅ | ✅ via `tabs` | ✅ |
| Customer: Zalo Active list | ✅ | ✅ `zaloActiveTable` | ✅ |
| Coupon: KPIs | ✅ | ✅ `ShopCouponPayload` | ✅ |
| Coupon: Detail table | ✅ | ✅ `detailTable` | ✅ |

### [UI] ✅

| UI Element | Web | Mobile | Status |
|-----------|-----|--------|--------|
| Shop dropdown | 3 separate selectors per section | ✅ 1 unified dropdown (accepted simplification) | ✅ |
| Date filter | ✅ | ✅ `DateFilterBar` | ✅ |
| Section tabs (Sales/Customers/Coupon) | ✅ | ✅ | ✅ |
| Sales KPI + tabs | ✅ | ✅ | ✅ |
| Customer KPI + tabs + Zalo Active | ✅ | ✅ | ✅ |
| Coupon KPI + detail table | ✅ | ✅ | ✅ |
| Coupon: Prefix filter + Campaign filter | ✅ per section | ❌ Not on mobile coupon tab | ⚠️ accepted simplification |

### [EMPTY-STATE] ✅ "Please select a store to view details"
### [TEST] ✅ 7 widget tests

### Open Action Items
None (coupon section filter omission accepted as mobile simplification).

---

## PAGE 8 — Customer Detail

**Web:** `GET /customer/detail/` → `customer/detail.html`  
**Mobile:** `CustomerDetailPage` → `GET /analytics/customer-detail/`  
**File:** `semir-phone/lib/features/analytics/customer_detail/customer_detail_page.dart`

### [PAGE-EXISTS] ✅

### [DATA] ⚠️ Multiple fields missing from API + mobile

| Data Field | Web template renders | API returns | Mobile renders | Status |
|-----------|---------------------|-------------|----------------|--------|
| Name | ✅ | ✅ `name` | ✅ | ✅ |
| Phone (masked) | ✅ | ✅ `phone` | ✅ | ✅ |
| VIP ID | ✅ | ✅ `vip_id` | ✅ | ✅ |
| Grade | ✅ | ✅ `grade` | ✅ | ✅ |
| Registration Store | ✅ | ✅ `registration_store` | ✅ | ✅ |
| Registration Date | ✅ | ✅ `registration_date` | ✅ | ✅ |
| CNV Sync status | ✅ | ✅ `cnv_sync_status` | ✅ | ✅ |
| Email | ✅ | ✅ `email` | ✅ | ✅ |
| **Zalo Active Date** | ✅ `detail.html:204-213` | ❌ Not in API | ❌ | **❌ Gap #13** |
| **Loyalty Points (POS)** | ✅ `detail.html:215-219` | ❌ Not in API | ❌ | **❌ Gap #14** |
| **Loyalty Points (CNV)** | ✅ `detail.html:220-224` | ❌ Not in API | ❌ | **❌ Gap #14** |
| Stats: Total Purchases | ✅ | ✅ as `total_invoices` | ✅ | ✅ |
| Stats: Total Amount | ✅ | ✅ as `total_revenue` | ✅ | ✅ |
| Stats: **Last Purchase Date** | ✅ `detail.html:247-249` | ❌ Not in API | ❌ | **❌ Gap #15** |
| Invoice: Invoice No | ✅ | ✅ `invoice_id` | ✅ | ✅ |
| Invoice: Sales Date | ✅ | ✅ `date` | ✅ | ✅ |
| Invoice: Shop | ✅ | ✅ `shop` | ✅ | ✅ |
| Invoice: Amount | ✅ | ✅ `amount` | ✅ | ✅ |
| Invoice: **Coupon ID** | ✅ `detail.html:285-291` | ❌ Not in API | ❌ | **❌ Gap #16** |
| Invoice: **Face Value** | ✅ `detail.html:292-299` | ❌ Not in API | ❌ | **❌ Gap #16** |
| Invoice: **Coupon Amount** | ✅ `detail.html:300-306` | ❌ Not in API | ❌ | **❌ Gap #16** |

### [UI] ⚠️

| UI Element | Web | Mobile | Status |
|-----------|-----|--------|--------|
| Search by VIP ID | ✅ | ✅ | ✅ |
| Search by Phone | ✅ | ✅ | ✅ |
| Profile card (core fields) | ✅ | ✅ | ✅ |
| Registration Store + Date | ✅ | ✅ | ✅ |
| CNV sync icon | ✅ | ✅ | ✅ |
| Email field | ✅ | ✅ | ✅ |
| **Zalo Active Date** | ✅ | ❌ Missing | **❌ Gap #13** |
| **Loyalty Points (POS + CNV)** | ✅ | ❌ Missing | **❌ Gap #14** |
| KPIs (Total Invoices, Revenue) | ✅ | ✅ 2 `KpiCard`s | ✅ |
| **Last Purchase Date** | ✅ | ❌ Missing | **❌ Gap #15** |
| Invoice table (7 cols) | ✅ | ⚠️ 4 cols (missing Coupon, Face Value, Coupon Amt) | **⚠️ Gap #16** |
| Not found state | ✅ | ✅ `_NotFoundBanner` | ✅ |

### [EMPTY-STATE] ✅
### [TEST] ✅ 15 widget tests

### Open Action Items
- ❌ **Gap #13:** Add Zalo Active Date to API + mobile (P2)
- ❌ **Gap #14:** Add POS/CNV Loyalty Points to API + mobile (P2)
- ❌ **Gap #15:** Add Last Purchase Date to API + mobile (P2)
- ❌ **Gap #16:** Add Coupon ID, Face Value, Coupon Amount to invoice table (P2)

---

## Rollout Status

### Phase 1 — Critical Fixes (P0) ✅ COMPLETE (Sprint 1)
- [x] Fix Customer `comparison` key bug → `customer_comparison`
- [x] Fix CustomerDetail `fromJson` flat response parsing + add `name` to API
- [x] Fix `registrationStore`, `registrationDate`, `cnvSyncStatus` fields

### Phase 2 — Feature Completeness Sprint 1 (P1) ✅ COMPLETE
- [x] Add `by_season` + `by_week` to CustomerAnalytics API + mobile tabs (5 tabs)
- [x] All chart fixes: donut format, trend format, RangeError guard, DateFilterBar, TrendLineChart
- [x] AllShops tabs for Sales, Zalo tab for Customer, Zalo Active for ShopDetail, email for CustomerDetail

### Phase 3 — Test Coverage Sprint 1 (P1) ✅ COMPLETE
- [x] `flutter test`: **226/226 passing**
- [x] `python manage.py test tests.test_api`: **57/57 passing**

### Phase 4 — Sprint 2 P1 Gaps ❌ PENDING
- [ ] SalesPage: Buyer Without Info section (API + mobile)
- [ ] SalesPage: Customer Details table (API + mobile)
- [ ] All 3 Chart pages: expand API to full donut set + data tables + multi-series trend + bar chart

### Phase 5 — Sprint 2 P2 Gaps ❌ PENDING
- [ ] CustomerPage: all-shops breakdown tabs + Points Analysis tab
- [ ] CustomerDetailPage: Zalo date, loyalty points, last purchase, invoice 7 cols
- [ ] CouponPage: campaign selector filter

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
