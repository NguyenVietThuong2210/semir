"""
tests/test_upload.py — Upload header validation tests.

Covers:
  1. _validate_headers() helper — returns missing headers for bad files, [] for good files
  2. Service-level validation — each process_*_file raises ValueError with clear message
  3. View-level validation — bad headers → immediate redirect with error message (no job started)
  4. View-level validation — good file → job created and started
"""
import io
from unittest.mock import patch

import pandas as pd
from django.contrib.auth.models import User
from django.contrib.messages import get_messages
from django.test import Client, TestCase, override_settings

from App.views.upload import _validate_headers

INPUT_DIR = __import__("pathlib").Path(__file__).parent / "input"


# ─────────────────────────────────────────────────────────────────────────────
# Helper: build a minimal in-memory file from a list of column headers
# ─────────────────────────────────────────────────────────────────────────────

def _make_csv(headers: list[str], rows: list[dict] | None = None) -> bytes:
    """Return CSV bytes with given headers and optional data rows."""
    lines = [",".join(headers)]
    for row in (rows or []):
        lines.append(",".join(str(row.get(h, "")) for h in headers))
    return "\n".join(lines).encode()


def _make_xlsx(headers: list[str], rows: list[dict] | None = None) -> bytes:
    """Return xlsx bytes with given headers and optional data rows."""
    buf = io.BytesIO()
    df = pd.DataFrame(rows or [], columns=headers)
    df.to_excel(buf, index=False)
    return buf.getvalue()


# ─────────────────────────────────────────────────────────────────────────────
# 1. _validate_headers() unit tests
# ─────────────────────────────────────────────────────────────────────────────

