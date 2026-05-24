"""App/analytics/product_analytics.py — Product-level sales analytics from SaleDetail."""
import logging
from collections import OrderedDict

from django.db.models import Sum, Count, Q
from django.db.models.functions import TruncMonth, TruncWeek, TruncYear
from django.core.cache import cache

from App.models import SaleDetail

logger = logging.getLogger(__name__)
_TTL = 300
_VERSION_KEY = 'prod_tab_version'

# Tabs served by product_tab AJAX endpoint
PRODUCT_TABS = ['vip_grade', 'year', 'month', 'week', 'product_season', 'brand', 'category', 'shop', 'product']

GRADE_ORDER = {'No Grade': 0, 'Member': 1, 'Silver': 2, 'Gold': 3, 'Diamond': 4}


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


# ── Helpers ───────────────────────────────────────────────────────────────────

def _build_cat_groups(cat_rows):
    """Group a list of {category_l1, category_l2, qty, amount, settlement, tag_amount, lines}
    into [{l1, vi_rows: [{...}], subtotal}] sorted by L1 occurrence."""
    l1_map = OrderedDict()
    for r in cat_rows:
        l1 = r.get('category_l1') or '—'
        if l1 not in l1_map:
            l1_map[l1] = []
        l1_map[l1].append(r)
    result = []
    for l1, rows in l1_map.items():
        st_qty = sum(r.get('qty') or 0 for r in rows)
        st_amt = sum(float(r.get('amount') or 0) for r in rows)
        st_sett = sum(float(r.get('settlement') or 0) for r in rows)
        st_tag = sum(float(r.get('tag_amount') or 0) for r in rows)
        st_lines = sum(r.get('lines') or 0 for r in rows)
        for r in rows:
            r['disc_pct'] = _disc_pct(r.get('tag_amount'), r.get('settlement'))
        result.append({
            'l1': l1,
            'rows': rows,
            'subtotal': {
                'qty': st_qty, 'amount': st_amt, 'settlement': st_sett,
                'tag_amount': st_tag, 'lines': st_lines,
                'disc_pct': _disc_pct(st_tag, st_sett),
            },
        })
    return result


def _period_with_cat(qs, trunc_fn, label_fn, period_key):
    """
    Single DB query: group by (period, cat_l1, cat_l2).
    Returns list of period dicts, each with cat_groups for drill-down.
    """
    rows = list(
        qs.annotate(**{period_key: trunc_fn('sales_date')})
        .values(period_key, 'category_l1', 'category_l2')
        .annotate(
            qty=Sum('quantity'),
            amount=Sum('sales_amount'),
            settlement=Sum('settlement_amount'),
            tag_amount=Sum('tag_amount'),
            lines=Count('id'),
        )
        .order_by(f'-{period_key}', 'category_l1', 'category_l2')
    )

    periods = OrderedDict()
    for r in rows:
        pk = r[period_key]
        if pk not in periods:
            periods[pk] = {
                period_key: pk,
                'label': label_fn(pk),
                'qty': 0, 'amount': 0.0, 'settlement': 0.0,
                'tag_amount': 0.0, 'lines': 0,
                '_cat_rows': [],
            }
        p = periods[pk]
        p['qty'] += r.get('qty') or 0
        p['amount'] += float(r.get('amount') or 0)
        p['settlement'] += float(r.get('settlement') or 0)
        p['tag_amount'] += float(r.get('tag_amount') or 0)
        p['lines'] += r.get('lines') or 0
        p['_cat_rows'].append({
            'category_l1': r.get('category_l1') or '—',
            'category_l2': r.get('category_l2') or '—',
            'qty': r.get('qty') or 0,
            'amount': float(r.get('amount') or 0),
            'settlement': float(r.get('settlement') or 0),
            'tag_amount': float(r.get('tag_amount') or 0),
            'lines': r.get('lines') or 0,
        })

    result = []
    for p in periods.values():
        p['disc_pct'] = _disc_pct(p['tag_amount'], p['settlement'])
        p['cat_groups'] = _build_cat_groups(p.pop('_cat_rows'))
        result.append(p)
    return result


def _by_year(qs):
    return _period_with_cat(
        qs, TruncYear, lambda d: str(d.year) if d else '—', 'year_trunc'
    )


def _by_month(qs):
    return _period_with_cat(
        qs, TruncMonth,
        lambda d: d.strftime('%Y-%m') if d else '—',
        'month_trunc'
    )


def _by_week(qs):
    return _period_with_cat(
        qs, TruncWeek,
        lambda d: f"W{d.strftime('%V')} {d.strftime('%Y')}" if d else '—',
        'week_trunc'
    )


