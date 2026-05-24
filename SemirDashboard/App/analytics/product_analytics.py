"""App/analytics/product_analytics.py — Product-level sales analytics from SaleDetail."""
import logging

from django.db.models import Sum, Count
from django.core.cache import cache

from django.db.models import Q

from App.models import SaleDetail

logger = logging.getLogger(__name__)
_TTL = 300
_VERSION_KEY = 'prod_tab_version'

PRODUCT_TABS = ['season', 'month', 'week', 'brand', 'category', 'shop', 'product']


def bump_product_version():
    """Invalidate all product tab caches by incrementing the version counter."""
    try:
        cache.incr(_VERSION_KEY)
    except ValueError:
        cache.set(_VERSION_KEY, 1, None)


def _base_qs(date_from=None, date_to=None, shop_group=None):
    qs = SaleDetail.objects.all()
    if date_from:
        qs = qs.filter(sales_date__gte=date_from)
    if date_to:
        qs = qs.filter(sales_date__lte=date_to)
    if shop_group:
        sg = shop_group.lower()
        if 'bala' in sg:
            qs = qs.filter(Q(shop_name__icontains='Bala') | Q(shop_name__icontains='巴拉'))
        elif 'semir' in sg:
            qs = qs.filter(Q(shop_name__icontains='Semir') | Q(shop_name__icontains='森马'))
        elif 'others' in sg:
            qs = qs.exclude(
                Q(shop_name__icontains='Bala') | Q(shop_name__icontains='巴拉') |
                Q(shop_name__icontains='Semir') | Q(shop_name__icontains='森马')
            )
    return qs


def _cache_key(tab, date_from, date_to, shop_group):
    v = cache.get(_VERSION_KEY, 0)
    return f"prod_tab_v{v}_{tab}_{date_from}_{date_to}_{shop_group}"


def _disc_pct(tag, settlement):
    """Effective discount %: how much was discounted from tag price."""
    try:
        t = float(tag or 0)
        if t <= 0:
            return None
        return round((1 - float(settlement or 0) / t) * 100, 1)
    except (TypeError, ZeroDivisionError):
        return None


def _overview(qs):
    from django.db.models import Min, Max
    agg = qs.aggregate(
        total_lines=Count('id'),
        total_qty=Sum('quantity'),
        total_amount=Sum('sales_amount'),
        total_settlement=Sum('settlement_amount'),
        total_tag_amount=Sum('tag_amount'),
        min_date=Min('sales_date'),
        max_date=Max('sales_date'),
    )
    agg['date_range'] = {'from': agg.pop('min_date'), 'to': agg.pop('max_date')}
    agg['disc_pct'] = _disc_pct(agg.get('total_tag_amount'), agg.get('total_settlement'))
    return agg


def _by_season(qs):
    rows = list(
        qs.values('year', 'season')
        .annotate(
            qty=Sum('quantity'),
            amount=Sum('sales_amount'),
            settlement=Sum('settlement_amount'),
            tag_amount=Sum('tag_amount'),
            lines=Count('id'),
        )
        .order_by('-year', 'season')
    )
    for r in rows:
        r['disc_pct'] = _disc_pct(r.get('tag_amount'), r.get('settlement'))
    return rows


def _by_month(qs):
    from django.db.models.functions import TruncMonth
    rows = list(
        qs.annotate(month=TruncMonth('sales_date'))
        .values('month')
        .annotate(
            qty=Sum('quantity'),
            amount=Sum('sales_amount'),
            settlement=Sum('settlement_amount'),
            tag_amount=Sum('tag_amount'),
            lines=Count('id'),
        )
        .order_by('-month')
    )
    for r in rows:
        try:
            m = r['month']
            r['label'] = m.strftime('%Y-%m') if m else '—'
        except Exception:
            r['label'] = '—'
        r['disc_pct'] = _disc_pct(r.get('tag_amount'), r.get('settlement'))
    return rows


