"""App/analytics/inventory_functions.py — Inventory analytics for Shop Detail and global overview."""
import logging
from collections import defaultdict
from datetime import date

from django.db.models import Sum, Count, Q
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


def _shop_group_filter(qs, shop_group: str):
    if not shop_group:
        return qs
    sg = shop_group.lower()
    if 'bala' in sg:
        return qs.filter(Q(shop_name__icontains='Bala') | Q(shop_name__icontains='巴拉'))
    elif 'semir' in sg:
        return qs.filter(Q(shop_name__icontains='Semir') | Q(shop_name__icontains='森马'))
    elif 'others' in sg:
        return qs.exclude(
            Q(shop_name__icontains='Bala') | Q(shop_name__icontains='巴拉') |
            Q(shop_name__icontains='Semir') | Q(shop_name__icontains='森马')
        )
    return qs


def _overview_cache_key(shop_group: str, year=None, season: str = None) -> str:
    import hashlib
    v = cache.get(_VERSION_KEY, 0)
    key_str = f"{shop_group or ''}|{year or ''}|{season or ''}"
    slug = hashlib.md5(key_str.encode()).hexdigest()[:8]
    return f"inv_overview_v{v}_{slug}"


def get_inventory_overview(shop_group: str = None, year: int = None, season: str = None) -> dict:
    """
    Aggregate InventorySnapshot across ALL shops (optionally filtered by shop_group).
    Returns two sections:
      - 'for_sale': items where tag_amount > 0 (commercial inventory)
      - 'gifts':    items where tag_amount = 0 (free/promo/packaging items)
    Each section contains totals + by_shop + by_brand + by_season breakdowns.
    Dead-stock threshold: year <= current_year - 1.
    """
    ck = _overview_cache_key(shop_group or '', year, season)
    cached = cache.get(ck)
    if cached is not None:
        return cached

    base_qs = _shop_group_filter(InventorySnapshot.objects.all(), shop_group or '')
    if year:
        base_qs = base_qs.filter(year=year)
    if season:
        base_qs = base_qs.filter(season=season)

    sale_qs = base_qs.filter(tag_amount__gt=0)
    gift_qs = base_qs.filter(tag_amount=0)

    dead_year = date.today().year - 1

    def _totals(qs):
        return qs.aggregate(
            sku_lines=Count('id'),
            on_hand_qty=Sum('inventory_qty'),
            in_transit_qty=Sum('in_transit_qty'),
            total_qty=Sum('total_qty'),
            inv_value=Sum('tag_amount'),
        )

    def _by_shop(qs):
        return list(
            qs.values('shop_name')
            .annotate(
                qty=Sum('inventory_qty'),
                in_transit=Sum('in_transit_qty'),
                total=Sum('total_qty'),
                value=Sum('tag_amount'),
                lines=Count('id'),
            )
            .order_by('-qty')
        )

    def _by_brand(qs):
        return list(
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

    def _by_season(qs):
        return list(
            qs.values('year', 'season')
            .annotate(
                qty=Sum('inventory_qty'),
                total=Sum('total_qty'),
                value=Sum('tag_amount'),
                lines=Count('id'),
            )
            .order_by('-year', 'season')
        )

    def _dead(qs):
        dq = qs.filter(year__lte=dead_year, inventory_qty__gt=0)
        agg = dq.aggregate(
            sku_lines=Count('id'),
            dead_qty=Sum('inventory_qty'),
            dead_value=Sum('tag_amount'),
        )
        top = list(
            dq.values('shop_name', 'product_code', 'product_name', 'product_name_vn',
                      'color', 'size', 'brand', 'category_l1', 'category_l3',
                      'gender', 'tag_price', 'year', 'season')
            .annotate(qty=Sum('inventory_qty'), value=Sum('tag_amount'))
            .order_by('-qty')[:50]
        )
        return {'summary': agg, 'top': top}

    def _by_shop_full(qs, by_shop_rows):
        """Per-shop brand + season + dead-stock-SKU breakdown in 4 DB queries (not N)."""
        dead_qs = qs.filter(year__lte=dead_year, inventory_qty__gt=0)

        shop_brand_rows = list(
            qs.values('shop_name', 'brand')
            .annotate(qty=Sum('inventory_qty'), in_transit=Sum('in_transit_qty'),
                      total=Sum('total_qty'), value=Sum('tag_amount'), lines=Count('id'))
            .order_by('shop_name', '-qty')
        )
        shop_season_rows = list(
            qs.values('shop_name', 'year', 'season')
            .annotate(qty=Sum('inventory_qty'), total=Sum('total_qty'),
                      value=Sum('tag_amount'), lines=Count('id'))
            .order_by('shop_name', '-year', 'season')
        )
        dead_shop_rows = list(
            dead_qs.values('shop_name')
            .annotate(dead_qty=Sum('inventory_qty'), dead_value=Sum('tag_amount'),
                      dead_lines=Count('id'))
        )
        # Dead stock SKUs per shop — single query, top 50 per shop by qty
        dead_sku_rows = list(
            dead_qs.values('shop_name', 'product_code', 'product_name', 'product_name_vn',
                           'color', 'size', 'brand', 'category_l1', 'category_l3',
                           'gender', 'tag_price', 'year', 'season')
            .annotate(qty=Sum('inventory_qty'), value=Sum('tag_amount'))
            .order_by('shop_name', '-qty')
        )
        dead_skus_map: dict = defaultdict(list)
        for r in dead_sku_rows:
            sn = r['shop_name']
            if len(dead_skus_map[sn]) < 50:
                dead_skus_map[sn].append(r)

        brand_map   = defaultdict(list)
        for r in shop_brand_rows:
            brand_map[r['shop_name']].append(r)

        season_map  = defaultdict(list)
        for r in shop_season_rows:
            season_map[r['shop_name']].append(r)

        dead_map = {r['shop_name']: r for r in dead_shop_rows}

        result = []
        for s in by_shop_rows:
            sn   = s['shop_name']
            dead = dead_map.get(sn, {})
            result.append({
                **s,
                'brands':     brand_map[sn],
                'seasons':    season_map[sn],
                'dead_qty':   dead.get('dead_qty') or 0,
                'dead_value': dead.get('dead_value') or 0,
                'dead_lines': dead.get('dead_lines') or 0,
                'dead_skus':  dead_skus_map[sn],
            })
        return result

    sale_totals = _totals(sale_qs)
    if not (sale_totals.get('sku_lines') or _totals(gift_qs).get('sku_lines')):
        return {}

    sale_by_shop = _by_shop(sale_qs)

    result = {
        'for_sale': {
            'totals':      sale_totals,
            'by_shop':     sale_by_shop,
            'by_shop_full': _by_shop_full(sale_qs, sale_by_shop),
            'by_brand':    _by_brand(sale_qs),
            'by_season':   _by_season(sale_qs),
            'dead':        _dead(sale_qs),
        },
        'gifts': {
            'totals':    _totals(gift_qs),
            'by_shop':   _by_shop(gift_qs),
            'by_brand':  _by_brand(gift_qs),
            'by_season': _by_season(gift_qs),
        },
        'dead_year_threshold': dead_year,
    }
    cache.set(ck, result, _TTL)
    logger.info(
        "inventory overview loaded: shop_group=%s year=%s season=%s sale_lines=%d gift_lines=%d",
        shop_group, year, season,
        sale_totals.get('sku_lines', 0), _totals(gift_qs).get('sku_lines', 0),
        extra={"step": "inventory_overview"},
    )
    return result


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
