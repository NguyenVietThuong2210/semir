"""
tests/test_customer.py — Customer analytics page: CNV comparison + full timing.

Pipeline:
  customer.xlsx  → Customer (POSCustomer) DB
  cnv_customers.csv → CNVCustomer DB (bulk_create from CSV)
  Sale *.xlsx    → SalesTransaction DB
               → _compute_cnv_comparison() → verified output

Run:
  cd SemirDashboard && python manage.py test tests.test_customer -v 2

Regenerate snapshots:
  UPDATE_SNAPSHOTS=1 python manage.py test tests.test_customer -v 2
"""
import csv
import io
import time
from datetime import date, datetime

from django.utils import timezone

from App.models import Customer
from App.cnv.models import CNVCustomer
from App.services import process_customer_file, process_sales_file
from App.cnv.service import compute_cnv_comparison as _compute_cnv_comparison
from App.analytics.tab_functions import get_customer_tab, CUSTOMER_TABS

from tests.base import SnapshotTestCase, INPUT_DIR, get_run_log

CUSTOMER_FILE = INPUT_DIR / "customer.xlsx"
CNV_FILE      = INPUT_DIR / "cnv_customers.csv"
SALE_FILES    = [INPUT_DIR / "Sale 2024.xlsx", INPUT_DIR / "Sale 2025.xlsx", INPUT_DIR / "Sale 2026.xlsx"]


def _named(path):
    with open(path, "rb") as f:
        data = f.read()
    class _N(io.BytesIO):
        pass
    obj = _N(data)
    obj.name = path.name
    return obj


def _load_cnv_customers_from_csv():
    """
    Bulk-load CNVCustomer records from cnv_customers.csv.
    Expected columns (case-insensitive):
      id/cnv_id, phone, last_name, first_name, email, level_name,
      points, total_points, used_points, cnv_created_at, cnv_updated_at,
      zalo_app_id, zalo_oa_id
    Returns (created_count, skipped_count).
    """
    if not CNV_FILE.exists():
        return 0, 0

    with open(CNV_FILE, newline="", encoding="utf-8-sig") as f:
        content = f.read().strip()
    if not content:
        return 0, 0

    reader = csv.DictReader(io.StringIO(content))
    # Normalise headers to lowercase stripped
    rows = []
    for row in reader:
        rows.append({k.strip().lower(): v.strip() for k, v in row.items()})

    if not rows:
        return 0, 0

    def _int(v, default=0):
        try: return int(float(v)) if v else default
        except: return default

    def _dec(v, default=0):
        try: return float(v) if v else default
        except: return default

    def _dt(v):
        if not v:
            return None
        from django.utils.dateparse import parse_datetime as _parse
        from dateutil import parser as _dparser
        # Try django parser first
        try:
            result = _parse(v.replace("+00", "+00:00").replace(" ", "T", 1))
            if result:
                if timezone.is_naive(result):
                    return timezone.make_aware(result)
                return result
        except Exception:
            pass
        # Fallback: dateutil
        try:
            result = _dparser.parse(v)
            if timezone.is_naive(result):
                return timezone.make_aware(result)
            return result
        except Exception:
            pass
        # Last resort: strip timezone suffix and parse as naive
        for fmt in ("%Y-%m-%d %H:%M:%S.%f", "%Y-%m-%d %H:%M:%S", "%Y-%m-%dT%H:%M:%S", "%Y-%m-%d"):
            try:
                clean = v.split("+")[0].split("Z")[0].strip()
                naive = datetime.strptime(clean, fmt)
                return timezone.make_aware(naive)
            except ValueError:
                continue
        return None

    # Column name aliases
    def _get(row, *keys, default=""):
        for k in keys:
            if k in row and row[k]:
                return row[k]
        return default

    objs = []
    seen_ids = set()
    for row in rows:
        # CSV has both 'id' (DB auto PK) and 'cnv_id' — always use 'cnv_id'
        cnv_id_raw = _get(row, "cnv_id")
        if not cnv_id_raw:
            cnv_id_raw = _get(row, "id")  # fallback if no cnv_id column
        try:
            cnv_id = int(float(cnv_id_raw))
        except (ValueError, TypeError):
            continue
        if cnv_id in seen_ids:
            continue
        seen_ids.add(cnv_id)

        # Skip if already exists
        if CNVCustomer.objects.filter(cnv_id=cnv_id).exists():
            continue

        objs.append(CNVCustomer(
            cnv_id        = cnv_id,
            phone         = _get(row, "phone", "phone_number") or None,
            last_name     = _get(row, "last_name", "lastname") or None,
            first_name    = _get(row, "first_name", "firstname") or None,
            email         = _get(row, "email") or None,
            level_name    = _get(row, "level_name", "level") or None,
            points        = _dec(_get(row, "points")),
            total_points  = _dec(_get(row, "total_points")),
            used_points   = _dec(_get(row, "used_points")),
            cnv_created_at = _dt(_get(row, "cnv_created_at", "created_at")),
            cnv_updated_at = _dt(_get(row, "cnv_updated_at", "updated_at")),
            zalo_app_id   = _get(row, "zalo_app_id") or None,
            zalo_oa_id    = _get(row, "zalo_oa_id") or None,
        ))

    BATCH = 2000
    created = 0
    for i in range(0, len(objs), BATCH):
        batch = objs[i:i+BATCH]
        CNVCustomer.objects.bulk_create(batch, ignore_conflicts=True)
        created += len(batch)

    return created, len(rows) - created


