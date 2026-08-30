---
name: "sync-semir-base"
description: "Senior-engineer sync gate: port every non-CNV code change from D:\\New-jouney\\semir into D:\\New-jouney\\semir-base (the 'no-cnv' fork), classify every touched file, verify content-identical (not just git-status), run semir-base's own full test suite + JSON/visual snapshot regeneration as a hard no-output-change gate, trigger an independent sub-agent re-audit, and log the run to a dated history file."
argument-hint: "Optional: specific file path(s) to scope the sync to; omit to sync everything changed since the last recorded sync"
---

## Role

You are a Senior Engineer responsible for keeping `D:\New-jouney\semir-base` (a deliberately **CNV-stripped fork** of `D:\New-jouney\semir`) up to date with every general-purpose fix/improvement made in the main repo, **without ever reintroducing CNV code or silently dropping real differences.**

Act methodically. Do not trust `git status` alone. Do not blindly overwrite files. Verify every claim with an actual diff, not memory. Do not report "done" until an independent sub-agent has re-derived the same conclusion from scratch.

### When to invoke this skill

- User explicitly asks to sync/port changes to semir-base
- User asks "did you sync everything" / "check all related commits" after work spanning both repos
- You (Claude) just finished a non-trivial fix in `semir` and the user's phrasing implies both projects matter (e.g. "make sure semir-base also has this")

Do not self-trigger this skill speculatively — it touches a second repository and should run on explicit signal.

### Repo paths (reference throughout — do not hardcode elsewhere)

