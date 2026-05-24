"""
Render every key GET page with sample data and snapshot the HTML output.

Outputs are written to:  SemirDashboard/tests/render/
  - <label>.html       — full rendered HTML for visual inspection
  - <label>.tables.txt — extracted table-by-table summary (header rows + first data rows)
  - _index.md          — index of all snapshots with timestamps + sizes

Run from SemirDashboard/ directory:
  python manage.py shell -c "exec(open('tests/snapshot_render.py').read())"

RULE: regenerate this snapshot every time templates are updated, then audit each
page's HTML against the project_ui.md design rules.
"""
import os
import re
import time
from pathlib import Path
from html.parser import HTMLParser

from django.conf import settings
settings.ALLOWED_HOSTS = list(set(settings.ALLOWED_HOSTS) | {'testserver', 'localhost', '127.0.0.1'})
from django.test import Client
from django.contrib.auth.models import User

# Output folder alongside tests/
RENDER_DIR = Path(settings.BASE_DIR).resolve() / "tests" / "render"
RENDER_DIR.mkdir(parents=True, exist_ok=True)

c = Client()
superuser = User.objects.filter(is_superuser=True).first()
if not superuser:
    print("ERROR: no superuser found - create one first")
    raise SystemExit(1)
c.force_login(superuser)

# ── Pages to snapshot ────────────────────────────────────────────────────────
pages = [
    ("/",                                                              "01_home"),
    ("/analytics/",                                                    "02_sales_alltime"),
    ("/analytics/?start_date=2025-01-01&end_date=2025-12-31",          "03_sales_2025"),
    ("/cnv/customer-analytics/",                                       "04_customer_alltime"),
    ("/cnv/customer-analytics/?start_date=2025-01-01&end_date=2025-12-31", "05_customer_2025"),
    ("/coupons/",                                                      "06_coupon_alltime"),
    ("/coupons/?start_date=2025-01-01&end_date=2025-12-31",            "07_coupon_2025"),
    ("/shop-detail/",                                                  "08_shop_detail"),
    ("/customer-detail/",                                              "09_customer_detail"),
    ("/formulas/",                                                     "10_formulas"),
    ("/analytics/chart/",                                              "11_sales_chart"),
    ("/coupons/chart/",                                                "12_coupon_chart"),
    ("/cnv/customer-chart/",                                           "13_customer_chart"),
    ("/cnv/sync-status/",                                              "14_cnv_sync_status"),
    ("/upload/customers/",                                             "15_upload_customers"),
    ("/users/",                                                        "16_user_management"),
    ("/admin-logs/",                                                   "17_admin_logs"),
    ("/products/",                                                     "18_product_analytics"),
    ("/inventory/",                                                    "19_inventory_analytics"),
    ("/upload/inventory/",                                             "20_upload_inventory"),
    ("/upload/sales/",                                                 "21_upload_sale_detail"),
]


