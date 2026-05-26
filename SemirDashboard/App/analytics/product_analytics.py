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
    'product_season', 'vip_grade', 'brand', 'category', 'campaign', 'shop', 'shop_card', 'product',
    'top_by_brand', 'top_by_campaign',
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


def _top_products_by_period(qs, trunc_fn, period_key, top_n=50, campaigns=None):
    """Query top N products per period.
    Returns ({period_val: [top_products]}, {period_val: [camp_rows]}, {period_val: {camp: [top_products]}}).
    Rows are DB-ordered by -amount within period, so first top_n seen per (period,camp) are correct.
    """
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
    camp_agg: dict = {}   # {pk: {(camp,l1,l2,l3): aggregated_row}}
    top_camp: dict = {}   # {pk: {camp: [top_products]}}
    for r in rows:
        pk = r[period_key]
        camp = _lookup_campaign(r.get('product_code') or '', campaigns)
        amt  = float(r.get('amount') or 0)
        sett = float(r.get('settlement') or 0)
        tag  = float(r.get('tag_amount') or 0)
        l1 = r.get('category_l1') or ''
        l2 = r.get('category_l2') or ''
        l3 = r.get('category_l3') or ''

        # ── Overall top N per period ──
        if pk not in by_period:
            by_period[pk] = []
        if len(by_period[pk]) < top_n:
            entry = {
                'product_code': r.get('product_code') or '',
                'product_name': r.get('product_name') or '',
                'brand': r.get('brand') or '—',
                'category_l1': l1, 'category_l2': l2, 'category_l3': l3,
                'qty': r.get('qty') or 0, 'lines': r.get('lines') or 0,
                'amount': amt, 'settlement': sett, 'tag_amount': tag,
                'campaign': camp,
            }
            entry['disc_pct'] = _disc_pct(tag, sett)
            by_period[pk].append(entry)

        # ── Top N per (period, campaign) ──
        if pk not in top_camp:
            top_camp[pk] = {}
        if camp not in top_camp[pk]:
            top_camp[pk][camp] = []
        if len(top_camp[pk][camp]) < top_n:
            ce = {
                'product_code': r.get('product_code') or '',
                'product_name': r.get('product_name') or '',
                'brand': r.get('brand') or '—',
                'category_l1': l1, 'category_l2': l2, 'category_l3': l3,
                'qty': r.get('qty') or 0, 'lines': r.get('lines') or 0,
                'amount': amt, 'settlement': sett, 'tag_amount': tag,
                'campaign': camp,
            }
            ce['disc_pct'] = _disc_pct(tag, sett)
            top_camp[pk][camp].append(ce)

        # ── Campaign aggregation (all rows) ──
        if pk not in camp_agg:
            camp_agg[pk] = {}
        ckey = (camp, l1, l2, l3)
        if ckey not in camp_agg[pk]:
            camp_agg[pk][ckey] = {'campaign': camp, 'category_l1': l1, 'category_l2': l2,
                                   'category_l3': l3, 'qty': 0, 'amount': 0.0,
                                   'settlement': 0.0, 'tag_amount': 0.0, 'lines': 0}
        e = camp_agg[pk][ckey]
        e['qty'] += r.get('qty') or 0
        e['amount'] += amt
        e['settlement'] += sett
        e['tag_amount'] += tag
        e['lines'] += (r.get('lines') or 0)

    camp_rows_by_period = {pk: list(v.values()) for pk, v in camp_agg.items()}
    return by_period, camp_rows_by_period, top_camp


