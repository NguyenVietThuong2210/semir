# Tasks: Permission Group Redesign

**Input**: Design documents from `specs/001-permission-group-redesign/`  
**Branch**: `001-permission-group-redesign`  
**Spec**: [spec.md](spec.md) | **Plan**: [plan.md](plan.md) | **Data model**: [data-model.md](data-model.md)

**Organization**: Tasks grouped by user story to enable independent implementation and testing.  
**Tests**: Included for perm sync (constitution IV mandates ≥1 green test per URL; user_management already covered in `tests/test_pages.py:95`).

## Format: `[ID] [P?] [Story] Description`

- **[P]**: Can run in parallel (different files, no dependencies)
- **[Story]**: Which user story this task belongs to
- Exact file paths included in all task descriptions

---

## Phase 1: Setup

**Purpose**: No new infrastructure required — existing Django project. Single verification step.

- [x] T001 Confirm dev environment: run `cd SemirDashboard && python manage.py test tests -v 2` — all tests must be green before any changes

---

## Phase 2: Foundational (Blocking Prerequisites)

**Purpose**: Update the permission source-of-truth. ALL user story phases depend on this — no US work begins until T002 and T003 are complete.

**⚠️ CRITICAL**: US1, US2, and US3 all read from `PERMISSION_DEFS` and `PERM_RENAMES`. Complete this phase first.

- [x] T002 [P] Update `PERMISSION_DEFS` (replace all 20 tuples with new codenames, labels, domain groups) and set `VIEWER_PERMISSIONS = ["sales.view"]` in `SemirDashboard/App/permissions.py`. Use the exact table from [data-model.md](data-model.md). `ADMIN_PERMISSIONS = ALL_PERMISSIONS` auto-derives — no separate change.

- [x] T003 [P] Add all 20 one-to-one entries to `PERM_RENAMES` dict in `SemirDashboard/App/management/commands/perm.py` (line 57), keeping the existing `'page_cnv': ['page_cnv_sync', 'page_cnv_comparison']` entry first. Use the exact dict from [data-model.md](data-model.md).

**Checkpoint**: `PERMISSION_DEFS` now has 7 domain groups. `PERM_RENAMES` has 21 entries total. Running `perm show` will show the updated definitions; `perm sync` will migrate roles. User story work can begin.

---

## Phase 3: User Story 1 — Domain-Grouped Display (Priority: P1) 🎯 MVP

**Goal**: The role management page at `/users/` shows permissions grouped under 7 domain headers instead of 3 flat categories. Each checkbox label uniquely identifies its action within the group.

**Independent Test**: Open `/users/` → Roles tab → open any role card. Confirm 7 section headers: "Sales Analytics", "Coupons", "CNV / Customer Analytics", "Customers", "Shop Detail", "Data Management", "Admin". Confirm zero occurrences of "Pages" or "Downloads" headings.

> **Note**: T002 (Foundational) already delivers the domain grouping — `users.py` builds `permission_categories` from `PERMISSION_DEFS[2]` and the template iterates it. Tasks T004–T012 are the mandatory call-site updates (FR-005). They can all run in parallel with each other.

### Implementation for User Story 1

- [x] T004 [P] [US1] Update `@requires_perm` codenames in `SemirDashboard/App/views/analytics.py` (5 occurrences):
  - `"page_analytics"` → `"sales.view"` (×2, lines 30, 84)
  - `"page_chart"` → `"sales.chart"` (line 121)
  - `"download_analytics"` → `"sales.export"` (line 185)
  - `"download_chart_excel"` → `"sales.export_chart"` (line 232)

- [x] T005 [P] [US1] Update `@requires_perm` codenames in `SemirDashboard/App/views/coupon.py` (6 occurrences):
  - `"page_coupons"` → `"coupons.view"` (×2, lines 29, 87)
  - `"download_coupons"` → `"coupons.export"` (line 125)
  - `"page_coupon_chart"` → `"coupons.chart"` (line 178)
  - `"manage_campaigns"` → `"coupons.manage"` (line 222)
  - `"download_coupon_chart_excel"` → `"coupons.export_chart"` (line 320)

- [x] T006 [P] [US1] Update `@requires_perm` in `SemirDashboard/App/views/customer.py` (1 occurrence):
  - `"page_customer_detail"` → `"customers.detail"` (line 15)

- [x] T007 [P] [US1] Update `@requires_perm` (×4) and `_ajax_perm_check` (×3) in `SemirDashboard/App/views/shop_detail.py` (5 unique codenames, 7 total occurrences):
  - `"page_shop_detail"` → `"shops.view"` (lines 84, 123, 144, 163)
  - `"download_shop_detail"` → `"shops.export"` (line 198)

- [x] T008 [P] [US1] Update `@requires_perm` in `SemirDashboard/App/views/upload.py` (6 occurrences, all same codename):
  - `"page_upload"` → `"data.upload"` (lines 65, 99, 118, 142, 160, 170)

