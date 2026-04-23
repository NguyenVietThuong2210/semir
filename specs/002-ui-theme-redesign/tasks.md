# Tasks: Web UI Theme Redesign

**Input**: Design documents from `specs/002-ui-theme-redesign/`
**Branch**: `002-ui-theme-redesign`
**Spec**: [spec.md](spec.md) | **Plan**: [plan.md](plan.md) | **Research**: [research.md](research.md)

> No tests included — this is a CSS-only visual change. Regression is verified by running the existing Django test suite (all tests must pass unchanged) and the DevTools console snippet from [quickstart.md](quickstart.md).

---

## Phase 1: Setup

**Purpose**: No new files or dependencies needed. All changes are edits to existing template files.

- [X] T001 Read `SemirDashboard/App/templates/base.html` to confirm current CSS variable block and all 4 hardcoded purple RGBA locations before making any changes

---

## Phase 2: Foundational — CSS Variable Block

**Purpose**: Update the `:root` CSS variable block in `base.html`. This is the **single blocking prerequisite** — every other task depends on these variables being defined first.

**⚠️ CRITICAL**: No user story work begins until T002 is complete. All `var(--primary)`, `var(--accent)`, `var(--nav-bg)` references in later tasks rely on this block.

- [X] T002 Update `:root` CSS variable block in `SemirDashboard/App/templates/base.html` — replace `--primary: #667eea` with `--primary: #1a3c8c`, add `--primary-hover: #152d6e`, `--bs-primary: #1a3c8c`, `--bs-primary-rgb: 26, 60, 140`, `--accent: #00bcd4`, `--highlight: #ffc107`, `--nav-bg: #1e2535`

**Checkpoint**: `:root` block defines all 8 design tokens. All Bootstrap utilities (`btn-primary`, `bg-primary`, `text-primary`) now automatically resolve to navy.

---

## Phase 3: User Story 1 — Global Color Palette Applied (Priority: P1) 🎯 MVP

**Goal**: Every page inheriting `base.html` shows the navy theme with no purple tones — including navbar, button hover, form focus rings, and dropdown hover states.

**Independent Test**: Open any authenticated page. Inspect with DevTools. Run the console snippet from `quickstart.md` — result must be `✅ No purple remnants found`. Navbar is `#1e2535`, no purple gradient.

### Implementation

- [X] T003 [US1] Replace navbar style in `SemirDashboard/App/templates/base.html` — change `background: linear-gradient(135deg, #667eea 0%, #764ba2 100%) !important` to `background: var(--nav-bg) !important` and `box-shadow: 0 2px 8px rgba(102, 126, 234, .3)` to `box-shadow: 0 2px 8px rgba(30, 37, 53, 0.4)`
- [X] T004 [US1] Fix `.btn-primary:hover` in `SemirDashboard/App/templates/base.html` — replace `background: #5847d0` with `background: var(--primary-hover)`
- [X] T005 [US1] Fix form focus ring in `SemirDashboard/App/templates/base.html` — replace `box-shadow: 0 0 0 .2rem rgba(102, 126, 234, .15)` with `box-shadow: 0 0 0 .2rem rgba(26, 60, 140, 0.15)`
- [X] T006 [US1] Fix dropdown item hover in `SemirDashboard/App/templates/base.html` — replace `background: rgba(102, 126, 234, .1)` with `background: rgba(26, 60, 140, 0.08)`
- [X] T007 [P] [US1] Fix table header row RGBA in `SemirDashboard/App/templates/analytics/chart.html` — replace `background:rgba(102,126,234,.08)` with `background:rgba(26,60,140,0.08)`
- [X] T008 [P] [US1] Fix table header row RGBA in `SemirDashboard/App/templates/cnv/customer_chart.html` — replace `background:rgba(102,126,234,.08)` with `background:rgba(26,60,140,0.08)`

> T007 and T008 are parallel — different files, no shared dependencies.

**Checkpoint**: US1 complete. DevTools console snippet returns ✅ on all authenticated pages (except customer/detail and home which are fixed in US2/US3). Navbar is charcoal navy, no purple anywhere in base-level CSS.

---

## Phase 4: User Story 2 — KPI Cards Navy Blue (Priority: P2)

**Goal**: KPI summary cards on all dashboard pages display deep navy (`#1a3c8c`) background with white text. A reusable `.kpi-card` CSS class is introduced so templates apply it cleanly.

