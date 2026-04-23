# Data Model: Permission Group Redesign

**Phase**: 1 — Design  
**Date**: 2026-04-23

No DB schema changes in this feature. All entities below are in-memory Python structures
or existing DB fields reused with new string values.

---

## Entities

### Role (existing DB model — `App/models/user.py`)

```python
class Role(Model):
    name        = CharField(max_length=50, unique=True)
    permissions = JSONField(default=list)   # list[str] — codenames
    is_system   = BooleanField(default=False)
```

**Changes**: None to schema. After `perm sync`, the `permissions` list contains new-format
codenames (`{domain}.{action}`) instead of old-format ones. The JSONField stores plain strings
— no migration file needed.

**Invariants after migration**:
- `admin` role: exactly all 20 new codenames, nothing else
- `viewer` role: exactly `["sales.view"]`
- Custom roles: every codename is a valid key in the new `PERMISSION_DEFS`

---

### PERMISSION_DEFS (in-memory — `App/permissions.py`)

A Python list of 3-tuples: `(codename: str, display_label: str, domain_group: str)`.

**New structure** (20 entries, 7 domain groups):

| # | codename | display_label | domain_group |
|---|---|---|---|
| 1 | `sales.view` | View Sales Analytics | Sales Analytics |
| 2 | `sales.chart` | View Sales Chart | Sales Analytics |
| 3 | `sales.export` | Export Sales Analytics (Excel) | Sales Analytics |
| 4 | `sales.export_chart` | Export Sales Chart (Excel) | Sales Analytics |
| 5 | `coupons.view` | View Coupon Dashboard | Coupons |
| 6 | `coupons.chart` | View Coupon Chart | Coupons |
| 7 | `coupons.export` | Export Coupons (Excel) | Coupons |
| 8 | `coupons.export_chart` | Export Coupon Chart (Excel) | Coupons |
| 9 | `coupons.manage` | Manage Coupon Campaigns | Coupons |
| 10 | `cnv.view` | View Customer Analytics (CNV) | CNV / Customer Analytics |
| 11 | `cnv.chart` | View Customer Chart (CNV) | CNV / Customer Analytics |
| 12 | `cnv.sync` | View CNV Sync Status | CNV / Customer Analytics |
| 13 | `cnv.export` | Export Customer Analytics (Excel) | CNV / Customer Analytics |
| 14 | `cnv.export_chart` | Export Customer Chart (Excel) | CNV / Customer Analytics |
| 15 | `customers.detail` | View Customer Detail | Customers |
| 16 | `shops.view` | View Shop Detail | Shop Detail |
| 17 | `shops.export` | Export Shop Detail (Excel) | Shop Detail |
| 18 | `data.upload` | Upload Data | Data Management |
| 19 | `data.formulas` | View Formulas | Data Management |
| 20 | `admin.users` | Manage Users | Admin |

**Derived values** (auto-computed from the list above — no separate change needed):
- `ALL_PERMISSIONS = [p[0] for p in PERMISSION_DEFS]` → all 20 new codenames
- `ADMIN_PERMISSIONS = ALL_PERMISSIONS` → all 20
- `VIEWER_PERMISSIONS = ["sales.view"]` → explicit list (must be set manually)

---

### PERM_RENAMES (in-memory — `App/management/commands/perm.py`)

A Python dict mapping old codename → list of new codenames. Used by `perm sync` Step 1
to migrate custom roles.

**New entries to add** (20 one-to-one renames):

```python
PERM_RENAMES = {
    # existing entry (keep):
    'page_cnv': ['page_cnv_sync', 'page_cnv_comparison'],

    # new entries for this feature:
    'page_analytics':               ['sales.view'],
    'page_chart':                   ['sales.chart'],
    'download_analytics':           ['sales.export'],
    'download_chart_excel':         ['sales.export_chart'],
    'page_coupons':                 ['coupons.view'],
    'page_coupon_chart':            ['coupons.chart'],
    'download_coupons':             ['coupons.export'],
    'download_coupon_chart_excel':  ['coupons.export_chart'],
    'manage_campaigns':             ['coupons.manage'],
    'page_cnv_comparison':          ['cnv.view'],
    'page_customer_chart':          ['cnv.chart'],
    'page_cnv_sync':                ['cnv.sync'],
    'download_cnv':                 ['cnv.export'],
    'download_customer_chart_excel': ['cnv.export_chart'],
    'page_customer_detail':         ['customers.detail'],
    'page_shop_detail':             ['shops.view'],
    'download_shop_detail':         ['shops.export'],
    'page_upload':                  ['data.upload'],
    'page_formulas':                ['data.formulas'],
    'manage_users':                 ['admin.users'],
}
```

**Note**: The existing `page_cnv` entry must be retained. If a custom role still holds
`page_cnv` (from a pre-previous migration), Step 1 will expand it to `[page_cnv_sync,
page_cnv_comparison]`, then the new entries will rename those to `[cnv.sync, cnv.view]`
in the same sync run (because the expanded codenames are now in the dict as keys too).
Order matters: PERM_RENAMES is applied iterating dict keys — in Python 3.7+ dicts are
insertion-ordered, so put `page_cnv` first.

---

### PermissionGroup (display-only concept — no DB storage)

A named group of related permissions shown as a collapsible section in the UI.
Derived at request time from `PERMISSION_DEFS` in `users.py`:

```python
categories = {}
for codename, display, group in PERMISSION_DEFS:
    categories.setdefault(group, []).append((codename, display))
# Result:
# {
#   "Sales Analytics":          [("sales.view", "View Sales Analytics"), ...],
#   "Coupons":                  [("coupons.view", "View Coupon Dashboard"), ...],
#   "CNV / Customer Analytics": [("cnv.view", "View Customer Analytics (CNV)"), ...],
#   "Customers":                [("customers.detail", "View Customer Detail")],
#   "Shop Detail":              [("shops.view", "View Shop Detail"), ...],
#   "Data Management":          [("data.upload", "Upload Data"), ...],
#   "Admin":                    [("admin.users", "Manage Users")],
# }
```

This dict is passed to the template as `permission_categories`. No change to view logic —
only the values change (new group names and codenames).

---

## State Transitions

### Custom role permissions — before → after `perm sync`

```
Before deploy:  role.permissions = ["page_analytics", "download_coupons", ...]
                                                 ↓ perm sync Step 1 (PERM_RENAMES)
After Step 1:   role.permissions = ["sales.view", "coupons.export", ...]
                                                 ↓ perm sync Step 2 (strip obsolete)
After Step 2:   role.permissions = ["sales.view", "coupons.export", ...]
                (no obsolete remain — all old names were in PERM_RENAMES)
```

### Built-in role permissions — before → after `perm sync`

```
Before deploy:  admin.permissions = [all 20 old codenames]
                viewer.permissions = ["page_analytics"]
                                                 ↓ perm sync (overwrite from ADMIN/VIEWER_PERMISSIONS)
After sync:     admin.permissions = [all 20 new codenames]
                viewer.permissions = ["sales.view"]
```