def _top_products_by_group(qs, group_field, top_n=50, campaigns=None):
    """Query top N products per group value.
    Returns ({group_val: [top_products]}, {group_val: [camp_rows]}, {group_val: {camp: [top_products]}}).
    Rows are DB-ordered by -amount within group, so first top_n seen per (group,camp) are correct.
    """
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
    top_camp: dict = {}   # {gv: {camp: [top_products]}}
    for r in rows:
        gv   = r.get(group_field) or '—'
        camp = _lookup_campaign(r.get('product_code') or '', campaigns)
        amt  = float(r.get('amount') or 0)
        sett = float(r.get('settlement') or 0)
        tag  = float(r.get('tag_amount') or 0)
        l1 = r.get('category_l1') or ''
        l2 = r.get('category_l2') or ''
        l3 = r.get('category_l3') or ''

        # ── Overall top N per group ──
        if gv not in by_group:
            by_group[gv] = []
        if len(by_group[gv]) < top_n:
            entry = {
                'product_code': r.get('product_code') or '',
                'product_name': r.get('product_name') or '',
                'brand': r.get('brand') or '—',
                'category_l1': l1, 'category_l2': l2, 'category_l3': l3,
                'qty': r.get('qty') or 0,
                'amount': amt, 'settlement': sett, 'tag_amount': tag,
                'lines': r.get('lines') or 0, 'campaign': camp,
            }
            entry['disc_pct'] = _disc_pct(tag, sett)
            by_group[gv].append(entry)

        # ── Top N per (group, campaign) ──
        if gv not in top_camp:
            top_camp[gv] = {}
        if camp not in top_camp[gv]:
            top_camp[gv][camp] = []
        if len(top_camp[gv][camp]) < top_n:
            ce = {
                'product_code': r.get('product_code') or '',
                'product_name': r.get('product_name') or '',
                'brand': r.get('brand') or '—',
                'category_l1': l1, 'category_l2': l2, 'category_l3': l3,
                'qty': r.get('qty') or 0,
                'amount': amt, 'settlement': sett, 'tag_amount': tag,
                'lines': r.get('lines') or 0, 'campaign': camp,
            }
            ce['disc_pct'] = _disc_pct(tag, sett)
            top_camp[gv][camp].append(ce)

        # ── Campaign aggregation (all rows) ──
        ckey = (camp, l1, l2, l3)
        if gv not in camp_agg:
            camp_agg[gv] = {}
        if ckey not in camp_agg[gv]:
            camp_agg[gv][ckey] = {'campaign': camp, 'category_l1': l1, 'category_l2': l2,
                                   'category_l3': l3, 'qty': 0, 'amount': 0.0,
                                   'settlement': 0.0, 'tag_amount': 0.0, 'lines': 0}
        e = camp_agg[gv][ckey]
        e['qty'] += r.get('qty') or 0
        e['amount'] += amt
        e['settlement'] += sett
        e['tag_amount'] += tag
        e['lines'] += (r.get('lines') or 0)

    camp_rows_by_group = {gv: list(v.values()) for gv, v in camp_agg.items()}
    return by_group, camp_rows_by_group, top_camp


def _period_with_cat(qs, trunc_fn, label_fn, period_key, top_n=50):
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

    # Query 2: period × product (top N overall + top N per campaign + campaign aggregation)
    top_by_period, camp_rows_by_period, top_camp_by_period = _top_products_by_period(
        qs, trunc_fn, period_key, top_n=top_n)

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
        p['campaign_groups'] = _build_campaign_groups(
            camp_rows_by_period.get(pk, []),
            top_by_camp=top_camp_by_period.get(pk))
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


def _by_sales_season(qs, top_n=50):
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
        # Derive top N per campaign from sorted_prods (already amount-desc)
        top_by_camp: dict = {}
        for pr in sorted_prods:
            c = pr.get('campaign') or ''
            if c not in top_by_camp:
                top_by_camp[c] = []
            if len(top_by_camp[c]) < top_n:
                top_by_camp[c].append(pr)
        p['campaign_groups'] = _build_campaign_groups(camp_rows, top_by_camp=top_by_camp)
        result.append(p)
    return result


