---
name: "mapping-mobile"
description: "Senior QA/PM parity audit: verify every Web page has 1:1 data, UI, and test coverage on Mobile. Fixes gaps, runs tests, writes report, self-improves."
argument-hint: "Optional: page name to focus on (e.g. 'shop_detail'), or 'quick' for summary-only"
---

## Role

You are a Senior QA/PM Engineer performing a **Web ↔ Mobile parity audit** for SemirDashboard + SemirPhone.

Your job: for every Web page, verify the Mobile equivalent has identical data, correct UI, and full test coverage.
Fix every gap you find. Do not skip steps. Document everything.

---

## Self-Learning Protocol (read before starting)

Before each run, read this SKILL.md to absorb all known bug patterns and lessons from prior runs.
After each run, update this file with new findings (Step 7).
The skill becomes smarter each sprint.

---

## Step 0 — Read prior reports

Read these files to understand current state before starting:

- `docs/mobile_web_mapping_checklist.md` — the canonical parity checklist
- `docs/FINAL_REPORT.md` — latest QA verdict
- `docs/project_mobile.md` — route table, provider rules, test structure

Note the last sprint date, test counts (Flutter + Django API), and any open action items.

---

## Step 1 — Discover page inventory (dynamic, never hardcode)

**Do NOT use a hardcoded list.** Discover dynamically:

### Web pages
Read `SemirDashboard/App/urls.py` and `SemirDashboard/App/cnv/urls.py`.
Extract every GET-accessible page route (exclude AJAX partials, exports, auth endpoints).

For each web page record:
- URL pattern
- View function + file
- Template file
- Key data fields rendered (read the view source)

### Mobile pages
Read `semir-phone/lib/app.dart`.
Extract every `GoRoute(path: ...)`.

For each mobile page record:
- Route path
- Page widget + file
- Provider + service file (from `lib/features/*/`)
- API endpoint it calls (read the service file)

### Build the mapping table
Match Web ↔ Mobile by feature area. Flag any Web page with no Mobile equivalent (gap) or Mobile route with no Web counterpart (orphan).

---

## Step 2 — Per-page parity audit

**MANDATORY read order for each page — do not skip any layer:**

```
1. Web template file (App/templates/…)           ← what the web ACTUALLY renders
2. Web view function (App/views/… or cnv/views)  ← what data the view passes to template
3. Django API view (App/api/views.py)             ← what JSON the API returns
4. Mobile service file (*_service.dart)           ← what fromJson parses
5. Mobile page widget file (*_page.dart)          ← what the widget ACTUALLY shows
```

Reading only steps 3+4 causes missed gaps — the web template shows sections the API view may not expose,
and the mobile page widget may not render fields that fromJson correctly parses.

For each mapped Web ↔ Mobile pair, check all 5 dimensions:

### [PAGE-EXISTS]
- Mobile route registered in GoRouter ✅/❌
- Mobile Dart file exists ✅/❌
- Provider + service files exist ✅/❌

### [DATA]
Read layers 1–5 above for this page.

**Web template audit first:**
Read the web HTML template. Extract every distinct section, card, table, and data field it renders.
Build a checklist: `[section/field] → present in template?`

**Then trace the chain for each item:**
1. Does the Django view pass it to template context?
2. Does the Django API view return it in the JSON response?
3. Does the mobile service `fromJson` parse it?
4. Does the mobile page widget actually render it?

All four must be ✅. Any broken link = **DATA GAP**.

**Known data gap patterns (from prior sprints — check these first):**
| Pattern | Description |
|---------|-------------|
| JSON key mismatch | API returns `customer_comparison`, mobile reads `comparison` → always empty |
| Nested vs flat | API returns flat dict, mobile tries to read `json['customer']['field']` → null |
| Type mismatch | API returns `int`, mobile casts to `String?` → null |
| Missing field | API never added field (e.g. `name`, `email`) — mobile gets empty string |
| Missing tab key | API response missing `by_season` / `by_week` → tab never populates |
| List parsed as Map | API returns `donuts` as `List`, mobile reads as `Map<String, dynamic>?` → always null |
| Pre-formatting missing | API returns raw `int` for display value, mobile needs formatted string |
| `percentage` field absent | API never computes `round(count/total*100, 1)` → donut percentages 0.0 |
| allshops_tabs absent | API missing `allshops_tabs` key when `shop_group` is set |
| zalo_active absent | API missing `zalo_active` table in shop-detail customer section |
| Section missing from API | Web template renders section (e.g. "Buyer Without Info") that API never exposes |
| Section parsed but not rendered | fromJson parses field correctly but page widget has no Widget for it |

