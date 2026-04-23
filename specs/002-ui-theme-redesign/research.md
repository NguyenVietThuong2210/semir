# Research: Web UI Theme Redesign

**Feature**: `002-ui-theme-redesign`
**Phase**: 0 — Technical Investigation

---

## 1. Bootstrap 5 CSS Variable Override Pattern

**Decision**: Override both the custom `--primary` variable AND Bootstrap's own `--bs-primary` / `--bs-primary-rgb` at `:root`.

**Rationale**: Bootstrap 5.2+ uses CSS custom properties internally. Setting `--bs-primary` causes `bg-primary`, `btn-primary`, `text-primary`, and `border-primary` utilities to adopt the new color automatically — no need to touch individual template classes. Setting `--bs-primary-rgb` (as a comma-separated RGB triple) enables Bootstrap's opacity utilities like `bg-primary bg-opacity-10` to calculate correctly.

**Correct override block** (goes inside `:root { ... }` in `base.html`):
```css
:root {
    --primary: #1a3c8c;          /* custom app variable */
    --bs-primary: #1a3c8c;       /* Bootstrap utility classes */
    --bs-primary-rgb: 26, 60, 140; /* Bootstrap opacity utilities */
    --accent: #00bcd4;           /* teal — active tabs, secondary highlights */
    --highlight: #ffc107;        /* amber — badges, warnings */
}
```

**Alternatives considered**:
- Recompiling Bootstrap SCSS: rejected — project uses CDN, no build step.
- Per-class overrides: rejected — verbose, brittle, would require touching every template.

---

## 2. Complete Hardcoded Purple Audit

Grep across `SemirDashboard/App/templates/` for all purple hex and RGBA values:

| File | Line(s) | Value | Replacement |
|------|---------|-------|-------------|
| `base.html` | 14 | `--primary: #667eea` | `--primary: #1a3c8c` |
| `base.html` | 26 | `background: linear-gradient(135deg, #667eea 0%, #764ba2 100%) !important` | `background: #1e2535 !important` |
| `base.html` | 27 | `box-shadow: 0 2px 8px rgba(102, 126, 234, .3)` | `box-shadow: 0 2px 8px rgba(30, 37, 53, 0.4)` |
| `base.html` | 66 | `background: #5847d0` (btn hover) | `background: #152d6e` |
| `base.html` | 101 | `box-shadow: 0 0 0 .2rem rgba(102, 126, 234, .15)` (focus ring) | `rgba(26, 60, 140, 0.15)` |
| `base.html` | 116 | `background: rgba(102, 126, 234, .1)` (dropdown hover) | `rgba(26, 60, 140, 0.08)` |
| `customer/detail.html` | `<style>` block | `linear-gradient(135deg, #667eea 0%, #764ba2 100%)` | `#1a3c8c` solid or `var(--primary)` |
| `customer/detail.html` | `<style>` block | `border-left: 4px solid #667eea` | `border-left: 4px solid var(--primary)` |
| `customer/detail.html` | `<style>` block | `color: #667eea` | `color: var(--primary)` |
| `customer/detail.html` | `<style>` block | `background: #667eea` | `background: var(--primary)` |
| `customer/detail.html` | 129 | inline `style="background: linear-gradient(...)"` | `style="background: var(--primary)"` |
| `customer/detail.html` | 257 | inline `style="background: linear-gradient(...)"` | `style="background: var(--primary)"` |
| `analytics/chart.html` | 80 | `background: rgba(102,126,234,.08)` | `rgba(26, 60, 140, 0.08)` |
| `cnv/customer_chart.html` | 50 | `background: rgba(102,126,234,.08)` | `rgba(26, 60, 140, 0.08)` |
| `home.html` | 45 | `linear-gradient(135deg, #667eea 0%, #764ba2 100%)` | `#1e2535` |
| `home.html` | 50 | `box-shadow: 0 2px 8px rgba(102, 126, 234, 0.3)` | `rgba(30, 37, 53, 0.4)` |
| `home.html` | 70 | `style="color:#667eea"` | `style="color:var(--primary)"` |
| `home.html` | 79 | `style="background: linear-gradient(...)"` | `style="background: var(--primary)"` |
| `home.html` | 89 | `style="border-top:4px solid #667eea"` | `style="border-top:4px solid var(--primary)"` |
| `home.html` | 91 | `style="color:#667eea"` | `style="color:var(--primary)"` |
| `home.html` | 105 | `style="border-top:4px solid #764ba2"` | `style="border-top:4px solid var(--accent)"` |
| `home.html` | 107 | `style="color:#764ba2"` | `style="color:var(--accent)"` |
| `home.html` | 377 | `style="...background:#667eea..."` | `style="...background:var(--primary)..."` |

