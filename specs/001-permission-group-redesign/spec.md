# Feature Specification: Permission Group Redesign

**Feature Branch**: `001-permission-group-redesign`
**Created**: 2026-04-22
**Status**: Draft

## Context (current state)

The system currently has 20 permissions in a flat list with 3 display groups
(Pages / Downloads / Admin). Problems:

1. **Naming is inconsistent** — `page_chart` (which chart?), `download_cnv` (download what?),
   `download_chart_excel` vs `export_analytics` (mix of "download" and "export" verbs)
2. **No domain grouping** — coupon-related permissions are scattered across Pages and Downloads
3. **Admin cannot tell at a glance** what a group of permissions covers for a given business area
4. **Action type missing from name** — `page_coupon_chart` doesn't convey it's a page permission
   for the coupon chart page

---

## Proposed Permission Structure

### New naming convention: `{domain}.{action}`

| Domain | Actions |
|--------|---------|
| `sales` | `view`, `chart`, `export`, `export_chart` |
| `coupons` | `view`, `chart`, `manage`, `export`, `export_chart` |
| `cnv` | `view`, `chart`, `sync`, `export`, `export_chart` |
| `customers` | `detail` |
| `shops` | `view`, `export` |
| `data` | `upload`, `formulas` |
| `admin` | `users` |

### Migration map (old → new)

| Old codename | New codename | Display label |
|---|---|---|
| `page_analytics` | `sales.view` | View Sales Analytics |
| `page_chart` | `sales.chart` | View Sales Chart |
| `download_analytics` | `sales.export` | Export Sales Analytics (Excel) |
| `download_chart_excel` | `sales.export_chart` | Export Sales Chart (Excel) |
| `page_coupons` | `coupons.view` | View Coupon Dashboard |
| `page_coupon_chart` | `coupons.chart` | View Coupon Chart |
| `download_coupons` | `coupons.export` | Export Coupons (Excel) |
| `download_coupon_chart_excel` | `coupons.export_chart` | Export Coupon Chart (Excel) |
| `manage_campaigns` | `coupons.manage` | Manage Coupon Campaigns |
| `page_cnv_comparison` | `cnv.view` | View Customer Analytics (CNV) |
| `page_customer_chart` | `cnv.chart` | View Customer Chart (CNV) |
| `page_cnv_sync` | `cnv.sync` | View CNV Sync Status |
| `download_cnv` | `cnv.export` | Export Customer Analytics (Excel) |
| `download_customer_chart_excel` | `cnv.export_chart` | Export Customer Chart (Excel) |
| `page_customer_detail` | `customers.detail` | View Customer Detail |
| `page_shop_detail` | `shops.view` | View Shop Detail |
| `download_shop_detail` | `shops.export` | Export Shop Detail (Excel) |
| `page_upload` | `data.upload` | Upload Data |
| `page_formulas` | `data.formulas` | View Formulas |
| `manage_users` | `admin.users` | Manage Users |

---

## User Scenarios & Testing

### User Story 1 — Admin sees domain-grouped permissions (Priority: P1)

An admin goes to `/users/` → Roles tab → opens a role card. Instead of a flat
PAGES / DOWNLOADS / ADMIN list, they see permissions grouped by business domain
with consistent labels.

**Why this priority**: This is the core UX problem. Everything else depends on this.

**Independent Test**: Open the role management page at 1366×768 viewport, 100% browser
zoom, Chrome default font. Confirm that permissions appear in domain groups (Sales Analytics,
Coupons, CNV / Customer Analytics, Customers, Shop Detail, Data Management, Admin), each
with clear section headers. No "Pages" or "Downloads" section headings appear.

**Acceptance Scenarios**:

1. **Given** I open any role's permission card, **When** I view the checkboxes,
   **Then** I see them grouped under domain headers: Sales Analytics, Coupons,
   CNV / Customer Analytics, Customers, Shop Detail, Data Management, Admin.
2. **Given** I view a domain group (e.g. "Sales Analytics"), **When** I read each
   checkbox label, **Then** I can distinguish action type: "View", "View Chart",
   "Export (Excel)", "Export Chart (Excel)" — without needing to read the codename.
3. **Given** I view the permissions list at 768px wide viewport (tablet), **When** I
   inspect the layout, **Then** each domain group header and its checkboxes remain
   visually distinct (header clearly separated from checkboxes below it, no overlapping).

---

### User Story 2 — Existing roles are automatically migrated (Priority: P1)

When the feature is deployed, all roles that currently have old-style codenames
(`page_analytics`, `download_coupons`, etc.) must retain exactly the same access —
no admin re-configuration required.

