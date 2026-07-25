# Perf plan P1-08/P1-09/P1-12: Postgres-only DDL.
#
# P1-08/P1-09 (Upper() + text_pattern_ops expression indexes): confirmed by
# direct EXPLAIN ANALYZE against a real PostgreSQL 16 instance that a plain
# expression index on UPPER(col) is NOT enough to serve `col__istartswith`
# (compiled to `UPPER(col::text) LIKE UPPER(x)||'%'`) — Postgres's default
# (non-C) collation means a btree cannot serve a LIKE 'prefix%' query at all
# unless the index uses the text_pattern_ops operator class.
#
# P1-12 (GIN trigram): pg_trgm/GIN are Postgres-only outright. QA deep-dive
# (2026-07-19) found the index MUST be built on Upper(col), not the raw
# column: Django always compiles `icontains` on Postgres to
# `UPPER(col::text) LIKE UPPER(pattern)` — a GIN trigram index on the raw
# column can never be used for that expression (confirmed: Seq Scan even
# with enable_seqscan=off). Fixed by wrapping in the same OpClass(Upper(...))
# pattern as P1-08/P1-09, with opclass 'gin_trgm_ops' instead of
# 'text_pattern_ops'. Verified after the fix: the real Django ORM
# `icontains` query naturally (no forcing) uses a Bitmap Index Scan.
#
# Both use SeparateDatabaseAndState so migration STATE is applied
# identically on every backend (keeping `makemigrations --check` clean
# everywhere) while the real DDL only runs where the database supports it.
import django.contrib.postgres.indexes
import django.db.models.functions.text
from django.contrib.postgres.operations import TrigramExtension
from django.db import migrations, models, connection

_is_pg = connection.vendor == "postgresql"

_coupon_upper_idx = models.Index(
    django.contrib.postgres.indexes.OpClass(
        django.db.models.functions.text.Upper("coupon_id"), name="text_pattern_ops"
    ),
    name="coupon_upper_couponid_idx",
)
_invsnap_upper_idx = models.Index(
    django.contrib.postgres.indexes.OpClass(
        django.db.models.functions.text.Upper("product_code"), name="text_pattern_ops"
    ),
    name="invsnap_upper_prodcode_idx",
)
_sales_trgm = django.contrib.postgres.indexes.GinIndex(
    django.contrib.postgres.indexes.OpClass(
        django.db.models.functions.text.Upper("shop_name"), name="gin_trgm_ops"
    ),
    name="sales_shop_trgm_gin",
)
_saledet_trgm = django.contrib.postgres.indexes.GinIndex(
    django.contrib.postgres.indexes.OpClass(
        django.db.models.functions.text.Upper("shop_name"), name="gin_trgm_ops"
    ),
    name="saledet_shop_trgm_gin",
)
_coupon_trgm = django.contrib.postgres.indexes.GinIndex(
    django.contrib.postgres.indexes.OpClass(
        django.db.models.functions.text.Upper("using_shop"), name="gin_trgm_ops"
    ),
    name="coupon_usingshop_trgm_gin",
)
_invsnap_trgm = django.contrib.postgres.indexes.GinIndex(
    django.contrib.postgres.indexes.OpClass(
        django.db.models.functions.text.Upper("shop_name"), name="gin_trgm_ops"
    ),
    name="invsnap_shop_trgm_gin",
)


class Migration(migrations.Migration):

    dependencies = [
        ("App", "0020_coupon_and_inventory_indexes"),
    ]

    operations = [
        migrations.SeparateDatabaseAndState(
            database_operations=[TrigramExtension()] if _is_pg else [],
            state_operations=[],
        ),
        migrations.SeparateDatabaseAndState(
            database_operations=(
                [migrations.AddIndex("coupon", _coupon_upper_idx)] if _is_pg else []
            ),
            state_operations=[migrations.AddIndex("coupon", _coupon_upper_idx)],
        ),
        migrations.SeparateDatabaseAndState(
            database_operations=(
                [migrations.AddIndex("inventorysnapshot", _invsnap_upper_idx)] if _is_pg else []
            ),
            state_operations=[migrations.AddIndex("inventorysnapshot", _invsnap_upper_idx)],
        ),
        migrations.SeparateDatabaseAndState(
            database_operations=(
                [migrations.AddIndex("salestransaction", _sales_trgm)] if _is_pg else []
            ),
            state_operations=[migrations.AddIndex("salestransaction", _sales_trgm)],
        ),
        migrations.SeparateDatabaseAndState(
            database_operations=(
                [migrations.AddIndex("saledetail", _saledet_trgm)] if _is_pg else []
            ),
            state_operations=[migrations.AddIndex("saledetail", _saledet_trgm)],
        ),
        migrations.SeparateDatabaseAndState(
            database_operations=(
                [migrations.AddIndex("coupon", _coupon_trgm)] if _is_pg else []
            ),
            state_operations=[migrations.AddIndex("coupon", _coupon_trgm)],
        ),
        migrations.SeparateDatabaseAndState(
            database_operations=(
                [migrations.AddIndex("inventorysnapshot", _invsnap_trgm)] if _is_pg else []
            ),
            state_operations=[migrations.AddIndex("inventorysnapshot", _invsnap_trgm)],
        ),
    ]