def _by_product_season(qs, top_n=50):
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
        amt  = float(r.get('amount') or 0)
        sett = float(r.get('settlement') or 0)
        tag  = float(r.get('tag_amount') or 0)
        entry = {
            'product_code': r.get('product_code') or '',
            'product_name': r.get('product_name') or '',
            'brand':        r.get('brand') or '—',
            'category_l1':  r.get('category_l1') or '',
            'category_l2':  r.get('category_l2') or '',
            'category_l3':  r.get('category_l3') or '',
            'qty':          r.get('qty') or 0,
            'lines':        r.get('lines') or 0,
            'amount': amt, 'settlement': sett, 'tag_amount': tag,
        }
        entry['disc_pct'] = _disc_pct(tag, sett)
        entry['campaign'] = _lookup_campaign(entry['product_code'], campaigns)
        all_rows_by_key[key].append(entry)
        if len(top_by_key[key]) < top_n:
            top_by_key[key].append(entry)

    result = []
    for key, p in seasons.items():
        p['disc_pct'] = _disc_pct(p['tag_amount'], p['settlement'])
        p['cat_groups'] = _build_cat_groups(p.pop('_cat_rows'))
        p['top_products'] = top_by_key.get(key, [])
        key_rows = all_rows_by_key.get(key, [])
        camp_rows = _derive_campaign_rows(key_rows, campaigns)
        # Derive top N per campaign from key_rows (already amount-desc from DB)
        top_by_camp: dict = {}
        for pr in key_rows:
            c = pr.get('campaign') or ''
            if c not in top_by_camp:
                top_by_camp[c] = []
            if len(top_by_camp[c]) < top_n:
                top_by_camp[c].append(pr)
        p['campaign_groups'] = _build_campaign_groups(camp_rows, top_by_camp=top_by_camp)
        result.append(p)
    return result


def _by_vip_grade(qs, top_n=50):
    """Group by VIP grade via SaleDetail → SalesTransaction → Customer."""
    rows = list(
        qs.values('transaction__customer__vip_grade', 'category_l1', 'category_l2', 'category_l3')
        .annotate(qty=Sum('quantity'), amount=Sum('sales_amount'),
                  settlement=Sum('settlement_amount'), tag_amount=Sum('tag_amount'),
                  lines=Count('id'))
        .order_by('transaction__customer__vip_grade', 'category_l1', 'category_l2', 'category_l3')
    )
    top_by_grade, camp_rows_by_grade, top_camp_by_grade = _top_products_by_group(
        qs, 'transaction__customer__vip_grade', top_n=top_n)

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
        top_by_camp = (
            top_camp_by_grade.get(lookup_key) or
            top_camp_by_grade.get(raw_grade) or
            top_camp_by_grade.get('—') or {}
        )
        p['campaign_groups'] = _build_campaign_groups(camp_rows, top_by_camp=top_by_camp)
    return result


def _by_brand(qs, top_n=50):
    """Group by brand with category drill-down and top products."""
    rows = list(
        qs.values('brand', 'category_l1', 'category_l2', 'category_l3')
        .annotate(qty=Sum('quantity'), amount=Sum('sales_amount'),
                  settlement=Sum('settlement_amount'), tag_amount=Sum('tag_amount'),
                  lines=Count('id'))
        .order_by('brand', 'category_l1', 'category_l2', 'category_l3')
    )
    top_by_brand, camp_rows_by_brand, top_camp_by_brand = _top_products_by_group(qs, 'brand', top_n=top_n)

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
        p['campaign_groups'] = _build_campaign_groups(
            camp_rows_by_brand.get(p['brand'], []),
            top_by_camp=top_camp_by_brand.get(p['brand']))
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


