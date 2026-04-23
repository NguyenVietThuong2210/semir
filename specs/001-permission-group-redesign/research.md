# Research: Permission Group Redesign

**Phase**: 0 — Pre-design research  
**Date**: 2026-04-23  
**Status**: Complete — no unknowns remain

All decisions were resolved during `/speckit-clarify` (two sessions, 2026-04-22).
No NEEDS CLARIFICATION markers were outstanding when planning began.
This file records the confirmed decisions and rationale for traceability.

---

## Decision 1 — Migration mechanism

**Decision**: Use the existing `perm sync` management command (`App/management/commands/perm.py`).
Custom roles are migrated by adding 20 entries to `PERM_RENAMES`. Built-in roles (`admin`,
`viewer`) are overwritten wholesale from updated `ADMIN_PERMISSIONS`/`VIEWER_PERMISSIONS`.

**Rationale**: The mechanism already exists and is production-tested (used previously for
`page_cnv → [page_cnv_sync, page_cnv_comparison]` split). No new infrastructure needed.
Operator runs it once post-deploy. Command is idempotent — safe to run again.

**Alternatives considered**:
- Data migration (Django `0xxx_migration.py`): rejected — permissions stored as plain JSON
  strings, not FK relations. A management command is simpler and operator-visible.
- Automatic on startup: rejected — could cause unintended side effects if app is restarted
  before the operator is ready to verify.

---

## Decision 2 — Codename format

**Decision**: `{domain}.{action}` using a dot separator. Seven domains:
`sales`, `coupons`, `cnv`, `customers`, `shops`, `data`, `admin`.

**Rationale**: Dot separates namespace from action without ambiguity. Confirmed safe in
`user_has_perm()` (plain Python `in` test), `@requires_perm`, `_ajax_perm_check()`, and
`{% check_perm %}` template tag — none of them parse the codename string.

**Alternatives considered**:
- Underscore separator (`sales_view`): rejected — looks identical to old convention and doesn't
  visually signal the domain.action grouping.
- Slash separator (`sales/view`): rejected — conflicts with URL path conventions.

---

## Decision 3 — `admin` domain name

**Decision**: Keep `admin.users` as the codename for the user management permission. The domain
name `admin` refers to the action category (administrative actions), not the built-in role name.

**Rationale**: UI shows the display label ("Manage Users"), not the codename. No collision risk
in the permission check system (`user_has_perm` checks the codename string against a list —
role name is irrelevant). Clarified in session 2026-04-22.

---

## Decision 4 — Hard cutover vs. alias period

**Decision**: Hard cutover. All permission checks in view code (`@requires_perm`,
`_ajax_perm_check`, `{% check_perm %}`) updated in the same release as `PERMISSION_DEFS`.
No old codenames remain as aliases after deploy.

**Rationale**: Alias mode adds complexity and a future cleanup task. Since all call-sites are
internal (no external API consumers), a clean cut is safe and avoids indefinite dual-mode state.

---

## Decision 5 — Group toggle save behaviour

**Decision**: Staged (visual only). Group toggle checks/unchecks all child checkboxes in the
domain group but does not auto-save. Admin must click "Save Permissions" to persist.

**Rationale**: Consistent with existing individual checkbox behaviour on the same page.
SC-002 = 2 actions: 1 group toggle (stage all permissions in domain) + 1 "Save Permissions".

---

## Decision 6 — Custom role rollback

**Decision**: No automatic reverse. Operator runs `perm show` before deploy as a snapshot.
If rollback needed for custom roles, operator manually restores using `perm add` / `perm remove`
from the snapshot. Built-in roles auto-restore via code revert + re-run `perm sync`.

**Rationale**: Reverse `PERM_RENAMES` would require a separate inverse dict and a new `perm
rollback` sub-command. Given the low number of custom roles in production, manual restore from
a text snapshot is a proportionate procedure for a rare rollback scenario.

---

## Code archaeology — confirmed facts

| Question | Finding | Source |
|---|---|---|
| Dot safe in codename? | Yes — `user_has_perm` uses `codename in list` | `App/permissions.py:44` |
| PERM_RENAMES mechanism exists? | Yes — maps `old → [new, ...]` | `App/management/commands/perm.py:57` |
| perm sync idempotent? | Yes — checks `if old_code in perms` before acting | `perm.py:99` |
| Users.py grouping logic? | `categories.setdefault(category, [])` from PERMISSION_DEFS[2] | `App/views/users.py:111` |
| Template grouping loop? | `{% for category, perms in permission_categories.items %}` | `user_management.html:156` |
| Unknown codename stripping? | Step 2 of `_sync()` — existing behaviour | `perm.py:109-117` |
| ADMIN_PERMISSIONS definition? | `ADMIN_PERMISSIONS = ALL_PERMISSIONS` (auto-derives from PERMISSION_DEFS) | `permissions.py:30` |
