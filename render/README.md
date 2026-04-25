# Render Snapshots

Visual snapshots of every key page. Used as a knowledge base to:

1. **Detect UI regressions** before they reach prod (compare PNG/PDF vs prior version)
2. **Audit design rule compliance** (token usage, color rules, component patterns)
3. **Let the user review** UI changes before deployment

## Folder Layout

```
render/
├── _index.md                    auto-generated index of all snapshots
├── README.md                    this file
├── <label>.html                 raw rendered HTML (for grep / diff)
├── <label>.tables.txt           per-page table summary (headers + first rows)
├── <label>.token_issues.txt     hardcoded color violations (when present)
├── pdf/
│   └── <label>.pdf              full-page PDF (Chrome print)
└── png/
    └── <label>.png              full-page PNG screenshot (1440x2400)
```

## RULE: Regenerate after every template change

Whenever you edit any template under `App/templates/`, regenerate this folder:

```bash
cd SemirDashboard

# 1. Render HTML + tables + token compliance check
python manage.py shell -c "exec(open('tests/snapshot_render.py').read())"

# 2. Generate PDFs + PNGs from those HTML files
python tests/snapshot_visual.py
```

Then:

- Open `_index.md` to see status of every page (size, table count, token issues)
- Open `png/<label>.png` to visually verify the changed pages
- Compare with the previous version (git diff on these files works for HTML; visual diff for PNGs)

## Token compliance audit

`<label>.token_issues.txt` is created **only** when a page contains hardcoded hex colors outside `:root` token definitions. Any non-empty file = a rule violation that needs fixing.

The check excludes:
- Pure white (`#fff`, `#ffffff`) and pure black (`#000`, `#000000`)
- Content inside `<script>` blocks (Canvas API / Chart.js palettes are exempt)
- The `:root { ... }` block in base.html (those ARE the canonical token definitions)

## Per-page table summary

`<label>.tables.txt` extracts every `<table>` on the page with:
- Section heading the table is under
- Column count + row count
- Header row text
- First 2 data rows (truncated)

Useful for verifying table data and structure changed (or didn't) after a refactor.

## Pages snapshotted

See `_index.md` for the complete current list. Roughly: home, sales (alltime + 2025), customer (alltime + 2025), coupon (alltime + 2025), shop_detail, customer_detail, formulas, all 3 chart pages, cnv_sync_status, upload form, user mgmt, admin logs.

To add a new page: edit `tests/snapshot_render.py` `pages` list.