### [UI]
Read the **web template** first, then the **mobile page Dart file**.

**Method:** Go section-by-section through the web template. For each section/card/table in the web:
- Does the mobile page widget have a corresponding Widget subtree?
- If yes: does it use the same data? Same column headers? Same row structure?
- Does it handle loading / error / empty states?
- Does it use `const` constructors where possible?

Do NOT infer from the checklist document — read the actual files.

**UI completeness checklist per page:**
- [ ] Date range filter (`DateFilterBar`)
- [ ] Shop group filter (`ShopGroupFilter`) — where applicable
- [ ] All-Time KPI cards (verify count and label match web)
- [ ] Period KPI cards (verify count and label match web)
- [ ] Tab sections (lazy-loaded `DataTableWidget`) — verify tab count, labels, column headers
- [ ] All extra sections (e.g. "Buyer Without Info", "All Shops Comparison") — check web template explicitly
- [ ] Chart widgets (donut, trend) — verify title, slice count, trend presence matches web
- [ ] Pull-to-refresh (`PullToRefresh`)
- [ ] Loading overlay
- [ ] Error banner
- [ ] Empty state (`Center(child: Text('No data'))` or equivalent)

**Known UI gap patterns:**
| Pattern | Description |
|---------|-------------|
| Chart pages missing `DateFilterBar` | chart pages 2/4/6 had no date filter before sprint |
| Chart pages missing `TrendLineChart` | placeholder `Container` instead of real fl_chart widget |
| Tab key-lookup bug | `tabs.first` instead of `tabKey == 'by_shop'` → wrong tab shown |
| Missing `RangeError` guard | fl_chart returns `-1` for `touchedSectionIndex` on gap touch → crash |
| Missing Zalo Active table | Shop Detail customer section had no Zalo Active rendering |
| Missing email row | Customer Detail profile card missing email field |
| Non-const static widgets | `_Logo()` without `const` constructor — lost optimization |
| Section in web template not in mobile | Web has "Buyer Without Info" section → mobile page has no equivalent widget |
| Chart detail page missing sections | Web chart detail page shows breakdown table below chart → mobile page has no table |

**Known UI gap patterns:**
| Pattern | Description |
|---------|-------------|
| Chart pages missing `DateFilterBar` | chart pages 2/4/6 had no date filter before sprint |
| Chart pages missing `TrendLineChart` | placeholder `Container` instead of real fl_chart widget |
| Tab key-lookup bug | `tabs.first` instead of `tabKey == 'by_shop'` → wrong tab shown |
| Missing `RangeError` guard | fl_chart returns `-1` for `touchedSectionIndex` on gap touch → crash |
| Missing Zalo Active table | Shop Detail customer section had no Zalo Active rendering |
| Missing email row | Customer Detail profile card missing email field |
| Non-const static widgets | `_Logo()` without `const` constructor — lost optimization |

### [TEST]
Read `semir-phone/test/widget/` and `semir-phone/test/unit/`.

For each page, verify these tests exist:
- [ ] Loading state test
- [ ] Error state test
- [ ] Null / empty payload test → "No data" or empty shown, not crash
- [ ] Data state test (key fields rendered)
- [ ] Navigation / interaction test (where applicable)
- [ ] Golden snapshot test (for pages with significant UI)

For each service, verify:
- [ ] `fromJson` happy path test
- [ ] Empty / null field handling test
- [ ] Type edge case test (int cast, missing key)

**Minimum test counts per page (from last audit — use as floor, not ceiling):**
| Page | Widget tests | Notes |
|------|-------------|-------|
| SalesPage | 4 | + golden |
| SalesChartPage | 7 | loading, error, null, donut count, no trend, trend visible, legend |
| CustomerPage | 8 | |
| CustomerChartPage | 4 | |
| CouponPage | 7 | includes null payload + tab 0 |
| CouponChartPage | 4 | |
| ShopDetailPage | 7 | |
| CustomerDetailPage | 15 | full profile, phone masked, CNV states, email show/hide |

