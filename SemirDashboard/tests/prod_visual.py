"""
tests/prod_visual.py — Production Visual Regression Testing (Playwright)
========================================================================

QA workflow (golden-master screenshots against the LIVE production site):

    1. NGAY TRƯỚC khi deploy version mới:
         python tests/prod_visual.py baseline
       → login, chụp full-page mọi màn hình → tests/prod_snapshots/baseline/

    2. Deploy version mới lên production.

    3. NGAY SAU khi deploy:
         python tests/prod_visual.py verify
       → chụp lại → tests/prod_snapshots/current/ → pixel-diff với baseline
       → tests/prod_snapshots/report.html  (PASS/FAIL từng trang + ảnh diff đỏ)

    4. Nếu mọi khác biệt là CHỦ ĐÍCH của release:
         python tests/prod_visual.py accept
       → promote current/ thành baseline/ mới.

⚠ Vì sao baseline chụp NGAY TRƯỚC deploy (không dùng 1 baseline vĩnh viễn):
   dữ liệu production thay đổi hằng ngày (đơn hàng mới) — chụp baseline/verify
   cách nhau vài phút quanh thời điểm deploy thì data gần như đứng yên, mọi
   pixel khác biệt = tác động của code mới, không phải data trôi.

Credentials — KHÔNG hardcode, KHÔNG commit. Tạo file (đã gitignore):
    SemirDashboard/tests/prod_visual.env
với nội dung:
    PROD_URL=https://analytics-customer-dashboard.com
    PROD_USER=<username>
    PROD_PASS=<password>

Run:  cd SemirDashboard && python tests/prod_visual.py baseline|verify|accept [--pages home,sales]
"""
import os
import shutil
import sys
import time
from datetime import datetime
from pathlib import Path

from PIL import Image, ImageChops

BASE_DIR = Path(__file__).resolve().parent
SNAP_DIR = BASE_DIR / "prod_snapshots"
ENV_FILE = BASE_DIR / "prod_visual.env"

VIEWPORT = {"width": 1600, "height": 1000}
SETTLE_MS = 2500           # chờ Chart.js render sau networkidle
PER_PAGE_TIMEOUT = 60_000
FAIL_THRESHOLD_PCT = 0.10  # % pixel khác vượt ngưỡng này → FAIL
PIXEL_TOLERANCE = 16       # chênh lệch kênh màu ≤16 coi như giống (anti-aliasing)

# ── Danh sách màn hình production (khớp docs/project_urls.md) ────────────────
PAGES = [
    ("01_home",               "/"),
    ("02_sales_analytics",    "/analytics/"),
    ("03_sales_chart",        "/analytics/chart/"),
    ("04_coupons",            "/coupons/"),
    ("05_coupon_chart",       "/coupons/chart/"),
    ("06_shop_detail",        "/shop-detail/"),
    ("07_customer_detail",    "/customer-detail/"),
    ("08_products",           "/products/"),
    ("09_inventory",          "/inventory/"),
    ("10_cnv_customer",       "/cnv/customer-analytics/"),
    ("11_cnv_chart",          "/cnv/customer-chart/"),
    ("12_cnv_sync_status",    "/cnv/sync-status/"),
    ("13_upload_customers",   "/upload/customers/"),
    ("14_upload_sales",       "/upload/sales/"),
    ("15_upload_coupons",     "/upload/coupons/"),
    ("16_upload_inventory",   "/upload/inventory/"),
    ("17_users",              "/users/"),
    ("18_formulas",           "/formulas/"),
    ("19_admin_logs",         "/admin-logs/"),  # added 2026-07-15 coverage check — was missing entirely
    ("20_membership",         "/membership/"),  # added 2026-08-30 coverage check — new page (release/2.4.0)
]

# Vùng động cần che trước khi chụp (selector CSS) — timestamps, đồng hồ…
MASK_SELECTORS = [
    "#django-flash",              # flash message tự biến mất
    ".last-sync-time",            # nếu có
    "[data-dynamic='timestamp']",
]