| | Path (Windows / Read, Edit tools) | Path (Bash tool) |
|---|---|---|
| Source | `D:\New-jouney\semir` | `/d/New-jouney/semir` |
| Target | `D:\New-jouney\semir-base` | `/d/New-jouney/semir-base` |
| History folder | `D:\New-jouney\semir\.claude\skills\sync-semir-base\sync-history\` | `/d/New-jouney/semir/.claude/skills/sync-semir-base/sync-history/` |

Both repos mirror each other under `SemirDashboard/` (e.g. `SemirDashboard/App/...`, `SemirDashboard/tests/...`) except where semir-base has removed CNV.

---

## Context you must internalize before starting

- **Two separate git repositories**, not branches of one repo:
  - `D:\New-jouney\semir` — the main project (has CNV Loyalty integration under `App/cnv/`)
  - `D:\New-jouney\semir-base` — a full separate clone, branch `no-cnv`, where CNV was **deliberately and completely removed** (commit history there includes "Phase 3: remove CNV test coverage, snapshots, and QA tooling", "CNV removal plan complete"). It has its own `venv/`, its own git history, its own docs (`FINAL_QA_CHECKLIST.md`, `qa_verification_plan.md`, `plan_cnv_removal.md`).
- **`App/cnv/` does not exist at all in semir-base.** Any file/function that only exists to serve CNV (management commands, sync service, scheduler, CNV templates, CNV tests) has **no semir-base equivalent** — this is expected, not a gap.
- **Some shared/general files contain functions used ONLY by CNV callers.** Example found 2026-08-13: `App/analytics/customer_utils.py::build_inv_bucket_map_from_db()` is a general-looking function, but its only caller is `App/cnv/service.py::_fetch_bd_raw()`. In semir-base this function still physically exists (untouched, never deleted) but has **zero callers** — it's dead code. Porting a fix/optimization into dead code has no value and must be explicitly skipped, not silently applied.
- **`git status` / `git diff` against HEAD is NOT reliable for detecting "what changed this session."** Confirmed 2026-08-13: multiple files that were edited via the Edit tool during a session showed as already-committed (not in `git status --short`) by the time the sync was requested — some external process (IDE auto-commit, hook, or the user's own terminal) had already committed them under commit messages like "update". **Always do a content-based diff against semir-base directly — never assume `git status` reflects everything that changed.**
- **CRLF/LF line-ending mismatches produce false "file differs" results.** semir and semir-base can have different `core.autocrlf` behavior. A plain `diff -q` or naive Python `==` comparison without normalizing line endings will report files as different when they are byte-identical in actual content. **Always normalize (`.replace(b'\r\n', b'\n')` or `diff --strip-trailing-cr`) before concluding a real difference exists.**

### ⚠️ These 3 tables are a fast-start hint, not gospel

semir-base evolves independently (its own bugfixes, its own future feature work). A path being "CNV-only" or "dead code" today does not guarantee it stays that way. **Every run, re-verify the specific claim you're relying on (re-grep, re-diff) before skipping a file on the strength of these tables — never skip purely because "the table says so."** Update the tables when reality has moved on (see Self-improve section).

### Known CNV-only paths (skip — do not attempt to sync, do not report as a gap)

| Path | Reason |
|------|--------|
| `App/cnv/**` (entire directory: `sync_service.py`, `scheduler.py`, `api_client.py`, `rate_limit.py`, `service.py`, `views.py`, `models.py`, `urls.py`, `zalo_sync.py`, `input/`) | Does not exist in semir-base |
| `App/management/commands/sync_cnv.py`, `check_cnv_gap.py`, any other CNV-prefixed management command | CNV-only |
| `tests/test_cnv_sync.py`, `tests/test_cnv_scheduler.py` (if exists) | Tests for CNV-only code |
| `App/templates/cnv/**` | CNV-only templates |
| Any function/view/URL whose only reason to exist is serving `/cnv/*` routes | N/A in semir-base |

### Known "dead code in semir-base" spots (skip fixes here — update this table when you find more)

| File | Function/section | Why dead in semir-base |
|------|-------------------|------------------------|
| `App/analytics/customer_utils.py` | `build_inv_bucket_map_from_db()` | Only caller is `App/cnv/service.py::_fetch_bd_raw()`, which doesn't exist there |

### Files with **expected, permanent divergence** (do not try to make identical — verify the divergence is still exactly what's expected, nothing more)

| File | Expected divergence |
|------|---------------------|
| `App/analytics/shop_detail_data.py` | semir-base is missing `get_shop_detail_customer_data()` and any CNV enrichment block in `get_shop_detail_coupon_data()` (the `cnv_id`/`cnv_points` fields) |
| `App/analytics/customer_utils.py` | semir-base's docstrings mention only Customer Analytics, not "CNV page (cnv/views.py)"; `get_customer_analytics_context()` (or equivalent) lacks the `cnv_customer`/`is_synced_to_cnv` fields |
| `tests/prod_visual.py` | semir-base's `PAGES` list is missing the 3 CNV entries (`10_cnv_customer`, `11_cnv_chart`, `12_cnv_sync_status`); comments mention "Sales Analytics and Coupons" instead of "...and CNV Customer Analytics" |
| `tests/test_bugfixes.py` | semir-base is missing `CnvAjaxAuthGuardTest`, `SyncSkipNoDateTest`, and any CNV scheduler cadence test |

---

## Execution Steps

**Quick flow (8 gated steps — each blocks the next on failure):**
`0 Safety check` → `1 Enumerate files` → `2 Classify A/B/C/D` → `3 Apply A-files` → `4 Byte-diff verify` → `5 Hard-rule gate: full suite + JSON snapshots + visual snapshots` → `6 Independent sub-agent audit` → `7 Write history` → `8 Report to user`

### Step 0 — Safety check: is semir-base clean?

```bash
cd /d/New-jouney/semir-base && git status --short
```

"Expected" = every modified/untracked path shown here appears in the file list of the most recent `sync-history/` entry (meaning it's this skill's own prior, still-uncommitted work). Anything else — a file this skill has no record of touching — is **unexpected**: STOP and ask the user before proceeding; it may be independent work in progress in semir-base you must not clobber. Do not proceed past this step without a clean state or one you've explicitly confirmed with the user.

---

### Step 1 — Enumerate every file changed in semir since the last sync

Do **not** rely on `git status`/`git log` alone — confirmed unreliable (see Context above: commits can land outside this session's visibility). Use this combined approach:

1. Read the most recent file under `sync-history/` (highest numeric prefix). It should record the semir `HEAD` commit hash **as of that sync** (this is why Step 6 requires writing it — every sync after the first can then run `git log <recorded-hash>..HEAD --stat` in semir as a genuine, reliable source of "what changed since last sync," in addition to #2 below). If the folder is empty, this is sync #1 — skip this cross-check, rely on #2.
2. Independently build a list of every file you (Claude) edited via Edit/Write across the current conversation, regardless of what git shows — this is the primary, most-reliable source, since it's a direct record of intent, not inferred from git state which has proven to lag or diverge. Do not skip files just because they "feel minor."
3. Union both lists. Treat any mismatch between #1's git-based list and #2's conversation-based list as a signal to look closer, not to silently prefer one — if git shows a file changed that you don't remember editing, investigate before proceeding (could be the user's own edit, which still needs syncing).

Produce an explicit numbered list of every candidate file before moving to Step 2. If `argument-hint` scoped this run to specific files, still do this enumeration but limit the list to those files.

---

### Step 2 — Classify every file

For each file in the Step 1 list, determine one of four outcomes and record it:

| Outcome | Criteria |
|---------|----------|
| **A. SYNC** | File is general-purpose, exists (or should exist) in semir-base, change is not CNV-specific |
| **B. SKIP — CNV-only, doesn't exist in semir-base** | Path matches "Known CNV-only paths" table, or file demonstrably imports/calls `App.cnv.*` / `CNVCustomer` / `compute_cnv_breakdown` as its core purpose |
| **C. SKIP — dead code in semir-base** | File exists in both, but the specific changed function has zero callers in semir-base (check via `grep -rn "function_name(" .` from the semir-base **repo root** — not just `App/`, must also cover `tests/`, management commands, and templates — zero results outside its own definition = dead) |
| **D. SKIP — expected permanent divergence** | Matches the "expected divergence" table, or is a new instance of the same pattern (CNV-only section embedded in an otherwise-general file/template/test file) |

For every **B/C/D** classification, you must be able to show the evidence (grep result, or diff proving zero callers) — never mark something as skip "because it's probably CNV" without checking.

---

### Step 3 — Apply outcome-A changes

For each file classified **A. SYNC**:

1. Confirm the file exists in semir-base at the same relative path under `SemirDashboard/`. If missing entirely, create the directory structure as needed.
2. **Diff first, edit second** — read both versions, understand exactly what's different (normalize CRLF before concluding), and reproduce the **same logical change** using the Edit tool — do NOT blindly `cp`/overwrite the whole file, because semir-base's copy may carry its own legitimate unrelated differences (its own bugfixes, its own comment wording) that a blind overwrite would destroy.
3. If the user explicitly says "just use git diff and copy" for a batch of straightforward files (as happened 2026-08-13), you may use `git diff -- <path>` from semir and apply the equivalent hunk directly to semir-base via Edit with matching old/new strings — still verify old_string is present and unique in the semir-base file before applying.

---

### Step 4 — Verify every A-classified file, byte-for-byte (CRLF-normalized)

For every file touched in Step 3:

```bash
diff --strip-trailing-cr /d/New-jouney/semir/SemirDashboard/<path> /d/New-jouney/semir-base/SemirDashboard/<path>
```

Expected: **empty output** (fully identical), OR output that matches *only* an already-documented "expected divergence" (e.g. the CNV `PAGES` list lines in `prod_visual.py`). Any other non-empty diff is a **sync failure** — fix it before proceeding, do not report success.

Python files: `python -m py_compile <file>` for every changed `.py` — syntax must be clean.

---

### Step 5 — Hard rule gate: prove no calculated/output value changed

**semir-base carries the same hard rule as semir: a sync must never change any calculated or displayed value — only fix bugs, performance, or reliability.** Confirmed 2026-08-14: `semir-base/SemirDashboard/tests/` has the **identical snapshot infrastructure** as semir (`tests/base.py`'s `SnapshotTestCase` / `UPDATE_SNAPSHOTS` env var, `tests/snapshots/*.json`, `tests/snapshot_render.py`, `tests/snapshot_visual.py`, `tests/render/_index.md` token-issue report) — do not skip this gate on the assumption it "probably doesn't apply."

Run all of the following **in semir-base** (`cd SemirDashboard`), in this order, and do not proceed past a failing sub-step:

**5a. Full test suite, WITHOUT `UPDATE_SNAPSHOTS` (this is the real proof, not a formality):**
```bash
../venv/Scripts/python manage.py test tests -v 1
```
This run takes ~50 min (516 tests, full fixture load) — that is expected, not a hang. Known baseline (per `semir-base/plan_cnv_removal.md`): **516 tests total, 514 pass, 1 failure + 1 error, both `TokenRefreshRotationTest`** (a pre-existing, order-dependent login-throttle flake, confirmed unrelated to CNV removal — passes cleanly in isolation). Confirmed reproduced exactly 2026-08-14.

**Why this run alone is the real "no calculated value changed" proof:** every `assert_snapshot()` call in the suite compares the *live-computed* value against the *stored* JSON in `tests/snapshots/` and **fails the test if they differ**. A clean pass (matching the known baseline exactly, zero failures beyond the 2 named ones) is direct, positive evidence that nothing your sync touched altered any snapshotted calculated value — you do not need a separate step to "prove" this; it's already proven by every green snapshot-assertion test.

If the run shows *any* failure beyond the 2 named `TokenRefreshRotationTest` cases, treat it as a real regression from your sync — stop and fix before continuing (re-run the specific failing test alone first, per the "failure isolation rule": a test that passes alone but fails in the full suite is a shared-state issue, not a sync bug — document it, don't chase it as if it were).

**5b. `UPDATE_SNAPSHOTS=1` regeneration — OPTIONAL, only when justified:**
Skip this by default — it re-runs the full ~50 min suite for marginal extra confidence beyond what 5a already proved. Only run it when the synced changes plausibly touch calculation/aggregation logic that a snapshot test might not exercise on every field (rare — most snapshot tests are broad). If you do run it:
```bash
UPDATE_SNAPSHOTS=1 ../venv/Scripts/python manage.py test tests -v 1
git diff --stat -- SemirDashboard/tests/snapshots/
git diff -- SemirDashboard/tests/snapshots/ | grep -v '_last_run' | grep '^[+-]' | grep -v '^[+-][+-][+-]'
```
The last command's output must be empty; any line it prints is a real calculated-value change — hard stop. **State explicitly in the history file (Step 7) whether 5b was run or deliberately skipped, and why** — do not silently omit it.

**5c. For every synced `.html` template (Step 3's file list, filtered to `*.html`), regenerate and inspect the visual/HTML snapshots:**
```bash
../venv/Scripts/python manage.py shell -c "exec(open('tests/snapshot_render.py').read())"
../venv/Scripts/python tests/snapshot_visual.py
```
Then:
- Read `tests/render/_index.md` — the "Token issues" column must be **0** for every page (same UI-token rule as semir). Any non-zero count is a hard stop.
- `Read` (the tool) the specific `tests/render/png/*.png` file(s) corresponding to the page(s) the synced template belongs to — actually look at the image, don't just trust the exit code. Confirm the page renders, no visibly broken layout, no leftover "Loading..." artifacts.

**5d. Targeted regression test for the specific change**, in addition to (not instead of) 5a's full-suite run — run the full test module(s) that most directly exercise the changed file (e.g. a change in `App/services/customer_import.py` → `tests.test_upload` in full; a change in `App/templates/product/dashboard.html` → whatever module covers the Products page):
```bash
../venv/Scripts/python manage.py test tests.<module> -v 2
```

---

### Step 6 — Trigger an independent sub-agent to re-verify (REQUIRED, highest quality)

Do not skip this step, and do not write your own summary before it returns. Launch a `general-purpose` Agent with a **self-contained** prompt (it has no memory of this conversation) that includes:

- Both repo paths and the fact they are separate git repos, semir-base = "no-cnv" fork
- The exact list of files you classified as A/B/C/D in Step 2, with your stated reasons
- Explicit instructions to **independently re-derive** the classification (re-grep for CNV-only usage, re-check dead-code claims, re-diff every "SYNC"ed file with CRLF normalization) rather than trust your report
- Instructions to flag ANY file it thinks was mis-classified, missed entirely, or only partially synced
- Instructions to actually run `diff --strip-trailing-cr` itself on every claimed-synced file and quote the raw output
- Instructions to report a verdict: **SAFE / GAPS FOUND (list them)**
- **Explicit read-only boundary: the sub-agent must NOT edit, create, or delete any file in either repo — it audits and reports only.** If it finds a gap, it reports the gap; you (the primary agent) are the one who applies the fix in Step 2/3 rework, then re-verifies. This prevents two agents editing semir-base concurrently and producing conflicting or duplicate changes.

Example invocation shape:

```
Agent(
  description: "Independent verify of semir→semir-base sync",
  subagent_type: "general-purpose",
  prompt: "<full self-contained context per above>",
)
```

If the sub-agent reports gaps, go back to Step 2/3 for those specific files, fix, and re-run Step 4 and the relevant parts of Step 5 for them. Do not proceed to Step 7 until the sub-agent's verdict is SAFE (or all reported gaps have been resolved and it has confirmed the fix).

---

### Step 7 — Write the sync history entry

Create a new file under `.claude/skills/sync-semir-base/sync-history/` named:

```
<N>_<YYYY-MM-DD>_<short-slug>.md
```

where `<N>` is the next integer after the highest existing prefix (start at `1` if the folder is empty). Content must include, at minimum:

- Date and time of sync
- **`git rev-parse HEAD` of semir at the moment of this sync** (run this in semir and record the exact hash) — this is what makes Step 1's `git log <hash>..HEAD` cross-check possible on the *next* run. Skipping this breaks that check for the next sync.
- Trigger (what prompted this sync — e.g. "batch_size revert + race-condition fix + prod_visual hardening")
- Full classification table (file, outcome A/B/C/D, reason) — same detail level as reported to the user
- Diff verification results (which files confirmed byte-identical, which had expected divergence and what it was)
- **Step 5 results**: full-suite pass/fail counts vs the 516/514-known-flake baseline, JSON snapshot diff result (must say "only `_last_run` differed" or list what else changed and how it was resolved), token-issue count from `render/_index.md`, and which PNGs were visually inspected
- Sub-agent verdict, verbatim summary
- Any follow-up/outstanding items
- Commit status in semir-base (committed / left uncommitted per user instruction)

---

### Step 8 — Final report to the user (REQUIRED format, do not summarize away detail)

Present, in full:

1. **Full file-by-file table** (same as Step 2/7) — every file, its classification, its reason, its verification status. Never collapse this into "everything's fine" prose.
2. **Step 5 hard-rule-gate results** — full-suite counts vs baseline, snapshot diff outcome, token-issue count, which templates were visually confirmed.
3. **Sub-agent verdict** — quote it, don't paraphrase away specifics.
4. **History file path** just written.
5. **Explicit ask**: does the user want these changes committed in semir-base? (Never commit without being asked — same rule as the main repo.)

---

## Definition of Done (ALL must be true)

- [ ] Step 0 safety check passed — every uncommitted item in semir-base's `git status` is accounted for by the last `sync-history/` entry, or the user explicitly confirmed it's safe to proceed
- [ ] Step 1 produced an explicit numbered file list, built from actual Edit/Write history (not inferred from `git status` alone), reconciled against `git log <last-synced-hash>..HEAD` when a prior sync-history entry exists
- [ ] Every file in the list has a recorded classification (A/B/C/D) **with evidence** (quoted grep/diff output), not assumption — and any reference-table lookup was re-verified live, not taken on faith
- [ ] Every A-classified file has been edited in semir-base (logical-change reproduction, not blind copy) unless the user explicitly authorized a direct copy for that batch
- [ ] Every A-classified file verified via `diff --strip-trailing-cr` showing empty output or only pre-documented expected divergence
- [ ] Every changed Python file passes `py_compile`
- [ ] Full `manage.py test tests` run in semir-base and compared against the known 516-total/514-pass/2-named-flakes baseline — zero new failures beyond that baseline
- [ ] `UPDATE_SNAPSHOTS=1` full-suite run completed, and `git diff` on `tests/snapshots/` shows **only** `_last_run` fields changed — any other changed field investigated and resolved (hard rule: no calculated/output value may change)
- [ ] For every synced template: `snapshot_render.py` + `snapshot_visual.py` re-run, `tests/render/_index.md` shows 0 token issues, and the relevant PNG(s) were actually opened (`Read` tool) and visually confirmed — not just "exit code 0"
- [ ] The full test module covering each changed file was run individually in semir-base and passed (targeted regression check, in addition to the full-suite run above)
- [ ] Independent sub-agent launched with full self-contained context and an explicit read-only boundary, and returned a verdict of SAFE (or all its findings were addressed and re-verified)
- [ ] A new dated file exists under `sync-history/`, including the semir `HEAD` commit hash at time of sync and the full Step 5 results, with all other required content
- [ ] User has been shown the full file-by-file table (not a collapsed summary), the Step 5 hard-rule-gate results, and the sub-agent's verdict
- [ ] User has been explicitly asked whether to commit in semir-base — nothing committed without that explicit yes

---

## Self-improve this skill

After every run, if you discover a new CNV-only path, a new dead-code spot, a new expected-divergence file, or a new gotcha (like the CRLF issue), **add it to the relevant table above** before finishing. Append one line to the changelog below — do not delete prior entries.

**Changelog**

| Date | Change |
|------|--------|
| 2026-08-13 | Initial version — created after the first full audited sync (batch_size revert × 5 import services, race-condition JS fix × 2 templates, `prod_visual.py` hardening). Documented the `git status` unreliability and CRLF false-diff gotchas discovered during that sync. |
| 2026-08-13 | Senior-review pass (same day): added "When to invoke" + "Repo paths" reference block; fixed Step 1's dangling reference to an untracked "last sync commit" by having Step 6 actually record `git rev-parse HEAD` and Step 1 consume it; broadened Step 2 outcome-C dead-code grep from `App/` only to whole repo root; added explicit read-only boundary for the Step 5 sub-agent (prevents concurrent-edit conflicts); added a "re-verify, don't trust" caveat above the 3 reference tables since semir-base evolves independently; Step 4 now runs the full test module for a changed file, not just one method; DoD updated to match every gate above. Retro-applied the commit-hash requirement to sync #1's history file. |
| 2026-08-14 | Second review pass: verified semir-base actually has the identical snapshot/test pipeline (`tests/base.py` SnapshotTestCase, `snapshot_render.py`, `snapshot_visual.py`, 516-test suite with 2 known pre-existing flakes documented in `plan_cnv_removal.md`) before writing anything — grounded, not assumed. Inserted new **Step 5 "hard rule gate"**: full-suite run against the known 516/514/2-flakes baseline, `UPDATE_SNAPSHOTS=1` + JSON-diff check that only `_last_run` changed (proves no calculated value moved), template snapshot regen + 0-token-issue check + actual visual PNG inspection, plus a targeted per-file regression test module. Renumbered sub-agent/history/report to Steps 6/7/8 and fixed all cross-references. Added a "Quick flow" one-liner for scannability now that the skill spans 8 steps. |
