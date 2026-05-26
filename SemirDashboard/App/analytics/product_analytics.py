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
_CAMPAIGN_CACHE_KEY = 'product_campaigns_list'

# Tabs served by product_tab AJAX endpoint
PRODUCT_TABS = [
    'month', 'year', 'week', 'sales_season',
    'product_season', 'vip_grade', 'brand', 'category', 'campaign', 'shop', 'product',
]

GRADE_ORDER = {'No Grade': 0, 'Member': 1, 'Silver': 2, 'Gold': 3, 'Diamond': 4}
_SEASON_MONTH_MAP = {2:'M2-4',3:'M2-4',4:'M2-4', 5:'M5-7',6:'M5-7',7:'M5-7',
                     8:'M8-10',9:'M8-10',10:'M8-10', 11:'M11-1',12:'M11-1',1:'M11-1'}


def bump_product_version():
    """Invalidate all product tab caches by incrementing the version counter."""
    cache.delete(_CAMPAIGN_CACHE_KEY)
    try:
        cache.incr(_VERSION_KEY)
    except ValueError:
        cache.set(_VERSION_KEY, 1, None)


def _base_qs(date_from=None, date_to=None, shop_group=None, shop_name=None):
    qs = SaleDetail.objects.all()
    if date_from:
        qs = qs.filter(sales_date__gte=date_from)
    if date_to:
        qs = qs.filter(sales_date__lte=date_to)
    if shop_name:
        qs = qs.filter(shop_name=shop_name)
    elif shop_group:
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


def _cache_key(tab, date_from, date_to, shop_group, shop_name=None):
    v = cache.get(_VERSION_KEY, 0)
    return f"prod_tab_v{v}_{tab}_{date_from}_{date_to}_{shop_group}_{shop_name}"


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


# ── Core helpers ───────────────────────────────────────────────────────────────

def _build_cat_groups(cat_rows):
    """
    Group [{category_l1, category_l2, category_l3, qty, amount, ...}]
    → [{l1, l2_groups:[{l2, rows:[L3 rows], subtotal}], subtotal}] sorted by amount desc.
    3-level hierarchy: L1 → L2 groups → L3 detail rows.
    """
    l1_map = OrderedDict()
    for r in cat_rows:
        l1 = r.get('category_l1') or ''
        l2 = r.get('category_l2') or ''
        if l1 not in l1_map:
            l1_map[l1] = OrderedDict()
        if l2 not in l1_map[l1]:
            l1_map[l1][l2] = []
        l1_map[l1][l2].append(r)

    result = []
    for l1, l2_map in l1_map.items():
        l1_qty = l1_amt = l1_sett = l1_tag = l1_lines = 0
        l2_groups = []
        for l2, rows in l2_map.items():
            rows = sorted(rows, key=lambda r: -(float(r.get('amount') or 0)))
            for r in rows:
                r['disc_pct'] = _disc_pct(r.get('tag_amount'), r.get('settlement'))
            l2_qty   = sum(r.get('qty') or 0 for r in rows)
            l2_amt   = sum(float(r.get('amount') or 0) for r in rows)
            l2_sett  = sum(float(r.get('settlement') or 0) for r in rows)
            l2_tag   = sum(float(r.get('tag_amount') or 0) for r in rows)
            l2_lines = sum(r.get('lines') or 0 for r in rows)
            l2_groups.append({
                'l2': l2,
                'rows': rows,
                'subtotal': {
                    'qty': l2_qty, 'amount': l2_amt, 'settlement': l2_sett,
                    'tag_amount': l2_tag, 'lines': l2_lines,
                    'disc_pct': _disc_pct(l2_tag, l2_sett),
                },
            })
            l1_qty   += l2_qty
            l1_amt   += l2_amt
            l1_sett  += l2_sett
            l1_tag   += l2_tag
            l1_lines += l2_lines
        l2_groups = sorted(l2_groups, key=lambda x: -(x['subtotal']['amount'] or 0))
        result.append({
            'l1': l1,
            'l2_groups': l2_groups,
            'subtotal': {
                'qty': l1_qty, 'amount': l1_amt, 'settlement': l1_sett,
                'tag_amount': l1_tag, 'lines': l1_lines,
                'disc_pct': _disc_pct(l1_tag, l1_sett),
            },
        })
    return sorted(result, key=lambda x: -(x['subtotal']['amount'] or 0))


def _build_top_products(prod_rows, top_n=10):
    """Convert aggregate rows → sorted top_products list."""
    result = []
    for r in prod_rows[:top_n]:
        result.append({
            'product_code': r.get('product_code') or '',
            'product_name': r.get('product_name') or '',
            'brand': r.get('brand') or '—',
            'qty': r.get('qty') or 0,
            'amount': float(r.get('amount') or 0),
            'settlement': float(r.get('settlement') or 0),
            'tag_amount': float(r.get('tag_amount') or 0),
            'lines': r.get('lines') or 0,
            'disc_pct': _disc_pct(r.get('tag_amount'), r.get('settlement')),
        })
    return result


def _top_products_by_period(qs, trunc_fn, period_key, top_n=10, campaigns=None):
    """Query top N products per period. Returns ({period_val: [top_products]}, {period_val: [camp_rows]})."""
    if campaigns is None:
        campaigns = _load_campaigns()
    rows = list(
        qs.annotate(**{period_key: trunc_fn('sales_date')})
        .values(period_key, 'product_code', 'product_name', 'brand',
                'category_l1', 'category_l2', 'category_l3')
        .annotate(qty=Sum('quantity'), amount=Sum('sales_amount'),
                  settlement=Sum('settlement_amount'), tag_amount=Sum('tag_amount'),
                  lines=Count('id'))
        .order_by(f'-{period_key}', '-amount')
    )
    by_period: dict = {}
    camp_agg: dict = {}  # {period_key: {(camp,l1,l2,l3): aggregated_row}}
    for r in rows:
        pk = r[period_key]
        camp = _lookup_campaign(r.get('product_code') or '', campaigns)
        if pk not in by_period:
            by_period[pk] = []
        if len(by_period[pk]) < top_n:
            entry = dict(r)
            entry['amount'] = float(entry.get('amount') or 0)
            entry['settlement'] = float(entry.get('settlement') or 0)
            entry['tag_amount'] = float(entry.get('tag_amount') or 0)
            entry['disc_pct'] = _disc_pct(entry.get('tag_amount'), entry.get('settlement'))
            entry['campaign'] = camp
            del entry[period_key]
            by_period[pk].append(entry)
        # Build campaign aggregation rows
        if pk not in camp_agg:
            camp_agg[pk] = {}
        l1 = r.get('category_l1') or ''
        l2 = r.get('category_l2') or ''
        l3 = r.get('category_l3') or ''
        ckey = (camp, l1, l2, l3)
        if ckey not in camp_agg[pk]:
            camp_agg[pk][ckey] = {'campaign': camp, 'category_l1': l1, 'category_l2': l2,
                                   'category_l3': l3, 'qty': 0, 'amount': 0.0,
                                   'settlement': 0.0, 'tag_amount': 0.0, 'lines': 0}
        e = camp_agg[pk][ckey]
        e['qty'] += r.get('qty') or 0
        e['amount'] += float(r.get('amount') or 0)
        e['settlement'] += float(r.get('settlement') or 0)
        e['tag_amount'] += float(r.get('tag_amount') or 0)
        e['lines'] += (r.get('lines') or 0)
    camp_rows_by_period = {pk: list(v.values()) for pk, v in camp_agg.items()}
    return by_period, camp_rows_by_period