# ── Table extractor ──────────────────────────────────────────────────────────
class TableSummaryParser(HTMLParser):
    """Walks HTML and extracts a per-table summary:
       - table index, parent section heading, # columns, # rows
       - header row text
       - first 2 data rows text (truncated)
    """

    def __init__(self):
        super().__init__()
        self.tables = []           # list of dicts
        self._stack = []           # tag stack
        self._in_table = False
        self._in_thead = False
        self._in_tbody = False
        self._in_tr = False
        self._cur_cell_text = []
        self._cur_row = []
        self._cur_table = None
        self._last_heading = ""
        self._last_card_header = ""
        self._heading_buf = []
        self._in_heading = False
        self._heading_tag = None

    def handle_starttag(self, tag, attrs):
        attrs_d = dict(attrs)
        self._stack.append(tag)

        # Track section headings (h1-h6) - capture text inside
        if tag in ("h1", "h2", "h3", "h4", "h5", "h6"):
            self._in_heading = True
            self._heading_tag = tag
            self._heading_buf = []

        # Track card-header divs (capture next text)
        if tag == "div":
            cls = attrs_d.get("class", "")
            if "card-header" in cls or "section-header" in cls or "table-header" in cls:
                self._last_card_header = "(in card-header)"

        if tag == "table":
            self._in_table = True
            self._cur_table = {
                "section": self._last_heading or self._last_card_header or "(no heading)",
                "classes": attrs_d.get("class", ""),
                "id": attrs_d.get("id", ""),
                "header_row": [],
                "first_rows": [],
                "row_count": 0,
                "col_count": 0,
            }
        elif tag == "thead" and self._in_table:
            self._in_thead = True
        elif tag == "tbody" and self._in_table:
            self._in_tbody = True
        elif tag == "tr" and self._in_table:
            self._in_tr = True
            self._cur_row = []
        elif tag in ("td", "th") and self._in_tr:
            self._cur_cell_text = []

    def handle_endtag(self, tag):
        if self._stack and self._stack[-1] == tag:
            self._stack.pop()

        if tag == self._heading_tag and self._in_heading:
            self._in_heading = False
            text = " ".join(self._heading_buf).strip()
            text = re.sub(r"\s+", " ", text)
            if text:
                self._last_heading = f"<{self._heading_tag}> {text}"
            self._heading_tag = None

        if tag in ("td", "th") and self._in_tr:
            cell_text = " ".join(self._cur_cell_text).strip()
            cell_text = re.sub(r"\s+", " ", cell_text)
            if len(cell_text) > 40:
                cell_text = cell_text[:37] + "..."
            self._cur_row.append(cell_text)
        elif tag == "tr" and self._in_table:
            self._in_tr = False
            if self._cur_row:
                if self._in_thead or (not self._cur_table["header_row"] and any(t == "th" for t in self._stack[-3:])):
                    self._cur_table["header_row"] = self._cur_row[:]
                else:
                    self._cur_table["row_count"] += 1
                    if len(self._cur_table["first_rows"]) < 2:
                        self._cur_table["first_rows"].append(self._cur_row[:])
                if not self._cur_table["col_count"]:
                    self._cur_table["col_count"] = len(self._cur_row)
        elif tag == "thead":
            self._in_thead = False
        elif tag == "tbody":
            self._in_tbody = False
        elif tag == "table":
            self._in_table = False
            if self._cur_table:
                self.tables.append(self._cur_table)
                self._cur_table = None

    def handle_data(self, data):
        if self._in_heading:
            self._heading_buf.append(data)
        if self._in_tr and self._stack and self._stack[-1] in ("td", "th", "strong", "span", "small", "i", "b", "a"):
            self._cur_cell_text.append(data)


def render_tables_summary(html_text, label, url, status_code):
    parser = TableSummaryParser()
    try:
        parser.feed(html_text)
    except Exception as e:
        return f"# {label}\nURL: {url}\nERROR parsing tables: {e}\n"

    out = [f"# {label}", f"URL: {url}", f"Status: {status_code}", f"Tables found: {len(parser.tables)}", ""]
    for i, t in enumerate(parser.tables, 1):
        out.append(f"## Table {i} - {t['section']}")
        out.append(f"  classes: {t['classes']}")
        if t['id']:
            out.append(f"  id: {t['id']}")
        out.append(f"  cols={t['col_count']}, rows={t['row_count']}")
        if t["header_row"]:
            out.append(f"  HEADER: {' | '.join(t['header_row'])}")
        for j, row in enumerate(t["first_rows"], 1):
            out.append(f"  ROW {j}: {' | '.join(row)}")
        out.append("")
    return "\n".join(out)


# ── Token compliance check (greps the rendered HTML for hardcoded brand colors)
HEX_COLOR_RE = re.compile(r"(?<![0-9a-fA-F&])#[0-9a-fA-F]{6}\b|(?<![0-9a-fA-F&])#[0-9a-fA-F]{3}\b")
ALLOWED_HEX = {"#fff", "#ffffff", "#000", "#000000"}  # pure white/black always OK


