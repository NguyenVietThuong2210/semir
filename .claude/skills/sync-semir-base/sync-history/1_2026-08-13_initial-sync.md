# Sync #1 — 2026-08-13

**Trigger:** Port to `semir-base` everything from the 2026-08 production incident response session in `semir`:
1. Upload batch_size revert (OOM mitigation) — 5 import services
2. Products/Shop-Detail tab race-condition fix (JS)
3. `prod_visual.py` hardening (retry + refuse-to-save-if-Loading, spinner-wait for `_click_all_tabs`)

Explicitly **not** in scope: the CNV customer-analytics OOM memory fix (`build_inv_bucket_map_from_db`), since that function is dead code in semir-base.

**Repos:**
- Source: `D:\New-jouney\semir` (branch `release/2.3.2` at time of sync)
- Target: `D:\New-jouney\semir-base` (branch `no-cnv`)
- **semir HEAD commit hash at time of sync:** `bbb17182c309f6829e3d9b41894bb2be96440045` (2026-08-13 21:35:54 +0700) — recorded per SKILL.md Step 6 so the *next* sync can run `git log bbb17182c309f6829e3d9b41894bb2be96440045..HEAD --stat` in semir as a reliable "what changed since" check. Note: as documented below, this hash alone would NOT have caught everything for *this* sync (several files were committed under it before the sync was even requested) — the file list for sync #1 came from conversation-history recall, not this hash. This hash is the baseline for sync #2 onward.

---

## Step 0 — Safety check

`git status --short` in semir-base before starting showed only the 5 import-service files already modified from an earlier partial sync attempt within the same session (batch_size). No unexpected/foreign uncommitted work found. Proceeded.

---

## Step 1 — File enumeration

Enumerated from conversation history (every file touched via Edit/Write during this session) rather than `git status`, because `git status` in the main `semir` repo showed only `tests/prod_visual.py` as modified at the time of this sync — the other files (checkpoint fix, batch_size revert, memory fix, race-condition fix) had **already been committed** (commit `bbb17182 "update"` and earlier in the same chain) by a process outside this session's visibility before the sync was requested. This is the exact "git status is unreliable" gotcha now documented in SKILL.md.

Candidate list (19 files):
`shop_detail_data.py`, `sync_service.py`, `scheduler.py`, `api_client.py`, `rate_limit.py`, `sync_cnv.py`, `check_cnv_gap.py`, `customer_import.py`, `sales_import.py`, `coupon_import.py`, `inventory_import.py`, `sale_detail_import.py`, `customer_utils.py`, `product/dashboard.html`, `shop_detail/_product_partial.html`, `prod_visual.py`, `test_customer.py`, `test_cnv_sync.py`, `test_bugfixes.py`.

---

## Step 2 & 3 — Classification and action

