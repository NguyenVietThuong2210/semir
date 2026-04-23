# Implementation Plan: Permission Group Redesign

**Branch**: `001-permission-group-redesign` | **Date**: 2026-04-23 | **Spec**: [spec.md](spec.md)  
**Input**: Feature specification from `specs/001-permission-group-redesign/spec.md`

## Summary

Rename all 20 permission codenames from an inconsistent flat list to a `{domain}.{action}` convention
grouped into 7 business domains. The role management UI shows permissions grouped by domain with
a group-level toggle checkbox (indeterminate state). Migration runs via `python manage.py perm sync`
post-deploy: built-in roles overwritten from updated `ADMIN_PERMISSIONS`/`VIEWER_PERMISSIONS`;
custom roles forward-renamed via `PERM_RENAMES` dict. All permission check call-sites
(`@requires_perm`, `_ajax_perm_check()`, `{% check_perm %}`) updated in the same release.
No dual-mode compat layer. No DB schema changes.

## Technical Context

**Language/Version**: Python 3.x / Django  
**Primary Dependencies**: Bootstrap 5 (UI), Django management commands (migration)  
**Storage**: SQLite3 (dev) / PostgreSQL 16 (prod) — `Role.permissions` is a JSONField (list of strings); no schema change  
**Testing**: Django test suite (`SnapshotTestCase`); `python manage.py test tests -v 2`  
**Target Platform**: Django web-service, admin-only low-traffic page (`/users/`)  
**Project Type**: web-service  
**Performance Goals**: N/A — admin-only page, no throughput target  
**Constraints**: `perm sync` must be idempotent; no dual-mode compat; hard cutover in same release  
**Scale/Scope**: 20 permissions → 20 permissions (rename only); ~10 Python view files; ~30 HTML templates

## Constitution Check

*GATE: Must pass before Phase 0 research. Re-checked after Phase 1 design.*

| Principle | Status | Notes |
|-----------|--------|-------|
| I. Business Logic Lock | PASS | No locked rule touched. Permission codenames are naming/UX, not business calculation. |
| II. Permission-Gated Access | PASS | FR-005 explicitly updates all three call-site types: `@requires_perm`, `_ajax_perm_check()`, `{% check_perm %}`. Hard cutover — no old codenames remain in view code. Superuser bypass unchanged. |
| III. Performance Budget | PASS | No new queries introduced. `PERMISSION_DEFS` is a Python list (in-memory). `user_management` view already groups by category in Python — new code keeps same pattern. |
| IV. Test-First with Snapshots | PASS | Tasks will include snapshot tests for `user_management` page (before + after migration). `perm sync` command tested in integration test. |
| V. Spec-Driven Feature Development | PASS | Full workflow: specify → clarify → plan (this file). |
| VI. Observability | PASS | No new background jobs. Existing `RequestIDMiddleware` covers all requests. `perm sync` is a management command (not a request) — no request_id needed. |

**Constitution Check verdict: ALL PASS. No violations.**

## Project Structure

### Documentation (this feature)

```text
specs/001-permission-group-redesign/
├── plan.md              ← this file
├── research.md          ← Phase 0 output
├── data-model.md        ← Phase 1 output
├── quickstart.md        ← Phase 1 output (deploy checklist)
└── tasks.md             ← Phase 2 output (/speckit-tasks — not yet created)
```

### Source Code (files touched by this feature)

```text
SemirDashboard/App/
├── permissions.py                         ← PERMISSION_DEFS, ADMIN_PERMISSIONS, VIEWER_PERMISSIONS
├── management/commands/perm.py            ← PERM_RENAMES dict (add 20 entries)
├── views/
│   ├── analytics.py                       ← @requires_perm codenames
│   ├── coupon.py                          ← @requires_perm codenames
│   ├── customer.py                        ← @requires_perm + _ajax_perm_check codenames
│   ├── shop_detail.py                     ← @requires_perm + _ajax_perm_check codenames
│   ├── upload.py                          ← @requires_perm codenames
│   ├── users.py                           ← @requires_perm codename; no grouping logic change needed
│   └── home.py                            ← @requires_perm (if any)
├── cnv/
│   └── views.py                           ← @requires_perm + _ajax_perm_check codenames
└── templates/
    ├── user_management.html               ← group toggle JS + indeterminate checkbox state
    └── **/*.html (~30 files)              ← {% check_perm 'old' %} → {% check_perm 'new' %}
```

