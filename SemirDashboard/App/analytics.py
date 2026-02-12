"""
analytics.py  --  v2.9

RETURN VISIT FORMULA (user-confirmed):
  Registration Date = First Purchase Date:
    - First invoice of that day    = first visit (NOT a return)
    - Subsequent invoices same day = return visits
    - Example: Reg 1/1, buy 3x on 1/1 -> total_purchases=3, return_visits=2
  
  Registration Date != First Purchase Date (or no reg date):
    - Customer already visited to register, so first purchase = already returning
    - First invoice = return visit
    - Example: Reg 1/1, buy 1x on 5/1 -> total_purchases=1, return_visits=1
  
  is_returning = return_visits > 0
"""
import logging
from collections import defaultdict
from decimal import Decimal

from django.db.models import Count, Min, Max

from .models import Customer, SalesTransaction, Coupon
from openpyxl import Workbook
from openpyxl.styles import Font, PatternFill, Alignment
from openpyxl.utils import get_column_letter

logger = logging.getLogger('customer_analytics')

GRADE_ORDER = {'No Grade': 0, 'Member': 1, 'Silver': 2, 'Gold': 3, 'Diamond': 4}

SEASON_DEFS = [
    ('M2-4',  [2, 3, 4]),
    ('M5-7',  [5, 6, 7]),
    ('M8-10', [8, 9, 10]),
    ('M11-1', [11, 12, 1]),
]


def _normalize_grade(raw):
    if not raw:
        return 'No Grade'
    raw = raw.strip()
    if raw.lower() in ('olden', 'gold', 'golden'):
        return 'Gold'
    return raw


def _get_session_key(d):
    """Year-aware season label."""
    if not d:
        return 'Unknown'
    m, y = d.month, d.year
    for prefix, months in SEASON_DEFS:
        if m in months:
            if prefix == 'M11-1':
                return f"M11-1 {y-1}-{y}" if m == 1 else f"M11-1 {y}-{y+1}"
            return f"{prefix} {y}"
    return 'Unknown'


def _session_sort_key(label):
    parts = label.rsplit(' ', 1)
    if len(parts) != 2:
        return (9999, 99)
    prefix, years = parts[0], parts[1]
    try:
        first_year = int(years.split('-')[0])
    except ValueError:
        return (9999, 99)
    order_map = {'M2-4': 0, 'M5-7': 1, 'M8-10': 2, 'M11-1': 3}
    return (first_year, order_map.get(prefix, 99))


def _get_session_for_range(date_from, date_to):
    if not date_from or not date_to:
        return None
    months, cur = set(), date_from.replace(day=1)
    while cur <= date_to:
        months.add(cur.month)
        cur = cur.replace(year=cur.year + 1, month=1) if cur.month == 12 \
            else cur.replace(month=cur.month + 1)
    for label, m_list in SEASON_DEFS:
        if months.issubset(set(m_list)):
            return label
    return None


def _calculate_return_visits(purchases_sorted, reg_date):
    """
    Return (return_visits, is_returning).
    
    Rule:
      - If reg_date == first_purchase_date: first invoice NOT a return, rest are
        -> return_visits = total_purchases - 1
      - If reg_date != first_purchase_date (or no reg): first invoice IS a return
        -> return_visits = total_purchases
      - is_returning = return_visits > 0
    """
    n = len(purchases_sorted)
    if n == 0:
        return 0, False
    
    first_purchase_date = purchases_sorted[0]['date']
    
    if reg_date and reg_date == first_purchase_date:
        # Registered same day as first purchase
        return_visits = n - 1
    else:
        # Registered earlier (or no reg) -> already a return
        return_visits = n
    
    return return_visits, (return_visits > 0)


def _empty_bucket():
    return {'active': 0, 'returning': 0, 'invoices': 0, 'amount': Decimal(0)}


def _write_header(ws, row, headers, font=None, fill=None):
    f  = font or Font(bold=True, color='FFFFFF', size=11)
    fi = fill or PatternFill(start_color='366092', end_color='366092', fill_type='solid')
    for ci, h in enumerate(headers, 1):
        c = ws.cell(row=row, column=ci, value=h)
        c.font = f; c.fill = fi
        c.alignment = Alignment(horizontal='center', wrap_text=True)


