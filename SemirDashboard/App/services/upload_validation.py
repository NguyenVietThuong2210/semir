"""
App/services/upload_validation.py

Unified pre-upload validation layer (refactor R2, plan.md Phase 2 design).
Runs in the request thread BEFORE a background job is created, so users get
immediate popup feedback instead of a failed job minutes later.

Pipeline (validate_upload):
    1. extension check
    2. required-header check (per upload type)
    3. duplicate-key check within the file (per-type policy below)
    4. zero-data-rows check

Duplicate-key policy (number-preservation review 2026-07-12):
    coupons      (Coupon ID)                 → ERROR  (unique key; real file has 0 dups)
    customers    (VIP ID, PHONE NO.)         → ERROR  (upsert key; real file has 0 dups)
    inventory    (WAREHOUSE/SHOP ID, PRODUCT CODE) → WARNING (service skips dups silently by design)
    sales        (INVOICE NUMBER)            → WARNING (upsert last-wins by design)
    sale_detail  (INVOICE+PRODUCT+BARCODE)   → WARNING (insert-as-is by design)
    used_points  (VIP ID, PHONE NO.)         → WARNING (update semantics)
"""
import hashlib
import io
from dataclasses import dataclass, field

import pandas as pd

ALLOWED_UPLOAD_EXTENSIONS = {"csv", "xls", "xlsx"}

# Required headers per upload type.
# uppercase=True → the file's headers are upper-cased before comparison.
REQUIRED_HEADERS = {
    "customers":   (["VIP ID", "PHONE NO."], True),
    "sales":       (["INVOICE NUMBER", "SHOP NAME", "SALES DATE", "SETTLEMENT AMOUNT"], True),
    "coupons":     (["Coupon ID"], False),
    "inventory":   (["WAREHOUSE/SHOP ID", "PRODUCT CODE"], True),
    "sale_detail": (["INVOICE NUMBER", "PRODUCT CODE", "SALES DATE"], True),
    "used_points": (["VIP ID", "PHONE NO.", "USED POINTS"], True),
}

# (key columns, uppercase headers?, hard error?) for the in-file duplicate check
_DUP_KEYS = {
    "coupons":     (["Coupon ID"], False, True),
    "customers":   (["VIP ID", "PHONE NO."], True, True),
    "inventory":   (["WAREHOUSE/SHOP ID", "PRODUCT CODE"], True, False),
    "sales":       (["INVOICE NUMBER"], True, False),
    "sale_detail": (["INVOICE NUMBER", "PRODUCT CODE", "BARCODE"], True, False),
    "used_points": (["VIP ID", "PHONE NO."], True, False),
}


@dataclass
class ValidationResult:
    errors: list = field(default_factory=list)     # block the upload
    warnings: list = field(default_factory=list)   # shown, upload proceeds
    row_count: int = 0
    # Perf plan P3-01: the DataFrame already parsed during validation, so the
    # background import thread can reuse it instead of parsing the file a
    # 2nd time. None when the file was unparseable (service re-parses and
    # raises with full context, unchanged from before this field existed).
    df: object = None

    @property
    def ok(self) -> bool:
        return not self.errors


def file_sha256(file_bytes: bytes) -> str:
    """Content hash for the re-upload guard (U-10)."""
    return hashlib.sha256(file_bytes).hexdigest()


def validate_upload_ext(filename: str) -> str | None:
    """Return error message if the extension is not allowed, else None."""
    ext = filename.rsplit(".", 1)[-1].lower() if "." in filename else ""
    if ext not in ALLOWED_UPLOAD_EXTENSIONS:
        return f"File type '.{ext}' is not allowed. Only CSV and Excel files are accepted."
    return None


def _read_df(file_bytes: bytes, filename: str, nrows=None):
    buf = io.BytesIO(file_bytes)
    if filename.lower().endswith(".csv"):
        return pd.read_csv(buf, dtype=str, nrows=nrows)
    return pd.read_excel(buf, dtype=str, nrows=nrows)