class ValidateHeadersTests(TestCase):
    """Unit tests for the _validate_headers() helper in upload.py."""

    # ── Customers ──────────────────────────────────────────────────────────

    def test_customers_valid_csv(self):
        data = _make_csv(["VIP ID", "PHONE NO.", "Name", "VIP Grade"])
        self.assertEqual(_validate_headers(data, "f.csv", "customers"), [])

    def test_customers_valid_xlsx(self):
        data = _make_xlsx(["VIP ID", "Phone NO.", "Name"])  # mixed case — service uppercases
        self.assertEqual(_validate_headers(data, "f.xlsx", "customers"), [])

    def test_customers_missing_phone(self):
        data = _make_csv(["VIP ID", "Name", "Registration Date"])
        self.assertEqual(_validate_headers(data, "f.csv", "customers"), ["PHONE NO."])

    def test_customers_missing_both_required(self):
        data = _make_csv(["Name", "Email", "Points"])
        missing = _validate_headers(data, "f.csv", "customers")
        self.assertIn("VIP ID", missing)
        self.assertIn("PHONE NO.", missing)

    # ── Sales ──────────────────────────────────────────────────────────────

    def test_sales_valid_xlsx(self):
        data = _make_xlsx(["Invoice Number", "Shop Name", "Sales Date",
                           "Settlement Amount", "Vip Id"])
        self.assertEqual(_validate_headers(data, "f.xlsx", "sales"), [])

    def test_sales_missing_invoice_number(self):
        data = _make_csv(["Shop Name", "Sales Date", "Settlement Amount"])
        self.assertIn("INVOICE NUMBER", _validate_headers(data, "f.csv", "sales"))

    def test_sales_missing_settlement_amount(self):
        data = _make_csv(["Invoice Number", "Shop Name", "Sales Date", "Vip Id"])
        self.assertIn("SETTLEMENT AMOUNT", _validate_headers(data, "f.csv", "sales"))

    # ── Coupons ──────────────────────────────────────────────────────────

    def test_coupons_valid(self):
        data = _make_xlsx(["Coupon ID", "Face Value", "Used", "Begin Date"])
        self.assertEqual(_validate_headers(data, "f.xlsx", "coupons"), [])

    def test_coupons_missing_coupon_id(self):
        data = _make_csv(["Face Value", "Used", "Begin Date"])
        self.assertEqual(_validate_headers(data, "f.csv", "coupons"), ["Coupon ID"])

    def test_coupons_wrong_case_rejected(self):
        # "COUPON ID" (all-caps) must not match because coupon service is case-sensitive
        data = _make_csv(["COUPON ID", "Face Value"])
        self.assertIn("Coupon ID", _validate_headers(data, "f.csv", "coupons"))

    # ── Inventory ─────────────────────────────────────────────────────────

    def test_inventory_valid(self):
        data = _make_xlsx(["Warehouse/Shop ID", "Product Code", "Brand", "Inventory Quantity"])
        self.assertEqual(_validate_headers(data, "f.xlsx", "inventory"), [])

    def test_inventory_missing_shop_id(self):
        data = _make_csv(["Product Code", "Brand"])
        self.assertIn("WAREHOUSE/SHOP ID", _validate_headers(data, "f.csv", "inventory"))

    def test_inventory_missing_product_code(self):
        data = _make_csv(["Warehouse/Shop ID", "Brand"])
        self.assertIn("PRODUCT CODE", _validate_headers(data, "f.csv", "inventory"))

    # ── Sale Detail ───────────────────────────────────────────────────────

    def test_sale_detail_valid(self):
        data = _make_xlsx(["Invoice Number", "Product Code", "Sales Date", "Quantity"])
        self.assertEqual(_validate_headers(data, "f.xlsx", "sale_detail"), [])

    def test_sale_detail_missing_sales_date(self):
        data = _make_csv(["Invoice Number", "Product Code", "Quantity"])
        self.assertIn("SALES DATE", _validate_headers(data, "f.csv", "sale_detail"))

    # ── Used Points ───────────────────────────────────────────────────────

    def test_used_points_valid(self):
        data = _make_csv(["VIP ID", "PHONE NO.", "USED POINTS"])
        self.assertEqual(_validate_headers(data, "f.csv", "used_points"), [])

    def test_used_points_missing_points(self):
        data = _make_csv(["VIP ID", "PHONE NO."])
        self.assertIn("USED POINTS", _validate_headers(data, "f.csv", "used_points"))

    # ── Unreadable file ───────────────────────────────────────────────────

    def test_unreadable_file_returns_empty(self):
        # Corrupt bytes — can't parse, validation skipped (let service handle it)
        self.assertEqual(_validate_headers(b"not a csv or xlsx", "f.xlsx", "customers"), [])

    # ── Real input files ──────────────────────────────────────────────────

    def test_real_customer_file_passes(self):
        data = (INPUT_DIR / "customer.xlsx").read_bytes()
        self.assertEqual(_validate_headers(data, "customer.xlsx", "customers"), [])

    def test_real_sales_file_passes(self):
        data = (INPUT_DIR / "Sale 2024.xlsx").read_bytes()
        self.assertEqual(_validate_headers(data, "Sale 2024.xlsx", "sales"), [])

    def test_real_coupon_file_passes(self):
        data = (INPUT_DIR / "coupon_1 (1).xlsx").read_bytes()
        self.assertEqual(_validate_headers(data, "coupon_1.xlsx", "coupons"), [])

    def test_real_inventory_file_passes(self):
        data = (INPUT_DIR / "inventory.xlsx").read_bytes()
        self.assertEqual(_validate_headers(data, "inventory.xlsx", "inventory"), [])

    def test_real_sale_detail_file_passes(self):
        data = (INPUT_DIR / "sale detail.xlsx").read_bytes()
        self.assertEqual(_validate_headers(data, "sale_detail.xlsx", "sale_detail"), [])


# ─────────────────────────────────────────────────────────────────────────────
# 2. Service-level validation tests
# ─────────────────────────────────────────────────────────────────────────────