| # | File | Outcome | Evidence / reason | Action taken |
|---|------|---------|--------------------|---------------|
| 1 | `App/services/customer_import.py` | A. SYNC | General upload code | `bulk_create`/`bulk_update` batch_size 2600/1800 → 1000 |
| 2 | `App/services/sales_import.py` | A. SYNC | General upload code | batch_size 3000/1800 → 1000 |
| 3 | `App/services/coupon_import.py` | A. SYNC | General upload code | batch_size 3000/1900 → 1000 |
| 4 | `App/services/inventory_import.py` | A. SYNC | General upload code | `BATCH_SIZE` 2000 → 1000 |
| 5 | `App/services/sale_detail_import.py` | A. SYNC | General upload code | `BATCH_SIZE` 1700 → 1000 |
| 6 | `App/templates/product/dashboard.html` | A. SYNC | General Product Analytics page, not CNV | Added `currentTab` guard to Section 1 tab-click handler — supersedes-response fix |
| 7 | `App/templates/shop_detail/_product_partial.html` | A. SYNC | General Shop Detail section, not CNV | Same `currentTab` guard pattern applied |
| 8 | `tests/prod_visual.py` | A. SYNC | General QA tooling | `_shot()` hardened (5x retry + refuse-to-save + delete stale file if still Loading); PASS B settle replaced with spinner-wait (`[id$=Spinner]` generic selector) |
| 9 | `App/analytics/customer_utils.py` | C. SKIP — dead code | `grep -rn "build_inv_bucket_map_from_db(" App/` in semir-base → 0 callers (App/cnv/ doesn't exist) | Not synced |
| 10 | `App/analytics/shop_detail_data.py` | D. SKIP — expected divergence | `get_shop_detail_customer_data()` calls `App.cnv.service.compute_cnv_breakdown` — no equivalent in semir-base | Not synced |
| 11 | `App/cnv/sync_service.py` | B. SKIP — CNV-only | `App/cnv/` doesn't exist in semir-base | N/A |
| 12 | `App/cnv/scheduler.py` | B. SKIP — CNV-only | same | N/A |
| 13 | `App/cnv/api_client.py` | B. SKIP — CNV-only | same | N/A |
| 14 | `App/cnv/rate_limit.py` | B. SKIP — CNV-only | same | N/A |
| 15 | `App/management/commands/sync_cnv.py` | B. SKIP — CNV-only | same | N/A |
| 16 | `App/management/commands/check_cnv_gap.py` | B. SKIP — CNV-only | same | N/A |
| 17 | `tests/test_customer.py` | B. SKIP — CNV-only | `InvBucketMapMemoryOptTest` tests dead-in-semir-base code (#9); rest of file uses `compute_cnv_comparison` | N/A |
| 18 | `tests/test_cnv_sync.py` | B. SKIP — CNV-only | Tests `App.cnv.sync_service` directly | N/A |
| 19 | `tests/test_bugfixes.py` | D. SKIP — expected divergence | Diff is entirely `CnvAjaxAuthGuardTest`, `SyncSkipNoDateTest`, CNV scheduler cadence test classes | N/A |

**8 files SYNC'd (1–8), 11 correctly skipped (9–19) with documented evidence.**

---

## Step 4 — Verification results

All 8 synced files verified via `diff --strip-trailing-cr` (CRLF-normalized):

| File | Result |
|------|--------|
| `customer_import.py` | 1-line comment-wording-only diff remains (functionally identical: `BATCH_SIZE=1000` matches) |
| `sales_import.py` | same — comment wording only |
| `coupon_import.py` | same — comment wording only |
| `inventory_import.py` | same — comment wording only |
| `sale_detail_import.py` | same — comment wording only (initially misread as "whole file differs" due to a CRLF-only false positive from plain `diff -q`; re-verified byte-for-byte with Python, confirmed only 1 comment line differs) |
| `product/dashboard.html` | **empty diff — 100% identical** |
| `shop_detail/_product_partial.html` | **empty diff — 100% identical** |
| `prod_visual.py` | Only the pre-existing, already-documented expected divergence remains (missing 3 CNV `PAGES` entries, genericized comment wording) — the new hardening code is byte-identical in both |

`python -m py_compile tests/prod_visual.py` → OK, no syntax errors.

---

## Step 5 — Hard rule gate: prove no calculated/output value changed

Retroactively executed 2026-08-14, after SKILL.md was revised to add this step (it did not exist when sync #1 was originally performed).

**5a. Full test suite, WITHOUT `UPDATE_SNAPSHOTS`:**
```bash
cd SemirDashboard && ../venv/Scripts/python manage.py test tests -v 1
```
Result: `Ran 516 tests in 3191.905s` → `FAILED (failures=1, errors=1, skipped=5)`. The 2 failures are `test_refresh_returns_new_refresh_token` and `test_old_refresh_still_valid_phase1`, both in `TokenRefreshRotationTest`. Cross-checked against `semir-base/plan_cnv_removal.md` line 15: *"Final result: 516 tests, 514 pass, 1 failure + 1 error — both the same pre-existing, order-dependent login-throttle flake (`TokenRefreshRotationTest`), confirmed unrelated to CNV by running it in isolation (passes cleanly alone)."* **Exact match to the pre-documented baseline — zero new failures caused by the sync.**

Since every `assert_snapshot()` call compares live-computed data against the stored JSON and fails on mismatch, this clean pass (matching the known baseline exactly) is itself direct proof that the sync (batch_size revert + JS tab-guard fix) did not alter any calculated/snapshotted value.

**5b. `UPDATE_SNAPSHOTS=1` regeneration + diff — deliberately SKIPPED.**
Reasoning: 5a already proves no snapshot value changed (see above); re-running the ~53-minute full suite a second time for this specific sync (batch_size tuning + client-side-only JS guard, neither of which touches Python calculation/aggregation code) would be redundant expense with no incremental evidence value. Per the revised SKILL.md, 5b is reserved for syncs that plausibly touch calculation/aggregation logic not fully exercised by existing snapshot assertions — not applicable here.

**5c. Template snapshot regen + visual check** (for the 2 synced `.html` files):
```bash
../venv/Scripts/python manage.py shell -c "exec(open('tests/snapshot_render.py').read())"
python tests/snapshot_visual.py
```
`snapshot_render.py` log confirmed: **"Total token issues across all pages: 0"**. Visually inspected (via Read tool) `tests/render/png/28_product_tab_brand.png` and `tests/render/png/22_product_shop_tab.png` — both show correct, complete, properly-labeled brand/shop data tables, no broken layout, no stuck-"Loading" artifacts.

**5d. Targeted test modules** for the changed files:
```bash
../venv/Scripts/python manage.py test tests.test_upload tests.test_shop_detail -v 2
```
Covers `test_upload.py` (batch_size-affected import services) and `test_shop_detail.py` (shop-detail product partial template, incl. `sales_alltime_vs_shop_tab`, `ajax_sales_partial`, `sales_period_vs_shop_tab_2025`, `snapshot_coupon_full`, `snapshot_sales_full` snapshot-verified checkpoints). Result: **`Ran 66 tests in 307.527s` → `OK`** — clean pass, zero failures.

**Step 5 verdict: PASS.** 5a full-suite matches documented baseline exactly (0 new failures), 5c shows 0 token issues + visually-confirmed correct rendering, 5d targeted modules 66/66 pass. No calculated/output value changed as a result of sync #1.

---

## Step 6 — Independent sub-agent verification

Retroactively executed 2026-08-14 via an independent `general-purpose` sub-agent (read-only, no repo access to this conversation's history — re-derived everything from the two repos on disk plus this history file).

**Verdict: SAFE — sync is accurate and complete, matches the record.**

Key independent findings:
- All 8 synced files re-diffed from scratch (CRLF-normalized): 5 import services show only comment-wording deltas, `batch_size`/`BATCH_SIZE` confirmed `1000` everywhere in both repos; both templates are **byte-identical**, `currentTab` guard confirmed present in **both** `.then()` and `.catch()` blocks (not just success path) in both files; `prod_visual.py` diff shows only the pre-existing expected CNV-page divergence.
- `python -m py_compile` clean on all 6 synced `.py` files.
- Sampled 5 of 11 skip claims independently — all held up (`build_inv_bucket_map_from_db` genuinely 0 callers repo-wide; `App/cnv/` genuinely absent; `shop_detail_data.py` has no CNV refs; `test_bugfixes.py` diff is purely CNV-only additions with nothing extraneous added to base).
- **New finding, not previously noted:** `git status --short` in semir-base shows ~150 additional modified files beyond the 8 sync files — these are byproducts of this sync's own Step 5 verification run (`tests/render/*`, `tests/snapshots/*`). Spot-checked 3 snapshot JSON diffs (`sales_alltime.json`, `coupon_alltime.json`, `product_season.json`): only `_last_run` timestamp lines changed in each. Expected noise, not stray work — **but must be excluded or explained when committing**, so it isn't mistaken for unrelated changes.

No gaps found.

---

## Outstanding / follow-up items

- Nothing committed in `semir-base` yet — user has not yet confirmed whether to commit.
- If `semir-base` later re-adds any CNV-like feature, re-check the "dead code" classification for `build_inv_bucket_map_from_db` (#9) — it may become live again.