def _top_products_by_group(qs, group_field, top_n=10, campaigns=None):
    """Query top N products per group value. Returns ({group_val: [top_products]}, {group_val: [camp_rows]})."""
    if campaigns is None:
        campaigns = _load_campaigns()
    rows = list(
        qs.values(group_field, 'product_code', 'product_name', 'brand',
                  'category_l1', 'category_l2', 'category_l3')
        .annotate(qty=Sum('quantity'), amount=Sum('sales_amount'),
                  settlement=Sum('settlement_amount'), tag_amount=Sum('tag_amount'),
                  lines=Count('id'))
        .order_by(group_field, '-amount')
    )
    by_group: dict = {}
    camp_agg: dict = {}
    for r in rows:
        gv = r.get(group_field) or '—'
        camp = _lookup_campaign(r.get('product_code') or '', campaigns)
        if gv not in by_group:
            by_group[gv] = []
        if len(by_group[gv]) < top_n:
            entry = {k: v for k, v in r.items() if k != group_field}
            entry['amount'] = float(entry.get('amount') or 0)
            entry['settlement'] = float(entry.get('settlement') or 0)
            entry['tag_amount'] = float(entry.get('tag_amount') or 0)
            entry['disc_pct'] = _disc_pct(entry.get('tag_amount'), entry.get('settlement'))
            entry['campaign'] = camp
            by_group[gv].append(entry)
        l1 = r.get('category_l1') or ''
        l2 = r.get('category_l2') or ''
        l3 = r.get('category_l3') or ''
        ckey = (camp, l1, l2, l3)
        if gv not in camp_agg:
            camp_agg[gv] = {}
        if ckey not in camp_agg[gv]:
            camp_agg[gv][ckey] = {'campaign': camp, 'category_l1': l1, 'category_l2': l2,
                                   'category_l3': l3, 'qty': 0, 'amount': 0.0,
                                   'settlement': 0.0, 'tag_amount': 0.0, 'lines': 0}
        e = camp_agg[gv][ckey]
        e['qty'] += r.get('qty') or 0
        e['amount'] += float(r.get('amount') or 0)
        e['settlement'] += float(r.get('settlement') or 0)
        e['tag_amount'] += float(r.get('tag_amount') or 0)
        e['lines'] += (r.get('lines') or 0)
    camp_rows_by_group = {gv: list(v.values()) for gv, v in camp_agg.items()}
    return by_group, camp_rows_by_group


def _period_with_cat(qs, trunc_fn, label_fn, period_key, top_n=10):
    """
    2 DB queries: (period × cat) + (period × product).
    Returns list of period dicts each with cat_groups + top_products.
    """
    # Query 1: period × cat
    rows = list(
        qs.annotate(**{period_key: trunc_fn('sales_date')})
        .values(period_key, 'category_l1', 'category_l2', 'category_l3')
        .annotate(qty=Sum('quantity'), amount=Sum('sales_amount'),
                  settlement=Sum('settlement_amount'), tag_amount=Sum('tag_amount'),
                  lines=Count('id'))
        .order_by(f'-{period_key}', 'category_l1', 'category_l2', 'category_l3')
    )

    # Query 2: period × product (for top_n products per period + campaign rows)
    top_by_period, camp_rows_by_period = _top_products_by_period(qs, trunc_fn, period_key, top_n=top_n)

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
            'category_l1': r.get('category_l1') or '',
            'category_l2': r.get('category_l2') or '',
            'category_l3': r.get('category_l3') or '',
            'qty': r.get('qty') or 0,
            'amount': float(r.get('amount') or 0),
            'settlement': float(r.get('settlement') or 0),
            'tag_amount': float(r.get('tag_amount') or 0),
            'lines': r.get('lines') or 0,
        })

    result = []
    for pk, p in periods.items():
        p['disc_pct'] = _disc_pct(p['tag_amount'], p['settlement'])
        p['cat_groups'] = _build_cat_groups(p.pop('_cat_rows'))
        p['top_products'] = top_by_period.get(pk, [])
        p['campaign_groups'] = _build_campaign_groups(camp_rows_by_period.get(pk, []))
        result.append(p)
    return result


def _by_year(qs):
    return _period_with_cat(qs, TruncYear, lambda d: str(d.year) if d else '—', 'year_trunc')


def _by_month(qs):
    return _period_with_cat(qs, TruncMonth,
                            lambda d: d.strftime('%Y-%m') if d else '—', 'month_trunc')


def _by_week(qs):
    return _period_with_cat(qs, TruncWeek,
                            lambda d: f"W{d.strftime('%V')} {d.strftime('%Y')}" if d else '—',
                            'week_trunc')


def _sales_season_key(dt):
    """Return ((sort_year, season_code), label) for a date."""
    m = dt.month
    y = dt.year
    code = _SEASON_MONTH_MAP[m]
    if code == 'M11-1':
        if m == 1:
            return (y - 1, code), f'M11-1 {y-1}-{y}'
        else:
            return (y, code), f'M11-1 {y}-{y+1}'
    return (y, code), f'{code} {y}'


def _by_sales_season(qs, top_n=10):
    """
    Group by sales-date business season (M2-4/M5-7/M8-10/M11-1).
    Uses month-level aggregation then re-groups in Python (no extra DB query).
    """
    # Query 1: month × cat (re-group to season in Python)
    rows = list(
        qs.annotate(month_trunc=TruncMonth('sales_date'))
        .values('month_trunc', 'category_l1', 'category_l2', 'category_l3')
        .annotate(qty=Sum('quantity'), amount=Sum('sales_amount'),
                  settlement=Sum('settlement_amount'), tag_amount=Sum('tag_amount'),
                  lines=Count('id'))
        .order_by('month_trunc', 'category_l1', 'category_l2', 'category_l3')
    )

    # Query 2: month × product (re-group to season)
    prod_rows = list(
        qs.annotate(month_trunc=TruncMonth('sales_date'))
        .values('month_trunc', 'product_code', 'product_name', 'brand',
                'category_l1', 'category_l2', 'category_l3')
        .annotate(qty=Sum('quantity'), amount=Sum('sales_amount'),
                  settlement=Sum('settlement_amount'), tag_amount=Sum('tag_amount'),
                  lines=Count('id'))
        .order_by('month_trunc', '-amount')
    )

    seasons: dict = OrderedDict()

    for r in rows:
        m = r.get('month_trunc')
        if not m:
            continue
        sk, label = _sales_season_key(m)
        if sk not in seasons:
            seasons[sk] = {
                'label': label, 'qty': 0, 'amount': 0.0,
                'settlement': 0.0, 'tag_amount': 0.0, 'lines': 0,
                '_cat_rows': [], '_prod_rows': [],
            }
        p = seasons[sk]
        p['qty'] += r.get('qty') or 0
        p['amount'] += float(r.get('amount') or 0)
        p['settlement'] += float(r.get('settlement') or 0)
        p['tag_amount'] += float(r.get('tag_amount') or 0)
        p['lines'] += r.get('lines') or 0
        p['_cat_rows'].append({
            'category_l1': r.get('category_l1') or '',
            'category_l2': r.get('category_l2') or '',
            'category_l3': r.get('category_l3') or '',
            'qty': r.get('qty') or 0,
            'amount': float(r.get('amount') or 0),
            'settlement': float(r.get('settlement') or 0),
            'tag_amount': float(r.get('tag_amount') or 0),
            'lines': r.get('lines') or 0,
        })

    for r in prod_rows:
        m = r.get('month_trunc')
        if not m:
            continue
        sk, _ = _sales_season_key(m)
        if sk in seasons:
            seasons[sk]['_prod_rows'].append({
                'product_code': r.get('product_code') or '',
                'product_name': r.get('product_name') or '',
                'brand': r.get('brand') or '—',
                'category_l1': r.get('category_l1') or '',
                'category_l2': r.get('category_l2') or '',
                'category_l3': r.get('category_l3') or '',
                'qty': r.get('qty') or 0,
                'amount': float(r.get('amount') or 0),
                'settlement': float(r.get('settlement') or 0),
                'tag_amount': float(r.get('tag_amount') or 0),
            })

    # Sort seasons: most recent year first, then season order
    _so = ['M2-4', 'M5-7', 'M8-10', 'M11-1']
    sorted_seasons = sorted(seasons.items(), key=lambda x: (-x[0][0], _so.index(x[0][1])))
    campaigns = _load_campaigns()

    result = []
    for sk, p in sorted_seasons:
        p['disc_pct'] = _disc_pct(p['tag_amount'], p['settlement'])
        p['cat_groups'] = _build_cat_groups(p.pop('_cat_rows'))
        # Aggregate products within season, sort, take top N
        prod_agg: dict = {}
        for pr in p.pop('_prod_rows'):
            key = pr['product_code']
            if key not in prod_agg:
                prod_agg[key] = dict(pr)
            else:
                prod_agg[key]['qty'] += pr['qty']
                prod_agg[key]['amount'] += pr['amount']
                prod_agg[key]['settlement'] += pr['settlement']
                prod_agg[key]['tag_amount'] += pr['tag_amount']
        sorted_prods = sorted(prod_agg.values(), key=lambda x: -(x.get('amount') or 0))
        for pr in sorted_prods:
            pr['disc_pct'] = _disc_pct(pr.get('tag_amount'), pr.get('settlement'))
            pr['campaign'] = _lookup_campaign(pr.get('product_code') or '', campaigns)
        p['top_products'] = sorted_prods[:top_n]
        camp_rows = _derive_campaign_rows(list(prod_agg.values()), campaigns)
        p['campaign_groups'] = _build_campaign_groups(camp_rows)
        result.append(p)
    return result