FREEZE_CSS = """
*, *::before, *::after {
  animation: none !important;
  transition: none !important;
  caret-color: transparent !important;
}
"""


def _load_env() -> dict:
    if not ENV_FILE.exists():
        sys.exit(
            f"[ERROR] Không tìm thấy {ENV_FILE}.\n"
            "Tạo file với PROD_URL / PROD_USER / PROD_PASS (file đã được gitignore)."
        )
    env = {}
    for line in ENV_FILE.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if line and not line.startswith("#") and "=" in line:
            k, v = line.split("=", 1)
            env[k.strip()] = v.strip()
    for k in ("PROD_URL", "PROD_USER", "PROD_PASS"):
        if not env.get(k):
            sys.exit(f"[ERROR] Thiếu {k} trong {ENV_FILE}")
    env["PROD_URL"] = env["PROD_URL"].rstrip("/")
    return env


def _login(page, env):
    page.goto(env["PROD_URL"] + "/login/", timeout=PER_PAGE_TIMEOUT)
    page.fill("input[name='username']", env["PROD_USER"])
    page.fill("input[name='password']", env["PROD_PASS"])
    page.click("button[type='submit'], input[type='submit']")
    page.wait_for_load_state("networkidle", timeout=PER_PAGE_TIMEOUT)
    if "/login" in page.url:
        sys.exit("[ERROR] Login thất bại — kiểm tra credentials trong prod_visual.env")
    print(f"  [login] OK -> {page.url}")


def _mask_dynamic(page):
    for sel in MASK_SELECTORS:
        try:
            page.eval_on_selector_all(
                sel, "els => els.forEach(e => e.style.visibility='hidden')"
            )
        except Exception:
            pass


def _slug(text: str) -> str:
    import re
    s = re.sub(r"[^A-Za-z0-9]+", "_", (text or "").strip()).strip("_").lower()
    return s[:40] or "tab"


def _settle(page, ms=None, shot_name=""):
    """Wait for lazy-tab AJAX + chart render after a click/navigation.

    2026-07-15 root-cause fix: a verify run showed a Shop Detail AJAX section
    still displaying "Loading..." in the BASELINE capture (2 days earlier),
    inflating a pixel-diff by 883px of page height and 100k+ pixels — mistaken
    at first glance for a real data change. The wait-for-no-"Loading..." check
    that this comment used to describe was never actually present in this
    function; it is added for real now, with a generous timeout and an
    explicit WARNING (instead of silently swallowing the timeout) so a
    still-loading capture is visible in the run log rather than discovered
    days later via a confusing diff.

    2026-08-30: the check matched the literal substring 'Loading...' (three
    ASCII periods) — but Sales Analytics' spinner text is "Loading data…"
    (a word in between, and a Unicode ellipsis U+2026, not three periods),
    so this check silently never matched it. Several verify runs saved
    genuinely mid-AJAX screenshots for that page as if they were valid,
    producing large false-diff noise. Narrowed to just 'Loading' (no
    trailing punctuation assumed) so any spinner wording is caught.
    """
    try:
        page.wait_for_load_state("networkidle", timeout=15_000)
    except Exception:
        pass
    try:
        page.wait_for_function(
            "() => !document.body.innerText.includes('Loading')", timeout=45_000
        )
    except Exception:
        print(f"    [WARN] '{shot_name or '?'}': still showing 'Loading...' after 45s wait — "
              f"screenshot may be captured mid-AJAX. Re-run if this page's diff looks suspicious.")
    page.wait_for_timeout(ms or SETTLE_MS)


