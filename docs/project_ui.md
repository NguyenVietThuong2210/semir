---
name: SemirDashboard UI Design System
description: CSS design tokens, color rules, component patterns, and UI concepts for SemirDashboard templates
type: project
---

## Core Rule

**No hardcoded colors outside `base.html`.** All color values must be CSS custom properties (tokens) defined in the `:root {}` block in `App/templates/base.html`. Templates use only `var(--token-name)`.

---

## Design Tokens (base.html `:root`)

### Brand Blues
| Token | Value | Usage |
|-------|-------|-------|
| `--primary` | `#0369a1` | Main brand color — buttons, borders, headers |
| `--primary-rgb` | `3, 105, 161` | For `rgba(var(--primary-rgb), .09)` opacity variants |
| `--primary-hover` | `#075985` | Button hover state |
| `--bs-primary` | `#0369a1` | Bootstrap override |
| `--bs-primary-rgb` | `3, 105, 161` | Bootstrap override |
| `--nav-bg` | `#064e77` | Navbar + dark-tabs container background |
| `--secondary` | `#4a6785` | Secondary brand |

### Accents
| Token | Value | Usage |
|-------|-------|-------|
| `--accent` | `#06b6d4` | Cyan accent |
| `--accent-rgb` | `6, 182, 212` | For rgba opacity |
| `--coupon` | `#7b4000` | Brown — reserved (do not use for headers) |
| `--success` | `#198754` | Green status |
| `--success-rgb` | `25, 135, 84` | For rgba opacity |
| `--danger` | `#dc3545` | Red error/danger |
| `--danger-rgb` | `220, 53, 69` | For rgba opacity |

### Amber / Yellow
| Token | Value | Usage |
|-------|-------|-------|
| `--orange` | `#eab308` | Orange/amber |
| `--orange-rgb` | `234, 179, 8` | For rgba opacity |
| `--orange-dark` | `#a16207` | Darker amber |
| `--highlight` | `#fef08a` | Yellow highlight tint |

### CNV Section Palette
| Token | Value | Usage |
|-------|-------|-------|
| `--cnv-purple` | `#7b3f9e` | CNV POS/CNV comparison purple |
| `--cnv-navy` | `#1a5cb0` | CNV navy |
| `--cnv-forest` | `#156f3a` | CNV forest green (Zalo tab) |

### Status Gradients
| Token | Value | Usage |
|-------|-------|-------|
| `--gradient-synced` | `linear-gradient(135deg, #11998e, #38ef7d)` | Synced badge |
| `--gradient-not-synced` | `linear-gradient(135deg, #ee0979, #ff6a00)` | Not synced badge |

### Grade Badges
| Token | Value | Usage |
|-------|-------|-------|
| `--silver` | `#94a3b8` | Silver tier badge background |

### Row Highlight Tints (JS-compatible)
| Token | Value | Usage |
|-------|-------|-------|
| `--highlight-warn` | `#fff3cd` | JS row warning highlight (yellow) |
| `--highlight-ok` | `#f0fdf4` | JS row success highlight (green) |

### Code Syntax (formulas.html)
| Token | Value | Usage |
|-------|-------|-------|
| `--code-keyword` | `#0066cc` | IF/ELSE keywords in pseudo-code |
| `--code-comment` | `#666666` | Comment lines in pseudo-code |
| `--example-bg` | `#eef3fb` | Example box background |

### Neutrals
| Token | Value | Usage |
|-------|-------|-------|
| `--text` | `#374151` | Primary text color |
| `--text-dark` | `#212529` | Darker text (JS label resets) |
| `--text-muted` | `#6c757d` | Muted/secondary text |
| `--border` | `#dee2e6` | Border color |
| `--bg` | `#f8fafc` | Page background |
| `--bg-light` | `#f8f9fa` | Card/light section background |
| `--gray-tint` | `#f0f2f5` | Neutral table cell tint (`td.c-gray`) |

---

## Text Color Rule

**Text is only white or black.** No brand-colored text.

| Background type | Text rule |
|----------------|-----------|
| Dark bg (`var(--primary)`, `var(--nav-bg)`, etc.) | `color: #fff` |
| Light bg (`var(--bg-light)`, `var(--bg)`, white) | `color: var(--text)` or `color: var(--text-muted)` |

**Never use:** `color: var(--primary)`, `color: var(--orange-dark)`, `color: var(--accent)` for body/stat text.

Exception: semantic data badges (success = green, danger = red) may use Bootstrap utility classes (`text-success`, `text-danger`) when conveying meaning (e.g. used vs unused counts).

---

## Component Patterns

### Section Card Headers

All primary section headers use solid primary blue + white text. **No tinted/rgba backgrounds for headers.**

```html
<!-- Standard card-header pattern -->
<div class="card-header" style="background:var(--primary); color:#fff; border-bottom:none;">
    <h5 class="mb-0 text-white"><i class="bi bi-..."></i> Section Title</h5>
</div>

<!-- shop_detail / customer_analytics section-header pattern -->
<div class="section-header">  <!-- CSS: background:var(--primary); color:white -->
    <span class="section-title">...</span>
</div>
```

Never use `var(--coupon)` or any other color for section headers — all must be `var(--primary)`.

### Dark Tabs (`.dark-tabs`)

