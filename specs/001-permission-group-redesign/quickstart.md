# Quickstart: Permission Group Redesign

**Branch**: `001-permission-group-redesign`  
**Date**: 2026-04-23

Quick reference for developers implementing this feature and operators deploying it.

---

## For Developers

### What changes and where

| What | File | Change type |
|------|------|-------------|
| Permission definitions | `App/permissions.py` | Replace 20 tuples (codenames + labels + groups) |
| Viewer default | `App/permissions.py` | `VIEWER_PERMISSIONS = ["sales.view"]` |
| Migration dict | `App/management/commands/perm.py` | Add 20 entries to `PERM_RENAMES` |
| View decorators | `App/views/analytics.py`, `coupon.py`, `customer.py`, `shop_detail.py`, `upload.py`, `users.py`, `home.py` | `@requires_perm("old")` → `@requires_perm("new")` |
| AJAX perm checks | `App/views/customer.py`, `shop_detail.py`, `App/cnv/views.py` | `_ajax_perm_check(request, "old")` → new |
| Template tags | ~30 HTML templates | `{% check_perm 'old' %}` → `{% check_perm 'new' %}` |
| Group toggle UI | `App/templates/user_management.html` | Add group checkbox + indeterminate JS |

### No changes needed

- `App/permissions.py` — `user_has_perm()`, `requires_perm()` functions (no parsing of codename)
- `App/templatetags/perm_tags.py` — calls `user_has_perm()`, no codename parsing
- DB migrations — `Role.permissions` is a JSONField storing strings; schema unchanged
- URL routes — no new endpoints

### Verification commands

```bash
# Run full test suite
cd SemirDashboard && python manage.py test tests -v 2

# Dry-run the permission state before/after
cd SemirDashboard && python manage.py perm show

# Apply migration (development)
cd SemirDashboard && python manage.py perm sync
```

### Testing the group toggle

Open `http://localhost:8000/users/` → Roles tab → open any role card.
- Click a domain group header checkbox → all checkboxes in that group toggle
- Uncheck all except 2 in a group → group header shows indeterminate state
- Click "Save Permissions" → role persists correctly (verify via `perm show`)

---

## For Operators (Deploy Checklist)

### Pre-deploy (do this BEFORE deploying the new code)

- [ ] Run `python manage.py perm show` and save the output as `perm_snapshot_before.txt`
- [ ] Note every role name and its current permission list in the snapshot

### Deploy

- [ ] Deploy the new code (git pull / release)
- [ ] Restart the application server

### Post-deploy (do this immediately after restart)

- [ ] Run `python manage.py perm sync`
- [ ] Confirm output shows:
  - `admin` role updated with 20 new codenames
  - `viewer` role updated to `["sales.view"]`
  - Each custom role shows `migrated <role>: <old> -> [<new>]` for each renamed permission
  - No `DRIFT` or `MISSING` warnings in a follow-up `perm show`
- [ ] Run `python manage.py perm show` and save as `perm_snapshot_after.txt`
- [ ] Compare snapshots: every old codename in before → exactly one new codename in after (per migration map)

### Smoke test

For each role in production, log in as a user with that role and verify:

| Page | Required permission | Old codename | New codename |
|------|--------------------|-|---|
| Sales Analytics | sales.view | page_analytics | sales.view |
| Sales Chart | sales.chart | page_chart | sales.chart |
| Coupon Dashboard | coupons.view | page_coupons | coupons.view |
| CNV Comparison | cnv.view | page_cnv_comparison | cnv.view |
| Customer Detail | customers.detail | page_customer_detail | customers.detail |
| Shop Detail | shops.view | page_shop_detail | shops.view |
| Upload | data.upload | page_upload | data.upload |
| Formulas | data.formulas | page_formulas | data.formulas |
| User Management | admin.users | manage_users | admin.users |

### Rollback procedure

**Built-in roles** (`admin`, `viewer`):
1. Revert the deploy (restore previous code)
2. Restart application server
3. Run `python manage.py perm sync` — built-in roles are overwritten back to old codenames

**Custom roles**:
1. Compare `perm_snapshot_before.txt` (saved pre-deploy) with current `perm show` output
2. For each permission that needs to be restored, run:
   ```bash
   python manage.py perm add --codename <old_codename> --role <role_name>
   python manage.py perm remove --codename <new_codename> --role <role_name>
   ```
   Note: this only works after reverting the code (old codenames must be valid in `PERMISSION_DEFS` again)
