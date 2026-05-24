"""App/analytics/inventory_functions.py — Inventory analytics for Shop Detail."""
import logging
from datetime import date

from django.db.models import Sum, Count
from django.core.cache import cache

from App.models import InventorySnapshot

logger = logging.getLogger(__name__)
_TTL = 300
_VERSION_KEY = 'inv_data_version'


def bump_inventory_version():
    """Invalidate all per-shop inventory caches by incrementing the version counter."""
    try:
        cache.incr(_VERSION_KEY)
    except ValueError:
        cache.set(_VERSION_KEY, 1, None)


def _cache_key(shop_name: str) -> str:
    import hashlib
    v = cache.get(_VERSION_KEY, 0)
    slug = hashlib.md5(shop_name.encode('utf-8')).hexdigest()[:12]
    return f"inv_shop_v{v}_{slug}"


def get_shop_inventory_data(shop_name: str) -> dict:
    """
    Return inventory KPIs + breakdowns for one shop from InventorySnapshot.
    Cached 5 min per shop. Cache is busted when a new inventory file is uploaded.
    """
    ck = _cache_key(shop_name)
    cached = cache.get(ck)
    if cached:
        return cached

    qs = InventorySnapshot.objects.filter(shop_name=shop_name)

    # Alias names must NOT match model field names used as Sum() args in the same call.
    # 'on_hand_qty' = inventory_qty (on-hand stock only)
    # 'total_qty'   = total_qty field (on-hand + in-transit)
    totals = qs.aggregate(
        sku_lines=Count('id'),
        on_hand_qty=Sum('inventory_qty'),
        in_transit_qty=Sum('in_transit_qty'),
        total_qty=Sum('total_qty'),
        inv_value=Sum('tag_amount'),
        total_tag_amt=Sum('total_tag_amount'),
    )
    if not totals.get('sku_lines'):
        return {}

    # ── Dead stock: year <= current_year - 1 and inventory_qty > 0 ────────────
    dead_year = date.today().year - 1
    dead_qs = qs.filter(year__lte=dead_year, inventory_qty__gt=0)
    dead = dead_qs.aggregate(
        sku_lines=Count('id'),
        dead_qty=Sum('inventory_qty'),
        dead_value=Sum('tag_amount'),
    )

    # ── By Brand ──────────────────────────────────────────────────────────────
    by_brand = list(
        qs.values('brand')
        .annotate(
            qty=Sum('inventory_qty'),
            in_transit=Sum('in_transit_qty'),
            total=Sum('total_qty'),
            value=Sum('tag_amount'),
            lines=Count('id'),
        )
        .order_by('-qty')
    )

    # ── By Season ─────────────────────────────────────────────────────────────
    by_season = list(
        qs.values('year', 'season')
        .annotate(
            qty=Sum('inventory_qty'),
            total=Sum('total_qty'),
            value=Sum('tag_amount'),
            lines=Count('id'),
        )
        .order_by('-year', 'season')
    )

    # ── Top 20 SKUs by qty ────────────────────────────────────────────────────
    top_skus = list(
        qs.filter(inventory_qty__gt=0)
        .values('product_code', 'product_name', 'color', 'size', 'brand', 'tag_price', 'year', 'season')
        .annotate(qty=Sum('inventory_qty'), value=Sum('tag_amount'))
        .order_by('-qty')[:20]
    )

    # ── Dead stock detail (top 20) ────────────────────────────────────────────
    dead_skus = list(
        dead_qs.values('product_code', 'product_name', 'color', 'size', 'brand', 'tag_price', 'year', 'season')
        .annotate(qty=Sum('inventory_qty'), value=Sum('tag_amount'))
        .order_by('-qty')[:20]
    )

    result = {
        'totals': totals,
        'dead': dead,
        'dead_year_threshold': dead_year,
        'by_brand': by_brand,
        'by_season': by_season,
        'top_skus': top_skus,
        'dead_skus': dead_skus,
    }
    cache.set(ck, result, _TTL)
    logger.info("inventory data loaded: shop=%s lines=%d", shop_name, totals.get('sku_lines', 0),
                extra={"step": "inventory_functions"})
    return result