Used when tab nav is placed on a dark (`var(--nav-bg)`) container background.

```css
.dark-tabs { border-bottom: none; }
.dark-tabs .nav-link {
    background: rgba(255,255,255,.08);
    color: rgba(255,255,255,.85);
    border: 1px solid rgba(255,255,255,.15);
    border-radius: 6px 6px 0 0;
    margin-right: 3px;
    font-weight: 500;
    font-size: .88rem;
}
.dark-tabs .nav-link:hover  { background: rgba(255,255,255,.18); color: #fff; }
.dark-tabs .nav-link.active { background: #fff; color: var(--nav-bg); border-color: #fff; font-weight: 600; }
```

Container HTML:
```html
<div class="card-header p-0 border-0" style="background:var(--nav-bg)">
    <ul class="nav dark-tabs px-3 pt-2" ...>
```

### Table Column Headers

All `tbl-hdr-*` classes use `var(--primary)` — no per-column color coding.

```css
.tbl-hdr-shop, .tbl-hdr-used, .tbl-hdr-cnv,
.tbl-hdr-pct, .tbl-hdr-pct2, .tbl-hdr-amt,
.tbl-hdr-gray, .tbl-hdr-red {
    background: var(--primary) !important;
    color: #fff !important;
}
```

### Stat Cards (KPI Cards)

Light background cards on analytics pages — never solid blue for stat cards:

```html
<!-- Light tinted stat card -->
<div class="card stat-card border-0 shadow-sm" style="background:rgba(var(--primary-rgb),.09)">
    <div class="card-body">
        <div class="stat-label" style="color:var(--text-muted)">Label</div>
        <div class="stat-value" style="color:var(--text)">Value</div>
    </div>
</div>
```

### Home Page Action Cards

All action cards have uniform blue top border:

```html
<div class="card action-card" style="border-top:4px solid var(--primary)">
```

No per-card accent/highlight colors — all borders use `var(--primary)`.

---

## Page Concept: Sales / Customer / Coupon

Sales, Customer Analytics, and Coupon Analytics are **the same UI framework** showing different data. They must have identical structure:

- Same dark-tabs pattern (white-on-dark)
- Same section card-header style (solid `var(--primary)` + white text)
- Same stat card style (light tinted, `var(--text)` labels)
- Same table header colors (all `var(--primary)`)

The Sales page is the reference standard. When updating Customer or Coupon pages, use Sales as the baseline.

---

## rgba() Usage

For opacity variants, always use the companion `-rgb` token:

```css
/* ✅ Correct */
background: rgba(var(--primary-rgb), .09);
box-shadow: 0 2px 8px rgba(var(--primary-rgb), 0.35);

/* ❌ Wrong */
background: rgba(3, 105, 161, .09);
```

### canvas / Chart.js Exception

`ctx.fillStyle` and Chart.js color arrays **cannot** accept `var()` — literal hex values are acceptable only inside `<script>` blocks that use the Canvas API.

### JS Inline Styles

JavaScript `element.style.background = 'var(--primary)'` **does** support CSS variables. Always use tokens in JS inline style assignments.

---

## File Reference

- **Token definition:** `App/templates/base.html` `:root {}` block
- **Sales page:** `App/templates/analytics/dashboard.html`
- **Customer page:** `App/templates/cnv/customer_analytics.html`
- **Coupon page:** `App/templates/coupon/dashboard.html`
- **Shop Detail:** `App/templates/shop_detail.html`
- **Home:** `App/templates/home.html`

---

## Visual Snapshot System — `render/`

Every UI change MUST be visually verified by regenerating snapshots in the `render/` folder.

### What's snapshotted

For each key page (home, sales, customer, coupon, shop_detail, customer_detail, formulas, charts, sync, upload, user mgmt, admin logs), 4 artifacts are written:

1. `render/<label>.html` — raw rendered HTML for grep/diff
2. `render/<label>.tables.txt` — per-table summary (headers + first rows)
3. `render/<label>.token_issues.txt` — only created when hardcoded colors found
4. `render/pdf/<label>.pdf` + `render/png/<label>.png` — full-page visual

### Regenerate after every template change

```bash
cd SemirDashboard
python manage.py shell -c "exec(open('tests/snapshot_render.py').read())"
python tests/snapshot_visual.py
```

Target: `render/_index.md` should show **0 token issues** across all pages.

### What the snapshot script checks

- Inline `style="..."` attributes in static HTML (not inside `<script>` blocks)
- `<style>...</style>` blocks (excluding the canonical `:root { ... }` token-definition block)
- Allowed exceptions: `#fff`, `#ffffff`, `#000`, `#000000` (pure white/black)
- Canvas API calls (`ctx.fillStyle = '#xxx'`) and Chart.js palette arrays inside `<script>` are exempt — they cannot accept CSS `var()`

### Adding a new page to snapshot list

Edit `SemirDashboard/tests/snapshot_render.py` and append to the `pages` list:

```python
pages = [
    ...
    ("/your/new-route/", "18_new_page"),
]
```

### Visual review workflow

After making template changes:

1. Run both scripts above
2. Open `render/_index.md` — verify Token issues = 0
3. Open the relevant `render/png/<label>.png` files for changed pages
4. Compare against the design rules above (text color, dark-tabs, section headers, stat cards, table headers)
5. Iterate until visual matches the rules