def _by_week(qs):
    from django.db.models.functions import TruncWeek
    rows = list(
        qs.annotate(week=TruncWeek('sales_date'))
        .values('week')
        .annotate(
            qty=Sum('quantity'),
            amount=Sum('sales_amount'),
            settlement=Sum('settlement_amount'),
            tag_amount=Sum('tag_amount'),
            lines=Count('id'),
        )
        .order_by('-week')
    )
    for r in rows:
        try:
            w = r['week']
            r['label'] = f"W{w.strftime('%V')} {w.strftime('%Y')}" if w else '—'
        except Exception:
            r['label'] = '—'
        r['disc_pct'] = _disc_pct(r.get('tag_amount'), r.get('settlement'))
    return rows


def _by_category(qs):
    rows = list(
        qs.values('category_l1', 'category_l2')
        .annotate(
            qty=Sum('quantity'),
            amount=Sum('sales_amount'),
            settlement=Sum('settlement_amount'),
            tag_amount=Sum('tag_amount'),
            lines=Count('id'),
        )
        .order_by('category_l1', '-qty')
    )
    for r in rows:
        r['disc_pct'] = _disc_pct(r.get('tag_amount'), r.get('settlement'))
    return rows


def _by_brand(qs):
    rows = list(
        qs.values('brand')
        .annotate(
            qty=Sum('quantity'),
            amount=Sum('sales_amount'),
            settlement=Sum('settlement_amount'),
            tag_amount=Sum('tag_amount'),
            lines=Count('id'),
        )
        .order_by('-qty')
    )
    for r in rows:
        r['disc_pct'] = _disc_pct(r.get('tag_amount'), r.get('settlement'))
    return rows


def _by_product(qs, limit=50):
    """Top `limit` products ranked by qty sold."""
    rows = list(
        qs.values('product_code', 'product_name', 'brand', 'category_l1', 'year', 'season')
        .annotate(
            qty=Sum('quantity'),
            amount=Sum('sales_amount'),
            settlement=Sum('settlement_amount'),
            tag_amount=Sum('tag_amount'),
            lines=Count('id'),
        )
        .order_by('-qty')[:limit]
    )
    for r in rows:
        r['disc_pct'] = _disc_pct(r.get('tag_amount'), r.get('settlement'))
    return rows


def _by_shop(qs):
    rows = list(
        qs.values('shop_name')
        .annotate(
            qty=Sum('quantity'),
            amount=Sum('sales_amount'),
            settlement=Sum('settlement_amount'),
            tag_amount=Sum('tag_amount'),
            lines=Count('id'),
        )
        .order_by('-qty')
    )
    for r in rows:
        r['disc_pct'] = _disc_pct(r.get('tag_amount'), r.get('settlement'))
    return rows


def get_product_tab(tab: str, date_from=None, date_to=None, shop_group=None) -> dict:
    """Return product analytics data for one tab. Cached 5 min."""
    key = _cache_key(tab, date_from, date_to, shop_group)
    cached = cache.get(key)
    if cached:
        return cached

    qs = _base_qs(date_from, date_to, shop_group)
    overview = _overview(qs)
    if not overview.get('total_lines'):
        return {}

    tab_data = {}
    if tab == 'season':
        tab_data['by_season'] = _by_season(qs)
    elif tab == 'month':
        tab_data['by_month'] = _by_month(qs)
    elif tab == 'week':
        tab_data['by_week'] = _by_week(qs)
    elif tab == 'brand':
        tab_data['by_brand'] = _by_brand(qs)
    elif tab == 'category':
        tab_data['by_category'] = _by_category(qs)
    elif tab == 'shop':
        tab_data['by_shop'] = _by_shop(qs)
    elif tab == 'product':
        tab_data['by_product'] = _by_product(qs)

    result = {'overview': overview, **tab_data}
    cache.set(key, result, _TTL)
    logger.info("product_tab %s loaded: lines=%d", tab, overview.get('total_lines', 0),
                extra={"step": "product_analytics"})
    return result