### [API-ENDPOINT]
For each mobile API call, verify the Django endpoint exists and returns the expected shape:
- Run: `python manage.py test tests.test_api -v 2` — must be all green
- Check `tests/snapshots/api_*_shape.json` — field list must match mobile service `fromJson`

### [EMPTY-STATE]
Test the `null payload` path. When API returns no data or errors:
- Mobile must show a graceful empty state, not a crash or blank screen
- Standard pattern: `payload == null ? Center(child: Text('No data')) : _buildContent(payload!)`

---

## Step 3 — Submit plan + checklist for approval (REQUIRED before any fix)

**Do NOT implement any fix until the user approves the plan.**

After completing Step 2, produce two artifacts and present them to the user:

### 3a — Fix Plan

A table of every gap found, sorted by priority:

```markdown
## Parity Audit — Fix Plan

| # | Priority | Page | Dimension | Gap description | Proposed fix |
|---|----------|------|-----------|-----------------|--------------|
| 1 | P0 | CustomerPage | DATA | `customer_comparison` key mismatch → always empty | API: rename key; Mobile: update fromJson |
| 2 | P1 | SalesChartPage | UI | Missing `TrendLineChart` widget | Add fl_chart widget replacing placeholder Container |
| ... | | | | | |
```

### 3b — Sprint Checklist

A checklist the user can tick off, grouped by priority:

```markdown
## Sprint Checklist — [DATE]

### P0 — Data Silent Failures (fix first)
- [ ] [PageName] [DATA] Short description of gap
- [ ] ...

### P1 — Missing Features (fix after P0)
- [ ] [PageName] [UI/TEST] Short description
- [ ] ...

### P2 — UI Polish (fix last)
- [ ] [PageName] [UI] Short description
- [ ] ...

### Tests to add / update
- [ ] [PageName] Add/update [test type] test for [gap fixed]
- [ ] ...

**Total gaps:** N (P0: X, P1: Y, P2: Z)
**Estimated test delta:** +N tests
```

### 3c — Wait for approval

After presenting the plan and checklist, **stop and wait**.

Say exactly:
> "Plan and checklist above. Reply **'go'** (or approve specific items) to start fixing, or **'skip [#]'** to exclude items."

- If the user replies `go` or `approve` → proceed to Step 3d with the full plan
- If the user replies `skip 3, 5` → remove those items, confirm updated scope, then proceed
- If the user replies `only P0` → fix only P0 items, then re-present checklist for P1 approval
- Do NOT begin any code changes before receiving an explicit go signal

### 3d — Execute approved fixes

For every approved gap, implement the fix.

**Fix priority (if full plan approved):**
1. **P0 — Data silent failures** (field always null/empty, comparison tabs always empty) — fix first
2. **P1 — Missing features** (tab not wired, section not rendered) — fix second
3. **P2 — UI polish** (missing empty state, missing const, wrong icon) — fix third

**Fix rules:**
- Backend fix: add field to Django API view JSON response
- Mobile fix: add field to service `fromJson`, add display in page widget
- Always add or update tests when fixing a data gap
- Never fix a P2 before all P0 and P1 are done
- After each fix, tick the corresponding checklist item ✅ and report it to the user

---

## Step 4 — Run full test suite

Kill stale processes first:

```powershell
Get-WmiObject Win32_Process | Where-Object {
    $_.CommandLine -like "*manage.py test*" -and $_.CommandLine -notlike "*powershell*"
} | ForEach-Object { Stop-Process -Id $_.ProcessId -Force -ErrorAction SilentlyContinue }
```

Then run in this order:

```bash
# Django API parity tests (fastest gate — run first)
cd SemirDashboard
python manage.py test tests.test_api -v 2 2>&1

# Django full suite (run once, no background)
python manage.py test tests -v 2 2>&1

# Flutter analyze (0 errors required)
cd semir-phone
flutter analyze 2>&1

# Flutter full test suite
flutter test --reporter expanded 2>&1
```

**Acceptance gates (all must pass before Step 5):**
- Django API tests: all green
- Django full suite: all green (skipped ≤ pre-existing count)
- Flutter analyze: 0 errors
- Flutter tests: all green, count ≥ previous count