**Independent Test**: Open Analytics dashboard, Coupon dashboard, Shop Detail page. KPI cards show navy backgrounds with white text. Icons are visible (white or light-toned).

### Implementation

- [X] T009 [US2] Add `.kpi-card` CSS class to `SemirDashboard/App/templates/base.html` — insert new rule: `.kpi-card { background: var(--primary); color: #fff; }` and `.kpi-card .text-muted { color: rgba(255,255,255,0.75) !important; }`
- [X] T010 [US2] Update `SemirDashboard/App/templates/customer/detail.html` inline `<style>` block — replace all 4 hardcoded purple values: `linear-gradient(135deg, #667eea 0%, #764ba2 100%)` → `var(--primary)`, `border-left: 4px solid #667eea` → `border-left: 4px solid var(--primary)`, `color: #667eea` → `color: var(--primary)`, `background: #667eea` → `background: var(--primary)`
- [X] T011 [US2] Update 2 inline `style=` card-header attributes in `SemirDashboard/App/templates/customer/detail.html` (lines ~129 and ~257) — replace `style="background: linear-gradient(135deg, #667eea 0%, #764ba2 100%)"` with `style="background: var(--primary)"`

**Checkpoint**: US2 complete. Customer detail page card headers are navy. `.kpi-card` class available for any template to use for navy KPI cards.

---

## Phase 5: User Story 3 — Accent Colors for Tabs, Badges, and Interactive States (Priority: P3)

**Goal**: Active nav-tabs show teal (`#00bcd4`) underline. Warning badges use dark text (WCAG fix). Home page secondary accent elements use CSS variables instead of hardcoded purple/violet.

**Independent Test**: Open User Management — amber badges show dark text (not white). Click between Analytics tabs — active tab shows teal underline. Open home page — no purple tones on card accents or icons.

### Implementation

- [X] T012 [US3] Add active nav-tab teal override to `SemirDashboard/App/templates/base.html` — insert new rule: `.nav-tabs .nav-link.active, .nav-tabs .nav-link:focus { color: var(--accent); border-bottom-color: var(--accent); }`
- [X] T013 [US3] Add warning badge dark-text override to `SemirDashboard/App/templates/base.html` — insert new rule: `.badge.bg-warning, .badge.text-bg-warning { color: var(--text) !important; }` (fixes WCAG fail: white text on amber is only 1.9:1 contrast)
- [X] T014 [US3] Update all hardcoded purple instances in `SemirDashboard/App/templates/home.html`:
  - Hero section gradient → `background: var(--nav-bg)` and `box-shadow: rgba(30, 37, 53, 0.4)`
  - Icon `style="color:#667eea"` → `style="color:var(--primary)"`
  - Group-header gradient → `style="background: var(--primary)"`
  - Card border-top `#667eea` → `style="border-top:4px solid var(--primary)"`
  - Card icon `color:#667eea` → `style="color:var(--primary)"`
  - Card border-top `#764ba2` → `style="border-top:4px solid var(--accent)"`
  - Card icon `color:#764ba2` → `style="color:var(--accent)"`
  - Step badge `background:#667eea` → `style="background:var(--primary)"`

**Checkpoint**: US3 complete. No purple tones on home page. Active tabs use teal. Amber badges readable with dark text.

---

## Phase 6: User Story 4 — Login Page Theme Consistency (Priority: P4)

**Goal**: Login page shows navy branding with no purple. Per research, `login.html` has no hardcoded purple — it inherits all styles from `base.html`. This phase is a verification task only.

**Independent Test**: Open `/login/` unauthenticated. Submit button is navy. No purple anywhere. Form input focus ring is navy.

### Implementation

- [X] T015 [US4] Verify `SemirDashboard/App/templates/login.html` — read the file and grep for any purple hex values (`667eea`, `764ba2`, `5847d0`, `102.*126.*234`). If found, replace with `var(--primary)` or navy equivalents. If clean (per research), no changes needed — mark complete.

**Checkpoint**: US4 complete. Login page confirmed clean — inherits navy theme from `base.html` with no per-page overrides needed.

---

## Phase 7: Polish & Verification

**Purpose**: Final sweep to confirm zero purple remnants, all pages load correctly, existing tests pass.