class CNVCustomerImportTest(SnapshotTestCase):
    """Test loading cnv_customers.csv into CNVCustomer table."""

    def test_import_cnv_customers(self):
        if not CNV_FILE.exists() or CNV_FILE.stat().st_size < 10:
            self.skipTest(f"cnv_customers.csv missing or empty")

        t = self.timer("import_cnv_customers")
        created, skipped = _load_cnv_customers_from_csv()
        t.checkpoint(f"bulk_create CNVCustomer → created={created} skipped/dup={skipped}")
        t.report()

        total = CNVCustomer.objects.count()
        get_run_log().log(f"  CNVCustomer total in DB: {total}")
        print(f"\n  CNVCustomer in DB: {total}")
        self.assertGreater(total, 0, "No CNV customers loaded")


class CustomerAnalyticsTest(SnapshotTestCase):
    """Full customer/CNV comparison pipeline — defines expected output."""

    @classmethod
    def setUpTestData(cls):
        # POS customers
        if CUSTOMER_FILE.exists():
            process_customer_file(_named(CUSTOMER_FILE))
        # Sales
        for path in SALE_FILES:
            if path.exists():
                process_sales_file(_named(path))
        # CNV customers
        _load_cnv_customers_from_csv()

    # ── Full page timing ──────────────────────────────────────────────────

    def test_page_timing_alltime(self):
        """Simulate full customer page load — instrument each DB query phase."""
        from django.db.models import Count, Q as _Q
        from App.analytics.customer_utils import get_inv_lookups_for_period, _norm_vid

        log = get_run_log()
        log.section("CUSTOMER PAGE TIMING (all-time) — per-query breakdown")
        t = self.timer("customer_page_alltime")

        pos_all = (Customer.objects
                   .filter(vip_id__isnull=False, phone__isnull=False)
                   .exclude(vip_id=0).exclude(phone=""))
        cnv_all = CNVCustomer.objects.filter(phone__isnull=False).exclude(phone="")

        # Phase 1: Totals
        total_pos = pos_all.count()
        total_cnv = CNVCustomer.objects.count()
        t.checkpoint(f"DB count pos={total_pos} cnv={total_cnv}")

        # Phase 2: Materialise phone sets (needed for Python set ops)
        pos_phones = set(pos_all.values_list("phone", flat=True))
        t.checkpoint(f"materialise POS phone set → {len(pos_phones)} phones")

        cnv_phones = set(cnv_all.values_list("phone", flat=True))
        t.checkpoint(f"materialise CNV phone set → {len(cnv_phones)} phones")

        # Phase 3: Python set ops
        pos_only_count = len(pos_phones - cnv_phones)
        cnv_only_count = len(cnv_phones - pos_phones)
        shared_count   = len(pos_phones & cnv_phones)
        t.checkpoint(f"Python set diff → pos_only={pos_only_count} cnv_only={cnv_only_count} shared={shared_count}")

        # Phase 4: POS-only list (SQL anti-join)
        _cnv_phone_qs = cnv_all.values("phone")
        _pos_phone_qs = pos_all.values("phone")
        pos_only_all = list(pos_all.exclude(phone__in=_cnv_phone_qs)
                            .values("vip_id","phone","name","vip_grade","registration_date","points")
                            .order_by("-registration_date"))
        t.checkpoint(f"DB pos_only_all list → {len(pos_only_all)} rows")

        # Phase 5: CNV-only list
        cnv_only_all = list(cnv_all.exclude(phone__in=_pos_phone_qs)
                            .values("cnv_id","phone","last_name","first_name",
                                    "level_name","points","total_points","used_points")
                            .order_by("-cnv_created_at"))
        t.checkpoint(f"DB cnv_only_all list → {len(cnv_only_all)} rows")

        # Phase 6: Points mismatch (shared phones)
        pos_map = {c["phone"]: c for c in
                   pos_all.filter(phone__in=_cnv_phone_qs)
                   .values("vip_id","phone","name","vip_grade","points","used_points")}
        cnv_map = {c["phone"]: c for c in
                   cnv_all.filter(phone__in=_pos_phone_qs)
                   .values("cnv_id","phone","last_name","first_name","level_name",
                            "points","total_points","used_points")}
        t.checkpoint(f"DB points mismatch maps → pos={len(pos_map)} cnv={len(cnv_map)}")

        mismatch = []
        for phone, pc in pos_map.items():
            cc = cnv_map.get(phone)
            if cc:
                pos_net = int(pc.get("points") or 0) - int(pc.get("used_points") or 0)
                cnv_pts = int(float(cc.get("points") or 0))
                if pos_net != cnv_pts:
                    mismatch.append(phone)
        t.checkpoint(f"Python points mismatch loop → {len(mismatch)} mismatches")

        # Phase 7: Zalo counts
        zalo_app = CNVCustomer.objects.filter(zalo_app_id__isnull=False).exclude(zalo_app_id="").count()
        zalo_oa  = CNVCustomer.objects.filter(zalo_oa_id__isnull=False).exclude(zalo_oa_id="").count()
        t.checkpoint(f"DB zalo counts → app={zalo_app} oa={zalo_oa}")

        # Phase 8: Breakdown (compute_cnv_comparison)
        data = _compute_cnv_comparison("", "")
        t.checkpoint(f"_compute_cnv_comparison full (includes breakdown)")

        total = t.total()
        t.report()
        self.record_page_timing("CUSTOMER (all-time)", total, t._checkpoints)
        self.assertLess(total, 30, f"Customer page all-time took {total:.1f}s > 30s threshold")

    def test_page_timing_2025(self):
        log = get_run_log()
        log.section("CUSTOMER PAGE TIMING (2025 filter)")
        t = self.timer("customer_page_2025")
        data = _compute_cnv_comparison("2025-01-01", "2025-12-31")
        total = t.total()
        t.checkpoint(f"_compute_cnv_comparison(2025) → has_filter={data['has_filter']}")
        t.report()
        self.record_page_timing("CUSTOMER (2025 filter)", total, t._checkpoints)

    # ── Snapshots ─────────────────────────────────────────────────────────

    def test_snapshot_alltime(self):
        t = self.timer("customer_snapshot_alltime")
        data = _compute_cnv_comparison("", "")
        t.checkpoint("_compute_cnv_comparison(all-time)")
        t.report()
        self.assert_snapshot("customer_alltime", {
            "has_filter": data["has_filter"],
            "total_pos": data["total_pos"],
            "total_cnv": data["total_cnv"],
            "pos_only_all_count": data["pos_only_all_count"],
            "cnv_only_all_count": data["cnv_only_all_count"],
            "points_mismatch_count": data["points_mismatch_count"],
            "total_points_mismatch_count": data["total_points_mismatch_count"],
            "cnv_used_points_count": data["cnv_used_points_count"],
            "zalo_app_all_count": data["zalo_app_all_count"],
            "zalo_oa_all_count": data["zalo_oa_all_count"],
            "zalo_app_all_pct": data["zalo_app_all_pct"],
            "zalo_oa_all_pct": data["zalo_oa_all_pct"],
            "new_pos_count": data.get("new_pos_count", 0),
            "new_cnv_count": data.get("new_cnv_count", 0),
        })

    def test_snapshot_2025(self):
        t = self.timer("customer_snapshot_2025")
        data = _compute_cnv_comparison("2025-01-01", "2025-12-31")
        t.checkpoint("_compute_cnv_comparison(2025)")
        t.report()
        self.assert_snapshot("customer_2025", {
            "has_filter": data["has_filter"],
            "total_pos": data["total_pos"],
            "total_cnv": data["total_cnv"],
            "pos_only_period_count": data.get("pos_only_period_count", 0),
            "cnv_only_period_count": data.get("cnv_only_period_count", 0),
            "new_pos_count": data.get("new_pos_count", 0),
            "new_cnv_count": data.get("new_cnv_count", 0),
            "zalo_app_period_count": data.get("zalo_app_period_count", 0),
            "zalo_oa_period_count": data.get("zalo_oa_period_count", 0),
        })

    def test_snapshot_breakdown(self):
        t = self.timer("customer_snapshot_breakdown")
        data = _compute_cnv_comparison("", "")
        bd = data.get("breakdown", {})
        t.checkpoint(f"_compute_cnv_comparison → breakdown keys={list(bd.keys())}")
        t.report()
        # Keys in compute_cnv_breakdown return: 'season', 'month', 'week', 'shop'
        self.assert_snapshot("customer_breakdown", {
            "by_season_count": len(bd.get("season", [])),
            "by_month_count":  len(bd.get("month", [])),
            "by_week_count":   len(bd.get("week", [])),
            "by_shop_count":   len(bd.get("shop", [])),
            "by_season": bd.get("season", []),
            "by_month":  bd.get("month", []),
        })

    # ── Sanity ────────────────────────────────────────────────────────────

    def test_pos_cnv_math(self):
        data = _compute_cnv_comparison("", "")
        pos_only = data["pos_only_all_count"]
        total_pos = data["total_pos"]
        total_cnv = data["total_cnv"]
        cnv_only = data["cnv_only_all_count"]
        # POS-side: every POS customer is either POS-only or matched to CNV
        pos_in_cnv = total_pos - pos_only
        self.assertGreaterEqual(pos_in_cnv, 0, f"pos_in_cnv negative: {pos_in_cnv}")
        # CNV-side: every CNV customer is either CNV-only or matched to POS
        cnv_in_pos = total_cnv - cnv_only
        self.assertGreaterEqual(cnv_in_pos, 0, f"cnv_in_pos negative: {cnv_in_pos}")

    def test_no_filter_flag(self):
        data = _compute_cnv_comparison("", "")
        self.assertFalse(data["has_filter"])

    def test_with_filter_flag(self):
        data = _compute_cnv_comparison("2025-01-01", "2025-12-31")
        self.assertTrue(data["has_filter"])

    def test_invalid_date_graceful(self):
        data = _compute_cnv_comparison("not-a-date", "also-bad")
        self.assertFalse(data["has_filter"])