def calculate_return_rate_analytics(date_from=None, date_to=None):
    logger.info("START date_from=%s date_to=%s", date_from, date_to)

    total_customers_in_db    = Customer.objects.count()
    member_active_all_time   = Customer.objects.filter(points__gt=0).count()
    member_inactive_all_time = Customer.objects.filter(points=0).count()

    qs = SalesTransaction.objects.select_related('customer').order_by('sales_date')
    if date_from:
        qs = qs.filter(sales_date__gte=date_from)
    if date_to:
        qs = qs.filter(sales_date__lte=date_to)
    if not qs.exists():
        return None

    sales_list = list(qs)
    date_stats = qs.aggregate(start_date=Min('sales_date'), end_date=Max('sales_date'))
    logger.info("Transactions: %d", len(sales_list))

    # Group by customer (VIP ID blank/0 -> key='0')
    customer_purchases = defaultdict(list)
    for s in sales_list:
        vid = (s.vip_id or '').strip()
        key = '0' if vid in ('', '0', 'None') else vid
        customer_purchases[key].append({
            'date':     s.sales_date,
            'invoice':  s.invoice_number,
            'amount':   s.sales_amount or Decimal(0),
            'shop':     s.shop_name or 'Unknown Shop',
            'customer': s.customer if key != '0' else None,
            'session':  _get_session_key(s.sales_date),
        })

    buyer_no_info_invoices = len(customer_purchases.get('0', []))
    logger.info("Customers: %d  buyer_no_info_invoices: %d",
                len(customer_purchases), buyer_no_info_invoices)

    # Per-customer analysis
    returning_customers   = set()
    new_members_in_period = set()
    customer_details      = []
    total_amount_period   = Decimal(0)

    for vip_id, purchases in customer_purchases.items():
        purchases_sorted = sorted(purchases, key=lambda x: x['date'])
        n = len(purchases_sorted)

        if vip_id == '0':
            cust = None; grade = 'No Grade'
            name = 'Unknown (No VIP)'; reg_date = None
        else:
            # FIX: Lookup customer directly from database by VIP ID
            # Don't rely on foreign key which may be None
            cust = purchases_sorted[0]['customer']
            if not cust:
                # Foreign key is None, lookup by VIP ID
                try:
                    cust = Customer.objects.get(vip_id=vip_id)
                except Customer.DoesNotExist:
                    cust = None
            
            grade    = _normalize_grade(cust.vip_grade if cust else None)
            name     = (cust.name if cust else '') or 'Unknown'
            reg_date = cust.registration_date if cust else None

        rc, is_ret = _calculate_return_visits(purchases_sorted, reg_date)
        if is_ret:
            returning_customers.add(vip_id)

        if reg_date and vip_id != '0':
            lo = date_from or date_stats['start_date']
            hi = date_to   or date_stats['end_date']
            if lo <= reg_date <= hi:
                new_members_in_period.add(vip_id)

        amt = sum(p['amount'] for p in purchases_sorted)
        total_amount_period += amt

        customer_details.append({
            'vip_id':              vip_id,
            'name':                name,
            'vip_grade':           grade,
            'registration_date':   reg_date,
            'first_purchase_date': purchases_sorted[0]['date'],
            'total_purchases':     n,
            'return_visits':       rc,
            'total_spent':         float(amt),
        })

    total_active    = len(customer_purchases)
    total_returning = len(returning_customers)
    return_rate_p   = round(total_returning / total_active          * 100, 2) if total_active          else 0
    return_rate_at  = round(total_returning / total_customers_in_db * 100, 2) if total_customers_in_db else 0

    # All-time grade counts
    grade_db = {}
    for row in Customer.objects.values('vip_grade').annotate(cnt=Count('id')):
        g = _normalize_grade(row['vip_grade'])
        grade_db[g] = grade_db.get(g, 0) + row['cnt']

    # Grade stats
    grade_buckets = defaultdict(_empty_bucket)
    for d in customer_details:
        g = d['vip_grade']
        grade_buckets[g]['active']   += 1
        grade_buckets[g]['amount']   += Decimal(str(d['total_spent']))
        grade_buckets[g]['invoices'] += d['total_purchases']
        if d['return_visits'] > 0:
            grade_buckets[g]['returning'] += 1

    for g in GRADE_ORDER:
        if g not in grade_buckets:
            _ = grade_buckets[g]

    grade_stats = []
    for grade in sorted(grade_buckets, key=lambda x: GRADE_ORDER.get(x, 99)):
        s   = grade_buckets[grade]
        tdb = grade_db.get(grade, 0)
        grade_stats.append({
            'grade':                grade,
            'total_customers':      s['active'],
            'total_in_db':          tdb,
            'returning_customers':  s['returning'],
            'return_rate':          round(s['returning'] / s['active'] * 100 if s['active'] else 0, 2),
            'return_rate_all_time': round(s['returning'] / tdb         * 100 if tdb          else 0, 2),
            'total_invoices':       s['invoices'],
            'total_amount':         float(s['amount']),
        })

    # Session stats
    session_buckets = defaultdict(_empty_bucket)

    for vip_id, purchases in customer_purchases.items():
        if vip_id == '0':
            reg_date = None
        else:
            cust = purchases[0]['customer']
            reg_date = cust.registration_date if cust else None

        by_sess = defaultdict(list)
        for p in purchases:
            by_sess[p['session']].append(p)

        for sk, sp in by_sess.items():
            session_buckets[sk]['active']   += 1
            session_buckets[sk]['invoices'] += len(sp)
            session_buckets[sk]['amount']   += sum(p['amount'] for p in sp)
            
            # Within-season return: use same formula
            _, is_ret = _calculate_return_visits(sorted(sp, key=lambda x: x['date']), reg_date)
            if is_ret:
                session_buckets[sk]['returning'] += 1

    session_stats = []
    for key in sorted(session_buckets, key=_session_sort_key):
        s = session_buckets[key]
        ac = s['active']; rc = s['returning']
        session_stats.append({
            'session':             key,
            'total_customers':     ac,
            'returning_customers': rc,
            'return_rate':         round(rc / ac * 100 if ac else 0, 2),
            'total_invoices':      s['invoices'],
            'total_amount':        float(s['amount']),
        })
    logger.info("session_stats: %d rows", len(session_stats))

    # Shop stats
    shop_customers  = defaultdict(set)
    shop_invoices   = defaultdict(int)
    shop_amount     = defaultdict(Decimal)
    shop_returning  = defaultdict(set)
    shop_grade      = defaultdict(lambda: defaultdict(lambda: {
        'active': set(), 'returning': set(), 'invoices': 0, 'amount': Decimal(0)
    }))
    shop_sess       = defaultdict(lambda: defaultdict(_empty_bucket))

    for vip_id, purchases in customer_purchases.items():
        if vip_id == '0':
            grade = 'No Grade'; reg_date = None
        else:
            cust = purchases[0]['customer']
            grade = _normalize_grade(cust.vip_grade if cust else None)
            reg_date = cust.registration_date if cust else None

        by_shop_visits = defaultdict(list)
        for p in purchases:
            by_shop_visits[p['shop']].append(p)

        for sh, sh_p in by_shop_visits.items():
            shop_customers[sh].add(vip_id)
            shop_invoices[sh] += len(sh_p)
            for p in sh_p:
                shop_amount[sh] += p['amount']

            _, ret = _calculate_return_visits(sorted(sh_p, key=lambda x: x['date']), reg_date)
            if ret:
                shop_returning[sh].add(vip_id)

            shop_grade[sh][grade]['active'].add(vip_id)
            if ret:
                shop_grade[sh][grade]['returning'].add(vip_id)
            for p in sh_p:
                shop_grade[sh][grade]['invoices'] += 1
                shop_grade[sh][grade]['amount']   += p['amount']

            by_sess_shop = defaultdict(list)
            for p in sh_p:
                by_sess_shop[p['session']].append(p)
            for sk, sp in by_sess_shop.items():
                shop_sess[sh][sk]['active']   += 1
                shop_sess[sh][sk]['invoices'] += len(sp)
                shop_sess[sh][sk]['amount']   += sum(p['amount'] for p in sp)
                _, s_ret = _calculate_return_visits(sorted(sp, key=lambda x: x['date']), reg_date)
                if s_ret:
                    shop_sess[sh][sk]['returning'] += 1

    all_session_keys = sorted(session_buckets.keys(), key=_session_sort_key)

    shop_stats = []
    for sh in shop_customers:
        ac = len(shop_customers[sh])
        rc = len(shop_returning[sh])

        by_grade_list = []
        for grade in sorted(shop_grade[sh], key=lambda x: GRADE_ORDER.get(x, 99)):
            gd = shop_grade[sh][grade]
            a  = len(gd['active']); r = len(gd['returning'])
            by_grade_list.append({
                'grade':               grade,
                'total_customers':     a,
                'returning_customers': r,
                'return_rate':         round(r / a * 100 if a else 0, 2),
                'total_invoices':      gd['invoices'],
                'total_amount':        float(gd['amount']),
            })

        by_session_list = []
        for key in all_session_keys:
            sd = shop_sess[sh].get(key)
            if sd is None:
                sd = _empty_bucket()
            a = sd['active']; r = sd['returning']
            by_session_list.append({
                'session':             key,
                'total_customers':     a,
                'returning_customers': r,
                'return_rate':         round(r / a * 100 if a else 0, 2),
                'total_invoices':      sd['invoices'],
                'total_amount':        float(sd['amount']),
            })

        shop_stats.append({
            'shop_name':           sh,
            'total_customers':     ac,
            'returning_customers': rc,
            'return_rate':         round(rc / ac * 100 if ac else 0, 2),
            'total_invoices':      shop_invoices[sh],
            'total_amount':        float(shop_amount[sh]),
            'by_grade':            by_grade_list,
            'by_session':          by_session_list,
        })

    shop_stats.sort(key=lambda x: x['total_customers'], reverse=True)
    customer_details.sort(key=lambda x: x['return_visits'], reverse=True)
    logger.info("DONE  total_amount=%.2f  shops=%d  sessions=%d",
                float(total_amount_period), len(shop_stats), len(session_stats))

    return {
        'date_range':    {'start': date_stats['start_date'], 'end': date_stats['end_date']},
        'session_label': _get_session_for_range(date_from, date_to),
        'overview': {
            'total_customers_in_db':    total_customers_in_db,
            'member_active_all_time':   member_active_all_time,
            'member_inactive_all_time': member_inactive_all_time,
            'active_customers':         total_active,
            'returning_customers':      total_returning,
            'new_members_in_period':    len(new_members_in_period),
            'buyer_no_info_in_period':  buyer_no_info_invoices,
            'return_rate':              return_rate_p,
            'return_rate_all_time':     return_rate_at,
            'total_amount_period':      float(total_amount_period),
        },
        'by_grade':         grade_stats,
        'by_session':       session_stats,
        'by_shop':          shop_stats,
        'customer_details': customer_details,
    }


