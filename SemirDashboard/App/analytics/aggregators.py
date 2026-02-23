"""
App/analytics/aggregators.py

Data aggregation functions for different dimensions.
Handles by_grade, by_season, by_shop, and buyer_without_info analytics.

Version: 3.3 - Fixed within-season return calculation
"""
import logging
from collections import defaultdict
from decimal import Decimal

from .calculations import calculate_return_visits, create_empty_bucket
from .customer_utils import GRADE_ORDER, get_all_time_grade_counts
from .season_utils import session_sort_key

logger = logging.getLogger('customer_analytics')


def aggregate_by_grade(customer_details):
    """
    Aggregate customer data by VIP grade.
    
    Args:
        customer_details: List of customer detail dicts (already excludes VIP ID = 0)
    
    Returns:
        List of grade stats dicts sorted by grade order
    """
    grade_buckets = defaultdict(create_empty_bucket)
    
    for d in customer_details:
        g = d['vip_grade']
        grade_buckets[g]['active'] += 1
        grade_buckets[g]['amount'] += Decimal(str(d['total_spent']))
        grade_buckets[g]['invoices'] += d['total_purchases']
        
        # Track returning customers
        if d['return_visits'] > 0:
            grade_buckets[g]['returning'] += 1
            # NEW: Track returning invoices and amount
            grade_buckets[g]['returning_invoices'] = grade_buckets[g].get('returning_invoices', 0) + d['total_purchases']
            grade_buckets[g]['returning_amount'] = grade_buckets[g].get('returning_amount', Decimal(0)) + Decimal(str(d['total_spent']))
    
    # Ensure all grades exist
    for g in GRADE_ORDER:
        if g not in grade_buckets:
            _ = grade_buckets[g]
    
    # Get all-time grade counts from database
    grade_db = get_all_time_grade_counts()
    
    # Build stats list
    grade_stats = []
    for grade in sorted(grade_buckets, key=lambda x: GRADE_ORDER.get(x, 99)):
        s = grade_buckets[grade]
        tdb = grade_db.get(grade, 0)
        grade_stats.append({
            'grade': grade,
            'total_customers': s['active'],
            'total_in_db': tdb,
            'returning_customers': s['returning'],
            'return_rate': round(s['returning'] / s['active'] * 100 if s['active'] else 0, 2),
            'return_rate_all_time': round(s['returning'] / tdb * 100 if tdb else 0, 2),
            'returning_invoices': s.get('returning_invoices', 0),  # NEW
            'returning_amount': float(s.get('returning_amount', Decimal(0))),  # NEW
            'total_invoices': s['invoices'],
            'total_amount': float(s['amount']),
        })
    
    return grade_stats