**Why this priority**: Losing access on deploy is a critical regression. Existing
users must not be logged out or blocked from pages they previously could access.

**Independent Test**: Before deploy, run `python manage.py perm show` and record each
role's permission list. After deploy + `perm sync`, run `perm show` again. Every old
codename must map to exactly one new codename per the migration map. No permissions
may be lost or added beyond what the map specifies.

**Acceptance Scenarios**:

1. **Given** a role has `["page_analytics", "download_coupons"]` stored,
   **When** `perm sync` runs, **Then** the role now has `["sales.view", "coupons.export"]`
   and no other permissions are added or removed.
2. **Given** the built-in `admin` role (previously all 20 old codenames), **When** `perm sync`
   runs, **Then** it has exactly all 20 new codenames — no more, no less.
3. **Given** the built-in `viewer` role (previously `["page_analytics"]`),
   **When** `perm sync` runs, **Then** it has `["sales.view"]` and a user with that role
   can still access the Sales Analytics dashboard.

---

### User Story 3 — Admin can grant/revoke by domain group (Priority: P2)

When configuring a role, an admin can check/uncheck an entire domain group
(e.g., "Coupons") with one click, which toggles all permissions in that group.

**Why this priority**: Improves speed of role configuration. A "viewer" role for
only the coupon team currently requires individually checking 5 separate items.

**Independent Test**: Click the "Coupons" group header checkbox. Verify all 5 coupon
permissions toggle together. Uncheck the group — all 5 uncheck. Mix: check 3 of 5
manually — group header shows indeterminate state. Click "Save Permissions" — verify
the role is persisted correctly.

**Acceptance Scenarios**:

1. **Given** a role has no coupon permissions, **When** I click the "Coupons" group
   toggle and click "Save Permissions", **Then** all 5 coupon permissions are saved
   to the role in one Save action.
2. **Given** a role has all coupon permissions, **When** I click the "Coupons" toggle
   and save, **Then** all 5 coupon permissions are removed from the role.
3. **Given** a role has 2 of 5 coupon permissions, **When** I view the "Coupons" header,
   **Then** the group checkbox shows an indeterminate (partial) state.

---

### Edge Cases

- A role stored with an unknown codename (neither old nor new format) — the codename is
  stripped silently during `perm sync` (existing behavior: Step 2 in `_sync()` removes
  any codename not present in `PERMISSION_DEFS`). This is current behavior, not a new requirement.
- A permission codename with a dot (`.`) must work correctly in all view decorators,
  `_ajax_perm_check()` calls, and template tag checks.
- The built-in `admin` and `viewer` roles are updated by overwriting their permissions
  with `ADMIN_PERMISSIONS` / `VIEWER_PERMISSIONS` from `permissions.py` — not via `PERM_RENAMES`.
  Custom roles are migrated via `PERM_RENAMES`.
- Running `perm sync` twice after migration is safe — the command is idempotent. Second
  run finds no old codenames in `PERM_RENAMES` (already renamed) and no obsolete codenames
  to strip, so it makes no changes.

---

## Requirements

### Functional Requirements

- **FR-001**: The system MUST rename all 20 existing permission codenames to the
  `{domain}.{action}` format per the migration map above, by updating `PERMISSION_DEFS`,
  `ADMIN_PERMISSIONS`, and `VIEWER_PERMISSIONS` in `App/permissions.py`.

- **FR-002**: All 20 old→new codename mappings MUST be added to the `PERM_RENAMES` dict
  in `App/management/commands/perm.py`. Running `python manage.py perm sync` after deploy
  will then: (a) overwrite built-in roles with updated `ADMIN_PERMISSIONS`/`VIEWER_PERMISSIONS`,
  (b) rename old codenames in custom roles via `PERM_RENAMES`, (c) strip any remaining
  obsolete codenames. The command is run once post-deploy by the operator.

- **FR-003**: The system MUST display permissions on the role management page grouped
  by 7 domain sections: Sales Analytics, Coupons, CNV / Customer Analytics,
  Customers, Shop Detail, Data Management, Admin.

- **FR-004**: Each domain group MUST show a group-level toggle checkbox that
  checks/unchecks all permissions in that group (with indeterminate state support).

- **FR-005**: All permission checks in the codebase MUST be updated to use new codenames
  in the same release as `PERMISSION_DEFS`. This includes: `@requires_perm` decorators,
  `_ajax_perm_check()` inline calls in AJAX views, and `{% check_perm %}` template tags.
  No dual-mode compatibility layer is introduced.

- **FR-006**: The built-in `VIEWER_PERMISSIONS` list MUST be updated to `["sales.view"]`.

- **FR-007**: The built-in `ADMIN_PERMISSIONS` list MUST contain all 20 new codenames.

