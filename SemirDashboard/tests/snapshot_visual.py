"""
Visual snapshot generator: takes the rendered HTML files in SemirDashboard/tests/render/
and produces PDF + full-page PNG screenshots using headless Chrome.

Output:
  render/pdf/<label>.pdf      - print-style PDF capture
  render/png/<label>.png      - full-page screenshot

Run from SemirDashboard/ directory:
  python tests/snapshot_visual.py

Prerequisites: snapshot_render.py must have been run first to generate the .html files.
Chrome or Edge must be installed (auto-detected).
"""
import os
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent  # tests/ directory
RENDER_DIR = ROOT / "render"
PDF_DIR = RENDER_DIR / "pdf"
PNG_DIR = RENDER_DIR / "png"
PDF_DIR.mkdir(parents=True, exist_ok=True)
PNG_DIR.mkdir(parents=True, exist_ok=True)


def find_browser():
    """Locate Chrome or Edge executable on Windows."""
    candidates = [
        r"C:\Program Files\Google\Chrome\Application\chrome.exe",
        r"C:\Program Files (x86)\Google\Chrome\Application\chrome.exe",
        r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe",
        r"C:\Program Files\Microsoft\Edge\Application\msedge.exe",
    ]
    for c in candidates:
        if Path(c).exists():
            return c
    # Fall back to PATH
    for name in ("chrome", "chrome.exe", "msedge", "msedge.exe"):
        found = shutil.which(name)
        if found:
            return found
    return None


def html_files():
    return sorted(p for p in RENDER_DIR.glob("*.html"))


def render_pdf(browser, html_path: Path, pdf_path: Path) -> bool:
    url = html_path.resolve().as_uri()
    cmd = [
        browser,
        "--headless=new",
        "--disable-gpu",
        "--no-sandbox",
        "--hide-scrollbars",
        "--virtual-time-budget=5000",
        f"--print-to-pdf={pdf_path}",
        "--print-to-pdf-no-header",
        url,
    ]
    try:
        r = subprocess.run(cmd, capture_output=True, text=True, timeout=60)
        return pdf_path.exists() and pdf_path.stat().st_size > 0
    except Exception as e:
        print(f"  PDF error: {e}")
        return False


def render_png(browser, html_path: Path, png_path: Path) -> bool:
    url = html_path.resolve().as_uri()
    cmd = [
        browser,
        "--headless=new",
        "--disable-gpu",
        "--no-sandbox",
        "--hide-scrollbars",
        "--virtual-time-budget=5000",
        "--window-size=1440,2400",
        f"--screenshot={png_path}",
        url,
    ]
    try:
        subprocess.run(cmd, capture_output=True, text=True, timeout=60)
        return png_path.exists() and png_path.stat().st_size > 0
    except Exception as e:
        print(f"  PNG error: {e}")
        return False


def main():
    browser = find_browser()
    if not browser:
        print("ERROR: Chrome/Edge not found")
        return 1
    print(f"Browser: {browser}")
    print(f"Render dir: {RENDER_DIR}")

    files = html_files()
    if not files:
        print("ERROR: no .html files in render/ - run snapshot_render.py first")
        return 1

    print(f"\nGenerating PDFs + PNGs for {len(files)} pages...")
    print(f"{'Label':35s} {'PDF':>8s} {'PNG':>8s}")
    print("-" * 60)

    for html_path in files:
        label = html_path.stem
        pdf_path = PDF_DIR / f"{label}.pdf"
        png_path = PNG_DIR / f"{label}.png"

        pdf_ok = render_pdf(browser, html_path, pdf_path)
        png_ok = render_png(browser, html_path, png_path)

        pdf_size = f"{pdf_path.stat().st_size // 1024}KB" if pdf_ok else "FAIL"
        png_size = f"{png_path.stat().st_size // 1024}KB" if png_ok else "FAIL"
        print(f"  {label:33s} {pdf_size:>8s} {png_size:>8s}")

    print("-" * 60)
    print(f"PDFs: {PDF_DIR}")
    print(f"PNGs: {PNG_DIR}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