def aggregate_by_season(customer_purchases, get_customer_info_fn):
    """
    Aggregate customer data by season.
    
    Fixed v3.3: Now correctly counts BOTH within-season AND cross-season returns.
    
    Args:
        customer_purchases: Dict[vip_id] -> List[purchase_dict]
        get_customer_info_fn: Function to get customer info
    
    Returns:
        List of season stats dicts sorted chronologically
    """
    session_buckets = defaultdict(create_empty_bucket)
    session_vip0_invoices = defaultdict(int)
    session_vip0_amount = defaultdict(lambda: Decimal(0))
    # NEW: Track returning invoices and amounts
    session_returning_invoices = defaultdict(int)
    session_returning_amount = defaultdict(lambda: Decimal(0))
    
    for vip_id, purchases in customer_purchases.items():
        # Track VIP 0 separately
        if vip_id == '0':
            by_sess = defaultdict(list)
            for p in purchases:
                by_sess[p['session']].append(p)
            for sk, sp in by_sess.items():
                session_vip0_invoices[sk] += len(sp)
                session_vip0_amount[sk] += sum(p['amount'] for p in sp)
            continue
        
        # Get customer info
        grade, reg_date, name = get_customer_info_fn(vip_id, purchases[0]['customer'])
        
        # Sort all purchases by date (needed for cross-season check)
        all_purchases_sorted = sorted(purchases, key=lambda x: x['date'])
        
        # Group by session
        by_sess = defaultdict(list)
        for p in purchases:
            by_sess[p['session']].append(p)
        
        for sk, sp in by_sess.items():
            sp_sorted = sorted(sp, key=lambda x: x['date'])
            session_first_date = sp_sorted[0]['date']
            
            # Customer is ACTIVE in this session
            session_buckets[sk]['active'] += 1
            session_buckets[sk]['invoices'] += len(sp)
            session_buckets[sk]['amount'] += sum(p['amount'] for p in sp)
            
            # FIX v3.3: Check BOTH within-season AND cross-season returns
            # 1. Calculate return visits WITHIN this season
            _, is_ret_in_season = calculate_return_visits(sp_sorted, reg_date)
            
            # 2. Check if has prior purchases BEFORE this season
            has_prior_purchases = any(p['date'] < session_first_date for p in all_purchases_sorted)
            
            # Customer is returning if:
            # - Has multiple invoices in this season (is_ret_in_season), OR
            # - Has purchased before this season (has_prior_purchases)
            if is_ret_in_season or has_prior_purchases:
                session_buckets[sk]['returning'] += 1
                # NEW: Track returning invoices and amount
                session_returning_invoices[sk] += len(sp)
                session_returning_amount[sk] += sum(p['amount'] for p in sp)
    
    # Build stats list
    session_stats = []
    for key in sorted(session_buckets, key=session_sort_key):
        s = session_buckets[key]
        ac = s['active']
        rc = s['returning']
        
        vip0_inv = session_vip0_invoices.get(key, 0)
        vip0_amt = session_vip0_amount.get(key, Decimal(0))
        
        session_stats.append({
            'session': key,
            'total_customers': ac,
            'returning_customers': rc,
            'return_rate': round(rc / ac * 100 if ac else 0, 2),
            'returning_invoices': session_returning_invoices.get(key, 0),  # NEW
            'returning_amount': float(session_returning_amount.get(key, Decimal(0))),  # NEW
            'total_invoices': s['invoices'],
            'total_amount': float(s['amount']),
            'total_invoices_with_vip0': s['invoices'] + vip0_inv,
            'total_amount_with_vip0': float(s['amount'] + vip0_amt),
        })
    
    logger.info("session_stats: %d rows", len(session_stats))
    return session_stats


