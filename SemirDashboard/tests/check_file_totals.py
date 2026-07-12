"""
Standalone script: read 1.5 - 10.5.xlsx, print file totals, then import via
process_sale_detail_file and compare DB aggregates.
"""
import os, sys, django

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "SemirDashboard.settings")
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))
django.setup()

import pandas as pd
from decimal import Decimal
from django.db import connection
from App.services.sale_detail_import import process_sale_detail_file

FILE = os.path.join(os.path.dirname(__file__), "input", "1.5 - 10.5.xlsx")

# ── 1. FILE TOTALS ───────────────────────────────────────────────────────────
df = pd.read_excel(FILE)
file_rows           = len(df)
file_qty            = int(df["Quantity"].sum())
file_sales_amount   = float(df["Sales Amount"].sum())
file_settlement     = float(df["Settlement Amount"].sum())
file_tag_amount     = float(df["Tag Amount"].sum())

print("=== FILE TOTALS (raw Excel) ===")
print(f"  Rows             : {file_rows:,}")
print(f"  Quantity         : {file_qty:,}")
print(f"  Sales Amount     : {file_sales_amount:,.2f}")
print(f"  Settlement Amount: {file_settlement:,.2f}")
print(f"  Tag Amount       : {file_tag_amount:,.2f}")

print()
print("Barcode sample:", list(df["Barcode"].head(3)))
print("Discount sample:", list(df["Discount"].head(3)))

# ── 2. IMPORT ────────────────────────────────────────────────────────────────
import io
from App.models import SaleDetail

class WrappedFile(io.BytesIO):
    def __init__(self, path):
        data = open(path, "rb").read()
        super().__init__(data)
        self.name = os.path.basename(path)

deleted, _ = SaleDetail.objects.all().delete()
print(f"\nDeleted {deleted} existing rows for clean comparison.")

print("\nImporting…")
result = process_sale_detail_file(WrappedFile(FILE))
print(f"Import result: {result}")

# ── 3. DB TOTALS ─────────────────────────────────────────────────────────────
from django.db.models import Sum, Count
agg = SaleDetail.objects.aggregate(
    rows=Count("id"),
    qty=Sum("quantity"),
    sales=Sum("sales_amount"),
    settlement=Sum("settlement_amount"),
    tag=Sum("tag_amount"),
)

db_rows       = agg["rows"] or 0
db_qty        = agg["qty"] or 0
db_sales      = float(agg["sales"] or 0)
db_settlement = float(agg["settlement"] or 0)
db_tag        = float(agg["tag"] or 0)

print()
print("=== DB TOTALS (after import) ===")
print(f"  Rows             : {db_rows:,}")
print(f"  Quantity         : {db_qty:,}")
print(f"  Sales Amount     : {db_sales:,.2f}")
print(f"  Settlement Amount: {db_settlement:,.2f}")
print(f"  Tag Amount       : {db_tag:,.2f}")

# ── 4. COMPARISON ────────────────────────────────────────────────────────────
print()
print("=== COMPARISON ===")
def cmp(label, expected, actual, tolerance=1.0):
    diff = actual - expected
    ok = abs(diff) <= tolerance
    mark = "OK" if ok else "MISMATCH"
    print(f"  [{mark}] {label}: file={expected:,.2f}  db={actual:,.2f}  diff={diff:+,.2f}")

print(f"  [{'OK' if db_rows == file_rows else 'MISMATCH'}] Rows      : file={file_rows:,}  db={db_rows:,}  diff={db_rows-file_rows:+,}")
print(f"  [{'OK' if db_qty == file_qty else 'MISMATCH'}] Quantity  : file={file_qty:,}  db={db_qty:,}  diff={db_qty-file_qty:+,}")
cmp("Sales Amount     ", file_sales_amount, db_sales)
cmp("Settlement Amount", file_settlement, db_settlement)
cmp("Tag Amount       ", file_tag_amount, db_tag)