def _by_product_season(qs, top_n=10):
    """Group by product design year+season (SaleDetail.year / season fields)."""
    rows = list(
        qs.values('year', 'season', 'category_l1', 'category_l2', 'category_l3')
        .annotate(qty=Sum('quantity'), amount=Sum('sales_amount'),
                  settlement=Sum('settlement_amount'), tag_amount=Sum('tag_amount'),
                  lines=Count('id'))
        .order_by('-year', 'season', 'category_l1', 'category_l2', 'category_l3')
    )

    prod_rows = list(
        qs.values('year', 'season', 'product_code', 'product_name', 'brand',
                  'category_l1', 'category_l2', 'category_l3')
        .annotate(qty=Sum('quantity'), amount=Sum('sales_amount'),
                  settlement=Sum('settlement_amount'), tag_amount=Sum('tag_amount'),
                  lines=Count('id'))
        .order_by('-year', 'season', '-amount')
    )

    seasons: dict = OrderedDict()
    for r in rows:
        yr = r.get('year')
        se = r.get('season') or '—'
        key = (yr, se)
        label = f"{yr} {se}" if yr else (se or '—')
        if key not in seasons:
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
            'category_l1': r.get('category_l1') or '',
            'category_l2': r.get('category_l2') or '',
            'category_l3': r.get('category_l3') or '',
            'qty': r.get('qty') or 0,
            'amount': float(r.get('amount') or 0),
            'settlement': float(r.get('settlement') or 0),
            'tag_amount': float(r.get('tag_amount') or 0),
            'lines': r.get('lines') or 0,
        })

    campaigns = _load_campaigns()
    top_by_key: dict = {}
    all_rows_by_key: dict = {}
    for r in prod_rows:
        key = (r.get('year'), r.get('season') or '—')
        if key not in top_by_key:
            top_by_key[key] = []
            all_rows_by_key[key] = []
        entry = {
            'product_code': r.get('product_code') or '',
            'product_name': r.get('product_name') or '',
            'brand': r.get('brand') or '—',
            'category_l1': r.get('category_l1') or '',
            'category_l2': r.get('category_l2') or '',
            'category_l3': r.get('category_l3') or '',
            'qty': r.get('qty') or 0,
            'amount': float(r.get('amount') or 0),
            'settlement': float(r.get('settlement') or 0),
            'tag_amount': float(r.get('tag_amount') or 0),
            'lines': r.get('lines') or 0,
        }
        entry['disc_pct'] = _disc_pct(entry['tag_amount'], entry['settlement'])
        entry['campaign'] = _lookup_campaign(entry['product_code'], campaigns)
        all_rows_by_key[key].append(entry)
        if len(top_by_key[key]) < top_n:
            top_by_key[key].append(entry)

    result = []
    for key, p in seasons.items():
        p['disc_pct'] = _disc_pct(p['tag_amount'], p['settlement'])
        p['cat_groups'] = _build_cat_groups(p.pop('_cat_rows'))
        p['top_products'] = top_by_key.get(key, [])
        camp_rows = _derive_campaign_rows(all_rows_by_key.get(key, []), campaigns)
        p['campaign_groups'] = _build_campaign_groups(camp_rows)
        result.append(p)
    return result