def _build_campaign_groups(rows, top_by_camp=None):
    """
    Group [{campaign, category_l1, category_l2, category_l3, qty, amount, ...}]
    → [{campaign, l1_groups:[{l1, l2_groups:[{l2, rows, subtotal}], subtotal}], subtotal, top_products:[]}]
    Campaign '' → displayed as 'Not Assigned'.
    top_by_camp: optional {campaign_name: [top_products]} attached to each group.
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
            'top_products': (top_by_camp or {}).get(camp, []),
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


def _by_product_campaign(qs, top_n=50):
    """Campaign → L1 → L2 → L3 breakdown. Campaign derived from product_code prefix.
    Single DB query: includes product_name + brand so top products need no second fetch.
    Rows sorted by -amount so first top_n seen per campaign are correct top products.
    """
    campaigns = _load_campaigns()
    rows = list(
        qs.values('product_code', 'product_name', 'brand',
                  'category_l1', 'category_l2', 'category_l3')
        .annotate(qty=Sum('quantity'), amount=Sum('sales_amount'),
                  settlement=Sum('settlement_amount'), tag_amount=Sum('tag_amount'),
                  lines=Count('id'))
        .order_by('-amount')
    )
    for r in rows:
        r['amount']     = float(r.get('amount') or 0)
        r['settlement'] = float(r.get('settlement') or 0)
        r['tag_amount'] = float(r.get('tag_amount') or 0)

    # Build top-N per campaign and campaign aggregation in one pass
    by_camp_top: dict = {}
    for r in rows:
        camp = _lookup_campaign(r.get('product_code') or '', campaigns)
        r['campaign'] = camp  # cache for _derive_campaign_rows reuse
        if camp not in by_camp_top:
            by_camp_top[camp] = []
        if len(by_camp_top[camp]) < top_n:
            by_camp_top[camp].append({
                'product_code': r.get('product_code') or '',
                'product_name': r.get('product_name') or '',
                'brand':        r.get('brand') or '—',
                'category_l1':  r.get('category_l1') or '',
                'category_l2':  r.get('category_l2') or '',
                'category_l3':  r.get('category_l3') or '',
                'qty':          r.get('qty') or 0,
                'amount':       r['amount'],
                'settlement':   r['settlement'],
                'tag_amount':   r['tag_amount'],
                'lines':        r.get('lines') or 0,
                'campaign':     camp,
                'disc_pct':     _disc_pct(r['tag_amount'], r['settlement']),
            })

    camp_rows = _derive_campaign_rows(rows, campaigns)  # reuses r['campaign'] set above
    return _build_campaign_groups(camp_rows, top_by_camp=by_camp_top)


def _top_products_by_period_shop(qs, trunc_fn, period_key, top_n=10, campaigns=None):
    """Returns ({shop: {period: [top_products]}}, {shop: {period: [camp_rows]}},
               {shop: {period: {camp: [top_products]}}}) for each shop × period.
    camp_rows covers ALL products (not just top_n) so campaign_groups are complete.
    Rows are DB-ordered by -amount within (shop, period), so first top_n per (shop,period,camp) are correct.
    """
    if campaigns is None:
        campaigns = []
    rows = list(
        qs.annotate(**{period_key: trunc_fn('sales_date')})
        .values('shop_name', period_key, 'product_code', 'product_name', 'brand',
                'category_l1', 'category_l2', 'category_l3')
        .annotate(qty=Sum('quantity'), amount=Sum('sales_amount'),
                  settlement=Sum('settlement_amount'), tag_amount=Sum('tag_amount'),
                  lines=Count('id'))
        .order_by('shop_name', f'-{period_key}', '-amount')
    )
    result: dict = {}
    camp_agg: dict = {}   # {sn: {period_val: {(camp,l1,l2,l3): agg_row}}}
    top_camp: dict = {}   # {sn: {period_val: {camp: [top_products]}}}
    for r in rows:
        sn   = r.get('shop_name') or '—'
        pk   = r.get(period_key)
        camp = _lookup_campaign(r.get('product_code') or '', campaigns)
        amt  = float(r.get('amount') or 0)
        sett = float(r.get('settlement') or 0)
        tag  = float(r.get('tag_amount') or 0)
        l1 = r.get('category_l1') or ''
        l2 = r.get('category_l2') or ''
        l3 = r.get('category_l3') or ''

        # ── Overall top N per (shop, period) ──
        result.setdefault(sn, {}).setdefault(pk, [])
        if len(result[sn][pk]) < top_n:
            entry = {
                'product_code': r.get('product_code') or '',
                'product_name': r.get('product_name') or '',
                'brand': r.get('brand') or '—',
                'category_l1': l1, 'category_l2': l2, 'category_l3': l3,
                'qty': r.get('qty') or 0, 'lines': r.get('lines') or 0,
                'amount': amt, 'settlement': sett, 'tag_amount': tag,
                'campaign': camp,
            }
            entry['disc_pct'] = _disc_pct(tag, sett)
            result[sn][pk].append(entry)

        # ── Top N per (shop, period, campaign) ──
        top_camp.setdefault(sn, {}).setdefault(pk, {}).setdefault(camp, [])
        if len(top_camp[sn][pk][camp]) < top_n:
            ce = {
                'product_code': r.get('product_code') or '',
                'product_name': r.get('product_name') or '',
                'brand': r.get('brand') or '—',
                'category_l1': l1, 'category_l2': l2, 'category_l3': l3,
                'qty': r.get('qty') or 0, 'lines': r.get('lines') or 0,
                'amount': amt, 'settlement': sett, 'tag_amount': tag,
                'campaign': camp,
            }
            ce['disc_pct'] = _disc_pct(tag, sett)
            top_camp[sn][pk][camp].append(ce)

        # ── Campaign aggregation (ALL rows) ──
        camp_agg.setdefault(sn, {}).setdefault(pk, {})
        ckey = (camp, l1, l2, l3)
        if ckey not in camp_agg[sn][pk]:
            camp_agg[sn][pk][ckey] = {'campaign': camp, 'category_l1': l1,
                                       'category_l2': l2, 'category_l3': l3,
                                       'qty': 0, 'amount': 0.0, 'settlement': 0.0,
                                       'tag_amount': 0.0, 'lines': 0}
        e = camp_agg[sn][pk][ckey]
        e['qty']        += r.get('qty') or 0
        e['amount']     += amt
        e['settlement'] += sett
        e['tag_amount'] += tag
        e['lines']      += r.get('lines') or 0

    camp_rows_by_shop = {sn: {pk: list(v.values()) for pk, v in periods.items()}
                         for sn, periods in camp_agg.items()}
    return result, camp_rows_by_shop, top_camp


def _top_products_by_group_shop(qs, group_field, top_n=10, campaigns=None):
    """Returns ({shop: {group: [top_products]}}, {shop: {group: [camp_rows]}},
               {shop: {group: {camp: [top_products]}}}) for each shop × group.
    camp_rows covers ALL products (not just top_n) so campaign_groups are complete.
    Rows are DB-ordered by -amount within (shop, group), so first top_n per (shop,group,camp) are correct.
    """
    if campaigns is None:
        campaigns = []
    rows = list(
        qs.values('shop_name', group_field, 'product_code', 'product_name', 'brand',
                  'category_l1', 'category_l2', 'category_l3')
        .annotate(qty=Sum('quantity'), amount=Sum('sales_amount'),
                  settlement=Sum('settlement_amount'), tag_amount=Sum('tag_amount'),
                  lines=Count('id'))
        .order_by('shop_name', group_field, '-amount')
    )
    result: dict = {}
    camp_agg: dict = {}   # {sn: {group_val: {(camp,l1,l2,l3): agg_row}}}
    top_camp: dict = {}   # {sn: {group_val: {camp: [top_products]}}}
    for r in rows:
        sn   = r.get('shop_name') or '—'
        gv   = r.get(group_field) or '—'
        camp = _lookup_campaign(r.get('product_code') or '', campaigns)
        amt  = float(r.get('amount') or 0)
        sett = float(r.get('settlement') or 0)
        tag  = float(r.get('tag_amount') or 0)
        l1 = r.get('category_l1') or ''
        l2 = r.get('category_l2') or ''
        l3 = r.get('category_l3') or ''

        # ── Overall top N per (shop, group) ──
        result.setdefault(sn, {}).setdefault(gv, [])
        if len(result[sn][gv]) < top_n:
            entry = {
                'product_code': r.get('product_code') or '',
                'product_name': r.get('product_name') or '',
                'brand': r.get('brand') or '—',
                'category_l1': l1, 'category_l2': l2, 'category_l3': l3,
                'qty': r.get('qty') or 0, 'lines': r.get('lines') or 0,
                'amount': amt, 'settlement': sett, 'tag_amount': tag,
                'campaign': camp,
            }
            entry['disc_pct'] = _disc_pct(tag, sett)
            result[sn][gv].append(entry)

        # ── Top N per (shop, group, campaign) ──
        top_camp.setdefault(sn, {}).setdefault(gv, {}).setdefault(camp, [])
        if len(top_camp[sn][gv][camp]) < top_n:
            ce = {
                'product_code': r.get('product_code') or '',
                'product_name': r.get('product_name') or '',
                'brand': r.get('brand') or '—',
                'category_l1': l1, 'category_l2': l2, 'category_l3': l3,
                'qty': r.get('qty') or 0, 'lines': r.get('lines') or 0,
                'amount': amt, 'settlement': sett, 'tag_amount': tag,
                'campaign': camp,
            }
            ce['disc_pct'] = _disc_pct(tag, sett)
            top_camp[sn][gv][camp].append(ce)

        # ── Campaign aggregation (ALL rows) ──
        ckey = (camp, l1, l2, l3)
        camp_agg.setdefault(sn, {}).setdefault(gv, {})
        if ckey not in camp_agg[sn][gv]:
            camp_agg[sn][gv][ckey] = {'campaign': camp, 'category_l1': l1,
                                       'category_l2': l2, 'category_l3': l3,
                                       'qty': 0, 'amount': 0.0, 'settlement': 0.0,
                                       'tag_amount': 0.0, 'lines': 0}
        e = camp_agg[sn][gv][ckey]
        e['qty']        += r.get('qty') or 0
        e['amount']     += amt
        e['settlement'] += sett
        e['tag_amount'] += tag
        e['lines']      += r.get('lines') or 0

    camp_rows_by_shop = {sn: {gv: list(v.values()) for gv, v in groups.items()}
                         for sn, groups in camp_agg.items()}
    return result, camp_rows_by_shop, top_camp


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

def _group_trunc_by_shop(flat_rows, period_field, label_fn, top_by_shop=None,
                         camp_rows_by_shop=None, top_camp_by_shop=None):
    """Build {shop_name: [period_dicts_with_cat_groups + top_products + campaign_groups]} from annotated DB rows.
    top_by_shop: {shop_name: {period_key_val: [top_products]}} — optional.
    camp_rows_by_shop: {shop_name: {period_key_val: [camp_rows]}} — optional.
    top_camp_by_shop: {shop_name: {period_key_val: {camp: [top_products]}}} — optional.
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
            'category_l3': r.get('category_l3') or '',
            'qty': r.get('qty') or 0,
            'amount': float(r.get('amount') or 0),
            'settlement': float(r.get('settlement') or 0),
            'tag_amount': float(r.get('tag_amount') or 0),
            'lines': r.get('lines') or 0,
        })
    result = {}
    for sn, periods in shop_map.items():
        lst = []
        shop_top       = (top_by_shop or {}).get(sn, {})
        shop_camp      = (camp_rows_by_shop or {}).get(sn, {})
        shop_top_camp  = (top_camp_by_shop or {}).get(sn, {})
        for pk_val, p in periods.items():
            raw_pk = p.pop('_pk')
            p['disc_pct'] = _disc_pct(p['tag_amount'], p['settlement'])
            p['cat_groups'] = _build_cat_groups(p.pop('_cat_rows'))
            p['top_products'] = shop_top.get(raw_pk, [])
            p['campaign_groups'] = _build_campaign_groups(
                shop_camp.get(raw_pk, []),
                top_by_camp=shop_top_camp.get(raw_pk))
            lst.append(p)
        result[sn] = lst
    return result


