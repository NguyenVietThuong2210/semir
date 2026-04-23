# Quickstart: Theme Verification Guide

**Feature**: `002-ui-theme-redesign`
**Purpose**: Visual acceptance testing checklist — run after implementation, before merging.

---

## 1-Minute Smoke Test

Open a browser in an incognito window. Log in to the app. Run through these in order:

```
1. Home page (/)                → navbar is dark navy #1e2535, no purple gradient
2. Analytics dashboard (/analytics/)  → KPI cards are navy, buttons are navy
3. User Management (/users/)    → role badges show amber with dark text
4. Login page (/login/)         → submit button is navy, no purple anywhere
```

All 4 must pass before proceeding to detailed checks.

---

## Detailed Visual Checklist

### Navbar (all authenticated pages)

- [ ] Background: `#1e2535` charcoal navy — no purple gradient
- [ ] Shadow: subtle dark shadow, not purple glow
- [ ] Links: white text, full-white on hover
- [ ] Mobile (narrow viewport): collapsed menu still shows navy, no purple hamburger

### KPI Summary Cards

- [ ] Analytics dashboard: customer/return-rate cards are navy (`#1a3c8c`) with white text
- [ ] Coupon dashboard: summary cards match navy style
- [ ] Shop Detail page: summary cards match navy style
- [ ] Icons inside cards: visible (white or light enough to contrast navy)

### Buttons

- [ ] Any `btn-primary`: navy default (`#1a3c8c`)
- [ ] Hover: button darkens to `#152d6e` — no purple flash
- [ ] Focus ring: navy-blue glow (`rgba(26,60,140,0.15)`) — no purple ring

### Form Inputs

- [ ] Default state: neutral gray border
- [ ] Focus state: navy border + navy focus ring (no purple ring visible)

### Navigation Tabs

- [ ] Active tab has teal underline (`#00bcd4`)
- [ ] Inactive tabs: neutral
- [ ] Switching tabs: teal underline moves correctly

### Badges

- [ ] Amber badges (`bg-warning`): amber background with **dark** text — NOT white text
- [ ] Navy badges (`bg-primary`): navy background with white text
- [ ] Superuser badge in User Management: still renders correctly

### Dropdown Menus

- [ ] Hover state: subtle navy tint (`rgba(26,60,140,0.08)`) — no purple highlight
- [ ] Dropdown shadow: dark neutral shadow, no purple tint

### Login Page

- [ ] Submit button: navy
- [ ] No purple gradient or purple accent anywhere on the page
- [ ] Form focus ring: navy glow

---

## DevTools Verification (automated check)

Open browser DevTools → Console → paste and run:

```javascript
// Check for purple computed style remnants
const allElements = document.querySelectorAll('*');
const purplePatterns = [/667eea/i, /764ba2/i, /5847d0/i, /102,\s*126,\s*234/i];
const flagged = [];
allElements.forEach(el => {
    const styles = window.getComputedStyle(el);
    ['backgroundColor', 'color', 'borderColor', 'boxShadow', 'outline'].forEach(prop => {
        const val = styles[prop];
        if (purplePatterns.some(p => p.test(val))) {
            flagged.push({ el: el.tagName + (el.className ? '.' + el.className.split(' ')[0] : ''), prop, val });
        }
    });
});
console.log(flagged.length === 0 ? '✅ No purple remnants found' : `❌ ${flagged.length} purple remnants:`, flagged);
```

**Expected result**: `✅ No purple remnants found`

---

## WCAG Contrast Quick-Check

| Color pair | Expected ratio | Tool |
|-----------|---------------|------|
| White on `#1a3c8c` (KPI cards, btn) | ≥ 7.0:1 | [contrast checker](https://webaim.org/resources/contrastchecker/) |
| White on `#1e2535` (navbar) | ≥ 12:1 | Same tool |
| `#2c3e50` on amber `#ffc107` (badges) | ≥ 5.0:1 | Same tool |
| `#00bcd4` teal: must NOT appear as text on white | — | Ensure teal is only border/indicator |

---

## Regression Check

After visual confirmation, run the Django test suite to confirm no functional breakage:

```bash
cd SemirDashboard && python manage.py test tests -v 2
```

All tests must pass. Since this is a CSS-only change, no snapshot content should differ — any snapshot data change indicates an unintended template logic change and must be investigated before merging.

---

## Files Changed Reference

| File | What changed |
|------|-------------|
| `App/templates/base.html` | CSS variables, navbar, btn-primary hover, form focus ring, dropdown hover |
| `App/templates/customer/detail.html` | Inline style block + 2 card-header inline styles |
| `App/templates/analytics/chart.html` | Table header row RGBA |
| `App/templates/cnv/customer_chart.html` | Table header row RGBA |
| `App/templates/home.html` | Hero gradient, box-shadow, icon colors, card accents |