def _by_vip_grade(qs, top_n=10):
    """Group by VIP grade via SaleDetail → SalesTransaction → Customer."""
    rows = list(
        qs.values('transaction__customer__vip_grade', 'category_l1', 'category_l2', 'category_l3')
        .annotate(qty=Sum('quantity'), amount=Sum('sales_amount'),
                  settlement=Sum('settlement_amount'), tag_amount=Sum('tag_amount'),
                  lines=Count('id'))
        .order_by('transaction__customer__vip_grade', 'category_l1', 'category_l2', 'category_l3')
    )
    top_by_grade, camp_rows_by_grade = _top_products_by_group(qs, 'transaction__customer__vip_grade', top_n=top_n)

    grades: dict = OrderedDict()
    for r in rows:
        grade = r.get('transaction__customer__vip_grade') or 'No Grade'
        if grade not in grades:
            grades[grade] = {
                'grade': grade,
                'qty': 0, 'amount': 0.0, 'settlement': 0.0,
                'tag_amount': 0.0, 'lines': 0, '_cat_rows': [],
            }
        p = grades[grade]
        p['qty'] += r.get('qty') or 0
        p['amount'] += float(r.get('amount') or 0)
        p['settlement'] += float(r.get('settlement') or 0)
        p['tag_amount'] += float(r.get('tag_amount') or 0)
        p['lines'] += r.get('lines') or 0
        p['_cat_rows'].append({
            'category_l1': r.get('category_l1') or '',
            'category_l2': r.get('category_l2') or '',
            'category_l3': r.get('category_l3') or '',
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
        raw_grade = p['grade']
        lookup_key = None if raw_grade == 'No Grade' else raw_grade
        p['top_products'] = (
            top_by_grade.get(lookup_key, []) or
            top_by_grade.get(raw_grade, []) or
            top_by_grade.get('—', [])
        )
        camp_rows = (
            camp_rows_by_grade.get(lookup_key) or
            camp_rows_by_grade.get(raw_grade) or
            camp_rows_by_grade.get('—') or []
        )
        p['campaign_groups'] = _build_campaign_groups(camp_rows)
    return result


def _by_brand(qs, top_n=10):
    """Group by brand with category drill-down and top products."""
    rows = list(
        qs.values('brand', 'category_l1', 'category_l2', 'category_l3')
        .annotate(qty=Sum('quantity'), amount=Sum('sales_amount'),
                  settlement=Sum('settlement_amount'), tag_amount=Sum('tag_amount'),
                  lines=Count('id'))
        .order_by('brand', 'category_l1', 'category_l2', 'category_l3')
    )
    top_by_brand, camp_rows_by_brand = _top_products_by_group(qs, 'brand', top_n=top_n)

    brands: dict = OrderedDict()
    for r in rows:
        br = r.get('brand') or '—'
        if br not in brands:
            brands[br] = {
                'brand': br,
                'qty': 0, 'amount': 0.0, 'settlement': 0.0,
                'tag_amount': 0.0, 'lines': 0, '_cat_rows': [],
            }
        p = brands[br]
        p['qty'] += r.get('qty') or 0
        p['amount'] += float(r.get('amount') or 0)
        p['settlement'] += float(r.get('settlement') or 0)
        p['tag_amount'] += float(r.get('tag_amount') or 0)
        p['lines'] += r.get('lines') or 0
        p['_cat_rows'].append({
            'category_l1': r.get('category_l1') or '',
            'category_l2': r.get('category_l2') or '',
            'category_l3': r.get('category_l3') or '',
            'qty': r.get('qty') or 0,
            'amount': float(r.get('amount') or 0),
            'settlement': float(r.get('settlement') or 0),
            'tag_amount': float(r.get('tag_amount') or 0),
            'lines': r.get('lines') or 0,
        })

    result = sorted(brands.values(), key=lambda x: -(x.get('amount') or 0))
    for p in result:
        p['disc_pct'] = _disc_pct(p['tag_amount'], p['settlement'])
        p['cat_groups'] = _build_cat_groups(p.pop('_cat_rows'))
        p['top_products'] = top_by_brand.get(p['brand'], [])
        p['campaign_groups'] = _build_campaign_groups(camp_rows_by_brand.get(p['brand'], []))
    return result


def _build_brand_cat_groups(rows):
    """
    Build 4-level hierarchy: Brand → L1 groups → L2 groups → L3 rows.
    Input rows must include: brand, category_l1, category_l2, category_l3, qty, amount, settlement, tag_amount, lines.
    """
    brand_map = OrderedDict()
    for r in rows:
        br = r.get('brand') or '—'
        l1 = r.get('category_l1') or ''
        l2 = r.get('category_l2') or ''
        brand_map.setdefault(br, OrderedDict()).setdefault(l1, OrderedDict()).setdefault(l2, []).append(r)

    result = []
    for br, l1_map in brand_map.items():
        br_qty = br_amt = br_sett = br_tag = br_lines = 0
        l1_groups = []
        for l1, l2_map in l1_map.items():
            l1_qty = l1_amt = l1_sett = l1_tag = l1_lines = 0
            l2_groups = []
            for l2, l3_rows in l2_map.items():
                l3_rows = sorted(l3_rows, key=lambda r: -(float(r.get('amount') or 0)))
                for r in l3_rows:
                    r['disc_pct'] = _disc_pct(r.get('tag_amount'), r.get('settlement'))
                l2_qty   = sum(r.get('qty') or 0 for r in l3_rows)
                l2_amt   = sum(float(r.get('amount') or 0) for r in l3_rows)
                l2_sett  = sum(float(r.get('settlement') or 0) for r in l3_rows)
                l2_tag   = sum(float(r.get('tag_amount') or 0) for r in l3_rows)
                l2_lines = sum(r.get('lines') or 0 for r in l3_rows)
                l2_groups.append({
                    'l2': l2,
                    'rows': l3_rows,
                    'subtotal': {'qty': l2_qty, 'amount': l2_amt, 'settlement': l2_sett,
                                 'tag_amount': l2_tag, 'lines': l2_lines,
                                 'disc_pct': _disc_pct(l2_tag, l2_sett)},
                })
                l1_qty += l2_qty; l1_amt += l2_amt; l1_sett += l2_sett
                l1_tag += l2_tag; l1_lines += l2_lines
            l2_groups = sorted(l2_groups, key=lambda x: -(x['subtotal']['amount'] or 0))
            l1_groups.append({
                'l1': l1,
                'l2_groups': l2_groups,
                'subtotal': {'qty': l1_qty, 'amount': l1_amt, 'settlement': l1_sett,
                             'tag_amount': l1_tag, 'lines': l1_lines,
                             'disc_pct': _disc_pct(l1_tag, l1_sett)},
            })
            br_qty += l1_qty; br_amt += l1_amt; br_sett += l1_sett
            br_tag += l1_tag; br_lines += l1_lines
        l1_groups = sorted(l1_groups, key=lambda x: -(x['subtotal']['amount'] or 0))
        result.append({
            'brand': br,
            'l1_groups': l1_groups,
            'subtotal': {'qty': br_qty, 'amount': br_amt, 'settlement': br_sett,
                         'tag_amount': br_tag, 'lines': br_lines,
                         'disc_pct': _disc_pct(br_tag, br_sett)},
        })
    return sorted(result, key=lambda x: -(x['subtotal']['amount'] or 0))


def _load_campaigns():
    """Load ProductCampaign list from DB, cached 5 min. Returns [{name, prefixes:[]}]."""
    cached = cache.get(_CAMPAIGN_CACHE_KEY)
    if cached is not None:
        return cached
    from App.models import ProductCampaign
    result = []
    for c in ProductCampaign.objects.values('name', 'prefix'):
        prefixes = [p.strip().upper() for p in c['prefix'].split(',') if p.strip()]
        result.append({'name': c['name'], 'prefixes': prefixes})
    cache.set(_CAMPAIGN_CACHE_KEY, result, 300)
    return result


def _lookup_campaign(product_code, campaigns):
    """Return campaign name for a product_code by prefix match, or '' if none."""
    if not product_code or not campaigns:
        return ''
    pc = (product_code or '').upper()
    for c in campaigns:
        for prefix in c['prefixes']:
            if pc.startswith(prefix):
                return c['name']
    return ''


def _build_campaign_groups(rows):
    """
    Group [{campaign, category_l1, category_l2, category_l3, qty, amount, ...}]
    → [{campaign, l1_groups:[{l1, l2_groups:[{l2, rows, subtotal}], subtotal}], subtotal, top_products:[]}]
    Campaign '' → displayed as 'Not Assigned'.
    """
    camp_map = OrderedDict()
    for r in rows:
        camp = r.get('campaign') or ''
        l1 = r.get('category_l1') or ''
        l2 = r.get('category_l2') or ''
        camp_map.setdefault(camp, OrderedDict()).setdefault(l1, OrderedDict()).setdefault(l2, []).append(r)

    result = []
    for camp, l1_map in camp_map.items():
        br_qty = br_amt = br_sett = br_tag = br_lines = 0
        l1_groups = []
        for l1, l2_map in l1_map.items():
            l1_qty = l1_amt = l1_sett = l1_tag = l1_lines = 0
            l2_groups = []
            for l2, l3_rows in l2_map.items():
                l3_rows = sorted(l3_rows, key=lambda r: -(float(r.get('amount') or 0)))
                for r in l3_rows:
                    r['disc_pct'] = _disc_pct(r.get('tag_amount'), r.get('settlement'))
                l2_qty   = sum(r.get('qty') or 0 for r in l3_rows)
                l2_amt   = sum(float(r.get('amount') or 0) for r in l3_rows)
                l2_sett  = sum(float(r.get('settlement') or 0) for r in l3_rows)
                l2_tag   = sum(float(r.get('tag_amount') or 0) for r in l3_rows)
                l2_lines = sum(r.get('lines') or 0 for r in l3_rows)
                l2_groups.append({
                    'l2': l2, 'rows': l3_rows,
                    'subtotal': {'qty': l2_qty, 'amount': l2_amt, 'settlement': l2_sett,
                                 'tag_amount': l2_tag, 'lines': l2_lines,
                                 'disc_pct': _disc_pct(l2_tag, l2_sett)},
                })
                l1_qty += l2_qty; l1_amt += l2_amt; l1_sett += l2_sett
                l1_tag += l2_tag; l1_lines += l2_lines
            l2_groups = sorted(l2_groups, key=lambda x: -(x['subtotal']['amount'] or 0))
            l1_groups.append({
                'l1': l1, 'l2_groups': l2_groups,
                'subtotal': {'qty': l1_qty, 'amount': l1_amt, 'settlement': l1_sett,
                             'tag_amount': l1_tag, 'lines': l1_lines,
                             'disc_pct': _disc_pct(l1_tag, l1_sett)},
            })
            br_qty += l1_qty; br_amt += l1_amt; br_sett += l1_sett
            br_tag += l1_tag; br_lines += l1_lines
        l1_groups = sorted(l1_groups, key=lambda x: -(x['subtotal']['amount'] or 0))
        result.append({
            'campaign': camp,
            'l1_groups': l1_groups,
            'subtotal': {'qty': br_qty, 'amount': br_amt, 'settlement': br_sett,
                         'tag_amount': br_tag, 'lines': br_lines,
                         'disc_pct': _disc_pct(br_tag, br_sett)},
        })
    return sorted(result, key=lambda x: -(x['subtotal']['amount'] or 0))


def _derive_campaign_rows(rows_with_code, campaigns):
    """
    Given rows with {product_code, category_l1, category_l2, category_l3, qty, amount, ...},
    derive campaign per row and aggregate by (campaign, l1, l2, l3).
    If a row already has 'campaign' set, that value is reused (avoids redundant lookup).
    Returns rows suitable for _build_campaign_groups().
    """
    agg: dict = {}
    for r in rows_with_code:
        camp = r.get('campaign') or _lookup_campaign(r.get('product_code') or '', campaigns)
        l1 = r.get('category_l1') or ''
        l2 = r.get('category_l2') or ''
        l3 = r.get('category_l3') or ''
        key = (camp, l1, l2, l3)
        if key not in agg:
            agg[key] = {'campaign': camp, 'category_l1': l1, 'category_l2': l2, 'category_l3': l3,
                        'qty': 0, 'amount': 0.0, 'settlement': 0.0, 'tag_amount': 0.0, 'lines': 0}
        e = agg[key]
        e['qty'] += r.get('qty') or 0
        e['amount'] += float(r.get('amount') or 0)
        e['settlement'] += float(r.get('settlement') or 0)
        e['tag_amount'] += float(r.get('tag_amount') or 0)
        e['lines'] += r.get('lines') or 0
    return list(agg.values())


def _top_products_for_campaign(cat_rows, campaigns, top_n=10):
    """Build top_products list per campaign from campaign_groups data (for _by_product_campaign)."""
    by_camp: dict = {}
    for r in cat_rows:
        camp = r.get('campaign') or ''
        if camp not in by_camp:
            by_camp[camp] = []
        by_camp[camp].append(r)
    result = {}
    for camp, rows in by_camp.items():
        sorted_rows = sorted(rows, key=lambda x: -(float(x.get('amount') or 0)))
        result[camp] = sorted_rows[:top_n]
    return result


def _by_category(qs):
    """Brand → L1 → L2 → L3 breakdown sorted by amount desc."""
    rows = list(
        qs.values('brand', 'category_l1', 'category_l2', 'category_l3')
        .annotate(qty=Sum('quantity'), amount=Sum('sales_amount'),
                  settlement=Sum('settlement_amount'), tag_amount=Sum('tag_amount'),
                  lines=Count('id'))
        .order_by('brand', 'category_l1', 'category_l2', '-amount')
    )
    for r in rows:
        r['amount'] = float(r.get('amount') or 0)
        r['settlement'] = float(r.get('settlement') or 0)
        r['tag_amount'] = float(r.get('tag_amount') or 0)
    return _build_brand_cat_groups(rows)


def _by_product_campaign(qs, top_n=10):
    """Campaign → L1 → L2 → L3 breakdown. Campaign derived from product_code prefix."""
    campaigns = _load_campaigns()
    rows = list(
        qs.values('product_code', 'category_l1', 'category_l2', 'category_l3')
        .annotate(qty=Sum('quantity'), amount=Sum('sales_amount'),
                  settlement=Sum('settlement_amount'), tag_amount=Sum('tag_amount'),
                  lines=Count('id'))
        .order_by('category_l1', 'category_l2', '-amount')
    )
    for r in rows:
        r['amount'] = float(r.get('amount') or 0)
        r['settlement'] = float(r.get('settlement') or 0)
        r['tag_amount'] = float(r.get('tag_amount') or 0)

    camp_rows = _derive_campaign_rows(rows, campaigns)
    campaign_groups = _build_campaign_groups(camp_rows)

    # Top products per campaign (from top products overall, campaign lookup)
    top_rows = list(
        qs.values('product_code', 'product_name', 'brand',
                  'category_l1', 'category_l2', 'category_l3')
        .annotate(qty=Sum('quantity'), amount=Sum('sales_amount'),
                  settlement=Sum('settlement_amount'), tag_amount=Sum('tag_amount'),
                  lines=Count('id'))
        .order_by('-amount')
    )
    by_camp_top: dict = {}
    for r in top_rows:
        camp = _lookup_campaign(r.get('product_code') or '', campaigns)
        if camp not in by_camp_top:
            by_camp_top[camp] = []
        if len(by_camp_top[camp]) < top_n:
            entry = {
                'product_code': r.get('product_code') or '',
                'product_name': r.get('product_name') or '',
                'brand': r.get('brand') or '—',
                'category_l1': r.get('category_l1') or '',
                'category_l2': r.get('category_l2') or '',
                'category_l3': r.get('category_l3') or '',
                'qty': r.get('qty') or 0,
                'amount': float(r.get('amount') or 0),
                'settlement': float(r.get('settlement') or 0),
                'tag_amount': float(r.get('tag_amount') or 0),
                'lines': r.get('lines') or 0,
                'campaign': camp,
                'disc_pct': _disc_pct(r.get('tag_amount'), r.get('settlement')),
            }
            by_camp_top[camp].append(entry)

    for g in campaign_groups:
        g['top_products'] = by_camp_top.get(g['campaign'], [])
    return campaign_groups


def _top_products_by_period_shop(qs, trunc_fn, period_key, top_n=10, campaigns=None):
    """Returns {shop_name: {period_val: [top_products]}} for each shop × period."""
    if campaigns is None:
        campaigns = []
    rows = list(
        qs.annotate(**{period_key: trunc_fn('sales_date')})
        .values('shop_name', period_key, 'product_code', 'product_name', 'brand',
                'category_l1', 'category_l2', 'category_l3')
        .annotate(qty=Sum('quantity'), amount=Sum('sales_amount'),
                  settlement=Sum('settlement_amount'), tag_amount=Sum('tag_amount'))
        .order_by('shop_name', f'-{period_key}', '-amount')
    )
    result: dict = {}
    for r in rows:
        sn = r.get('shop_name') or '—'
        pk = r.get(period_key)
        if sn not in result:
            result[sn] = {}
        if pk not in result[sn]:
            result[sn][pk] = []
        if len(result[sn][pk]) < top_n:
            entry = {
                'product_code': r.get('product_code') or '',
                'product_name': r.get('product_name') or '',
                'brand': r.get('brand') or '—',
                'category_l1': r.get('category_l1') or '',
                'category_l2': r.get('category_l2') or '',
                'category_l3': r.get('category_l3') or '',
                'qty': r.get('qty') or 0,
                'amount': float(r.get('amount') or 0),
                'settlement': float(r.get('settlement') or 0),
                'tag_amount': float(r.get('tag_amount') or 0),
                'campaign': _lookup_campaign(r.get('product_code') or '', campaigns),
            }
            entry['disc_pct'] = _disc_pct(entry['tag_amount'], entry['settlement'])
            result[sn][pk].append(entry)
    return result


def _top_products_by_group_shop(qs, group_field, top_n=10, campaigns=None):
    """Returns {shop_name: {group_val: [top_products]}} for each shop × group."""
    if campaigns is None:
        campaigns = []
    rows = list(
        qs.values('shop_name', group_field, 'product_code', 'product_name', 'brand',
                  'category_l1', 'category_l2', 'category_l3')
        .annotate(qty=Sum('quantity'), amount=Sum('sales_amount'),
                  settlement=Sum('settlement_amount'), tag_amount=Sum('tag_amount'))
        .order_by('shop_name', group_field, '-amount')
    )
    result: dict = {}
    for r in rows:
        sn = r.get('shop_name') or '—'
        gv = r.get(group_field) or '—'
        if sn not in result:
            result[sn] = {}
        if gv not in result[sn]:
            result[sn][gv] = []
        if len(result[sn][gv]) < top_n:
            entry = {
                'product_code': r.get('product_code') or '',
                'product_name': r.get('product_name') or '',
                'brand': r.get('brand') or '—',
                'category_l1': r.get('category_l1') or '',
                'category_l2': r.get('category_l2') or '',
                'category_l3': r.get('category_l3') or '',
                'qty': r.get('qty') or 0,
                'amount': float(r.get('amount') or 0),
                'settlement': float(r.get('settlement') or 0),
                'tag_amount': float(r.get('tag_amount') or 0),
                'campaign': _lookup_campaign(r.get('product_code') or '', campaigns),
            }
            entry['disc_pct'] = _disc_pct(entry['tag_amount'], entry['settlement'])
            result[sn][gv].append(entry)
    return result


def _by_product(qs, limit=50):
    """Top `limit` products ranked by sales amount."""
    campaigns = _load_campaigns()
    rows = list(
        qs.values('product_code', 'product_name', 'brand',
                  'category_l1', 'category_l2', 'category_l3', 'year', 'season')
        .annotate(qty=Sum('quantity'), amount=Sum('sales_amount'),
                  settlement=Sum('settlement_amount'), tag_amount=Sum('tag_amount'),
                  lines=Count('id'))
        .order_by('-amount')[:limit]
    )
    for r in rows:
        r['disc_pct'] = _disc_pct(r.get('tag_amount'), r.get('settlement'))
        r['amount'] = float(r.get('amount') or 0)
        r['settlement'] = float(r.get('settlement') or 0)
        r['tag_amount'] = float(r.get('tag_amount') or 0)
        r['campaign'] = _lookup_campaign(r.get('product_code') or '', campaigns)
    return rows


# ── Shop Full (Section 2) ──────────────────────────────────────────────────────

def _group_trunc_by_shop(flat_rows, period_field, label_fn, top_by_shop=None):
    """Build {shop_name: [period_dicts_with_cat_groups + top_products]} from annotated DB rows.
    top_by_shop: {shop_name: {period_key_val: [top_products]}} — optional.
    """
    shop_map: dict = {}
    for r in flat_rows:
        sn = r.get('shop_name') or '—'
        pk = r.get(period_field)
        if sn not in shop_map:
            shop_map[sn] = OrderedDict()
        if pk not in shop_map[sn]:
            shop_map[sn][pk] = {
                '_pk': pk,
                'label': label_fn(pk),
                'qty': 0, 'amount': 0.0, 'settlement': 0.0,
                'tag_amount': 0.0, 'lines': 0, '_cat_rows': [],
            }
        p = shop_map[sn][pk]
        p['qty'] += r.get('qty') or 0
        p['amount'] += float(r.get('amount') or 0)
        p['settlement'] += float(r.get('settlement') or 0)
        p['tag_amount'] += float(r.get('tag_amount') or 0)
        p['lines'] += r.get('lines') or 0
        p['_cat_rows'].append({
            'category_l1': r.get('category_l1') or '',
            'category_l2': r.get('category_l2') or '',
            'qty': r.get('qty') or 0,
            'amount': float(r.get('amount') or 0),
            'settlement': float(r.get('settlement') or 0),
            'tag_amount': float(r.get('tag_amount') or 0),
            'lines': r.get('lines') or 0,
        })
    result = {}
    for sn, periods in shop_map.items():
        lst = []
        shop_top = (top_by_shop or {}).get(sn, {})
        for pk_val, p in periods.items():
            raw_pk = p.pop('_pk')
            p['disc_pct'] = _disc_pct(p['tag_amount'], p['settlement'])
            p['cat_groups'] = _build_cat_groups(p.pop('_cat_rows'))
            p['top_products'] = shop_top.get(raw_pk, [])
            lst.append(p)
        result[sn] = lst
    return result


def _by_shop_full(qs):
    """
    Section 2: shop summary + full Section 1 per shop.
    8 DB queries: totals + year + month + week + product_season + vip_grade + brand + top_products.
    Sales season computed from month data (no extra query).
    """
    # 1. Shop totals
    shop_rows = list(
        qs.values('shop_name')
        .annotate(qty=Sum('quantity'), amount=Sum('sales_amount'),
                  settlement=Sum('settlement_amount'), tag_amount=Sum('tag_amount'),
                  lines=Count('id'))
        .order_by('-amount')
    )
    for r in shop_rows:
        r['disc_pct'] = _disc_pct(r.get('tag_amount'), r.get('settlement'))
        r['amount'] = float(r.get('amount') or 0)
        r['settlement'] = float(r.get('settlement') or 0)
        r['tag_amount'] = float(r.get('tag_amount') or 0)

    if not shop_rows:
        return shop_rows

    campaigns = _load_campaigns()

    # 2. Year × cat × shop  +  top products per year per shop
    year_flat = list(
        qs.annotate(year_trunc=TruncYear('sales_date'))
        .values('shop_name', 'year_trunc', 'category_l1', 'category_l2')
        .annotate(qty=Sum('quantity'), amount=Sum('sales_amount'),
                  settlement=Sum('settlement_amount'), tag_amount=Sum('tag_amount'),
                  lines=Count('id'))
        .order_by('shop_name', '-year_trunc', 'category_l1', 'category_l2')
    )
    tp_year_by_shop = _top_products_by_period_shop(qs, TruncYear, 'year_trunc', campaigns=campaigns)
    year_by_shop = _group_trunc_by_shop(
        year_flat, 'year_trunc', lambda d: str(d.year) if d else '—',
        top_by_shop=tp_year_by_shop,
    )

    # 3. Month × cat × shop  +  top products per month per shop
    month_flat = list(
        qs.annotate(month_trunc=TruncMonth('sales_date'))
        .values('shop_name', 'month_trunc', 'category_l1', 'category_l2')
        .annotate(qty=Sum('quantity'), amount=Sum('sales_amount'),
                  settlement=Sum('settlement_amount'), tag_amount=Sum('tag_amount'),
                  lines=Count('id'))
        .order_by('shop_name', '-month_trunc', 'category_l1', 'category_l2')
    )
    tp_month_by_shop = _top_products_by_period_shop(qs, TruncMonth, 'month_trunc', campaigns=campaigns)
    month_by_shop = _group_trunc_by_shop(
        month_flat, 'month_trunc', lambda d: d.strftime('%Y-%m') if d else '—',
        top_by_shop=tp_month_by_shop,
    )

    # Compute sales_season from month_flat (no extra DB query)
    # Also derive top products for each sales_season from tp_month_by_shop
    ss_shop_map: dict = {}
    for r in month_flat:
        sn = r.get('shop_name') or '—'
        m = r.get('month_trunc')
        if not m:
            continue
        sk, label = _sales_season_key(m)
        if sn not in ss_shop_map:
            ss_shop_map[sn] = OrderedDict()
        if sk not in ss_shop_map[sn]:
            ss_shop_map[sn][sk] = {
                'label': label, 'qty': 0, 'amount': 0.0,
                'settlement': 0.0, 'tag_amount': 0.0, 'lines': 0,
                '_cat_rows': [], '_month_keys': [],
            }
        p = ss_shop_map[sn][sk]
        p['qty'] += r.get('qty') or 0
        p['amount'] += float(r.get('amount') or 0)
        p['settlement'] += float(r.get('settlement') or 0)
        p['tag_amount'] += float(r.get('tag_amount') or 0)
        p['lines'] += r.get('lines') or 0
        p['_cat_rows'].append({
            'category_l1': r.get('category_l1') or '',
            'category_l2': r.get('category_l2') or '',
            'qty': r.get('qty') or 0,
            'amount': float(r.get('amount') or 0),
            'settlement': float(r.get('settlement') or 0),
            'tag_amount': float(r.get('tag_amount') or 0),
            'lines': r.get('lines') or 0,
        })
        mk = r.get('month_trunc')
        if mk and mk not in p['_month_keys']:
            p['_month_keys'].append(mk)

    _so = ['M2-4', 'M5-7', 'M8-10', 'M11-1']
    sales_season_by_shop: dict = {}
    for sn, seasons in ss_shop_map.items():
        lst = sorted(seasons.items(), key=lambda x: (-x[0][0], _so.index(x[0][1])))
        result_lst = []
        shop_month_top = tp_month_by_shop.get(sn, {})
        for sk, p in lst:
            p['disc_pct'] = _disc_pct(p['tag_amount'], p['settlement'])
            p['cat_groups'] = _build_cat_groups(p.pop('_cat_rows'))
            # Merge top products from contributing months, re-sort, take top 10
            prod_agg: dict = {}
            for mk in p.pop('_month_keys'):
                for pr in shop_month_top.get(mk, []):
                    key = pr['product_code']
                    if key not in prod_agg:
                        prod_agg[key] = dict(pr)
                    else:
                        prod_agg[key]['qty'] += pr['qty']
                        prod_agg[key]['amount'] += pr['amount']
                        prod_agg[key]['settlement'] += pr['settlement']
                        prod_agg[key]['tag_amount'] += pr['tag_amount']
            sorted_prods = sorted(prod_agg.values(), key=lambda x: -(x.get('amount') or 0))
            for pr in sorted_prods:
                pr['disc_pct'] = _disc_pct(pr.get('tag_amount'), pr.get('settlement'))
            p['top_products'] = sorted_prods[:10]
            result_lst.append(p)
        sales_season_by_shop[sn] = result_lst

    # 4. Week × cat × shop  +  top products per week per shop
    week_flat = list(
        qs.annotate(week_trunc=TruncWeek('sales_date'))
        .values('shop_name', 'week_trunc', 'category_l1', 'category_l2')
        .annotate(qty=Sum('quantity'), amount=Sum('sales_amount'),
                  settlement=Sum('settlement_amount'), tag_amount=Sum('tag_amount'),
                  lines=Count('id'))
        .order_by('shop_name', '-week_trunc', 'category_l1', 'category_l2')
    )
    tp_week_by_shop = _top_products_by_period_shop(qs, TruncWeek, 'week_trunc', campaigns=campaigns)
    week_by_shop = _group_trunc_by_shop(
        week_flat, 'week_trunc',
        lambda d: f"W{d.strftime('%V')} {d.strftime('%Y')}" if d else '—',
        top_by_shop=tp_week_by_shop,
    )

    # 5. Product season × cat × shop  +  top products per product_season per shop
    ps_flat = list(
        qs.values('shop_name', 'year', 'season', 'category_l1', 'category_l2')
        .annotate(qty=Sum('quantity'), amount=Sum('sales_amount'),
                  settlement=Sum('settlement_amount'), tag_amount=Sum('tag_amount'),
                  lines=Count('id'))
        .order_by('shop_name', '-year', 'season', 'category_l1', 'category_l2')
    )
    ps_top_flat = list(
        qs.values('shop_name', 'year', 'season', 'product_code', 'product_name', 'brand')
        .annotate(qty=Sum('quantity'), amount=Sum('sales_amount'),
                  settlement=Sum('settlement_amount'), tag_amount=Sum('tag_amount'))
        .order_by('shop_name', '-year', 'season', '-amount')
    )
    ps_top_by_shop: dict = {}
    for r in ps_top_flat:
        sn = r.get('shop_name') or '—'
        key = (r.get('year'), r.get('season') or '—')
        if sn not in ps_top_by_shop:
            ps_top_by_shop[sn] = {}
        if key not in ps_top_by_shop[sn]:
            ps_top_by_shop[sn][key] = []
        if len(ps_top_by_shop[sn][key]) < 10:
            entry = {
                'product_code': r.get('product_code') or '',
                'product_name': r.get('product_name') or '',
                'brand': r.get('brand') or '—',
                'qty': r.get('qty') or 0,
                'amount': float(r.get('amount') or 0),
                'settlement': float(r.get('settlement') or 0),
                'tag_amount': float(r.get('tag_amount') or 0),
                'campaign': _lookup_campaign(r.get('product_code') or '', campaigns),
            }
            entry['disc_pct'] = _disc_pct(entry['tag_amount'], entry['settlement'])
            ps_top_by_shop[sn][key].append(entry)

    ps_shop_map: dict = {}
    for r in ps_flat:
        sn = r.get('shop_name') or '—'
        yr = r.get('year')
        se = r.get('season') or '—'
        key = (yr, se)
        label = f"{yr} {se}" if yr else (se or '—')
        if sn not in ps_shop_map:
            ps_shop_map[sn] = OrderedDict()
        if key not in ps_shop_map[sn]:
            ps_shop_map[sn][key] = {
                'label': label, 'qty': 0, 'amount': 0.0,
                'settlement': 0.0, 'tag_amount': 0.0, 'lines': 0, '_cat_rows': [],
            }
        p = ps_shop_map[sn][key]
        p['qty'] += r.get('qty') or 0
        p['amount'] += float(r.get('amount') or 0)
        p['settlement'] += float(r.get('settlement') or 0)
        p['tag_amount'] += float(r.get('tag_amount') or 0)
        p['lines'] += r.get('lines') or 0
        p['_cat_rows'].append({
            'category_l1': r.get('category_l1') or '',
            'category_l2': r.get('category_l2') or '',
            'qty': r.get('qty') or 0,
            'amount': float(r.get('amount') or 0),
            'settlement': float(r.get('settlement') or 0),
            'tag_amount': float(r.get('tag_amount') or 0),
            'lines': r.get('lines') or 0,
        })
    ps_by_shop: dict = {}
    for sn, seasons in ps_shop_map.items():
        lst = []
        shop_ps_top = ps_top_by_shop.get(sn, {})
        for key, p in seasons.items():
            p['disc_pct'] = _disc_pct(p['tag_amount'], p['settlement'])
            p['cat_groups'] = _build_cat_groups(p.pop('_cat_rows'))
            p['top_products'] = shop_ps_top.get(key, [])
            lst.append(p)
        ps_by_shop[sn] = lst

    # 6. VIP Grade × cat × shop  +  top products per grade per shop
    tp_vip_by_shop = _top_products_by_group_shop(qs, 'transaction__customer__vip_grade', campaigns=campaigns)
    vip_flat = list(
        qs.values('shop_name', 'transaction__customer__vip_grade', 'category_l1', 'category_l2')
        .annotate(qty=Sum('quantity'), amount=Sum('sales_amount'),
                  settlement=Sum('settlement_amount'), tag_amount=Sum('tag_amount'),
                  lines=Count('id'))
        .order_by('shop_name', 'transaction__customer__vip_grade', 'category_l1', 'category_l2')
    )
    vip_shop_map: dict = {}
    for r in vip_flat:
        sn = r.get('shop_name') or '—'
        grade = r.get('transaction__customer__vip_grade') or 'No Grade'
        if sn not in vip_shop_map:
            vip_shop_map[sn] = {}
        if grade not in vip_shop_map[sn]:
            vip_shop_map[sn][grade] = {
                'grade': grade, 'qty': 0, 'amount': 0.0,
                'settlement': 0.0, 'tag_amount': 0.0, 'lines': 0, '_cat_rows': [],
            }
        p = vip_shop_map[sn][grade]
        p['qty'] += r.get('qty') or 0
        p['amount'] += float(r.get('amount') or 0)
        p['settlement'] += float(r.get('settlement') or 0)
        p['tag_amount'] += float(r.get('tag_amount') or 0)
        p['lines'] += r.get('lines') or 0
        p['_cat_rows'].append({
            'category_l1': r.get('category_l1') or '',
            'category_l2': r.get('category_l2') or '',
            'qty': r.get('qty') or 0, 'amount': float(r.get('amount') or 0),
            'settlement': float(r.get('settlement') or 0),
            'tag_amount': float(r.get('tag_amount') or 0), 'lines': r.get('lines') or 0,
        })
    vip_by_shop: dict = {}
    for sn, grades in vip_shop_map.items():
        shop_vip_top = tp_vip_by_shop.get(sn, {})
        lst = sorted(grades.values(), key=lambda x: GRADE_ORDER.get(x['grade'], 99))
        for p in lst:
            p['disc_pct'] = _disc_pct(p['tag_amount'], p['settlement'])
            p['cat_groups'] = _build_cat_groups(p.pop('_cat_rows'))
            raw_grade = p['grade']
            # _top_products_by_group_shop stores None vip_grade as '—'
            lookup_key = None if raw_grade == 'No Grade' else raw_grade
            p['top_products'] = (
                shop_vip_top.get(lookup_key, []) or
                shop_vip_top.get(raw_grade, []) or
                shop_vip_top.get('—', [])
            )
        vip_by_shop[sn] = lst

    # 7. Brand × cat × shop  +  top products per brand per shop
    tp_brand_by_shop = _top_products_by_group_shop(qs, 'brand', campaigns=campaigns)
    brand_flat = list(
        qs.values('shop_name', 'brand', 'category_l1', 'category_l2')
        .annotate(qty=Sum('quantity'), amount=Sum('sales_amount'),
                  settlement=Sum('settlement_amount'), tag_amount=Sum('tag_amount'),
                  lines=Count('id'))
        .order_by('shop_name', 'brand', 'category_l1', 'category_l2')
    )
    brand_shop_map: dict = {}
    for r in brand_flat:
        sn = r.get('shop_name') or '—'
        br = r.get('brand') or '—'
        if sn not in brand_shop_map:
            brand_shop_map[sn] = {}
        if br not in brand_shop_map[sn]:
            brand_shop_map[sn][br] = {
                'brand': br, 'qty': 0, 'amount': 0.0,
                'settlement': 0.0, 'tag_amount': 0.0, 'lines': 0, '_cat_rows': [],
            }
        p = brand_shop_map[sn][br]
        p['qty'] += r.get('qty') or 0
        p['amount'] += float(r.get('amount') or 0)
        p['settlement'] += float(r.get('settlement') or 0)
        p['tag_amount'] += float(r.get('tag_amount') or 0)
        p['lines'] += r.get('lines') or 0
        p['_cat_rows'].append({
            'category_l1': r.get('category_l1') or '',
            'category_l2': r.get('category_l2') or '',
            'qty': r.get('qty') or 0, 'amount': float(r.get('amount') or 0),
            'settlement': float(r.get('settlement') or 0),
            'tag_amount': float(r.get('tag_amount') or 0), 'lines': r.get('lines') or 0,
        })
    brand_by_shop: dict = {}
    for sn, brands in brand_shop_map.items():
        shop_brand_top = tp_brand_by_shop.get(sn, {})
        lst = sorted(brands.values(), key=lambda x: -(x.get('amount') or 0))
        for p in lst:
            p['disc_pct'] = _disc_pct(p['tag_amount'], p['settlement'])
            p['cat_groups'] = _build_cat_groups(p.pop('_cat_rows'))
            p['top_products'] = shop_brand_top.get(p['brand'], [])
        brand_by_shop[sn] = lst

    # 8. Top products × shop
    tp_flat = list(
        qs.values('shop_name', 'product_code', 'product_name', 'brand')
        .annotate(qty=Sum('quantity'), amount=Sum('sales_amount'),
                  settlement=Sum('settlement_amount'), tag_amount=Sum('tag_amount'),
                  lines=Count('id'))
        .order_by('shop_name', '-amount')
    )
    tp_by_shop: dict = {}
    for r in tp_flat:
        sn = r.get('shop_name') or '—'
        if sn not in tp_by_shop:
            tp_by_shop[sn] = []
        if len(tp_by_shop[sn]) < 15:
            entry = {
                'product_code': r.get('product_code') or '',
                'product_name': r.get('product_name') or '',
                'brand': r.get('brand') or '—',
                'qty': r.get('qty') or 0,
                'amount': float(r.get('amount') or 0),
                'settlement': float(r.get('settlement') or 0),
                'tag_amount': float(r.get('tag_amount') or 0),
                'lines': r.get('lines') or 0,
                'campaign': _lookup_campaign(r.get('product_code') or '', campaigns),
            }
            entry['disc_pct'] = _disc_pct(entry['tag_amount'], entry['settlement'])
            tp_by_shop[sn].append(entry)

    # Compute category (flat total) per shop from month_flat
    cat_shop_map: dict = {}
    for r in month_flat:
        sn = r.get('shop_name') or '—'
        l1 = r.get('category_l1') or '—'
        l2 = r.get('category_l2') or '—'
        key = (l1, l2)
        if sn not in cat_shop_map:
            cat_shop_map[sn] = {}
        if key not in cat_shop_map[sn]:
            cat_shop_map[sn][key] = {
                'category_l1': l1, 'category_l2': l2,
                'qty': 0, 'amount': 0.0, 'settlement': 0.0, 'tag_amount': 0.0, 'lines': 0,
            }
        p = cat_shop_map[sn][key]
        p['qty'] += r.get('qty') or 0
        p['amount'] += float(r.get('amount') or 0)
        p['settlement'] += float(r.get('settlement') or 0)
        p['tag_amount'] += float(r.get('tag_amount') or 0)
        p['lines'] += r.get('lines') or 0
    cat_groups_by_shop: dict = {}
    for sn, cats in cat_shop_map.items():
        flat = list(cats.values())
        for c in flat:
            c['disc_pct'] = _disc_pct(c.get('tag_amount'), c.get('settlement'))
        cat_groups_by_shop[sn] = _build_cat_groups(flat)

    # Attach everything to shop_rows
    for r in shop_rows:
        sn = r.get('shop_name') or '—'
        r['by_year']          = year_by_shop.get(sn, [])
        r['by_month']         = month_by_shop.get(sn, [])
        r['by_week']          = week_by_shop.get(sn, [])
        r['by_sales_season']  = sales_season_by_shop.get(sn, [])
        r['by_product_season'] = ps_by_shop.get(sn, [])
        r['by_vip_grade']     = vip_by_shop.get(sn, [])
        r['by_brand']         = brand_by_shop.get(sn, [])
        r['by_category']      = cat_groups_by_shop.get(sn, [])
        r['top_products']     = tp_by_shop.get(sn, [])

    return shop_rows


def get_product_tab(tab: str, date_from=None, date_to=None,
                    shop_group=None, shop_name=None) -> dict:
    """Return product analytics data for one tab. Cached 5 min."""
    key = _cache_key(tab, date_from, date_to, shop_group, shop_name)
    cached = cache.get(key)
    if cached:
        return cached

    qs = _base_qs(date_from, date_to, shop_group, shop_name)
    overview = _overview(qs)
    if not overview.get('total_lines'):
        return {}

    tab_data = {}
    if tab == 'month':
        tab_data['by_month'] = _by_month(qs)
    elif tab == 'year':
        tab_data['by_year'] = _by_year(qs)
    elif tab == 'week':
        tab_data['by_week'] = _by_week(qs)
    elif tab == 'sales_season':
        tab_data['by_sales_season'] = _by_sales_season(qs)
    elif tab == 'product_season':
        tab_data['by_product_season'] = _by_product_season(qs)
    elif tab == 'vip_grade':
        tab_data['by_vip_grade'] = _by_vip_grade(qs)
    elif tab == 'brand':
        tab_data['by_brand'] = _by_brand(qs)
    elif tab == 'category':
        tab_data['by_category'] = _by_category(qs)
        tab_data['campaign_groups'] = _by_product_campaign(qs)
        tab_data['top_products'] = _by_product(qs, limit=20)
    elif tab == 'campaign':
        tab_data['campaign_groups'] = _by_product_campaign(qs)
        tab_data['top_products'] = _by_product(qs, limit=20)
    elif tab == 'shop':
        tab_data['by_shop'] = _by_shop_full(qs)
    elif tab == 'product':
        tab_data['by_product'] = _by_product(qs)

    result = {'overview': overview, **tab_data}
    cache.set(key, result, _TTL)
    logger.info("product_tab %s loaded: lines=%d", tab, overview.get('total_lines', 0),
                extra={"step": "product_analytics"})
    return result