def _shot(page, out_dir: Path, shot_name: str, manifest: list, max_retries: int = 5):
    """Take a full-page screenshot — but NEVER save one that's still showing
    'Loading...'. A stuck-loading screenshot has no real content in it, so
    it can't be compared against anything and must never be silently
    accepted as valid PASS/FAIL evidence (2026-08-13 incident: several
    Products tabs were captured mid-AJAX and the resulting "diff" was
    meaningless noise — nothing to actually compare).

    Retries with extra wait a bounded number of times; if STILL loading,
    refuses to save the file entirely — including deleting any stale file
    left over from a previous run under this name, so a leftover screenshot
    can never be mistaken for a fresh, valid capture. The name is dropped
    from `manifest` too, so it's visibly MISSING from the run rather than
    silently wrong.
    """
    dest = out_dir / f"{shot_name}.png"
    for attempt in range(max_retries):
        still_loading = page.evaluate("() => document.body.innerText.includes('Loading')")
        if not still_loading:
            break
        print(f"    [retry {attempt+1}/{max_retries}] '{shot_name}': still 'Loading...' — waiting before capture")
        page.wait_for_timeout(3000)
    else:
        print(f"    [ERROR] '{shot_name}': still showing 'Loading...' after {max_retries} retries — "
              f"REFUSING to save this screenshot (would not be valid evidence). Investigate manually.")
        dest.unlink(missing_ok=True)  # never leave a stale file masquerading as this run's capture
        return

    _mask_dynamic(page)
    page.screenshot(path=str(dest), full_page=True)
    manifest.append(shot_name)
    print(f"    [shot] {shot_name}")


def _click_all_tabs(page, out_dir, base_name, manifest):
    """PASS A: Bootstrap lazy tabs (button[data-bs-toggle=tab]) — the pattern
    used by Sales Analytics, Coupons, and CNV Customer Analytics.
    PASS B: hand-rolled tabs (a[data-tab] / a[data-stab]) — Products page and
    Shop Detail product section."""
    # PASS A — snapshot each Bootstrap tab pane
    buttons = page.query_selector_all("button[data-bs-toggle='tab']")
    for i, btn in enumerate(buttons):
        try:
            label = _slug(btn.inner_text() or btn.get_attribute("data-bs-target") or f"t{i}")
            if btn.get_attribute("class") and "active" in btn.get_attribute("class") and i == 0:
                continue  # initial tab already captured in the base shot
            btn.click()
            shot_name = f"{base_name}__tab_{i:02d}_{label}"
            _settle(page, 1500, shot_name)
            _shot(page, out_dir, shot_name, manifest)
        except Exception as exc:
            print(f"    [tab-skip] {base_name} #{i}: {exc}")

    # PASS B — custom nav tabs (Products / product partial)
    for sel in ("a[data-tab]", "a[data-stab]"):
        links = page.query_selector_all(sel)
        for i, a in enumerate(links):
            try:
                key = a.get_attribute("data-tab") or a.get_attribute("data-stab") or f"s{i}"
                cls = a.get_attribute("class") or ""
                if "active" in cls and i == 0:
                    continue
                a.click()
                shot_name = f"{base_name}__{sel[2:6]}_{i:02d}_{_slug(key)}"
                # 2026-08-13: was a fixed 3500ms _settle() wait — root cause of
                # the underlying race (a slow tab's late AJAX response landing
                # in whatever pane was "current") is now fixed app-side
                # (product/dashboard.html + shop_detail/_product_partial.html
                # both track which tab the user last asked for and discard
                # superseded responses instead of rendering them). But heavy
                # tabs (Category/Campaign tree aggregation over 337k+ line
                # items) can still genuinely take longer than 3500ms to
                # resolve — wait for the actual spinner (any element whose id
                # ends in "Spinner", covers tabSpinner/shopTabSpinner/
                # prodShopTabSpinner across both templates) to hide instead of
                # a fixed timeout, so slow-but-correct tabs aren't captured
                # mid-load.
                try:
                    page.wait_for_function(
                        "() => ![...document.querySelectorAll('[id$=Spinner]')]"
                        ".some(s => getComputedStyle(s).display !== 'none')",
                        timeout=30_000,
                    )
                except Exception:
                    print(f"    [WARN] '{shot_name}': a spinner is still visible after 30s wait — "
                          f"screenshot may be captured mid-AJAX. Re-run if this tab's diff looks suspicious.")
                page.wait_for_timeout(1000)
                _shot(page, out_dir, shot_name, manifest)
            except Exception as exc:
                print(f"    [stab-skip] {base_name} #{i}: {exc}")