def calculate_coupon_analytics(date_from=None, date_to=None, coupon_id_prefix=None):
    logger.info("START coupon from=%s to=%s prefix=%s", date_from, date_to, coupon_id_prefix)

    # Build customer lookup: VIP ID -> (name, phone)
    customer_lookup = {}
    for c in Customer.objects.only('vip_id', 'name', 'phone'):
        customer_lookup[c.vip_id] = {
            'name':  c.name or '',
            'phone': c.phone or '',
        }

    inv_lookup = {
        s.invoice_number: s
        for s in SalesTransaction.objects.only(
            'invoice_number', 'vip_id', 'sales_date', 'shop_name', 'sales_amount')
    }

    def _stats(qs):
        total  = qs.count()
        used   = qs.filter(used=1).count()
        unused = qs.filter(used=0).count()
        amt    = Decimal(0)
        for c in qs.filter(used=1):
            inv = inv_lookup.get(c.docket_number)
            if inv:
                amt += inv.sales_amount or Decimal(0)
        return {
            'total':        total,
            'used':         used,
            'used_pct':     round(used   / total * 100, 2) if total else 0,
            'unused':       unused,
            'unused_pct':   round(unused / total * 100, 2) if total else 0,
            'total_amount': float(amt),
        }

    base_qs = Coupon.objects.all()
    if coupon_id_prefix:
        base_qs = base_qs.filter(coupon_id__istartswith=coupon_id_prefix)
        logger.info("Filtering by prefix: %s -> %d coupons", coupon_id_prefix, base_qs.count())
    all_time_stats = _stats(base_qs)

    period_qs = base_qs
    if date_from:
        period_qs = period_qs.filter(using_date__gte=date_from)
    if date_to:
        period_qs = period_qs.filter(using_date__lte=date_to)
    period_stats  = _stats(period_qs)
    period_total  = period_stats['total']
    period_used   = period_stats['used']

    by_shop = []
    for sh in period_qs.values_list('using_shop', flat=True).distinct():
        sh_qs   = period_qs.filter(using_shop=sh)
        sh_used = sh_qs.filter(used=1).count()
        sh_amt  = Decimal(0)
        for c in sh_qs.filter(used=1):
            inv = inv_lookup.get(c.docket_number)
            if inv:
                sh_amt += inv.sales_amount or Decimal(0)
        by_shop.append({
            'shop_name':          sh or 'Unknown',
            'used':               sh_used,
            'used_pct_period':    round(sh_used / period_total * 100, 2) if period_total else 0,
            'used_pct_of_used':   round(sh_used / period_used  * 100, 2) if period_used  else 0,
            'total_amount':       float(sh_amt),
        })
    by_shop.sort(key=lambda x: (x['shop_name'] or '').lower())

    details = []
    for c in period_qs.order_by('coupon_id'):
        inv       = inv_lookup.get(c.docket_number)
        vip_id    = inv.vip_id       if inv else ''
        sales_day = inv.sales_date   if inv else None
        inv_shop  = inv.shop_name    if inv else ''
        amount    = float(inv.sales_amount or 0) if inv else 0.0
        
        # Get customer name + phone from VIP ID
        cust_info = customer_lookup.get(vip_id, {'name': '', 'phone': ''})
        cust_name  = cust_info['name']
        cust_phone = cust_info['phone']
        
        notes = []
        if c.used == 1 and inv:
            if c.using_shop and inv_shop and c.using_shop.strip() != inv_shop.strip():
                notes.append(f"Shop mismatch: coupon={c.using_shop} / invoice={inv_shop}")
            if c.using_date and sales_day and c.using_date != sales_day:
                notes.append(f"Date mismatch: coupon={c.using_date} / invoice={sales_day}")
        
        details.append({
            'coupon_id':      c.coupon_id,
            'creator':        c.creator or '',
            'face_value':     float(c.face_value or 0),
            'using_shop':     c.using_shop or '',
            'using_date':     c.using_date,
            'vip_id':         vip_id,
            'customer_name':  cust_name,
            'customer_phone': cust_phone,
            'sales_day':      sales_day,
            'inv_shop':       inv_shop,
            'amount':         amount,
            'note':           ' | '.join(notes),
        })

    logger.info("DONE coupon  period=%d by_shop=%d", len(details), len(by_shop))
    return {
        'all_time': all_time_stats,
        'period':   period_stats,
        'by_shop':  by_shop,
        'details':  details,
    }