**Structure Decision**: Single Django app. All changes are in-place renames — no new files, no new
URL routes, no DB migrations. The view (`users.py`) already groups permissions by the third tuple
element in `PERMISSION_DEFS`; updating that element is sufficient for the backend grouping change.
The group-level toggle is a frontend-only addition (JavaScript + indeterminate checkbox state in
`user_management.html`).

## Implementation Strategy

### Step A — Backend: update codenames (no UI change yet)

1. **`App/permissions.py`**: Replace all 20 tuples in `PERMISSION_DEFS` with new `(codename, label, domain_group)` values per the migration map. Update `VIEWER_PERMISSIONS = ["sales.view"]`. `ADMIN_PERMISSIONS = ALL_PERMISSIONS` auto-derives from the updated list — no separate change needed.

2. **`App/management/commands/perm.py`**: Add all 20 entries to `PERM_RENAMES` dict (one-to-one map: `old_code → [new_code]`). Running `perm sync` after deploy will then auto-rename custom roles.

3. **View files** (10 files): Replace every `@requires_perm("old")` and `_ajax_perm_check(request, "old")` with the corresponding new codename.

4. **Template files** (~30 files): Replace every `{% check_perm 'old' %}` with the new codename.

### Step B — Frontend: group toggle UI

5. **`App/templates/user_management.html`**: The template already iterates `permission_categories` (a dict built from `PERMISSION_DEFS` group field). After Step A, it will automatically show 7 domain group headers instead of 3. Add:
   - A group-level `<input type="checkbox">` per domain header with `data-group` attribute
   - JavaScript: clicking group checkbox toggles all child checkboxes in that group; when child state changes, re-evaluate group checkbox indeterminate state
   - Indeterminate state: set via `checkbox.indeterminate = true` in JS (not a CSS/HTML attr)

### Step C — Migration (post-deploy)

6. Operator runs `python manage.py perm show` before deploy (snapshot).
7. After deploy, operator runs `python manage.py perm sync` once.
8. Smoke-test each of the 20 permission-gated pages with a test account per role.

### Codename migration map (authoritative reference)

| Old codename | New codename | Domain group |
|---|---|---|
| `page_analytics` | `sales.view` | Sales Analytics |
| `page_chart` | `sales.chart` | Sales Analytics |
| `download_analytics` | `sales.export` | Sales Analytics |
| `download_chart_excel` | `sales.export_chart` | Sales Analytics |
| `page_coupons` | `coupons.view` | Coupons |
| `page_coupon_chart` | `coupons.chart` | Coupons |
| `download_coupons` | `coupons.export` | Coupons |
| `download_coupon_chart_excel` | `coupons.export_chart` | Coupons |
| `manage_campaigns` | `coupons.manage` | Coupons |
| `page_cnv_comparison` | `cnv.view` | CNV / Customer Analytics |
| `page_customer_chart` | `cnv.chart` | CNV / Customer Analytics |
| `page_cnv_sync` | `cnv.sync` | CNV / Customer Analytics |
| `download_cnv` | `cnv.export` | CNV / Customer Analytics |
| `download_customer_chart_excel` | `cnv.export_chart` | CNV / Customer Analytics |
| `page_customer_detail` | `customers.detail` | Customers |
| `page_shop_detail` | `shops.view` | Shop Detail |
| `download_shop_detail` | `shops.export` | Shop Detail |
| `page_upload` | `data.upload` | Data Management |
| `page_formulas` | `data.formulas` | Data Management |
| `manage_users` | `admin.users` | Admin |

### Key architectural insight — no view logic change for grouping

`users.py` view already builds `permission_categories = {}` from `PERMISSION_DEFS` third element
and passes it to the template. The template already iterates `permission_categories.items`. So:
- Step A (updating `PERMISSION_DEFS`) automatically produces 7 domain groups in the UI
- No Python view logic needs to change for grouping — only codenames in decorator args
- The only new Python/JS code is the group toggle (Step B)

### `.` in codename — confirmed safe

Django `user_has_perm()` in `permissions.py` does `codename in (profile.role.permissions or [])` —
plain Python string membership test, no parsing. Template tag `{% check_perm %}` calls the same
function. `@requires_perm` passes the string directly to `user_has_perm`. Dot character is safe
in all three call-site types.

## Complexity Tracking

> No Constitution violations found — section not applicable.