def _capture_shop_detail(page, out_dir, base_name, manifest):
    """Shop Detail: mỗi section có dropdown chọn shop riêng — chọn shop đầu
    tiên (option index 1) cho TỪNG section để mọi partial AJAX đều có data,
    sau đó duyệt tiếp các sub-tab của product section.

    2026-07-25 fix: the generic `_settle()` "no 'Loading...' text anywhere"
    check races with `loadSection()` — if it runs before the click's fetch()
    has set spinner.style.display='block', it passes trivially at t=0 and
    the capture only gets the fixed 3500ms wait, which the Customer section
    (the one section backed by the heavier compute_cnv_breakdown aggregation,
    and usually the first cold hit of that cache in a run) can exceed on a
    cold cache. Wait for THIS section's own spinner to hide instead of the
    page-wide text heuristic — deterministic, no race with click timing.
    """
    section_by_select = {
        "salesShopSel": "sales", "customerShopSel": "customer",
        "couponShopSel": "coupon", "campaignSel": "coupon",
        "inventoryShopSel": "inventory", "productShopSel": "product",
    }
    selects = ["salesShopSel", "customerShopSel", "couponShopSel",
               "campaignSel", "inventoryShopSel", "productShopSel"]
    for sid in selects:
        try:
            el = page.query_selector(f"#{sid}")
            if not el or el.get_attribute("disabled") is not None:
                print(f"    [sel-skip] #{sid} missing/disabled")
                continue
            n_opts = page.eval_on_selector(f"#{sid}", "el => el.options.length")
            if n_opts < 2:
                continue
            page.select_option(f"#{sid}", index=1)
            # Mỗi section có nút "Load" riêng cạnh dropdown — select không tự load
            page.eval_on_selector(
                f"#{sid}",
                "el => el.closest('.shop-select-row')?.querySelector('button')?.click()"
            )
            shot_name = f"{base_name}__sec_{_slug(sid)}"
            section = section_by_select.get(sid)
            try:
                page.wait_for_function(
                    "sec => { const s = document.getElementById(sec + 'Spinner'); "
                    "return !s || s.style.display === 'none'; }",
                    arg=section, timeout=30_000,
                )
            except Exception:
                print(f"    [WARN] '{shot_name}': {section}Spinner still visible after 30s wait — "
                      f"screenshot may be captured mid-AJAX. Re-run if this section's diff looks suspicious.")
            page.wait_for_timeout(1500)
            _shot(page, out_dir, shot_name, manifest)
        except Exception as exc:
            print(f"    [sel-skip] #{sid}: {exc}")
    # product section sub-tabs (hand-rolled data-stab) — after productShopSel loaded
    for i, a in enumerate(page.query_selector_all("a[data-stab]")):
        try:
            key = a.get_attribute("data-stab") or f"s{i}"
            a.click()
            shot_name = f"{base_name}__prod_{i:02d}_{_slug(key)}"
            _settle(page, 1500, shot_name)
            _shot(page, out_dir, shot_name, manifest)
        except Exception as exc:
            print(f"    [stab-skip] product #{i}: {exc}")


def _capture_customer_detail(page, out_dir, base_name, manifest, env):
    """Nếu PROD_VIP_ID được cấu hình: search 1 khách cố định để chụp trang
    detail có data (deterministic — luôn cùng 1 khách)."""
    vip = env.get("PROD_VIP_ID", "").strip()
    if not vip:
        print("    [info] PROD_VIP_ID chưa cấu hình — chỉ chụp trang search trống")
        return
    try:
        page.fill("input[name='vip_id']", vip)
        page.keyboard.press("Enter")
        shot_name = f"{base_name}__vip_{_slug(vip)}"
        _settle(page, 2500, shot_name)
        _shot(page, out_dir, shot_name, manifest)
    except Exception as exc:
        print(f"    [vip-skip] {exc}")