def aggregate_by_shop(customer_purchases, get_customer_info_fn, all_session_keys):
    """
    Aggregate customer data by shop with sub-breakdowns.
    
    Fixed v3.3: Shop→Season now counts within-season returns correctly.
    
    Args:
        customer_purchases: Dict[vip_id] -> List[purchase_dict]
        get_customer_info_fn: Function to get customer info
        all_session_keys: List of all season keys (for consistent shop sub-breakdowns)
    
    Returns:
        List of shop stats dicts with by_grade and by_session breakdowns
    """
    shop_customers = defaultdict(set)
    shop_invoices = defaultdict(int)
    shop_amount = defaultdict(Decimal)
    shop_returning = defaultdict(set)
    # NEW: Track returning invoices and amounts at shop level
    shop_returning_invoices = defaultdict(int)
    shop_returning_amount = defaultdict(lambda: Decimal(0))
    
    shop_grade = defaultdict(lambda: defaultdict(lambda: {
        'active': set(), 'returning': set(), 'invoices': 0, 'amount': Decimal(0),
        'returning_invoices': 0, 'returning_amount': Decimal(0)  # NEW
    }))
    shop_sess = defaultdict(lambda: defaultdict(create_empty_bucket))
    # NEW: Track returning for shop-session
    shop_sess_returning = defaultdict(lambda: defaultdict(lambda: {'invoices': 0, 'amount': Decimal(0)}))
    
    # NEW: VIP 0 tracking
    shop_vip0_invoices = defaultdict(int)
    shop_vip0_amount = defaultdict(lambda: Decimal(0))
    shop_sess_vip0 = defaultdict(lambda: defaultdict(lambda: {'invoices': 0, 'amount': Decimal(0)}))
    
    for vip_id, purchases in customer_purchases.items():
        # Track VIP 0
        if vip_id == '0':
            by_shop = defaultdict(list)
            for p in purchases:
                by_shop[p['shop']].append(p)
            
            for sh, sh_p in by_shop.items():
                shop_vip0_invoices[sh] += len(sh_p)
                shop_vip0_amount[sh] += sum(p['amount'] for p in sh_p)
                
                # By session within shop
                by_sess = defaultdict(list)
                for p in sh_p:
                    by_sess[p['session']].append(p)
                for sk, sp in by_sess.items():
                    shop_sess_vip0[sh][sk]['invoices'] += len(sp)
                    shop_sess_vip0[sh][sk]['amount'] += sum(p['amount'] for p in sp)
            continue
        
        # Get customer info
        grade, reg_date, name = get_customer_info_fn(vip_id, purchases[0]['customer'])
        
        # Group purchases by shop
        by_shop_visits = defaultdict(list)
        for p in purchases:
            by_shop_visits[p['shop']].append(p)
        
        for sh, sh_p in by_shop_visits.items():
            shop_customers[sh].add(vip_id)
            shop_invoices[sh] += len(sh_p)
            for p in sh_p:
                shop_amount[sh] += p['amount']
            
            # Shop-level returning calculation
            _, ret = calculate_return_visits(sorted(sh_p, key=lambda x: x['date']), reg_date)
            if ret:
                shop_returning[sh].add(vip_id)
                # NEW: Track returning invoices and amount at shop level
                shop_returning_invoices[sh] += len(sh_p)
                shop_returning_amount[sh] += sum(p['amount'] for p in sh_p)
            
            # Shop → By Grade breakdown
            shop_grade[sh][grade]['active'].add(vip_id)
            if ret:
                shop_grade[sh][grade]['returning'].add(vip_id)
                # NEW: Track returning for this grade
                shop_grade[sh][grade]['returning_invoices'] += len(sh_p)
                shop_grade[sh][grade]['returning_amount'] += sum(p['amount'] for p in sh_p)
            for p in sh_p:
                shop_grade[sh][grade]['invoices'] += 1
                shop_grade[sh][grade]['amount'] += p['amount']
            
            # Shop → By Session - FIXED v3.3: Within-season + Cross-season
            sh_p_sorted = sorted(sh_p, key=lambda x: x['date'])
            
            by_sess_shop = defaultdict(list)
            for p in sh_p:
                by_sess_shop[p['session']].append(p)
            
            for sk, sp in by_sess_shop.items():
                sp_sorted = sorted(sp, key=lambda x: x['date'])
                session_first_date = sp_sorted[0]['date']
                
                shop_sess[sh][sk]['active'] += 1
                shop_sess[sh][sk]['invoices'] += len(sp)
                shop_sess[sh][sk]['amount'] += sum(p['amount'] for p in sp)
                
                # FIX v3.3: Check BOTH within-season AND cross-season returns
                # 1. Calculate return visits WITHIN this season
                _, is_ret_in_season = calculate_return_visits(sp_sorted, reg_date)
                
                # 2. Check if has prior shop purchases BEFORE this season
                has_prior_shop_purchases = any(p['date'] < session_first_date for p in sh_p_sorted)
                
                # Customer is returning if:
                # - Has multiple invoices in this season (is_ret_in_season), OR
                # - Has purchased at this shop before this season (has_prior_shop_purchases)
                if is_ret_in_season or has_prior_shop_purchases:
                    shop_sess[sh][sk]['returning'] += 1
                    # NEW: Track returning invoices and amount for this shop-season
                    shop_sess_returning[sh][sk]['invoices'] += len(sp)
                    shop_sess_returning[sh][sk]['amount'] += sum(p['amount'] for p in sp)
    
    # Build shop stats list
    shop_stats = []
    for sh in shop_customers:
        ac = len(shop_customers[sh])
        rc = len(shop_returning[sh])
        
        # By grade list
        by_grade_list = []
        for grade in sorted(shop_grade[sh], key=lambda x: GRADE_ORDER.get(x, 99)):
            gd = shop_grade[sh][grade]
            a = len(gd['active'])
            r = len(gd['returning'])
            by_grade_list.append({
                'grade': grade,
                'total_customers': a,
                'returning_customers': r,
                'return_rate': round(r / a * 100 if a else 0, 2),
                'returning_invoices': gd.get('returning_invoices', 0),  # NEW
                'returning_amount': float(gd.get('returning_amount', Decimal(0))),  # NEW
                'total_invoices': gd['invoices'],
                'total_amount': float(gd['amount']),
            })
        
        # By season list
        by_session_list = []
        for key in all_session_keys:
            sd = shop_sess[sh].get(key)
            if sd is None:
                sd = create_empty_bucket()
            
            vip0_sess = shop_sess_vip0[sh].get(key, {'invoices': 0, 'amount': Decimal(0)})
            ret_sess = shop_sess_returning[sh].get(key, {'invoices': 0, 'amount': Decimal(0)})  # NEW
            
            a = sd['active']
            r = sd['returning']
            by_session_list.append({
                'session': key,
                'total_customers': a,
                'returning_customers': r,
                'return_rate': round(r / a * 100 if a else 0, 2),
                'returning_invoices': ret_sess['invoices'],  # NEW
                'returning_amount': float(ret_sess['amount']),  # NEW
                'total_invoices': sd['invoices'],
                'total_amount': float(sd['amount']),
                'total_invoices_with_vip0': sd['invoices'] + vip0_sess['invoices'],
                'total_amount_with_vip0': float(sd['amount'] + vip0_sess['amount']),
            })
        
        shop_stats.append({
            'shop_name': sh,
            'total_customers': ac,
            'returning_customers': rc,
            'return_rate': round(rc / ac * 100 if ac else 0, 2),
            'returning_invoices': shop_returning_invoices.get(sh, 0),  # NEW
            'returning_amount': float(shop_returning_amount.get(sh, Decimal(0))),  # NEW
            'total_invoices': shop_invoices[sh],
            'total_amount': float(shop_amount[sh]),
            'total_invoices_with_vip0': shop_invoices[sh] + shop_vip0_invoices.get(sh, 0),
            'total_amount_with_vip0': float(shop_amount[sh] + shop_vip0_amount.get(sh, Decimal(0))),
            'by_grade': by_grade_list,
            'by_session': by_session_list,
        })
    
    # Sort by customer count
    shop_stats.sort(key=lambda x: x['total_customers'], reverse=True)
    return shop_stats