- [X] T016 [P] Run purple-remnant grep check from repo root: `grep -rn "667eea\|764ba2\|5847d0\|102, 126, 234\|102,126,234" SemirDashboard/App/templates/` — must return 0 results. If any found, fix before proceeding.
- [X] T017 [P] Start dev server (`cd SemirDashboard && python manage.py runserver`) and run the visual checklist from `specs/002-ui-theme-redesign/quickstart.md` — verify navbar, KPI cards, buttons, form focus, tabs, badges, dropdown hover, and login page all match spec.
- [X] T018 Run DevTools console snippet from `quickstart.md` on the Analytics dashboard page — result must be `✅ No purple remnants found`.
- [X] T019 Run full Django test suite: `cd SemirDashboard && python manage.py test tests -v 2` — all tests pass, zero snapshot data changes.

---

## Dependencies & Execution Order

### Phase Dependencies

```
Phase 1 (Setup/Read)
    └── Phase 2 (CSS Variables — T002) ← BLOCKING GATE
            ├── Phase 3 (US1 — T003–T008) ← can start immediately after T002
            ├── Phase 4 (US2 — T009–T011) ← can start after T002
            ├── Phase 5 (US3 — T012–T014) ← can start after T002
            └── Phase 6 (US4 — T015)      ← no dependencies (verification only)
                    └── Phase 7 (Polish — T016–T019)
```

### User Story Dependencies

| Story | Depends On | Can Parallelize With |
|-------|-----------|---------------------|
| US1 (base.html core) | T002 (CSS vars defined) | US2, US3, US4 |
| US2 (KPI cards) | T002 | US1, US3, US4 |
| US3 (tabs, badges, home) | T002 | US1, US2, US4 |
| US4 (login verification) | None (read-only check) | All |

### Within Phase 3 (US1)

- T003 → T004 → T005 → T006 (sequential — all in base.html, edit in order)
- T007 and T008 are parallel (different files — chart.html and customer_chart.html)

### Parallel Opportunities Summary

| Tasks | Can Run In Parallel | Reason |
|-------|--------------------|----|
| T007 + T008 | ✅ Yes | Different files |
| T009 + T010 | ❌ No | T009 adds class to base.html; T010 edits detail.html — different files but T009 should complete first so class exists |
| T010 + T011 | ❌ No | Same file (customer/detail.html) — edit sequentially |
| T012 + T013 | ❌ No | Same file (base.html) — edit sequentially |
| T016 + T017 | ✅ Yes | Grep check and dev server are independent |

---

## Parallel Example: US1 Chart Templates

```
After T003–T006 (base.html US1 edits complete):

Parallel execution:
├── T007: Fix analytics/chart.html RGBA
└── T008: Fix cnv/customer_chart.html RGBA
```

---

## Implementation Strategy

### MVP (User Story 1 only — ~15 minutes)

1. Read `base.html` (T001)
2. Update CSS variable block (T002) ← **foundation**
3. Apply US1 patches to `base.html` (T003–T006)
4. Fix chart template RGBAs (T007–T008)
5. Run grep check (T016) + open dev server to verify navbar
6. **STOP and validate** — run DevTools snippet → ✅ result
7. All pages look navy. Deploy or continue to US2.

### Full Delivery (all 4 stories — ~45 minutes)

1. T001 → T002 → T003–T008 (US1 complete)
2. T009 → T010 → T011 (US2 complete)
3. T012 → T013 → T014 (US3 complete)
4. T015 (US4 verification)
5. T016 → T017 → T018 → T019 (Polish)

### Single-Developer Sequence (recommended order)

```
T001 → T002 → T003 → T004 → T005 → T006 → T007+T008 (parallel)
     → T009 → T010 → T011
     → T012 → T013 → T014
     → T015
     → T016+T017 (parallel) → T018 → T019
```

---

## Notes

- **No Python changes** — every task is a template edit. No `makemigrations`, no view changes, no URL changes.
- **Grep is your friend** — after each file edit, run a targeted grep on that file to confirm no purple hex remains.
- **base.html is edited 4 times** (T002, T003–T006, T009, T012–T013) — work top-to-bottom through the CSS block to avoid context confusion.
- **T010/T011 are the same file** — read `customer/detail.html` once, make all changes, save once.
- **T015 is likely a no-op** — research confirmed `login.html` has no hardcoded purple; the task is a verification gate.
