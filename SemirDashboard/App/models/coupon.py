from django.db import models
from django.db.models.functions import Upper
from django.contrib.postgres.indexes import GinIndex, OpClass


class Coupon(models.Model):
    department = models.CharField(max_length=1000, blank=True, null=True)
    creator = models.CharField(max_length=1000, blank=True, null=True)
    document_number = models.CharField(max_length=1000, blank=True, null=True)
    # U-04: unique — coupon_id is the upsert key; without a DB constraint,
    # duplicate rows in one import batch would both insert (ignore_conflicts
    # has nothing to conflict against). Audit prod for dups BEFORE migrating.
    coupon_id = models.CharField(max_length=1000, unique=True)
    face_value = models.DecimalField(
        max_digits=12, decimal_places=2, blank=True, null=True
    )
    used = models.IntegerField(default=0)  # 0=unused, 1=used
    begin_date = models.DateField(blank=True, null=True)
    end_date = models.DateField(blank=True, null=True)
    using_shop = models.CharField(max_length=1000, blank=True, null=True, db_index=True)
    using_date = models.DateField(blank=True, null=True)
    push = models.CharField(max_length=1000, blank=True, null=True)
    member_id = models.CharField(max_length=1000, blank=True, null=True)
    member_name = models.CharField(max_length=1000, blank=True, null=True)
    member_phone = models.CharField(max_length=1000, blank=True, null=True)
    docket_number = models.CharField(
        max_length=1000, blank=True, null=True, db_index=True
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        indexes = [
            # P1-11: models.Index(fields=["coupon_id"]) removed — coupon_id
            # already has unique=True (migration 0019), which creates its own
            # unique index; the explicit one here was a duplicate since day 1
            # (migration 0002 created both on the same column).
            models.Index(fields=["docket_number"]),
            models.Index(fields=["using_date"]),
            models.Index(fields=["used"]),
            # P1-08: coupon_id__istartswith is compiled by Postgres to
            # UPPER(coupon_id::text) LIKE UPPER(x)||'%'. A plain expression
            # index on UPPER(coupon_id) is NOT enough — Postgres's default
            # (non-C) collation means a btree can't serve LIKE 'prefix%' at
            # all unless the index uses the text_pattern_ops operator class
            # (confirmed by EXPLAIN ANALYZE: without text_pattern_ops the
            # planner ignored the index entirely even with enable_seqscan=off;
            # with it, the same query dropped from ~14ms Seq Scan to a
            # naturally-chosen 0.18ms Bitmap Index Scan). Postgres-only DDL —
            # see migration 0021's SeparateDatabaseAndState wrapping.
            models.Index(
                OpClass(Upper("coupon_id"), name="text_pattern_ops"),
                name="coupon_upper_couponid_idx",
            ),
            # P1-10: Shop Detail coupon tab filters using_shop + using_date
            # together on every AJAX partial load — replaces 2 separate scans
            # with one composite index covering the hot path.
            models.Index(fields=["using_shop", "using_date"], name="coupon_usingshop_usingdate_idx"),
            # P1-12: using_shop__icontains (shop-group filter) — Postgres only.
            # QA deep-dive (2026-07-19) found the index MUST be on Upper(using_shop),
            # not the raw column: Django always compiles icontains on Postgres to
            # UPPER(col::text) LIKE UPPER(pattern) (see lookup_cast() in
            # django/db/backends/postgresql/operations.py) — a GIN trigram index on
            # the raw column can NEVER be used for that expression (confirmed via
            # EXPLAIN ANALYZE: Seq Scan even with enable_seqscan=off). Same class of
            # bug as P1-08/P1-09 (text_pattern_ops), just missed here originally.
            GinIndex(OpClass(Upper("using_shop"), name="gin_trgm_ops"), name="coupon_usingshop_trgm_gin"),
        ]

    def __str__(self):
        return f"{self.coupon_id} ({'Used' if self.used else 'Unused'})"


class CouponCampaign(models.Model):
    """Named coupon campaign grouping coupons by ID prefix."""

    name = models.CharField(max_length=200, unique=True)
    prefix = models.TextField()          # comma-separated prefixes, e.g. "ABC,DEF,XYZ"
    detail = models.TextField(blank=True, null=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["name"]

    def __str__(self):
        return f"{self.name} ({self.prefix})"


class ProductCampaign(models.Model):
    """Named product campaign grouping products by product code prefix."""

    name = models.CharField(max_length=200, unique=True)
    prefix = models.TextField()          # comma-separated prefixes, e.g. "2024A,2024B"
    detail = models.TextField(blank=True, null=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["name"]

    def __str__(self):
        return f"{self.name} ({self.prefix})"