# Excel exports (same as before, just update coupon detail columns)

def export_analytics_to_excel(data):
    logger.info("START export_analytics_to_excel")
    wb    = Workbook()
    TITLE = Font(bold=True, size=14)
    if 'Sheet' in wb.sheetnames:
        wb.remove(wb['Sheet'])

    ws = wb.create_sheet('Summary')
    ws['A1'] = 'Return Visit Rate Analysis'; ws['A1'].font = TITLE
    ws['A4'] = 'Start Date'; ws['B4'] = data['date_range']['start']
    ws['A5'] = 'End Date';   ws['B5'] = data['date_range']['end']
    _write_header(ws, 8, ['Metric', 'Value'])
    ov = data['overview']
    for i, (k, v) in enumerate([
        ('New Members (Period)',                    ov['new_members_in_period']),
        ('Returning Customers (Period)',            ov['returning_customers']),
        ('Active Customers (Period)',               ov['active_customers']),
        ('Return Visit Rate (Period) %',            ov['return_rate']),
        ('Total Amount (Period) VND',               ov['total_amount_period']),
        ('Buyer Without Info - Invoices (Period)',  ov['buyer_no_info_in_period']),
        ('Total Customers in DB (All Time)',        ov['total_customers_in_db']),
        ('Member Active (All Time)',                ov['member_active_all_time']),
        ('Member Inactive (All Time)',              ov['member_inactive_all_time']),
        ('Return Visit Rate (All Time) %',          ov['return_rate_all_time']),
    ], 9):
        ws[f'A{i}'] = k; ws[f'B{i}'] = v
    ws.column_dimensions['A'].width = 48
    ws.column_dimensions['B'].width = 22

    # -- By VIP Grade --
    ws = wb.create_sheet('By VIP Grade')
    ws['A1'] = 'By VIP Grade Analysis'; ws['A1'].font = TITLE
    ws['A2'] = 'Breakdown of customers by VIP tier with period and all-time metrics'
    ws['A2'].font = Font(italic=True, size=10, color='666666')
    
    _write_header(ws, 4, [
        'VIP Grade',
        'Returning\n(Period)',
        'Active\n(Period)',
        'Return Rate %\n(Period)',
        'Total in DB\n(All Time)',
        'Return Rate %\n(All Time)',
        'Total Invoices\n(Period)',
        'Total Amount\n(Period VND)'
    ])
    
    for r, d in enumerate(data['by_grade'], 5):
        ws.cell(r, 1, d['grade'])
        ws.cell(r, 2, d['returning_customers'])
        ws.cell(r, 3, d['total_customers'])
        ws.cell(r, 4, d['return_rate']).number_format = '0.00'
        ws.cell(r, 5, d['total_in_db'])
        ws.cell(r, 6, d['return_rate_all_time']).number_format = '0.00'
        ws.cell(r, 7, d['total_invoices'])
        ws.cell(r, 8, d['total_amount']).number_format = '#,##0'
    
    for i, w in enumerate([16, 12, 12, 16, 14, 16, 14, 20], 1):
        ws.column_dimensions[get_column_letter(i)].width = w

    # -- By Season --
    ws = wb.create_sheet('By Season')
    ws['A1'] = 'By Season Analysis (Year-Aware)'; ws['A1'].font = TITLE
    ws['A2'] = 'Seasonal breakdown with year labels (e.g., M11-1 2024-2025 spans Nov 2024 to Jan 2025)'
    ws['A2'].font = Font(italic=True, size=10, color='666666')
    
    _write_header(ws, 4, [
        'Season',
        'Returning\n(Period)',
        'Active\n(Period)',
        'Return Rate %\n(Period)',
        'Total Invoices\n(Period)',
        'Total Amount\n(Period VND)'
    ])
    
    for r, d in enumerate(data['by_session'], 5):
        ws.cell(r, 1, d['session'])
        ws.cell(r, 2, d['returning_customers'])
        ws.cell(r, 3, d['total_customers'])
        ws.cell(r, 4, d['return_rate']).number_format = '0.00'
        ws.cell(r, 5, d['total_invoices'])
        ws.cell(r, 6, d['total_amount']).number_format = '#,##0'
    
    for i, w in enumerate([22, 12, 12, 16, 14, 20], 1):
        ws.column_dimensions[get_column_letter(i)].width = w

    # ========================================
    # TAB: BY SHOP (Each shop gets its own table with grade + season breakdown)
    # ========================================
    ws = wb.create_sheet('By Shop')
    ws['A1'] = 'By Shop - Detailed Breakdown'; ws['A1'].font = TITLE
    ws['A2'] = 'Shop overview followed by detailed breakdowns for each shop'
    ws['A2'].font = Font(italic=True, size=10, color='666666')
    
    shops_sorted = sorted(data['by_shop'], key=lambda x: (x['shop_name'] or '').lower())
    
    shop_hdr_fill  = PatternFill(start_color='2C3E50', end_color='2C3E50', fill_type='solid')
    shop_hdr_font  = Font(bold=True, color='FFFFFF', size=11)
    grade_hdr_fill = PatternFill(start_color='BDD7EE', end_color='BDD7EE', fill_type='solid')
    grade_hdr_font = Font(bold=True, color='1F3864', size=10)
    sess_hdr_fill  = PatternFill(start_color='D5E8D4', end_color='D5E8D4', fill_type='solid')
    sess_hdr_font  = Font(bold=True, color='1A3D2B', size=10)
    
    rp = 4
    
    # --------------------
    # OVERVIEW TABLE - All Shops
    # --------------------
    ws.cell(rp, 1, 'Shop Overview').font = Font(bold=True, size=12, color='1F3864')
    rp += 1
    _write_header(ws, rp, ['Shop', 'Returning', 'Active', 'Return Rate %', 'Total Invoices', 'Total Amount (VND)'],
                  font=shop_hdr_font, fill=shop_hdr_fill)
    rp += 1
    
    for shop_data in shops_sorted:
        ws.cell(rp, 1, shop_data['shop_name'])
        ws.cell(rp, 2, shop_data['returning_customers'])
        ws.cell(rp, 3, shop_data['total_customers'])
        ws.cell(rp, 4, shop_data['return_rate']).number_format = '0.00'
        ws.cell(rp, 5, shop_data['total_invoices'])
        ws.cell(rp, 6, shop_data['total_amount']).number_format = '#,##0'
        rp += 1
    
    rp += 3  # extra spacing before detailed breakdowns
    
    # --------------------
    # DETAILED BREAKDOWN - Each Shop
    # --------------------
    ws.cell(rp, 1, 'Detailed Breakdown by Shop').font = Font(bold=True, size=12, color='1F3864')
    rp += 2
    
    for shop_data in shops_sorted:
        # Shop name header
        ws.cell(rp, 1, shop_data['shop_name']).font = Font(bold=True, size=12, color='1F3864')
        rp += 1
        
        # Shop overview
        _write_header(ws, rp, ['Shop', 'Returning', 'Active', 'Return Rate %', 'Total Invoices', 'Total Amount (VND)'],
                      font=shop_hdr_font, fill=shop_hdr_fill)
        rp += 1
        ws.cell(rp, 1, shop_data['shop_name'])
        ws.cell(rp, 2, shop_data['returning_customers'])
        ws.cell(rp, 3, shop_data['total_customers'])
        ws.cell(rp, 4, shop_data['return_rate']).number_format = '0.00'
        ws.cell(rp, 5, shop_data['total_invoices'])
        ws.cell(rp, 6, shop_data['total_amount']).number_format = '#,##0'
        rp += 1
        rp += 1  # spacing
        
        # By VIP Grade
        ws.cell(rp, 1, '  By VIP Grade').font = Font(bold=True, size=10, color='1F3864')
        rp += 1
        _write_header(ws, rp, ['Grade', 'Returning', 'Active', 'Return Rate %', 'Total Invoices', 'Total Amount (VND)'],
                      font=grade_hdr_font, fill=grade_hdr_fill)
        rp += 1
        
        for gd in shop_data['by_grade']:
            ws.cell(rp, 1, gd['grade'])
            ws.cell(rp, 2, gd['returning_customers'])
            ws.cell(rp, 3, gd['total_customers'])
            ws.cell(rp, 4, gd['return_rate']).number_format = '0.00'
            ws.cell(rp, 5, gd['total_invoices'])
            ws.cell(rp, 6, gd['total_amount']).number_format = '#,##0'
            rp += 1
        
        rp += 1  # spacing
        
        # By Season
        ws.cell(rp, 1, '  By Season').font = Font(bold=True, size=10, color='1A3D2B')
        rp += 1
        _write_header(ws, rp, ['Season', 'Returning', 'Active', 'Return Rate %', 'Total Invoices', 'Total Amount (VND)'],
                      font=sess_hdr_font, fill=sess_hdr_fill)
        rp += 1
        
        for sd in shop_data['by_session']:
            if sd['total_customers'] > 0:
                ws.cell(rp, 1, sd['session'])
                ws.cell(rp, 2, sd['returning_customers'])
                ws.cell(rp, 3, sd['total_customers'])
                ws.cell(rp, 4, sd['return_rate']).number_format = '0.00'
                ws.cell(rp, 5, sd['total_invoices'])
                ws.cell(rp, 6, sd['total_amount']).number_format = '#,##0'
                rp += 1
        
        rp += 2  # extra spacing between shops
    
    for i, w in enumerate([24, 12, 12, 16, 14, 20], 1):
        ws.column_dimensions[get_column_letter(i)].width = w
    
    # ========================================
    # TAB: BY VIP GRADE (Cross-shop comparison per grade)
    # ========================================
    ws = wb.create_sheet('By VIP Grade - Shops')
    ws['A1'] = 'By VIP Grade - Cross-Shop Comparison'; ws['A1'].font = TITLE
    ws['A2'] = 'Compare all shops within the same VIP grade'
    ws['A2'].font = Font(italic=True, size=10, color='666666')
    
    all_grades = []
    grade_order = ['No Grade', 'Member', 'Silver', 'Gold', 'Diamond']
    for g in grade_order:
        for shop_data in shops_sorted:
            if any(gd['grade'] == g for gd in shop_data['by_grade']):
                if g not in all_grades:
                    all_grades.append(g)
    
    grade_hdr_fill = PatternFill(start_color='BDD7EE', end_color='BDD7EE', fill_type='solid')
    grade_hdr_font = Font(bold=True, color='1F3864', size=10)
    
    rp = 4
    
    for grade in all_grades:
        ws.cell(rp, 1, f'Grade: {grade}').font = Font(bold=True, size=11, color='1F3864')
        rp += 1
        
        _write_header(ws, rp, ['Shop', 'Returning', 'Active', 'Return Rate %', 'Total Invoices', 'Total Amount (VND)'],
                      font=grade_hdr_font, fill=grade_hdr_fill)
        rp += 1
        
        for shop_data in shops_sorted:
            shop_grade_dict = {gd['grade']: gd for gd in shop_data['by_grade']}
            gd = shop_grade_dict.get(grade, {
                'total_customers': 0, 'returning_customers': 0,
                'return_rate': 0, 'total_invoices': 0, 'total_amount': 0
            })
            
            if gd['total_customers'] > 0:
                ws.cell(rp, 1, shop_data['shop_name'])
                ws.cell(rp, 2, gd['returning_customers'])
                ws.cell(rp, 3, gd['total_customers'])
                ws.cell(rp, 4, gd['return_rate']).number_format = '0.00'
                ws.cell(rp, 5, gd['total_invoices'])
                ws.cell(rp, 6, gd['total_amount']).number_format = '#,##0'
                rp += 1
        
        rp += 2  # spacing between grades
    
    for i, w in enumerate([28, 12, 12, 16, 14, 20], 1):
        ws.column_dimensions[get_column_letter(i)].width = w
    
    # ========================================
    # TAB: BY SEASON (Cross-shop comparison per season)
    # ========================================
    ws = wb.create_sheet('By Season - Shops')
    ws['A1'] = 'By Season - Cross-Shop Comparison'; ws['A1'].font = TITLE
    ws['A2'] = 'Compare all shops within the same season (year-aware)'
    ws['A2'].font = Font(italic=True, size=10, color='666666')
    
    all_seasons = [s['session'] for s in data['by_session']]
    
    sess_hdr_fill = PatternFill(start_color='D5E8D4', end_color='D5E8D4', fill_type='solid')
    sess_hdr_font = Font(bold=True, color='1A3D2B', size=10)
    
    rp = 4
    
    for season in all_seasons:
        ws.cell(rp, 1, f'Season: {season}').font = Font(bold=True, size=11, color='1A3D2B')
        rp += 1
        
        _write_header(ws, rp, ['Shop', 'Returning', 'Active', 'Return Rate %', 'Total Invoices', 'Total Amount (VND)'],
                      font=sess_hdr_font, fill=sess_hdr_fill)
        rp += 1
        
        for shop_data in shops_sorted:
            shop_season_dict = {sd['session']: sd for sd in shop_data['by_session']}
            sd = shop_season_dict.get(season, {
                'total_customers': 0, 'returning_customers': 0,
                'return_rate': 0, 'total_invoices': 0, 'total_amount': 0
            })
            
            if sd['total_customers'] > 0:
                ws.cell(rp, 1, shop_data['shop_name'])
                ws.cell(rp, 2, sd['returning_customers'])
                ws.cell(rp, 3, sd['total_customers'])
                ws.cell(rp, 4, sd['return_rate']).number_format = '0.00'
                ws.cell(rp, 5, sd['total_invoices'])
                ws.cell(rp, 6, sd['total_amount']).number_format = '#,##0'
                rp += 1
        
        rp += 2  # spacing between seasons
    
    for i, w in enumerate([28, 12, 12, 16, 14, 20], 1):
        ws.column_dimensions[get_column_letter(i)].width = w

    ws = wb.create_sheet('Customer Details')
    ws['A1'] = 'Customer Details'; ws['A1'].font = TITLE
    _write_header(ws, 3, ['VIP ID','Name','VIP Grade','Reg. Date',
                           'First Purchase','Total Purchases','Return Visits','Total Spent (VND)'])
    for r, c in enumerate(data['customer_details'], 4):
        ws.cell(r,1,c['vip_id']); ws.cell(r,2,c['name']); ws.cell(r,3,c['vip_grade'])
        ws.cell(r,4,c['registration_date']); ws.cell(r,5,c['first_purchase_date'])
        ws.cell(r,6,c['total_purchases']); ws.cell(r,7,c['return_visits'])
        ws.cell(r,8,float(c['total_spent'])).number_format = '#,##0'
    for i, w in enumerate([15,25,12,14,14,16,14,18], 1):
        ws.column_dimensions[get_column_letter(i)].width = w

    logger.info("DONE export_analytics_to_excel")
    return wb