def validate_headers(file_bytes: bytes, filename: str, upload_type: str) -> list:
    """Header-row check only (fast, nrows=0).
    Returns missing required column names ([] if the file can't even be parsed —
    the import service reports parse errors with full context)."""
    required, uppercase = REQUIRED_HEADERS.get(upload_type, ([], True))
    if not required:
        return []
    try:
        df = _read_df(file_bytes, filename, nrows=0)
    except Exception:
        return []
    cols = [str(c).strip().upper() for c in df.columns] if uppercase \
        else [str(c).strip() for c in df.columns]
    return [h for h in required if h not in cols]


def _check_duplicates(df, upload_type: str, result: ValidationResult) -> None:
    spec = _DUP_KEYS.get(upload_type)
    if not spec:
        return
    key_cols, uppercase, hard = spec
    cols = {str(c).strip().upper() if uppercase else str(c).strip(): c for c in df.columns}
    resolved = [cols.get(k) for k in key_cols]
    if any(c is None for c in resolved):
        # A dup-key column may legitimately be absent when it is not in
        # REQUIRED_HEADERS (e.g. sale_detail's BARCODE) — skip silently then;
        # for required columns the header check already reported the problem.
        return
    keys = df[resolved].astype(str).apply(lambda s: s.str.strip())
    mask = ~(keys.iloc[:, 0].isin(("", "nan", "None")))
    keys = keys[mask]
    dup_mask = keys.duplicated()
    if not dup_mask.any():
        return
    sample = keys[dup_mask].head(10).apply(lambda r: " + ".join(r.values), axis=1).tolist()
    n = int(dup_mask.sum())
    msg = (f"File contains {n} duplicated {' + '.join(key_cols)} row(s), "
           f"e.g.: {', '.join(sample[:5])}{'…' if n > 5 else ''}")
    if hard:
        result.errors.append(msg + " Remove duplicates and upload again.")
    else:
        result.warnings.append(msg + " Duplicates follow this type's normal rule (upsert/skip/insert-as-is).")


def _missing_headers_from_df(df, upload_type: str) -> list:
    required, uppercase = REQUIRED_HEADERS.get(upload_type, ([], True))
    if not required:
        return []
    cols = [str(c).strip().upper() for c in df.columns] if uppercase \
        else [str(c).strip() for c in df.columns]
    return [h for h in required if h not in cols]


def validate_upload(file_bytes: bytes, filename: str, upload_type: str) -> ValidationResult:
    """Full pre-job validation pipeline. Never raises — reports via result.

    The file is parsed ONCE (header check reuses the same DataFrame); large
    files therefore cost a single pandas read in the request thread."""
    result = ValidationResult()

    err = validate_upload_ext(filename)
    if err:
        result.errors.append(err)
        return result

    try:
        df = _read_df(file_bytes, filename)
    except Exception:
        # Unparseable content: dup/zero-row checks are skipped by design —
        # the import service reports parse errors with row context, and the
        # DB-level backstops (coupon_id unique 0019, inventory U-01 guard)
        # carry the safety load for the hard-error cases.
        return result

    missing = _missing_headers_from_df(df, upload_type)
    if missing:
        required, _ = REQUIRED_HEADERS.get(upload_type, ([], True))
        result.errors.append(
            f"Missing required column(s): {', '.join(missing)}. "
            f"Expected headers: {', '.join(required)}."
        )
        return result
    result.row_count = len(df)
    result.df = df

    if result.row_count == 0:
        # Destructive import (truncate+replace) must never start on an empty file;
        # other types would just no-op, so a warning suffices.
        msg = "File contains no data rows (header only)."
        if upload_type == "inventory":
            result.errors.append(msg + " Upload rejected — existing inventory preserved.")
        else:
            result.warnings.append(msg)
        return result

    _check_duplicates(df, upload_type, result)
    return result