def _by_product_season(qs):
    """Group by product design year+season (SaleDetail.year / season fields)."""
    rows = list(
        qs.values('year', 'season', 'category_l1', 'category_l2')
        .annotate(
            qty=Sum('quantity'),
            amount=Sum('sales_amount'),
            settlement=Sum('settlement_amount'),
            tag_amount=Sum('tag_amount'),
            lines=Count('id'),
        )
        .order_by('-year', 'season', 'category_l1', 'category_l2')
    )

    seasons = OrderedDict()
    for r in rows:
        key = (r.get('year'), r.get('season') or '—')
        if key not in seasons:
            yr, se = key
            label = f"{yr} {se}" if yr else (se or '—')
            seasons[key] = {
                'year': yr, 'season': se, 'label': label,
                'qty': 0, 'amount': 0.0, 'settlement': 0.0,
                'tag_amount': 0.0, 'lines': 0,
                '_cat_rows': [],
            }
        p = seasons[key]
        p['qty'] += r.get('qty') or 0
        p['amount'] += float(r.get('amount') or 0)
        p['settlement'] += float(r.get('settlement') or 0)
        p['tag_amount'] += float(r.get('tag_amount') or 0)
        p['lines'] += r.get('lines') or 0
        p['_cat_rows'].append({
            'category_l1': r.get('category_l1') or '—',
            'category_l2': r.get('category_l2') or '—',
            'qty': r.get('qty') or 0,
            'amount': float(r.get('amount') or 0),
            'settlement': float(r.get('settlement') or 0),
            'tag_amount': float(r.get('tag_amount') or 0),
            'lines': r.get('lines') or 0,
        })

    result = []
    for p in seasons.values():
        p['disc_pct'] = _disc_pct(p['tag_amount'], p['settlement'])
        p['cat_groups'] = _build_cat_groups(p.pop('_cat_rows'))
        result.append(p)
    return result


def _by_brand(qs):
    """Group by brand with category drill-down."""
    rows = list(
        qs.values('brand', 'category_l1', 'category_l2')
        .annotate(
            qty=Sum('quantity'),
            amount=Sum('sales_amount'),
            settlement=Sum('settlement_amount'),
            tag_amount=Sum('tag_amount'),
            lines=Count('id'),
        )
        .order_by('brand', 'category_l1', 'category_l2')
    )

    brands = OrderedDict()
    for r in rows:
        br = r.get('brand') or '—'
        if br not in brands:
            brands[br] = {
                'brand': br,
                'qty': 0, 'amount': 0.0, 'settlement': 0.0,
                'tag_amount': 0.0, 'lines': 0,
                '_cat_rows': [],
            }
        p = brands[br]
        p['qty'] += r.get('qty') or 0
        p['amount'] += float(r.get('amount') or 0)
        p['settlement'] += float(r.get('settlement') or 0)
        p['tag_amount'] += float(r.get('tag_amount') or 0)
        p['lines'] += r.get('lines') or 0
        p['_cat_rows'].append({
            'category_l1': r.get('category_l1') or '—',
            'category_l2': r.get('category_l2') or '—',
            'qty': r.get('qty') or 0,
            'amount': float(r.get('amount') or 0),
            'settlement': float(r.get('settlement') or 0),
            'tag_amount': float(r.get('tag_amount') or 0),
            'lines': r.get('lines') or 0,
        })

    result = sorted(brands.values(), key=lambda x: -(x.get('qty') or 0))
    for p in result:
        p['disc_pct'] = _disc_pct(p['tag_amount'], p['settlement'])
        p['cat_groups'] = _build_cat_groups(p.pop('_cat_rows'))
    return result


def _by_category(qs):
    """Flat L1→L2 category breakdown (no period nesting)."""
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
        r['amount'] = float(r.get('amount') or 0)
        r['settlement'] = float(r.get('settlement') or 0)
        r['tag_amount'] = float(r.get('tag_amount') or 0)
    return rows