def export_coupon_to_excel(data, date_from=None, date_to=None):
    logger.info("START export_coupon_to_excel")
    wb    = Workbook()
    TITLE = Font(bold=True, size=14)
    WARN  = PatternFill(start_color='FFEB9C', end_color='FFEB9C', fill_type='solid')
    period_label = f"{date_from} to {date_to}" if date_from and date_to else "All Time"
    if 'Sheet' in wb.sheetnames:
        wb.remove(wb['Sheet'])

    def _row(ws, row, label, s):
        ws.cell(row,1,label); ws.cell(row,2,s['total'])
        ws.cell(row,3,s['used']); ws.cell(row,4,s['used_pct'])
        ws.cell(row,5,s['unused']); ws.cell(row,6,s['unused_pct'])
        ws.cell(row,7,s['total_amount']).number_format = '#,##0'

    ws = wb.create_sheet('Coupon Overview')
    ws['A1'] = 'Coupon Overview'; ws['A1'].font = TITLE
    _write_header(ws, 5, ['Scope','Total','Used','Used %','Unused','Unused %','Total Amount (VND)'])
    _row(ws, 6, 'All Time', data['all_time'])
    _row(ws, 7, f'Period ({period_label})', data['period'])
    for i, w in enumerate([28,8,8,8,8,8,18], 1):
        ws.column_dimensions[get_column_letter(i)].width = w

    ws = wb.create_sheet('Coupon by Shop')
    ws['A1'] = 'Coupon by Shop'; ws['A1'].font = TITLE
    _write_header(ws, 3, ['Using Shop','Used Coupons',
                           '% of Total Coupons (Period)',
                           '% of Total Used (All Shops)',
                           'Total Amount (VND)'])
    for r, s in enumerate(data['by_shop'], 4):
        ws.cell(r,1,s['shop_name']); ws.cell(r,2,s['used'])
        ws.cell(r,3,s['used_pct_period']); ws.cell(r,4,s['used_pct_of_used'])
        ws.cell(r,5,s['total_amount']).number_format = '#,##0'
    for i, w in enumerate([30,14,28,28,20], 1):
        ws.column_dimensions[get_column_letter(i)].width = w

    ws = wb.create_sheet('Coupon Detail')
    ws['A1'] = 'Coupon Detail'; ws['A1'].font = TITLE
    _write_header(ws, 3, ['Coupon ID','Creator','Face Value','Using Shop','Using Date',
                           'VIP ID (Invoice)','Customer Name','Phone No',
                           'Sales Date (Invoice)','Shop (Invoice)','Amount (VND)','Note'])
    for r, d in enumerate(data['details'], 4):
        ws.cell(r,1,d['coupon_id']); ws.cell(r,2,d['creator'])
        ws.cell(r,3,d['face_value']).number_format = '#,##0'
        ws.cell(r,4,d['using_shop']); ws.cell(r,5,d['using_date'])
        ws.cell(r,6,d['vip_id']); ws.cell(r,7,d['customer_name']); ws.cell(r,8,d['customer_phone'])
        ws.cell(r,9,d['sales_day']); ws.cell(r,10,d['inv_shop'])
        ws.cell(r,11,d['amount']).number_format = '#,##0'
        ws.cell(r,12,d['note'])
        if d['note']:
            for ci in range(1, 13):
                ws.cell(r, ci).fill = WARN
    for i, w in enumerate([16,18,12,22,14,18,22,16,18,22,14,50], 1):
        ws.column_dimensions[get_column_letter(i)].width = w

    logger.info("DONE export_coupon_to_excel")
    return wb