def _by_shop_full(qs):
    """Shop summary KPIs only — 1 DB query. Per-shop detail lazy-loaded via shop_card tab."""
    rows = list(
        qs.values('shop_name')
        .annotate(qty=Sum('quantity'), amount=Sum('sales_amount'),
                  settlement=Sum('settlement_amount'), tag_amount=Sum('tag_amount'),
                  lines=Count('id'))
        .order_by('-amount')
    )
    for r in rows:
        r['amount']     = float(r.get('amount') or 0)
        r['settlement'] = float(r.get('settlement') or 0)
        r['tag_amount'] = float(r.get('tag_amount') or 0)
        r['disc_pct']   = _disc_pct(r['tag_amount'], r['settlement'])
    return rows


def _by_shop_card(qs, top_n=50):
    """All detail for one shop (qs already filtered). Reuses top-level tab functions.
    Returns same keys as global get_product_tab so _shop_card_body.html can use data.* directly.
    """
    return {
        'by_year':           _period_with_cat(qs, TruncYear,
                                 lambda d: str(d.year) if d else '—', 'year_trunc', top_n=top_n),
        'by_month':          _period_with_cat(qs, TruncMonth,
                                 lambda d: d.strftime('%Y-%m') if d else '—', 'month_trunc', top_n=top_n),
        'by_week':           _period_with_cat(qs, TruncWeek,
                                 lambda d: f"W{d.strftime('%V')} {d.strftime('%Y')}" if d else '—',
                                 'week_trunc', top_n=top_n),
        'by_sales_season':   _by_sales_season(qs, top_n=top_n),
        'by_product_season': _by_product_season(qs, top_n=top_n),
        'by_vip_grade':      _by_vip_grade(qs, top_n=top_n),
        'by_brand':          _by_brand(qs, top_n=top_n),
        'by_category':       _by_category(qs),
        'by_product':        _by_product(qs, limit=top_n),
        'campaign_groups':   _by_product_campaign(qs, top_n=top_n),
        'top_by_brand':      _top_by_brand(qs, top_n=top_n),
        'top_by_campaign':   _top_by_campaign(qs, top_n=top_n),
    }