- [x] T009 [P] [US1] Update `@requires_perm` in `SemirDashboard/App/views/users.py` (1 occurrence):
  - `"manage_users"` → `"admin.users"` (line 17)

- [x] T010 [P] [US1] Update `@requires_perm` in `SemirDashboard/App/views/home.py` (1 occurrence):
  - `"page_formulas"` → `"data.formulas"` (line 13)

- [x] T011 [P] [US1] Update `@requires_perm` codenames in `SemirDashboard/App/cnv/views.py` (10 occurrences):
  - `"page_cnv_sync"` → `"cnv.sync"` (×4, lines 28, 285, 356, 429)
  - `"page_cnv_comparison"` → `"cnv.view"` (×2, lines 85, 186)
  - `"download_cnv"` → `"cnv.export"` (line 218)
  - `"page_customer_chart"` → `"cnv.chart"` (line 644)
  - `"download_customer_chart_excel"` → `"cnv.export_chart"` (line 693)

- [x] T012 [P] [US1] Update all `{% check_perm %}` tags in 30 HTML templates. Run `grep -rn "check_perm" SemirDashboard/App/templates/` to find every occurrence, then apply the full migration map. Template groups:
  - `analytics/` (8 files): `page_analytics`→`sales.view`, `page_chart`→`sales.chart`, `download_analytics`→`sales.export`, `download_chart_excel`→`sales.export_chart`
  - `coupon/` (4 files): `page_coupons`→`coupons.view`, `page_coupon_chart`→`coupons.chart`, `download_coupons`→`coupons.export`, `download_coupon_chart_excel`→`coupons.export_chart`, `manage_campaigns`→`coupons.manage`
  - `cnv/` (11 files): `page_cnv_comparison`→`cnv.view`, `page_customer_chart`→`cnv.chart`, `page_cnv_sync`→`cnv.sync`, `download_cnv`→`cnv.export`, `download_customer_chart_excel`→`cnv.export_chart`
  - `base.html`, `home.html`, `shop_detail/` (3 files), `upload/coupons.html`: apply matching renames from the migration map
  - After editing: run `grep -rn "page_\|download_\|manage_users\|manage_campaigns" App/templates/` — must return zero matches for old codenames

**Checkpoint**: All 3 call-site types updated (FR-005). Start dev server; open `/users/` and confirm 7 domain group headers with correct labels. No old codenames anywhere in Python views or templates.

---

## Phase 4: User Story 2 — Automatic Migration (Priority: P1)

**Goal**: `python manage.py perm sync` migrates all existing roles to new codenames with zero data loss, requiring no manual admin reconfiguration.

**Independent Test**: Create a test role with old codenames, run `_sync()`, verify the role now holds new codenames per the migration map. Run sync a second time — role unchanged (idempotency).

### Tests for User Story 2

- [x] T013 [US2] Write integration tests for `perm sync` in `SemirDashboard/tests/test_perm_management.py` (new file). Use `TestCase` (no fixture data needed). Four scenarios:
  1. **Custom role rename**: Create role with `["page_analytics", "download_coupons"]` → call `Command()._sync()` → assert `role.permissions == ["sales.view", "coupons.export"]`
  2. **Admin role overwrite**: After sync, `admin` role has exactly all 20 new codenames — no more, no less
  3. **Viewer role overwrite**: After sync, `viewer` role has exactly `["sales.view"]`
  4. **Idempotency**: Run `_sync()` twice — second call changes nothing (no save calls trigger, role.permissions unchanged)

### Implementation Verification for User Story 2

- [x] T014 [US2] Run `perm sync` in dev environment and verify output: `cd SemirDashboard && python manage.py perm show && python manage.py perm sync && python manage.py perm show`. Confirm: (a) each role shows "migrated" or "OK" messages, (b) second `perm show` output has zero old codenames, (c) `admin` role lists all 20 new codenames.

**Checkpoint**: `perm sync` is verified working. T013 tests pass. Second sync run produces no output changes (idempotency confirmed).

---

## Phase 5: User Story 3 — Group Toggle UI (Priority: P2)

**Goal**: Admin clicks a domain group header checkbox to toggle all permissions in that group at once. Header shows indeterminate state when only some permissions in the group are checked.

**Independent Test**: Open role card → click "Coupons" group header checkbox → all 5 coupon permission checkboxes change state → manually uncheck 2 of the 5 → "Coupons" header shows browser indeterminate state (half-filled) → click "Save Permissions" → role persists exactly the 3 checked coupon permissions.

### Implementation for User Story 3

- [x] T015 [US3] Add `data-group="<domain>"` attribute to every permission `<input type="checkbox">` in `SemirDashboard/App/templates/user_management.html` (line ~161, inside the `{% for category, perms in permission_categories.items %}` loop). Add a group-level `<input type="checkbox" class="perm-group-toggle" data-group="{{ category }}">` element inside each category header (line ~157, the `<p class="fw-semibold">` header). The group toggle checkbox is NOT submitted to `perm_{{ role.pk }}` — it is a UI-only control.