def calculate_buyer_without_info(vip_0_purchases_period, all_sales, date_from, date_to,
                                  total_invoices_all_period, total_amount_all_period):
    """
    Calculate analytics for VIP ID = 0 (buyers without customer info).
    
    Args:
        vip_0_purchases_period: List of VIP ID = 0 purchases in period
        all_sales: All sales transactions (for all-time calculation)
        date_from: Period start date
        date_to: Period end date
        total_invoices_all_period: Total invoices INCLUDING VIP 0 in period
        total_amount_all_period: Total amount INCLUDING VIP 0 in period
    
    Returns:
        dict with period, all_time, and by_shop stats
    """
    # Period stats
    period_invoices = len(vip_0_purchases_period)
    period_amount = sum(p['amount'] for p in vip_0_purchases_period)
    
    # Calculate percentages
    pct_invoices = round(period_invoices / total_invoices_all_period * 100, 2) if total_invoices_all_period else 0
    pct_amount = round(period_amount / total_amount_all_period * 100, 2) if total_amount_all_period else 0
    
    # All-time stats (VIP ID = 0 only)
    all_time_vip_0 = [s for s in all_sales if (s.vip_id or '').strip() in ('', '0', 'None')]
    all_time_invoices = len(all_time_vip_0)
    all_time_amount = sum(s.sales_amount or Decimal(0) for s in all_time_vip_0)
    
    # By shop (period)
    shop_stats = defaultdict(lambda: {'invoices': 0, 'amount': Decimal(0)})
    for p in vip_0_purchases_period:
        shop = p['shop']
        shop_stats[shop]['invoices'] += 1
        shop_stats[shop]['amount'] += p['amount']
    
    shop_list = []
    for shop_name in sorted(shop_stats.keys()):  # Sort alphabetically
        inv = shop_stats[shop_name]['invoices']
        amt = shop_stats[shop_name]['amount']
        
        shop_list.append({
            'shop_name': shop_name,
            'invoices': inv,
            'amount': float(amt),
            'pct_of_period_invoices': round(inv / total_invoices_all_period * 100, 2) if total_invoices_all_period else 0,
            'pct_of_period_amount': round(amt / total_amount_all_period * 100, 2) if total_amount_all_period else 0,
        })
    
    return {
        'period': {
            'total_invoices': period_invoices,
            'total_amount': float(period_amount),
            'pct_of_all_invoices': pct_invoices,
            'pct_of_all_amount': pct_amount,
        },
        'all_time': {
            'total_invoices': all_time_invoices,
            'total_amount': float(all_time_amount),
        },
        'by_shop': shop_list,
    }