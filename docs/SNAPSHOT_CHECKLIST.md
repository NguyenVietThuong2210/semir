# Snapshot Checklist

**29 snapshot files** in `SemirDashboard/tests/snapshots/`

Each file has `"_last_run"` as the first JSON field — shows the last time that snapshot was written by a UT run.

**Standard run command (always use UPDATE_SNAPSHOTS=1):**
```bash
cd SemirDashboard
UPDATE_SNAPSHOTS=1 python manage.py test tests -v 2
```

After each run, `git diff` should show:
- **Stable data** → only the `_last_run` value changes (1 line per file)
- **Data changed** → more lines changed → investigate the formula

---

## Run results — 2026-04-02 (51/51 PASS)

### COUPON — 5 files ✓

| File | `_last_run` | Git diff | Notes |
|------|------------|----------|-------|
| `coupon_2025.json` | 2026-04-02 20:27:44 | `1+` | First-time `_last_run` added |
| `coupon_alltime.json` | 2026-04-02 20:27:45 | `1+` | First-time `_last_run` added |
| `coupon_tab_detail.json` | 2026-04-02 20:33:24 | `1+` | First-time `_last_run` added |
| `coupon_tab_duplicates.json` | 2026-04-02 20:33:24 | `1+` | First-time `_last_run` added |
| `coupon_tab_shop.json` | 2026-04-02 20:33:25 | `1+` | First-time `_last_run` added |

### CUSTOMER — 11 files ✓

| File | `_last_run` | Git diff | Notes |
|------|------------|----------|-------|
| `customer_2025.json` | 2026-04-02 20:38:34 | `1+` | First-time `_last_run` added |
| `customer_alltime.json` | 2026-04-02 20:38:38 | `1+` | First-time `_last_run` added |
| `customer_breakdown.json` | 2026-04-02 20:38:43 | `450+-` | **BUG FIX**: was all zeros (wrong keys `by_season` vs `season`). Now correct: by_season×8, by_month×21, by_week×92, by_shop×24 |
| `customer_tab_bd_month.json` | 2026-04-02 20:41:39 | `1+` | First-time `_last_run` added |
| `customer_tab_bd_month_allshops.json` | 2026-04-02 20:41:41 | `1+` | First-time `_last_run` added |
| `customer_tab_bd_season.json` | 2026-04-02 20:41:42 | `1+` | First-time `_last_run` added |
| `customer_tab_bd_season_allshops.json` | 2026-04-02 20:41:43 | `1+` | First-time `_last_run` added |
| `customer_tab_bd_shop.json` | 2026-04-02 20:41:45 | `1+` | First-time `_last_run` added. Keys: `by_shop`×24, `shop_detail`×24 (full) |
| `customer_tab_bd_week.json` | 2026-04-02 20:41:46 | `1+` | First-time `_last_run` added |
| `customer_tab_bd_week_allshops.json` | 2026-04-02 20:41:48 | `1+` | First-time `_last_run` added |
| `customer_tab_ca_points.json` | 2026-04-02 20:41:48 | `1+` | First-time `_last_run` added |
| `customer_tab_ca_pos_cnv.json` | 2026-04-02 20:41:51 | `1+` | First-time `_last_run` added |
| `customer_tab_ca_zalo.json` | 2026-04-02 20:41:51 | `109731+-` | **KEY ORDER CHANGE**: field order in CNVCustomer `.values()` changed from refactor. Data is identical, just dict key order differs. Stable after this run. |

### SALES — 11 files ✓

| File | `_last_run` | Git diff | Notes |
|------|------------|----------|-------|
| `sales_2025.json` | 2026-04-02 20:47:43 | `1+` | First-time `_last_run` added |
| `sales_alltime.json` | 2026-04-02 20:47:51 | `1+` | First-time `_last_run` added |
| `sales_tab_grade.json` | 2026-04-02 20:52:55 | `1+` | First-time `_last_run` added |
| `sales_tab_grade_allshops.json` | 2026-04-02 20:52:58 | large | Restored full `by_shop`×22 (was `by_shop_count` only). Keys: `by_grade`×5, `by_shop`×22 |
| `sales_tab_month.json` | 2026-04-02 20:52:59 | `1+` | First-time `_last_run` added |
| `sales_tab_month_allshops.json` | 2026-04-02 20:53:02 | large | Restored full `by_shop`×22 (was `by_shop_count` only). Keys: `by_month`×27, `by_shop`×22 |
| `sales_tab_season.json` | 2026-04-02 20:53:03 | `1+` | First-time `_last_run` added |
| `sales_tab_season_allshops.json` | 2026-04-02 20:53:06 | large | Restored full `by_shop`×22 (was `by_shop_count` only). Keys: `by_session`×10, `by_shop`×22 |
| `sales_tab_shop.json` | 2026-04-02 20:53:09 | `1+` | First-time `_last_run` added |
| `sales_tab_week.json` | 2026-04-02 20:53:10 | `1+` | First-time `_last_run` added |
| `sales_tab_week_allshops.json` | 2026-04-02 20:53:13 | large | Restored full `by_shop`×22 (was `by_shop_count` only). Keys: `by_week`×117, `by_shop`×22 |

---

## After commit: expected git diff per run

Once these changes are committed, every subsequent `UPDATE_SNAPSHOTS=1` run should produce:

```
 coupon_2025.json           | 2 +-   (old _last_run → new _last_run)
 coupon_alltime.json        | 2 +-
 ...all 29 files: 2 +- each...
```

If any file shows more than 2 lines changed → data changed → check formula.

---

## Quick check script

```bash
python -c "
import json, pathlib
snap_dir = pathlib.Path('tests/snapshots')
for f in sorted(snap_dir.glob('*.json')):
    d = json.loads(f.read_text(encoding='utf-8'))
    print(f'{f.name:50s}  {d.get(\"_last_run\", \"MISSING\")}')
"
```

---

## Data consistency rules

| Rule | Check |
|------|-------|
| Grade sum = active_customers | `test_grade_totals_consistent` |
| return_rate in [0, 100] | `test_return_rate_sanity` |
| returning_customers ≤ active_customers | `test_return_rate_sanity` |
| pos_only + shared = total_pos | `test_pos_cnv_math` |
| cnv_only + shared = total_cnv | `test_pos_cnv_math` |
| has_filter=False for all-time | `test_no_filter_flag` |
| has_filter=True for date filter | `test_with_filter_flag` |
