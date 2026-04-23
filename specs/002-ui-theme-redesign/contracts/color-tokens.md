# UI Contract: Color Token System

**Feature**: `002-ui-theme-redesign`
**Contract type**: CSS Design Token Interface
**Scope**: All templates extending `App/templates/base.html`

---

## Token Definitions

These CSS custom properties are defined at `:root` in `base.html` and form the authoritative interface between the design system and all page templates.

| Token | Value | Role | Usage |
|-------|-------|------|-------|
| `--primary` | `#1a3c8c` | Deep navy — primary brand color | Buttons, KPI card backgrounds, card-header border, active states |
| `--primary-hover` | `#152d6e` | Darker navy — interactive feedback | `btn-primary:hover`, focused element highlight |
| `--primary-rgb` | `26, 60, 140` | RGB triple for opacity utilities | Bootstrap `bg-opacity-*` utilities |
| `--nav-bg` | `#1e2535` | Charcoal navy — navigation surface | Navbar background |
| `--accent` | `#00bcd4` | Teal — interactive accent | Active tab border-bottom, secondary highlights (border/indicator ONLY — not body text) |
| `--highlight` | `#ffc107` | Amber — status and attention | Badges (with dark text `#2c3e50`), warning indicators |
| `--bg` | `#f7f9fc` | Off-white — page background | Body background (unchanged from current) |
| `--text` | `#2c3e50` | Dark slate — body text | All body text (unchanged from current) |

**Bootstrap overrides** (set alongside custom tokens):

| Bootstrap Variable | Value | Purpose |
|--------------------|-------|---------|
| `--bs-primary` | `#1a3c8c` | Propagates to `btn-primary`, `bg-primary`, `text-primary`, `border-primary` |
| `--bs-primary-rgb` | `26, 60, 140` | Enables Bootstrap opacity utilities |

---

## Usage Rules (Constraints)

### MUST
- `--primary` MUST be the only navy source — never hardcode `#1a3c8c` in templates; always use `var(--primary)`.
- `--accent` (teal) MUST only be used as a border, underline, or indicator color — never as text on white/light backgrounds (contrast ratio 2.6:1 fails WCAG AA).
- `--highlight` (amber) MUST always be paired with dark text (`var(--text)` or `#2c3e50`) — never white text on amber (contrast ratio 1.9:1 fails WCAG AA).
- KPI card backgrounds MUST use `var(--primary)` with white (`#fff`) text.
- Navbar background MUST use `var(--nav-bg)` (`#1e2535`).

### MUST NOT
- MUST NOT hardcode any purple hex value (`#667eea`, `#764ba2`, `#5847d0`) or purple RGBA (`rgba(102, 126, 234, ...)`) anywhere in templates.
- MUST NOT use `--accent` as a text color on any background lighter than `#1a3c8c`.
- MUST NOT use `--highlight` with white text (Bootstrap's default `badge bg-warning` white text must be overridden to dark).

### Verification
These constraints are mechanically verifiable:
1. `grep -r "667eea\|764ba2\|5847d0\|102, 126, 234\|102,126,234" SemirDashboard/App/templates/` → must return 0 results.
2. Browser devtools computed styles on any page → 0 instances of old purple values.

---

## Component Behavior Contracts

### Primary Button (`btn-primary`)

| State | Background | Text | Border |
|-------|-----------|------|--------|
| Default | `#1a3c8c` | `#ffffff` | none |
| Hover | `#152d6e` | `#ffffff` | none |
| Focus | `#1a3c8c` | `#ffffff` | ring: `rgba(26,60,140,0.15)` |
| Disabled | `#1a3c8c` at 65% opacity | `#ffffff` | — |

### Form Inputs (`form-control`, `form-select`)

| State | Border | Shadow |
|-------|--------|--------|
| Default | `#dee2e6` | none |
| Focus | `var(--primary)` | `0 0 0 0.2rem rgba(26,60,140,0.15)` |

### Navigation Bar

| Element | Color |
|---------|-------|
| Background | `#1e2535` |
| Shadow | `0 2px 8px rgba(30,37,53,0.4)` |
| Link default | `rgba(255,255,255,0.9)` |
| Link hover/active | `#ffffff` |

### Nav Tabs (Bootstrap `.nav-tabs`)

| State | Color | Border-bottom |
|-------|-------|--------------|
| Default | `var(--text)` | transparent |
| Active | `var(--accent)` (`#00bcd4`) | `var(--accent)` 2px |
| Hover | `var(--primary)` | — |

### Dropdown Items

| State | Background |
|-------|-----------|
| Default | transparent |
| Hover | `rgba(26,60,140,0.08)` |

### Warning Badges (`badge bg-warning`)

| Property | Value |
|----------|-------|
| Background | `#ffc107` |
| Text color | `#2c3e50` (dark, overrides Bootstrap default white) |

### KPI Cards (`.kpi-card`)

| Property | Value |
|----------|-------|
| Background | `var(--primary)` |
| Text color | `#ffffff` |
| Border | none |
| Border-radius | 8px (inherited from `.card`) |
| Shadow | `0 1px 3px rgba(0,0,0,0.08)` (inherited) |

---

## Files Implementing This Contract

| File | Change Type | Tokens Used |
|------|------------|------------|
| `App/templates/base.html` | Primary — defines all tokens | All tokens defined here |
| `App/templates/customer/detail.html` | Hardcoded → `var()` | `--primary`, `--accent` |
| `App/templates/analytics/chart.html` | RGBA replacement | `--primary-rgb` |
| `App/templates/cnv/customer_chart.html` | RGBA replacement | `--primary-rgb` |
| `App/templates/home.html` | Hardcoded → `var()` | `--primary`, `--accent`, `--nav-bg` |
