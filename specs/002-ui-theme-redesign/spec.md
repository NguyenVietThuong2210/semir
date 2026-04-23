# Feature Specification: Web UI Theme Redesign

**Feature Branch**: `002-ui-theme-redesign`
**Created**: 2026-04-23
**Status**: Draft
**Input**: User description: "bạn là 1 senior UI UX designer, hãy update theme của toàn bộ web cho đồng bộ, dựa trên những màu chủ đạo tôi cung cấp trong image"

---

## Color Palette Reference

| Role | Color Name | Hex | Used For |
|------|-----------|-----|---------|
| Primary | Deep Navy | `#1a3c8c` | Buttons, KPI cards, card-header border, active states |
| Primary Hover | Dark Navy | `#152d6e` | Button hover, focused element highlight |
| Navigation | Charcoal Navy | `#1e2535` | Navbar background |
| Accent | Teal | `#00bcd4` | Active tab indicator, secondary highlights |
| Highlight | Amber | `#ffc107` | Status badges, warning indicators |
| Background | Off-white | `#f7f9fc` | Page background (unchanged) |
| Surface | White | `#ffffff` | Cards, tables, content areas (unchanged) |
| Text | Dark Slate | `#2c3e50` | Body text (unchanged) |

> All hex values are extracted from the reference image and are the implementation targets. Visual fine-tuning is permitted during in-browser review.

---

## Clarifications

### Session 2026-04-23

- Q: Are the extracted approximate hex values acceptable as implementation targets, or are exact brand hex codes required? → A: Approximate values from the reference image are the implementation targets; fine-tuning occurs during visual review.
- Q: Should chart/graph colors (Chart.js dataset colors) be updated in this sprint? → A: Defer to a follow-up sprint. Base theme (navbar, cards, buttons, badges) is the full scope of this sprint.

---

## User Scenarios & Testing *(mandatory)*

### User Story 1 — Global Color Palette Applied (Priority: P1)

A user opens any page of SemirDashboard and sees a consistent navy-blue theme across the entire application — top navigation bar, KPI cards, buttons, badges, and tabs — with no purple or violet tones remaining from the old theme.

**Why this priority**: All color variables live in a single `<style>` block in `base.html`. Updating them cascades to every page automatically. This is the foundation all other stories build on.

**Independent Test**: Navigate to the Analytics dashboard, Coupon dashboard, and Login page. Every page displays deep navy primary elements, charcoal navy navigation, teal accents, and amber highlights. No purple or violet appears anywhere — including hover states, focus rings, and drop shadows.

**Acceptance Scenarios**:

1. **Given** the current purple theme (`--primary: #667eea`), **When** CSS variables are updated to the navy palette, **Then** every page inheriting from `base.html` reflects the new colors without per-page template changes.
2. **Given** a user views the top navigation bar, **When** on any authenticated page, **Then** the navbar background is charcoal navy (`#1e2535`) with white text, replacing the purple gradient.
3. **Given** any `btn-primary` button, **When** hovered, **Then** the button darkens to `#152d6e` — no purple tones visible.
4. **Given** any form input or select field, **When** focused, **Then** the focus ring color is navy-based — no purple glow.
5. **Given** any dropdown menu item, **When** hovered, **Then** the hover background uses a navy tint — no purple tint.

---

### User Story 2 — KPI Cards Match Navy Blue Style (Priority: P2)

An analytics user viewing any dashboard sees KPI summary cards rendered with deep navy blue backgrounds and white text, matching the reference design and clearly distinct from the white content area.

**Why this priority**: KPI cards are the most prominent data elements on every dashboard page. They set the visual tone and must represent the new brand identity immediately on load.

**Independent Test**: Open the Analytics dashboard. KPI cards show `#1a3c8c` navy backgrounds with white text. Icons are white or light-toned for contrast. The same card style appears on the Coupon dashboard and Shop Detail page.

**Acceptance Scenarios**:

1. **Given** the Analytics dashboard, **When** inspecting KPI summary cards, **Then** they display deep navy (`#1a3c8c`) background with white text and ≥4.5:1 contrast ratio.
2. **Given** a KPI card with a Bootstrap Icon, **When** viewed, **Then** the icon renders white or light enough to meet WCAG AA contrast against the navy card.
3. **Given** the Coupon dashboard and Shop Detail page, **When** viewed, **Then** their summary cards match the same navy card style as the Analytics page.

---

### User Story 3 — Accent Colors for Tabs, Badges, and Interactive States (Priority: P3)

A user navigating tabs and reading status badges sees teal for active/interactive elements and amber for highlighted status badges — giving the dashboard a distinct, data-focused feel.

**Why this priority**: Accent colors complete the palette and differentiate interaction feedback from the primary brand color. They require no layout changes.

**Independent Test**: Open User Management. Role badges display amber. Navigate between page tabs — the active tab indicator is teal. Dropdown hover states use a navy tint, not purple.

**Acceptance Scenarios**:

1. **Given** any page with Bootstrap nav-tabs (Analytics, User Management), **When** a tab is active, **Then** the active indicator is teal (`#00bcd4`).
2. **Given** User Management role badges, **When** viewed, **Then** highlight badges use amber (`#ffc107`) and primary role badges use navy.
3. **Given** any dropdown menu, **When** hovering an item, **Then** the hover background is `rgba(26, 60, 140, 0.08)` — navy tint, not purple.
4. **Given** any card header, **When** viewed, **Then** the bottom border accent uses navy (`#1a3c8c`) from the CSS variable — not the old purple.

---

### User Story 4 — Login Page Theme Consistency (Priority: P4)

A user opening the login page sees the same navy-blue branding as the authenticated app — login card, submit button, and any accent styling all use the updated palette with no purple remnants.