class CustomerTabSnapshotTest(SnapshotTestCase):
    """
    Step 1 — Lock per-tab data for ALL Customer Analytics tabs (all-time).
    Covers Session A (Registration Breakdown, 7 tabs) +
            Session B (Customer Analytics, 3 tabs).
    These snapshots are the ground-truth for Step 4 regression checks.
    """

    @classmethod
    def setUpTestData(cls):
        if CUSTOMER_FILE.exists():
            process_customer_file(_named(CUSTOMER_FILE))
        for path in SALE_FILES:
            if path.exists():
                process_sales_file(_named(path))
        _load_cnv_customers_from_csv()

    def _tab(self, tab):
        return get_customer_tab(tab)

    def test_tab_perf_all(self):
        """Time each customer tab individually via get_customer_tab() and compare."""
        log = get_run_log()
        log.section("CUSTOMER TAB PERF — per-tab via get_customer_tab()")
        timings = {}
        for tab in CUSTOMER_TABS:
            t = self.timer(f"customer_tab_{tab}")
            get_customer_tab(tab)
            elapsed = t.total()
            timings[tab] = elapsed
            t.checkpoint(f"{tab} → {elapsed:.2f}s")
            t.report()
        self.record_page_timing("CUSTOMER per-tab timings", sum(timings.values()),
                                [(f"tab:{k}", 0, v) for k, v in timings.items()])
        for tab, elapsed in timings.items():
            self.assertLess(elapsed, 30, f"Tab '{tab}' took {elapsed:.1f}s > 30s threshold")

    # ── Session A: Registration Breakdown (7 tabs) ─────────────────────────

    def test_tab_snapshot_bd_season(self):
        t = self.timer("customer_tab_bd_season")
        data = self._tab('bd_season')
        t.checkpoint(f"by_season → {len(data['by_season'])} rows  [{t.total():.2f}s]")
        t.report()
        self.assert_snapshot("customer_tab_bd_season", {"by_season": data["by_season"]})

    def test_tab_snapshot_bd_month(self):
        t = self.timer("customer_tab_bd_month")
        data = self._tab('bd_month')
        t.checkpoint(f"by_month → {len(data['by_month'])} rows  [{t.total():.2f}s]")
        t.report()
        self.assert_snapshot("customer_tab_bd_month", {"by_month": data["by_month"]})

    def test_tab_snapshot_bd_week(self):
        t = self.timer("customer_tab_bd_week")
        data = self._tab('bd_week')
        t.checkpoint(f"by_week → {len(data['by_week'])} rows  [{t.total():.2f}s]")
        t.report()
        self.assert_snapshot("customer_tab_bd_week", {"by_week": data["by_week"]})

    def test_tab_snapshot_bd_shop(self):
        t = self.timer("customer_tab_bd_shop")
        data = self._tab('bd_shop')
        t.checkpoint(f"by_shop → {len(data['by_shop'])} rows  [{t.total():.2f}s]")
        t.report()
        self.assert_snapshot("customer_tab_bd_shop", {
            "by_shop": data["by_shop"],
            "shop_detail": data["shop_detail"],
        })

    def test_tab_snapshot_bd_season_allshops(self):
        t = self.timer("customer_tab_bd_season_allshops")
        data = self._tab('bd_season_allshops')
        t.checkpoint(f"season_shop → {len(data['season_shop'])} rows  [{t.total():.2f}s]")
        t.report()
        self.assert_snapshot("customer_tab_bd_season_allshops", {
            "season_shop": data["season_shop"],
            "shop_season": data["shop_season"],
        })

    def test_tab_snapshot_bd_month_allshops(self):
        t = self.timer("customer_tab_bd_month_allshops")
        data = self._tab('bd_month_allshops')
        t.checkpoint(f"month_shop → {len(data['month_shop'])} rows  [{t.total():.2f}s]")
        t.report()
        self.assert_snapshot("customer_tab_bd_month_allshops", {
            "month_shop": data["month_shop"],
            "shop_month": data["shop_month"],
        })

    def test_tab_snapshot_bd_week_allshops(self):
        t = self.timer("customer_tab_bd_week_allshops")
        data = self._tab('bd_week_allshops')
        t.checkpoint(f"week_shop → {len(data['week_shop'])} rows  [{t.total():.2f}s]")
        t.report()
        self.assert_snapshot("customer_tab_bd_week_allshops", {
            "week_shop": data["week_shop"],
            "shop_week": data["shop_week"],
        })

    # ── Session B: Customer Analytics (3 tabs) ─────────────────────────────

    def test_tab_snapshot_ca_points(self):
        t = self.timer("customer_tab_ca_points")
        data = self._tab('ca_points')
        t.checkpoint(f"cnv_used_points → {data['cnv_used_points_count']} rows  [{t.total():.2f}s]")
        t.report()
        self.assert_snapshot("customer_tab_ca_points", {
            "cnv_used_points_count": data["cnv_used_points_count"],
            "cnv_used_points_list": data["cnv_used_points_list"],
        })

    def test_tab_snapshot_ca_zalo(self):
        t = self.timer("customer_tab_ca_zalo")
        data = self._tab('ca_zalo')
        t.checkpoint(
            f"zalo_app={data['zalo_app_all_count']} oa={data['zalo_oa_all_count']}  [{t.total():.2f}s]"
        )
        t.report()
        self.assert_snapshot("customer_tab_ca_zalo", {
            "zalo_app_all_count": data["zalo_app_all_count"],
            "zalo_oa_all_count": data["zalo_oa_all_count"],
            "zalo_app_all_pct": data["zalo_app_all_pct"],
            "zalo_oa_all_pct": data["zalo_oa_all_pct"],
            "zalo_mini_app_list": data["zalo_mini_app_list"],
            "zalo_oa_list": data["zalo_oa_list"],
        })

    def test_tab_snapshot_ca_pos_cnv(self):
        t = self.timer("customer_tab_ca_pos_cnv")
        data = self._tab('ca_pos_cnv')
        t.checkpoint(
            f"mismatch={data['points_mismatch_count']} "
            f"pos_only={data['pos_only_all_count']} "
            f"cnv_only={data['cnv_only_all_count']}  [{t.total():.2f}s]"
        )
        t.report()
        self.assert_snapshot("customer_tab_ca_pos_cnv", {
            "points_mismatch_count": data["points_mismatch_count"],
            "total_points_mismatch_count": data["total_points_mismatch_count"],
            "pos_only_all_count": data["pos_only_all_count"],
            "cnv_only_all_count": data["cnv_only_all_count"],
            "points_mismatch": data["points_mismatch"],
            "total_points_mismatch": data["total_points_mismatch"],
            "pos_only_all": data["pos_only_all"],
            "cnv_only_all": data["cnv_only_all"],
        })