def check_token_compliance(html_text):
    """Return list of hardcoded hex colors found in inline style attrs / <style> blocks.

    Excludes content inside <script> blocks (Canvas API / Chart.js palettes are exempt
    per project_ui.md). Inline style="..." attrs in static HTML are still checked, but
    JS template literals that build HTML strings are inside <script> blocks and excluded.
    """
    issues = []
    # Strip <script>...</script> blocks first - Canvas API & Chart.js palettes are exempt
    html_no_scripts = re.sub(r'<script[^>]*>.*?</script>', '', html_text, flags=re.DOTALL)
    # Inline style="..." attributes (static HTML only)
    for m in re.finditer(r'style\s*=\s*"([^"]*)"', html_no_scripts):
        inline = m.group(1)
        for hex_m in HEX_COLOR_RE.finditer(inline):
            color = hex_m.group(0).lower()
            if color in ALLOWED_HEX:
                continue
            ctx = inline[max(0, hex_m.start() - 20):hex_m.end() + 5]
            issues.append(f"inline style: ...{ctx}...")
    # <style>...</style> blocks - strip the :root{...} token-definition block first
    for m in re.finditer(r'<style[^>]*>(.*?)</style>', html_text, re.DOTALL):
        block = m.group(1)
        # Remove :root { ... } content - those ARE the canonical token definitions
        block_no_root = re.sub(r':root\s*\{[^}]*\}', '', block, flags=re.DOTALL)
        # Also strip @keyframes (mostly contain numeric values, sometimes colors that are intentional)
        block_no_root = re.sub(r'@keyframes\s+\w+\s*\{[^}]*(?:\{[^}]*\}[^}]*)*\}', '', block_no_root, flags=re.DOTALL)
        for hex_m in HEX_COLOR_RE.finditer(block_no_root):
            color = hex_m.group(0).lower()
            if color in ALLOWED_HEX:
                continue
            line_start = block_no_root.rfind('\n', 0, hex_m.start()) + 1
            line_end = block_no_root.find('\n', hex_m.end())
            if line_end == -1:
                line_end = len(block_no_root)
            line = block_no_root[line_start:line_end].strip()
            if len(line) > 100:
                line = line[:97] + "..."
            issues.append(f"<style>: {line}")
    return issues


# ── Run ──────────────────────────────────────────────────────────────────────
print(f"\nRender output dir: {RENDER_DIR}")
print(f"{'Label':35s} {'URL':55s} {'Status':10s} {'Time':>7s} {'Tokens':>8s}")
print("-" * 125)

index_lines = ["# Render Snapshot Index", "", f"Generated: {time.strftime('%Y-%m-%d %H:%M:%S')}", ""]
index_lines.append("| Label | URL | Status | Size | Tables | Token issues |")
index_lines.append("|-------|-----|--------|------|--------|--------------|")

total_issues = 0

for url, label in pages:
    try:
        t0 = time.time()
        r = c.get(url, follow=True)
        elapsed = time.time() - t0
        html_text = r.content.decode("utf-8", errors="replace")
        size_kb = len(r.content) / 1024.0

        # Save full HTML
        html_path = RENDER_DIR / f"{label}.html"
        html_path.write_text(html_text, encoding="utf-8")

        # Save tables summary
        tables_summary = render_tables_summary(html_text, label, url, r.status_code)
        tables_path = RENDER_DIR / f"{label}.tables.txt"
        tables_path.write_text(tables_summary, encoding="utf-8")
        n_tables = tables_summary.count("\n## Table ")

        # Token compliance - delete stale file if no issues this run
        issues = check_token_compliance(html_text)
        issues_path = RENDER_DIR / f"{label}.token_issues.txt"
        if issues:
            issues_path.write_text("\n".join(issues), encoding="utf-8")
            total_issues += len(issues)
        elif issues_path.exists():
            issues_path.unlink()

        index_lines.append(f"| {label} | `{url}` | {r.status_code} | {size_kb:.1f}KB | {n_tables} | {len(issues)} |")
        print(f"  {label:33s} {url:55s} {r.status_code:8} {elapsed:6.2f}s {len(issues):>5}")

    except Exception as e:
        print(f"  {label:33s} {url:55s} ERR    {str(e)[:40]}")
        index_lines.append(f"| {label} | `{url}` | ERR | - | - | - |")

(RENDER_DIR / "_index.md").write_text("\n".join(index_lines), encoding="utf-8")

print("-" * 125)
print(f"  Total token issues across all pages: {total_issues}")
print(f"  Index: {RENDER_DIR / '_index.md'}")
print(f"  Output dir: {RENDER_DIR}")