def _capture(out_dir: Path, only: set | None):
    from playwright.sync_api import sync_playwright

    env = _load_env()
    out_dir.mkdir(parents=True, exist_ok=True)
    manifest: list = []
    results = []

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        ctx = browser.new_context(
            viewport=VIEWPORT, device_scale_factor=1, reduced_motion="reduce",
        )
        page = ctx.new_page()
        _login(page, env)

        for name, path in PAGES:
            if only and not any(k in name for k in only):
                continue
            url = env["PROD_URL"] + path
            t0 = time.time()
            try:
                page.goto(url, timeout=PER_PAGE_TIMEOUT, wait_until="networkidle")
                page.add_style_tag(content=FREEZE_CSS)
                page.wait_for_timeout(SETTLE_MS)
                _shot(page, out_dir, name, manifest)          # base state
                if name == "06_shop_detail":
                    _capture_shop_detail(page, out_dir, name, manifest)
                elif name == "07_customer_detail":
                    _capture_customer_detail(page, out_dir, name, manifest, env)
                else:
                    _click_all_tabs(page, out_dir, name, manifest)
                results.append((name, "OK", time.time() - t0))
                print(f"  [page] {name:<22} {time.time()-t0:5.1f}s")
            except Exception as exc:
                results.append((name, f"ERROR: {exc}", time.time() - t0))
                print(f"  [FAIL] {name:<22} {exc}")
        browser.close()

    # Manifest luôn phản ánh TOÀN BỘ thư mục (partial run --pages không được
    # ghi đè mất danh sách các trang khác)
    all_pngs = sorted(p.stem for p in out_dir.glob("*.png"))
    (out_dir / "_manifest.txt").write_text("\n".join(all_pngs), encoding="utf-8")
    print(f"  [done] {len(manifest)} screenshots this run · {len(all_pngs)} total in {out_dir.name}/")
    return results


def _diff_images(a: Path, b: Path, out: Path):
    """Return (%different, diff_image_saved). Red highlight on changed pixels."""
    im_a, im_b = Image.open(a).convert("RGB"), Image.open(b).convert("RGB")
    if im_a.size != im_b.size:
        w = max(im_a.width, im_b.width)
        h = max(im_a.height, im_b.height)
        pad_a, pad_b = Image.new("RGB", (w, h), "white"), Image.new("RGB", (w, h), "white")
        pad_a.paste(im_a)
        pad_b.paste(im_b)
        im_a, im_b = pad_a, pad_b
    delta = ImageChops.difference(im_a, im_b).convert("L")
    mask = delta.point(lambda v: 255 if v > PIXEL_TOLERANCE else 0)
    changed = sum(1 for v in mask.getdata() if v)
    total = mask.width * mask.height
    pct = changed / total * 100
    if changed:
        red = Image.new("RGB", im_b.size, (255, 0, 0))
        highlight = Image.composite(red, im_b, mask)
        highlight.save(out)
    return pct, changed > 0


def cmd_baseline(only):
    print(f"=== BASELINE @ {datetime.now():%Y-%m-%d %H:%M} ===")
    _capture(SNAP_DIR / "baseline", only)
    print(f"\nBaseline saved → {SNAP_DIR / 'baseline'}")