- **FR-008**: Rollback procedure:
  - **Before deploy**: operator runs `python manage.py perm show` and saves the output
    as a reference snapshot of all role permissions.
  - **Built-in roles**: revert the deploy (restoring old `PERMISSION_DEFS`) + re-run
    `perm sync` → admin and viewer are overwritten back to old codenames automatically.
  - **Custom roles**: if rollback is needed, operator manually restores permissions from
    the pre-deploy `perm show` snapshot using `perm add` / `perm remove` commands.
    No automatic reverse is provided.

### Key Entities

- **Role**: has a `permissions` JSONField containing a list of codename strings.
  After migration, all strings follow `{domain}.{action}` format.
- **PermissionGroup**: a new display-only concept (not stored in DB) — a named group
  of related permissions shown as a section in the UI.
- **PERMISSION_DEFS**: the source-of-truth list in `App/permissions.py` defining codename,
  display label, and group membership — updated to reflect new codenames and 7 domain groups.
- **PERM_RENAMES**: dict in `perm.py` mapping old codename → new codename(s). This feature
  adds all 20 rename entries.

---

## Success Criteria

- **SC-001**: Every permission checkbox on the role management page is visible under a
  domain group header without requiring the user to read the codename. Verified by: opening
  a role card and confirming each checkbox's label uniquely identifies its action within
  the group (e.g., "View", "Export (Excel)") without ambiguity.
- **SC-002**: Configuring a role for a single business domain takes ≤ 2 user actions:
  1 group toggle (stages all permissions in that domain) + 1 "Save Permissions" click to persist.
- **SC-003**: Zero roles require manual reconfiguration after deployment — 100% automated
  migration via `perm sync`.
- **SC-004**: All existing role-gated pages remain accessible to users with the same
  roles after deployment (0 regressions). Verified by: running `perm show` before and after,
  and smoke-testing each of the 20 permission-gated pages with a test account per role.
- **SC-005**: At 1366×768 viewport, 100% zoom, Chrome default font, the full permission
  list for a role fits within the visible area of the role card without vertical scrolling
  inside the card.

---

## Clarifications

### Session 2026-04-22 (QA review follow-up)

- Q: Custom role rollback procedure if deploy must be reverted after `perm sync` ran? → A: Operator runs `perm show` before deploy as snapshot; restores manually via `perm add`/`perm remove`. No automatic reverse.
- Q: Does the domain group toggle auto-save or stage until "Save Permissions"? → A: Staged — visual only until Save click. Consistent with existing checkbox behaviour.

### Session 2026-04-22

- Q: When and how does the permission rename happen during deployment? → A: Via the existing
  `perm sync` management command. Custom roles renamed via `PERM_RENAMES` dict; built-in roles
  overwritten from `ADMIN_PERMISSIONS`/`VIEWER_PERMISSIONS`. Run once post-deploy.
- Q: Should the `admin` permission domain be renamed to avoid collision with the built-in role name?
  → A: No — keep `admin.users`. Domain refers to action category; UI shows the label, not the codename.
- Q: Should old codenames work temporarily as aliases after `perm sync` runs? → A: Hard cutover —
  all permission checks updated in the same release; old codenames removed immediately.

### Open Decisions

- **H1 — Custom role rollback**: Operator runs `perm show` before deploy as a snapshot.
  Built-in roles auto-restore via revert + re-run `perm sync`. Custom roles restored manually
  from snapshot using `perm add`/`perm remove`. No automatic reverse is provided. → **Resolved**.
- **H2 — Group toggle save behaviour**: Staged — group toggle updates checkboxes visually only;
  admin must click "Save Permissions" to persist. Consistent with existing individual checkbox
  behaviour. SC-002 = 2 actions (toggle + Save). → **Resolved**.

---

## Assumptions

- The `permissions` field on Role is a plain JSON list of strings — no relational FK
  to a permission table. Migration via `PERM_RENAMES` is a pure JSON string-replace operation.
- There are currently 2 built-in roles (`admin`, `viewer`) stored in the database; they are
  migrated by overwriting with updated `ADMIN_PERMISSIONS`/`VIEWER_PERMISSIONS`, not via `PERM_RENAMES`.
- The `.` character in permission codenames does not conflict with any Django internals
  or template tag parsing in this project.
- No external system (API, webhook, third-party) reads or writes permission codenames
  — they are internal to this Django app only.
- The group-level toggle (US3) is a frontend-only convenience; the underlying data model
  still stores individual permission codenames, not group-level grants.
- Unknown/obsolete codenames in custom roles are stripped silently by `perm sync` — this
  is existing behavior in `_sync()` Step 2, not a new requirement.
