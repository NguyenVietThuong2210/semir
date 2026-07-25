from django.db import models
from django.db.models.functions import Upper
from django.contrib.postgres.indexes import GinIndex, OpClass


class InventorySnapshot(models.Model):
    """
    Current inventory state per (shop, product variant).
    Uploading a new file overwrites existing rows for the same shop+product_code.
    No date-based history — only the latest state is stored.
    """
    uploaded_at      = models.DateTimeField(auto_now=True)
    shop_id          = models.CharField(max_length=100, db_index=True)
    shop_name        = models.CharField(max_length=200, db_index=True)
    brand            = models.CharField(max_length=100, db_index=True)
    product_code     = models.CharField(max_length=200, db_index=True)
    product_name     = models.CharField(max_length=500, blank=True)
    product_name_vn  = models.CharField(max_length=500, blank=True)
    barcode          = models.CharField(max_length=100, db_index=True)
    sku              = models.CharField(max_length=100, db_index=True)
    color            = models.CharField(max_length=100, blank=True)
    size             = models.CharField(max_length=50, blank=True)
    year             = models.IntegerField(null=True, blank=True, db_index=True)
    season           = models.CharField(max_length=10, blank=True, db_index=True)
    gender           = models.CharField(max_length=50, blank=True)
    category_l1      = models.CharField(max_length=100, blank=True)
    category_l2      = models.CharField(max_length=100, blank=True)
    category_l3      = models.CharField(max_length=100, blank=True)
    tag_price        = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    inventory_qty    = models.IntegerField(default=0)
    in_transit_qty   = models.IntegerField(default=0)
    total_qty        = models.IntegerField(default=0)
    tag_amount       = models.DecimalField(max_digits=15, decimal_places=2, default=0)
    total_tag_amount = models.DecimalField(max_digits=15, decimal_places=2, default=0)
    currency         = models.CharField(max_length=10, default='VND')

    class Meta:
        unique_together = ('shop_id', 'product_code')
        indexes = [
            models.Index(fields=['shop_name', 'brand']),
            models.Index(fields=['year', 'season']),
            models.Index(fields=['sku', 'shop_id']),
            # P1-09: product_code__istartswith needs text_pattern_ops, same
            # reason as P1-08 in App/models/coupon.py — Postgres-only DDL.
            models.Index(
                OpClass(Upper('product_code'), name='text_pattern_ops'),
                name='invsnap_upper_prodcode_idx',
            ),
            # P1-12: shop_name__icontains (shop-group filter) — Postgres only.
            # QA deep-dive (2026-07-19): must index Upper(shop_name), not the raw
            # column — see the detailed comment in App/models/coupon.py for why.
            GinIndex(OpClass(Upper('shop_name'), name='gin_trgm_ops'), name='invsnap_shop_trgm_gin'),
        ]

    def __str__(self):
        return f"{self.shop_name} | {self.product_code} | qty={self.inventory_qty}"