def _top_by_brand(qs, top_n=50):
    """Top N products per brand, one DB query. Returns [{brand, top_products, total_amount}]."""
    campaigns = _load_campaigns()
    by_brand, camp_rows_by_brand, __ = _top_products_by_group(qs, 'brand', top_n=top_n, campaigns=campaigns)
    result = []
    for brand, products in by_brand.items():
        # Sum from camp_rows (all camp×l1×l2×l3 rows) for correct brand total, not just top-N
        total_amount = sum(r['amount'] for r in camp_rows_by_brand.get(brand, []))
        result.append({'brand': brand or '—', 'top_products': products, 'total_amount': total_amount})
    return sorted(result, key=lambda x: -x['total_amount'])


def _top_by_campaign(qs, top_n=50):
    """Top N products per campaign (derived from product_code prefix), one DB query.
    Returns [{campaign, top_products, total_amount}] sorted by total_amount desc.
    Products not matching any campaign are grouped as '' (displayed as 'Not Assigned').
    """
    campaigns = _load_campaigns()
    rows = list(
        qs.values('product_code', 'product_name', 'brand',
                  'category_l1', 'category_l2', 'category_l3')
        .annotate(qty=Sum('quantity'), amount=Sum('sales_amount'),
                  settlement=Sum('settlement_amount'), tag_amount=Sum('tag_amount'),
                  lines=Count('id'))
        .order_by('-amount')
    )
    by_camp: dict = {}
    for r in rows:
        camp = _lookup_campaign(r.get('product_code') or '', campaigns)
        if camp not in by_camp:
            by_camp[camp] = {'campaign': camp, 'top_products': [], 'total_amount': 0.0}
        if len(by_camp[camp]['top_products']) < top_n:
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
            }
            entry['disc_pct'] = _disc_pct(entry['tag_amount'], entry['settlement'])
            by_camp[camp]['top_products'].append(entry)
        by_camp[camp]['total_amount'] += float(r.get('amount') or 0)
    return sorted(by_camp.values(), key=lambda x: -x['total_amount'])


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
    elif tab == 'campaign':
        tab_data['campaign_groups'] = _by_product_campaign(qs)
    elif tab == 'shop':
        tab_data['by_shop'] = _by_shop_full(qs)
    elif tab == 'shop_card':
        tab_data.update(_by_shop_card(qs))
    elif tab == 'product':
        tab_data['by_product'] = _by_product(qs)
    elif tab == 'top_by_brand':
        tab_data['top_by_brand'] = _top_by_brand(qs)
    elif tab == 'top_by_campaign':
        tab_data['top_by_campaign'] = _top_by_campaign(qs)

    result = {'overview': overview, **tab_data}
    cache.set(key, result, _TTL)
    logger.info("product_tab %s loaded: lines=%d", tab, overview.get('total_lines', 0),
                extra={"step": "product_analytics"})
    return result