class ServiceHeaderValidationTests(TestCase):
    """Each service raises ValueError with a clear message on bad headers."""

    def _file(self, headers, rows=None, name="test.csv"):
        buf = io.BytesIO(_make_csv(headers, rows))
        buf.name = name
        return buf

    def _xlsx_file(self, headers, rows=None, name="test.xlsx"):
        buf = io.BytesIO(_make_xlsx(headers, rows))
        buf.name = name
        return buf

    def test_customer_service_missing_phone(self):
        from App.services.customer_import import process_customer_file
        f = self._file(["VIP ID", "Name"])
        with self.assertRaises(ValueError) as ctx:
            process_customer_file(f)
        self.assertIn("PHONE NO.", str(ctx.exception))

    def test_customer_service_missing_vip_id(self):
        from App.services.customer_import import process_customer_file
        f = self._file(["PHONE NO.", "Name"])
        with self.assertRaises(ValueError) as ctx:
            process_customer_file(f)
        self.assertIn("VIP ID", str(ctx.exception))

    def test_sales_service_missing_invoice_number(self):
        from App.services.sales_import import process_sales_file
        f = self._file(["Shop Name", "Sales Date", "Settlement Amount"])
        with self.assertRaises(ValueError) as ctx:
            process_sales_file(f)
        self.assertIn("INVOICE NUMBER", str(ctx.exception))

    def test_sales_service_missing_settlement_amount(self):
        from App.services.sales_import import process_sales_file
        f = self._file(["Invoice Number", "Shop Name", "Sales Date"])
        with self.assertRaises(ValueError) as ctx:
            process_sales_file(f)
        self.assertIn("SETTLEMENT AMOUNT", str(ctx.exception))

    def test_coupon_service_missing_coupon_id(self):
        from App.services.coupon_import import process_coupon_file
        f = self._xlsx_file(["Face Value", "Used", "Begin Date"])
        with self.assertRaises(ValueError) as ctx:
            process_coupon_file(f)
        self.assertIn("Coupon ID", str(ctx.exception))

    def test_inventory_service_missing_shop_id(self):
        from App.services.inventory_import import process_inventory_file
        f = self._xlsx_file(["Product Code", "Brand"])
        with self.assertRaises(ValueError) as ctx:
            process_inventory_file(f)
        self.assertIn("WAREHOUSE/SHOP ID", str(ctx.exception))

    def test_inventory_service_missing_product_code(self):
        from App.services.inventory_import import process_inventory_file
        f = self._xlsx_file(["Warehouse/Shop ID", "Brand"])
        with self.assertRaises(ValueError) as ctx:
            process_inventory_file(f)
        self.assertIn("PRODUCT CODE", str(ctx.exception))

    def test_sale_detail_service_missing_invoice(self):
        from App.services.sale_detail_import import process_sale_detail_file
        f = self._xlsx_file(["Product Code", "Sales Date"])
        with self.assertRaises(ValueError) as ctx:
            process_sale_detail_file(f)
        self.assertIn("INVOICE NUMBER", str(ctx.exception))

    def test_sale_detail_service_missing_sales_date(self):
        from App.services.sale_detail_import import process_sale_detail_file
        f = self._xlsx_file(["Invoice Number", "Product Code"])
        with self.assertRaises(ValueError) as ctx:
            process_sale_detail_file(f)
        self.assertIn("SALES DATE", str(ctx.exception))


# ─────────────────────────────────────────────────────────────────────────────
# 3 & 4. View-level integration tests
# ─────────────────────────────────────────────────────────────────────────────