**Why this priority**: The login page is the first surface users see. Purple branding on the login page after a full theme update would be immediately noticeable and undermine the change.

**Independent Test**: Open `/login/` unauthenticated. Submit button is navy. No purple gradient or purple tones appear anywhere on the page.

**Acceptance Scenarios**:

1. **Given** a user on the login page, **When** viewing the submit button, **Then** it displays deep navy (`#1a3c8c`), not purple.
2. **Given** the login card or page background uses an accent color, **When** viewed, **Then** no purple or violet tones appear.
3. **Given** the login form input is focused, **When** viewed, **Then** the focus ring is navy-based, not purple.

---

### Edge Cases

- **Hardcoded RGBA values**: `base.html` contains 4 hardcoded purple RGBA values (navbar shadow, button hover, form focus ring, dropdown hover) that are NOT covered by updating `--primary`. These must be individually replaced with navy equivalents.
- **Inline `style=` attributes in templates**: Any template using inline `style="color: #667eea"` or similar must be identified by grep and replaced with CSS variable references.
- **Django admin (`/admin/`)**: Uses its own stylesheet — out of scope, will not be restyled.
- **Bootstrap utility alpha classes**: `bg-primary`, `text-primary`, `border-primary` auto-update via `--bs-primary` override. No manual changes needed for these.
- **Print / high-contrast mode**: Theme colors must maintain WCAG AA (4.5:1) — navy on white and white on navy both satisfy this naturally; teal on white must be verified.

---

## Requirements *(mandatory)*

### Functional Requirements

**Core palette (cascading via CSS variables):**

- **FR-001**: `base.html` CSS variable `--primary` MUST be updated from `#667eea` to `#1a3c8c`.
- **FR-002**: Bootstrap override variables (`--bs-primary`, `--bs-primary-rgb: 26, 60, 140`) MUST be set at `:root` so `btn-primary`, `bg-primary`, `text-primary` utilities adopt the navy color automatically.
- **FR-003**: The navbar background MUST be updated from the purple gradient to solid charcoal navy `#1e2535`.

**Hardcoded RGBA replacements (must be individually patched):**

- **FR-004**: Navbar `box-shadow` MUST change from `rgba(102, 126, 234, .3)` → `rgba(30, 37, 53, 0.4)`.
- **FR-005**: `.btn-primary:hover` background MUST change from `#5847d0` → `#152d6e`.
- **FR-006**: Form focus ring `box-shadow` MUST change from `rgba(102, 126, 234, .15)` → `rgba(26, 60, 140, 0.15)`.
- **FR-007**: Dropdown item hover background MUST change from `rgba(102, 126, 234, .1)` → `rgba(26, 60, 140, 0.08)`.

**Accent and surface colors:**

- **FR-008**: Teal (`#00bcd4`) MUST be applied as the active tab indicator color and secondary accent highlights.
- **FR-009**: Amber (`#ffc107`) MUST remain the highlight/warning badge color (Bootstrap `warning` — verify it is not overridden).
- **FR-010**: White MUST remain the background for content areas, table rows, and card surfaces.
- **FR-011**: All text on colored backgrounds MUST achieve WCAG AA contrast ratio ≥ 4.5:1.

**Scope and consistency:**

- **FR-012**: Inline `style=` attributes in any template that specify purple/violet hex values MUST be replaced with CSS custom property references.
- **FR-013**: The login page MUST apply the same primary and accent colors as the authenticated app — no purple on any element.
- **FR-014**: Chart/graph dataset colors are explicitly out of scope for this sprint and MUST NOT be modified.

---

### Key Entities

| Entity | Description |
|--------|-------------|
| **Color Palette** | The 8-color design token set defined in the reference table at the top of this spec |
| **Base Template** | `App/templates/base.html` — single source of CSS variables and the 4 hardcoded RGBA values |
| **Component Templates** | Page templates with inline `style=` attributes referencing old purple colors |

---

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: A browser devtools inspection of computed styles on any page shows zero instances of `#667eea`, `#764ba2`, `#5847d0`, or any purple/violet hex value.
- **SC-002**: A browser devtools inspection shows zero instances of `rgba(102, 126, 234, ...)` in computed styles — replaced by navy equivalents.
- **SC-003**: All color pairs in use pass WCAG AA (≥4.5:1): white on `#1a3c8c` ✓, white on `#1e2535` ✓, `#2c3e50` on `#f7f9fc` ✓, `#1e2535` on white ✓. Teal `#00bcd4` on white must be verified (it is borderline — use as a border/indicator, not body text).
- **SC-004**: All 30+ authenticated pages and the login page render at HTTP 200 with no layout shifts, broken icons, or missing styles after the theme update.
- **SC-005**: No existing functionality (form submissions, AJAX calls, table sorting, permission checks) is broken — the change is CSS-only with no Python or template logic modifications.

---

## Assumptions

- The 8-color palette in the reference table above is the implementation target. Visual fine-tuning (±10% lightness) is permitted during in-browser review without spec amendment.
- Django admin (`/admin/`) is out of scope — it has its own stylesheet.
- This is a color/theme-only update — no layout, spacing, typography, or component structure changes.
- Bootstrap 5.3 is loaded via CDN; `:root` CSS variable overrides propagate to all Bootstrap utility classes.
- Body `<a>` link color keeps Bootstrap default blue (`#0d6efd`) — it does not clash with the navy theme and changing it is out of scope.
- Chart.js dataset colors are deferred to a follow-up sprint.
- Teal (`#00bcd4`) is used only as a border/indicator color, never as a text color on white, to avoid WCAG contrast issues (its contrast ratio on white is ~2.6:1, below the 4.5:1 threshold).