class CustomerTimingBreakdownTest(SnapshotTestCase):
    """Isolated per-query timing — run after main import to identify bottlenecks."""

    @classmethod
    def setUpTestData(cls):
        if CUSTOMER_FILE.exists():
            process_customer_file(_named(CUSTOMER_FILE))
        for path in SALE_FILES:
            if path.exists():
                process_sales_file(_named(path))
        _load_cnv_customers_from_csv()

    def test_per_query_timing(self):
        """Run each DB query independently to pinpoint the slow ones."""
        log = get_run_log()
        log.section("CUSTOMER PAGE — isolated per-query timing")
        t = self.timer("customer_per_query")

        pos_all = Customer.objects.filter(vip_id__isnull=False, phone__isnull=False).exclude(vip_id=0).exclude(phone="")
        cnv_all = CNVCustomer.objects.filter(phone__isnull=False).exclude(phone="")
        _cnv_pqs = cnv_all.values("phone")
        _pos_pqs = pos_all.values("phone")

        n = pos_all.count();             t.checkpoint(f"pos_all.count() → {n}")
        n = CNVCustomer.objects.count(); t.checkpoint(f"CNVCustomer.count() → {n}")

        ps = set(pos_all.values_list("phone", flat=True))
        t.checkpoint(f"pos phones set → {len(ps)}")

        cs = set(cnv_all.values_list("phone", flat=True))
        t.checkpoint(f"cnv phones set → {len(cs)}")

        n = len(pos_all.exclude(phone__in=_cnv_pqs).values("phone", "vip_id"))
        t.checkpoint(f"pos_only anti-join count → {n}")

        n = len(cnv_all.exclude(phone__in=_pos_pqs).values("phone", "cnv_id"))
        t.checkpoint(f"cnv_only anti-join count → {n}")

        n = len(pos_all.filter(phone__in=_cnv_pqs).values("phone","points","used_points"))
        t.checkpoint(f"pos_map (shared phones) → {n}")

        n = len(cnv_all.filter(phone__in=_pos_pqs).values("phone","points","total_points"))
        t.checkpoint(f"cnv_map (shared phones) → {n}")

        n = CNVCustomer.objects.filter(zalo_app_id__isnull=False).exclude(zalo_app_id="").count()
        t.checkpoint(f"zalo_app count → {n}")
        n = CNVCustomer.objects.filter(zalo_oa_id__isnull=False).exclude(zalo_oa_id="").count()
        t.checkpoint(f"zalo_oa count → {n}")

        total = t.total()
        t.report()
        self.record_page_timing("CUSTOMER per-query isolated", total, t._checkpoints)