def _by_shop_full(qs):
    """
    Section 2: shop summary + per-shop mini Section 1.
    Each shop gets by_year, by_month, by_week, by_season — each with cat_groups per period.
    Total: 5 DB queries (1 totals + 4 period×cat×shop).
    """
    # 1 — shop totals
    shop_rows = list(
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
    for r in shop_rows:
        r['disc_pct'] = _disc_pct(r.get('tag_amount'), r.get('settlement'))
        r['amount'] = float(r.get('amount') or 0)
        r['settlement'] = float(r.get('settlement') or 0)
        r['tag_amount'] = float(r.get('tag_amount') or 0)

    if not shop_rows:
        return shop_rows

    def _group_trunc_by_shop(flat_rows, period_field, label_fn):
        """Build {shop_name: [period_dict_with_cat_groups]} from flat DB rows."""
        shop_map: dict = {}
        for r in flat_rows:
            sn = r.get('shop_name') or '—'
            pk = r.get(period_field)
            if sn not in shop_map:
                shop_map[sn] = OrderedDict()
            if pk not in shop_map[sn]:
                shop_map[sn][pk] = {
                    'label': label_fn(pk),
                    'qty': 0, 'amount': 0.0, 'settlement': 0.0,
                    'tag_amount': 0.0, 'lines': 0,
                    '_cat_rows': [],
                }
            p = shop_map[sn][pk]
            p['qty'] += r.get('qty') or 0
            p['amount'] += float(r.get('amount') or 0)
            p['settlement'] += float(r.get('settlement') or 0)
            p['tag_amount'] += float(r.get('tag_amount') or 0)
            p['lines'] += r.get('lines') or 0
            p['_cat_rows'].append({
                'category_l1': r.get('category_l1') or '—',
                'category_l2': r.get('category_l2') or '—',
                'qty': r.get('qty') or 0,
                'amount': float(r.get('amount') or 0),
                'settlement': float(r.get('settlement') or 0),
                'tag_amount': float(r.get('tag_amount') or 0),
                'lines': r.get('lines') or 0,
            })
        result = {}
        for sn, periods in shop_map.items():
            lst = []
            for p in periods.values():
                p['disc_pct'] = _disc_pct(p['tag_amount'], p['settlement'])
                p['cat_groups'] = _build_cat_groups(p.pop('_cat_rows'))
                lst.append(p)
            result[sn] = lst
        return result

    # 2 — year × cat × shop
    year_flat = list(
        qs.annotate(year_trunc=TruncYear('sales_date'))
        .values('shop_name', 'year_trunc', 'category_l1', 'category_l2')
        .annotate(qty=Sum('quantity'), amount=Sum('sales_amount'),
                  settlement=Sum('settlement_amount'), tag_amount=Sum('tag_amount'),
                  lines=Count('id'))
        .order_by('shop_name', '-year_trunc', 'category_l1', 'category_l2')
    )
    year_by_shop = _group_trunc_by_shop(
        year_flat, 'year_trunc', lambda d: str(d.year) if d else '—'
    )

    # 3 — month × cat × shop
    month_flat = list(
        qs.annotate(month_trunc=TruncMonth('sales_date'))
        .values('shop_name', 'month_trunc', 'category_l1', 'category_l2')
        .annotate(qty=Sum('quantity'), amount=Sum('sales_amount'),
                  settlement=Sum('settlement_amount'), tag_amount=Sum('tag_amount'),
                  lines=Count('id'))
        .order_by('shop_name', '-month_trunc', 'category_l1', 'category_l2')
    )
    month_by_shop = _group_trunc_by_shop(
        month_flat, 'month_trunc', lambda d: d.strftime('%Y-%m') if d else '—'
    )

    # 4 — week × cat × shop
    week_flat = list(
        qs.annotate(week_trunc=TruncWeek('sales_date'))
        .values('shop_name', 'week_trunc', 'category_l1', 'category_l2')
        .annotate(qty=Sum('quantity'), amount=Sum('sales_amount'),
                  settlement=Sum('settlement_amount'), tag_amount=Sum('tag_amount'),
                  lines=Count('id'))
        .order_by('shop_name', '-week_trunc', 'category_l1', 'category_l2')
    )
    week_by_shop = _group_trunc_by_shop(
        week_flat, 'week_trunc',
        lambda d: f"W{d.strftime('%V')} {d.strftime('%Y')}" if d else '—'
    )

    # 5 — product season × cat × shop (tuple key: year+season)
    season_flat = list(
        qs.values('shop_name', 'year', 'season', 'category_l1', 'category_l2')
        .annotate(qty=Sum('quantity'), amount=Sum('sales_amount'),
                  settlement=Sum('settlement_amount'), tag_amount=Sum('tag_amount'),
                  lines=Count('id'))
        .order_by('shop_name', '-year', 'season', 'category_l1', 'category_l2')
    )
    season_by_shop: dict = {}
    for r in season_flat:
        sn = r.get('shop_name') or '—'
        yr = r.get('year')
        se = r.get('season') or '—'
        key = (yr, se)
        label = f"{yr} {se}" if yr else (se or '—')
        if sn not in season_by_shop:
            season_by_shop[sn] = OrderedDict()
        if key not in season_by_shop[sn]:
            season_by_shop[sn][key] = {
                'label': label, 'qty': 0, 'amount': 0.0,
                'settlement': 0.0, 'tag_amount': 0.0, 'lines': 0,
                '_cat_rows': [],
            }
        p = season_by_shop[sn][key]
        p['qty'] += r.get('qty') or 0
        p['amount'] += float(r.get('amount') or 0)
        p['settlement'] += float(r.get('settlement') or 0)
        p['tag_amount'] += float(r.get('tag_amount') or 0)
        p['lines'] += r.get('lines') or 0
        p['_cat_rows'].append({
            'category_l1': r.get('category_l1') or '—',
            'category_l2': r.get('category_l2') or '—',
            'qty': r.get('qty') or 0,
            'amount': float(r.get('amount') or 0),
            'settlement': float(r.get('settlement') or 0),
            'tag_amount': float(r.get('tag_amount') or 0),
            'lines': r.get('lines') or 0,
        })
    season_by_shop_final: dict = {}
    for sn, seasons in season_by_shop.items():
        lst = []
        for p in seasons.values():
            p['disc_pct'] = _disc_pct(p['tag_amount'], p['settlement'])
            p['cat_groups'] = _build_cat_groups(p.pop('_cat_rows'))
            lst.append(p)
        season_by_shop_final[sn] = lst

    # Attach all period breakdowns to shop_rows
    for r in shop_rows:
        sn = r.get('shop_name') or '—'
        r['by_year']   = year_by_shop.get(sn, [])
        r['by_month']  = month_by_shop.get(sn, [])
        r['by_week']   = week_by_shop.get(sn, [])
        r['by_season'] = season_by_shop_final.get(sn, [])

    return shop_rows


def _by_vip_grade(qs):
    """
    Group by VIP grade via SaleDetail → SalesTransaction → Customer.
    Null grade (no linked customer, or vip_id=0) shows as 'No Grade'.
    Sorted by grade hierarchy: No Grade < Member < Silver < Gold < Diamond.
    """
    rows = list(
        qs.values('transaction__customer__vip_grade', 'category_l1', 'category_l2')
        .annotate(
            qty=Sum('quantity'),
            amount=Sum('sales_amount'),
            settlement=Sum('settlement_amount'),
            tag_amount=Sum('tag_amount'),
            lines=Count('id'),
        )
        .order_by('transaction__customer__vip_grade', 'category_l1', 'category_l2')
    )

    grades: dict = OrderedDict()
    for r in rows:
        grade = r.get('transaction__customer__vip_grade') or 'No Grade'
        if grade not in grades:
            grades[grade] = {
                'grade': grade,
                'qty': 0, 'amount': 0.0, 'settlement': 0.0,
                'tag_amount': 0.0, 'lines': 0,
                '_cat_rows': [],
            }
        p = grades[grade]
        p['qty'] += r.get('qty') or 0
        p['amount'] += float(r.get('amount') or 0)
        p['settlement'] += float(r.get('settlement') or 0)
        p['tag_amount'] += float(r.get('tag_amount') or 0)
        p['lines'] += r.get('lines') or 0
        p['_cat_rows'].append({
            'category_l1': r.get('category_l1') or '—',
            'category_l2': r.get('category_l2') or '—',
            'qty': r.get('qty') or 0,
            'amount': float(r.get('amount') or 0),
            'settlement': float(r.get('settlement') or 0),
            'tag_amount': float(r.get('tag_amount') or 0),
            'lines': r.get('lines') or 0,
        })

    result = sorted(grades.values(), key=lambda x: GRADE_ORDER.get(x['grade'], 99))
    for p in result:
        p['disc_pct'] = _disc_pct(p['tag_amount'], p['settlement'])
        p['cat_groups'] = _build_cat_groups(p.pop('_cat_rows'))
    return result


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
        r['amount'] = float(r.get('amount') or 0)
        r['settlement'] = float(r.get('settlement') or 0)
        r['tag_amount'] = float(r.get('tag_amount') or 0)
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
    if tab == 'vip_grade':
        tab_data['by_vip_grade'] = _by_vip_grade(qs)
    elif tab == 'year':
        tab_data['by_year'] = _by_year(qs)
    elif tab == 'month':
        tab_data['by_month'] = _by_month(qs)
    elif tab == 'week':
        tab_data['by_week'] = _by_week(qs)
    elif tab == 'product_season':
        tab_data['by_product_season'] = _by_product_season(qs)
    elif tab == 'brand':
        tab_data['by_brand'] = _by_brand(qs)
    elif tab == 'category':
        tab_data['by_category'] = _by_category(qs)
    elif tab == 'shop':
        tab_data['by_shop'] = _by_shop_full(qs)
    elif tab == 'product':
        tab_data['by_product'] = _by_product(qs)

    result = {'overview': overview, **tab_data}
    cache.set(key, result, _TTL)
    logger.info("product_tab %s loaded: lines=%d", tab, overview.get('total_lines', 0),
                extra={"step": "product_analytics"})
    return result