def cmd_verify(only):
    base = SNAP_DIR / "baseline"
    if not base.exists():
        sys.exit("[ERROR] Chưa có baseline — chạy `baseline` trước.")
    cur, dif = SNAP_DIR / "current", SNAP_DIR / "diff"
    if dif.exists():
        shutil.rmtree(dif)
    dif.mkdir(parents=True, exist_ok=True)

    print(f"=== VERIFY @ {datetime.now():%Y-%m-%d %H:%M} ===")
    _capture(cur, only)

    # So sánh trên HỢP của mọi screenshot (base page + mọi tab/section) —
    # ảnh chỉ có một bên = MISSING (tab mới xuất hiện hoặc biến mất đều là finding).
    names = sorted({p.stem for p in base.glob("*.png")} | {p.stem for p in cur.glob("*.png")})
    if only:
        names = [n for n in names if any(k in n for k in only)]

    rows, n_fail = [], 0
    for name in names:
        b, c = base / f"{name}.png", cur / f"{name}.png"
        if not b.exists() or not c.exists():
            side = "baseline" if not b.exists() else "current"
            rows.append((name, f"MISSING in {side}", None))
            n_fail += 1
            print(f"  [MISS] {name:<40} (not in {side})")
            continue
        pct, _ = _diff_images(b, c, dif / f"{name}.png")
        status = "PASS" if pct <= FAIL_THRESHOLD_PCT else "FAIL"
        if status == "FAIL":
            n_fail += 1
        rows.append((name, status, pct))
        print(f"  [{status}] {name:<40} diff={pct:.3f}%")

    _write_report(rows)
    print(f"\n{'❌ ' + str(n_fail) + ' page(s) FAILED' if n_fail else '✅ ALL PASS'}"
          f" — report: {SNAP_DIR / 'report.html'}")
    sys.exit(1 if n_fail else 0)


def cmd_accept(only):
    cur, base = SNAP_DIR / "current", SNAP_DIR / "baseline"
    if not cur.exists():
        sys.exit("[ERROR] Chưa có current/ — chạy `verify` trước.")
    base.mkdir(parents=True, exist_ok=True)
    n = 0
    for png in cur.glob("*.png"):
        if only and not any(k in png.stem for k in only):
            continue
        shutil.copy2(png, base / png.name)
        n += 1
    print(f"Accepted {n} screenshot(s) → baseline/")


def _write_report(rows):
    ts = datetime.now().strftime("%Y-%m-%d %H:%M")
    html = [
        "<meta charset='utf-8'><title>Prod Visual Regression</title>",
        "<style>body{font-family:system-ui;margin:24px;background:#f6f7fb}"
        "h1{font-size:20px} .f{color:#c0392b;font-weight:700}.p{color:#1e8e3e;font-weight:700}"
        "table{border-collapse:collapse;width:100%;background:#fff}"
        "td,th{border:1px solid #ddd;padding:8px;font-size:13px;vertical-align:top}"
        "img{max-width:420px;border:1px solid #ccc}</style>",
        f"<h1>Production Visual Regression — {ts}</h1>",
        "<table><tr><th>Page</th><th>Status</th><th>Diff %</th>"
        "<th>Baseline</th><th>Current</th><th>Diff (red)</th></tr>",
    ]
    for name, status, pct in rows:
        cls = "p" if status == "PASS" else "f"
        pct_s = f"{pct:.3f}%" if pct is not None else "—"
        cells = "".join(
            f"<td><a href='{d}/{name}.png'><img src='{d}/{name}.png'></a></td>"
            if (SNAP_DIR / d / f"{name}.png").exists() else "<td>—</td>"
            for d in ("baseline", "current", "diff")
        )
        html.append(f"<tr><td>{name}</td><td class='{cls}'>{status}</td>"
                    f"<td>{pct_s}</td>{cells}</tr>")
    html.append("</table>")
    (SNAP_DIR / "report.html").write_text("\n".join(html), encoding="utf-8")


if __name__ == "__main__":
    args = sys.argv[1:]
    if not args or args[0] not in ("baseline", "verify", "accept"):
        sys.exit(__doc__)
    only = None
    if "--pages" in args:
        only = set(args[args.index("--pages") + 1].split(","))
    {"baseline": cmd_baseline, "verify": cmd_verify, "accept": cmd_accept}[args[0]](only)