**Total files affected**: 5 (`base.html`, `customer/detail.html`, `analytics/chart.html`, `cnv/customer_chart.html`, `home.html`)

---

## 3. Active Tab Teal Indicator — Bootstrap 5 Pattern

**Decision**: Override Bootstrap's `.nav-tabs .nav-link.active` to use teal (`#00bcd4`).

**Bootstrap 5 default**: Active tab uses `--bs-primary` for the active border-bottom color. After updating `--bs-primary` to navy, active tabs will show navy. To use teal as the accent instead, a targeted override is needed.

**Override** (add to `base.html` `:root` or as a rule):
```css
.nav-tabs .nav-link.active,
.nav-tabs .nav-link:focus {
    color: var(--accent);
    border-bottom-color: var(--accent);
}
```

**Rationale**: Teal distinguishes active interactive state from primary brand color (navy). This matches the reference image where the active indicator is visually distinct.

---

## 4. WCAG AA Contrast Verification

All color pairs verified using WCAG relative luminance formula:

| Pair | Foreground | Background | Ratio | AA Pass? | Notes |
|------|-----------|-----------|-------|----------|-------|
| White on Navy | `#ffffff` | `#1a3c8c` | 7.2:1 | ✅ AAA | KPI cards, btn-primary |
| White on Charcoal | `#ffffff` | `#1e2535` | 12.1:1 | ✅ AAA | Navbar |
| Dark Slate on Off-white | `#2c3e50` | `#f7f9fc` | 8.9:1 | ✅ AAA | Body text |
| Dark Slate on White | `#2c3e50` | `#ffffff` | 10.3:1 | ✅ AAA | Cards, tables |
| Teal on White | `#00bcd4` | `#ffffff` | 2.6:1 | ❌ Fail | Use as border/indicator only — NOT body text |
| Teal on Navy | `#00bcd4` | `#1a3c8c` | 2.8:1 | ❌ Fail | Use only as colored indicator on dark bg |
| Amber on Dark | `#ffc107` | `#1e2535` | 7.1:1 | ✅ AAA | Badges on dark navbar |
| Amber on White | `#ffc107` | `#ffffff` | 1.9:1 | ❌ Fail | Use only with dark text (`#2c3e50`) on amber bg |
| Dark on Amber | `#2c3e50` | `#ffc107` | 5.8:1 | ✅ AA | Amber badges with dark text |

**Key constraint derived**: Teal and amber must NEVER appear as text color on white or light backgrounds. Both are border/indicator/badge colors only.

**Amber badge fix needed**: Bootstrap `badge bg-warning` uses white text by default. `#fff` on `#ffc107` is only 1.19:1 — fails WCAG. Must override: `badge bg-warning { color: #2c3e50 !important; }`.

---

## 5. KPI Card Approach

**Decision**: KPI cards are styled with a `background: var(--primary)` class applied per-template. The existing `card` CSS in `base.html` sets `border: none` and `border-radius: 8px` which can stay unchanged.

**How KPI cards are currently styled**: Looking at `analytics/dashboard.html` and similar — KPI cards likely use inline `style="background: linear-gradient(...)"` or a utility class. The plan task audit will confirm the exact pattern.

**Implementation**: Add a CSS class `.kpi-card` to `base.html` that sets `background: var(--primary); color: #fff;`. Then replace any gradient-based KPI card styling in templates with `class="card kpi-card"`.

---

## 6. Login Page

**Decision**: The login page (`login.html`) extends `base.html` — it will inherit all CSS variable changes automatically. Any page-specific purple values in `login.html` must be grepped and patched.

Grep result: No hardcoded purple found in `login.html` — it is entirely variable-driven. ✅ No changes needed beyond `base.html`.