@override_settings(ALLOWED_HOSTS=["*"])
class UploadViewHeaderValidationTests(TestCase):
    """
    View rejects bad headers immediately (no job created) and
    accepts good files (job created, thread started).
    """

    def setUp(self):
        self.client = Client()
        self.user = User.objects.create_superuser("testadmin", password="pw")
        self.client.force_login(self.user)

    def _upload(self, url, file_bytes, filename):
        return self.client.post(
            url,
            {"file": _django_file(file_bytes, filename)},
            SERVER_NAME="localhost",
        )

    # ── Customers ──────────────────────────────────────────────────────────

    def test_customers_bad_headers_redirect_with_error(self):
        data = _make_xlsx(["Name", "Email"])  # missing VIP ID and PHONE NO.
        with patch("App.views.upload._start_thread") as mock_thread:
            r = self.client.post(
                "/upload/customers/",
                {"file": _django_file(data, "bad.xlsx")},
                SERVER_NAME="localhost",
            )
        self.assertEqual(r.status_code, 302)
        mock_thread.assert_not_called()
        msgs = [str(m) for m in get_messages(r.wsgi_request)]
        self.assertTrue(any("VIP ID" in m or "PHONE NO." in m for m in msgs), msgs)

    def test_customers_good_headers_starts_job(self):
        data = _make_xlsx(["VIP ID", "PHONE NO.", "Name"])
        with patch("App.views.upload._start_thread") as mock_thread:
            r = self.client.post(
                "/upload/customers/",
                {"file": _django_file(data, "good.xlsx")},
                SERVER_NAME="localhost",
            )
        self.assertEqual(r.status_code, 302)
        mock_thread.assert_called_once()

    # ── Sales ──────────────────────────────────────────────────────────────

    def test_sales_bad_headers_redirect_with_error(self):
        data = _make_xlsx(["Name", "Date"])
        with patch("App.views.upload._start_thread") as mock_thread:
            r = self.client.post(
                "/upload/sales/",
                {"file": _django_file(data, "bad.xlsx")},
                SERVER_NAME="localhost",
            )
        self.assertEqual(r.status_code, 302)
        mock_thread.assert_not_called()
        msgs = [str(m) for m in get_messages(r.wsgi_request)]
        self.assertTrue(any("INVOICE NUMBER" in m for m in msgs), msgs)

    def test_sales_good_headers_starts_job(self):
        data = _make_xlsx(["Invoice Number", "Shop Name", "Sales Date",
                           "Settlement Amount", "Vip Id"])
        with patch("App.views.upload._start_thread") as mock_thread:
            r = self.client.post(
                "/upload/sales/",
                {"file": _django_file(data, "good.xlsx")},
                SERVER_NAME="localhost",
            )
        self.assertEqual(r.status_code, 302)
        mock_thread.assert_called_once()

    # ── Coupons ──────────────────────────────────────────────────────────

    def test_coupons_bad_headers_redirect_with_error(self):
        data = _make_xlsx(["Face Value", "Used"])  # missing Coupon ID
        with patch("App.views.upload._start_thread") as mock_thread:
            r = self.client.post(
                "/upload/coupons/",
                {"file": _django_file(data, "bad.xlsx")},
                SERVER_NAME="localhost",
            )
        self.assertEqual(r.status_code, 302)
        mock_thread.assert_not_called()
        msgs = [str(m) for m in get_messages(r.wsgi_request)]
        self.assertTrue(any("Coupon ID" in m for m in msgs), msgs)

    def test_coupons_good_headers_starts_job(self):
        data = _make_xlsx(["Coupon ID", "Face Value", "Used"])
        with patch("App.views.upload._start_thread") as mock_thread:
            r = self.client.post(
                "/upload/coupons/",
                {"file": _django_file(data, "good.xlsx")},
                SERVER_NAME="localhost",
            )
        self.assertEqual(r.status_code, 302)
        mock_thread.assert_called_once()

    # ── Inventory ─────────────────────────────────────────────────────────

    def test_inventory_bad_headers_redirect_with_error(self):
        data = _make_xlsx(["Brand", "SKU"])  # missing both required
        with patch("App.views.upload._start_thread") as mock_thread:
            r = self.client.post(
                "/upload/inventory/",
                {"file": _django_file(data, "bad.xlsx")},
                SERVER_NAME="localhost",
            )
        self.assertEqual(r.status_code, 302)
        mock_thread.assert_not_called()
        msgs = [str(m) for m in get_messages(r.wsgi_request)]
        self.assertTrue(any("WAREHOUSE/SHOP ID" in m or "PRODUCT CODE" in m for m in msgs), msgs)

    def test_inventory_good_headers_starts_job(self):
        data = _make_xlsx(["Warehouse/Shop ID", "Product Code", "Brand"])
        with patch("App.views.upload._start_thread") as mock_thread:
            r = self.client.post(
                "/upload/inventory/",
                {"file": _django_file(data, "good.xlsx")},
                SERVER_NAME="localhost",
            )
        self.assertEqual(r.status_code, 302)
        mock_thread.assert_called_once()


# ─────────────────────────────────────────────────────────────────────────────
# Helper: wrap bytes as a Django InMemoryUploadedFile
# ─────────────────────────────────────────────────────────────────────────────

def _django_file(data: bytes, filename: str):
    from django.core.files.uploadedfile import SimpleUploadedFile
    ct = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet" \
         if filename.endswith(".xlsx") else "text/csv"
    return SimpleUploadedFile(filename, data, content_type=ct)