- [x] T016 [US3] Add a `<script>` block to `SemirDashboard/App/templates/user_management.html` implementing group toggle logic (scoped per role card so multiple open cards don't interfere):
  - **On group header click**: Find all `[name="perm_{{ role.pk }}"][data-group="<domain>"]` checkboxes within the same card, set `.checked = header.checked` for each.
  - **On any child checkbox change**: Count checked vs total within same card+group. If all checked → header `.checked=true, .indeterminate=false`. If none → `.checked=false, .indeterminate=false`. If some → `.indeterminate=true`.
  - **On page load (DOMContentLoaded)**: Evaluate and set indeterminate state for every group header across all role cards based on the pre-rendered checkbox state.

**Checkpoint**: Group toggle works at 1366×768, 100% zoom (SC-005). Two-action flow: 1 group toggle + 1 Save Permissions = role configured for a full domain (SC-002).

---

## Phase 6: Polish & Cross-Cutting Concerns

- [x] T017 [P] Update `docs/project_business_logic.md` — replace the 20-permission table with the new 7-domain grouped table (per Constitution II: "New permissions MUST be documented in docs/project_business_logic.md"). Use the table from [data-model.md](data-model.md).

- [x] T018 Run full test suite: `cd SemirDashboard && python manage.py test tests -v 2`. All tests must be green. Zero snapshot diffs from this feature (permission changes don't affect analytics data shapes).

- [x] T019 [P] Sanity grep: `grep -rn "page_analytics\|page_chart\|page_coupons\|page_coupon_chart\|page_cnv\|page_customer\|page_shop\|page_upload\|page_formulas\|download_analytics\|download_chart_excel\|download_coupons\|download_coupon_chart\|download_cnv\|download_customer\|download_shop\|manage_campaigns\|manage_users" SemirDashboard/App/ --include="*.py" --include="*.html"` — must return zero matches (confirms no old codenames remain in source).

---

## Dependencies & Execution Order

### Phase Dependencies

```
Phase 1 (Setup/Verify)
    ↓
Phase 2 (Foundational: T002, T003) ← BLOCKS everything
    ↓
Phase 3 (US1: T004–T012)    Phase 4 (US2: T013–T014)
    ↓                              ↓
Phase 5 (US3: T015–T016)  ← needs Phase 3 complete (template work builds on Phase 3)
    ↓
Phase 6 (Polish: T017–T019)
```

### User Story Dependencies

- **US2 (migration)**: Depends only on Foundational (T002, T003). Can be implemented alongside US1.
- **US1 (grouped display)**: Depends on Foundational (T002, T003).
- **US3 (group toggle)**: Depends on US1 being complete (adds JS to the template modified in US1 Phase 3).

### Within Phase 3 (US1)

All of T004–T012 can run in parallel — they touch different files. T004–T011 are Python view files. T012 is templates. No conflicts.

---

## Parallel Execution Examples

### Phase 2 (Foundational) — run together

```
T002: Update App/permissions.py (PERMISSION_DEFS + VIEWER_PERMISSIONS)
T003: Update App/management/commands/perm.py (PERM_RENAMES)
```

### Phase 3 (US1) — run all together after Phase 2

```
T004: App/views/analytics.py
T005: App/views/coupon.py
T006: App/views/customer.py
T007: App/views/shop_detail.py
T008: App/views/upload.py
T009: App/views/users.py
T010: App/views/home.py
T011: App/cnv/views.py
T012: App/templates/**/*.html (30 files)
```

---

## Implementation Strategy

### MVP (US1 + US2 — P1 stories only)

1. T001 — verify green baseline
2. T002 + T003 — Foundational (parallel)
3. T004–T012 — US1 view + template updates (all parallel)
4. T013 + T014 — US2 perm sync tests + verification
5. T017–T019 — Polish
6. **STOP and VALIDATE**: Open `/users/` — confirm 7 domain groups. Run `perm sync` — confirm output correct.

### Incremental delivery

1. MVP → deploy → verify 7 domain groups and migration work (US1 + US2)
2. Add group toggle (US3) → deploy → verify two-action role config works

### Execution summary

| Phase | Tasks | Parallel? | Blocks |
|-------|-------|-----------|--------|
| 1 | T001 | — | — |
| 2 | T002, T003 | ✅ with each other | US1, US2, US3 |
| 3 (US1) | T004–T012 | ✅ all parallel | US3 |
| 4 (US2) | T013, T014 | sequential (T013→T014) | — |
| 5 (US3) | T015, T016 | sequential (T015→T016) | — |
| 6 | T017, T018, T019 | T017+T019 parallel; T018 last | — |

**Total: 19 tasks** (T001–T019)