**Failure isolation rule:**
If a test fails in the full suite but passes in isolation → shared cache/state issue, not a code bug.
Document as known limitation. Add `cache.clear()` in `tearDown` if appropriate.

---

## Step 5 — Update `docs/mobile_web_mapping_checklist.md`

Rewrite the checklist to reflect current state. Structure:

```markdown
# Mobile ↔ Web Mapping Checklist
**Last updated:** YYYY-MM-DD (sprint sign-off)
**Flutter test suite:** N/N passing
**Django API tests:** N/N passing

## Executive Summary table (8 pages × Data/UI/Tests/Status columns)

## Fixes Applied This Sprint
### P0 Fixes
### P1 Fixes
### P2 Fixes
### Test Fixes

## PAGE 1 — Sales Analytics
[PAGE-EXISTS] / [DATA] / [UI] / [TEST] / [EMPTY-STATE] / Open Action Items

... (repeat for all 8 pages)

## Rollout Status (Phase 1-5 checklist)

## Appendix — File Reference
```

Mark every item ✅ Done / ⚠️ Partial / ❌ Missing.
Every "Open Action Items" section must either list concrete next steps or say "None."

---

## Step 6 — Update all affected docs

| What changed | Doc to update |
|-------------|---------------|
| New mobile route | `docs/project_mobile.md` navigation table |
| New provider | `docs/project_mobile.md` provider rules + logout invalidation list |
| New API field added | `docs/project_urls.md` + snapshot JSON |
| Home card count changed | `docs/project_mobile.md` home card table |
| New test file | `docs/project_mobile.md` test structure section |
| Performance baseline changed | `docs/performance_report.md` |
| Flutter test count changed | `docs/mobile_web_mapping_checklist.md` header |
| Django API test count changed | `docs/mobile_web_mapping_checklist.md` header |
| Any structural change | `docs/project_structure.md` |

Verify `CLAUDE.md` commands are still accurate after any path/file changes.

---

## Step 7 — Self-improve this skill

After every sprint, read this SKILL.md and update it based on what happened.

**What to look for:**

| Situation | Update to make |
|-----------|---------------|
| New data gap pattern found | Add to the DATA gap patterns table in Step 2 |
| New UI gap pattern found | Add to the UI gap patterns table in Step 2 |
| New page added to the product | Add to minimum test count table in Step 2 |
| Test count floor raised | Update the minimum test counts table |
| A bug pattern is now impossible (refactored away) | Remove or mark as resolved from the patterns table |
| New doc consistency rule needed | Add to Step 6 table |
| Step command failed due to wrong path | Fix the command in place |
| A known false-fail test appeared | Add to Step 4 failure isolation rule |

**How to update:**

1. Read the current SKILL.md
2. Make targeted edits — do not rewrite working steps
3. Append a one-line entry to the changelog below

**Changelog** (append — do not delete prior entries):

| Date | Change |
|------|--------|
| 2026-05-06 | v1.0 created from `docs/mobile_web_mapping_checklist.md` sprint audit (2026-05-03 sign-off) |
| 2026-05-06 | Step 3 split into approval gate: audit → present Fix Plan + Sprint Checklist → wait for user `go` → execute fixes |
| 2026-05-06 | Step 2 [DATA] and [UI]: added mandatory 5-layer read order (web template → web view → API → service → mobile widget); API↔fromJson key-only scan caused missed gaps ("Buyer Without Info" section, chart detail page sections) |

---

## Pass Criteria (all must be true for Sprint Sign-off)

| Check | Requirement |
|-------|-------------|
| All 8 pages exist on mobile | ✅ |
| Data parity | Every Web field present in API response AND parsed in mobile `fromJson` AND displayed in widget |
| UI parity | Every Web UI element has mobile equivalent (accepted simplifications documented) |
| Empty states | All pages handle `null payload` gracefully |
| Widget tests | Count ≥ floor from Step 2 table |
| Unit tests | All service `fromJson` paths covered |
| Flutter analyze | 0 errors |
| Flutter tests | All green |
| Django API tests | All green |
| Checklist updated | `docs/mobile_web_mapping_checklist.md` accurate and dated |
| Docs consistent | `project_mobile.md`, `project_urls.md`, `project_structure.md` all accurate |
