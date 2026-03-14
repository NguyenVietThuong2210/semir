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
from .season_utils import session_sort_key, month_sort_key, year_sort_key, week_sort_key

logger = logging.getLogger('customer_analytics')


def aggregate_by_grade(customer_details, new_members=None):
    """
    Aggregate customer data by VIP grade.

    Args:
        customer_details: List of customer detail dicts (already excludes VIP ID = 0)
        new_members: Set of vip_ids whose registration_date falls in the analysis period

    Returns:
        List of grade stats dicts sorted by grade order
    """
    grade_buckets = defaultdict(create_empty_bucket)
    grade_new = defaultdict(int)

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

        # Track new members
        if new_members and d['vip_id'] in new_members:
            grade_new[g] += 1

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
        new_c = grade_new.get(grade, 0)
        grade_stats.append({
            'grade': grade,
            'total_customers': s['active'],
            'total_in_db': tdb,
            'new_customers': new_c,
            'new_rate': round(new_c / s['active'] * 100, 2) if s['active'] else 0,
            'returning_customers': s['returning'],
            'return_rate': round(s['returning'] / s['active'] * 100 if s['active'] else 0, 2),
            'return_rate_all_time': round(s['returning'] / tdb * 100 if tdb else 0, 2),
            'returning_invoices': s.get('returning_invoices', 0),  # NEW
            'returning_amount': float(s.get('returning_amount', Decimal(0))),  # NEW
            'total_invoices': s['invoices'],
            'total_amount': float(s['amount']),
        })

    return grade_stats


def aggregate_by_season(customer_purchases, get_customer_info_fn, new_members=None):
    """
    Aggregate customer data by season.

    Fixed v3.3: Now correctly counts BOTH within-season AND cross-season returns.

    Args:
        customer_purchases: Dict[vip_id] -> List[purchase_dict]
        get_customer_info_fn: Function to get customer info
        new_members: Set of vip_ids whose registration_date falls in the analysis period

    Returns:
        List of season stats dicts sorted chronologically
    """
    session_buckets = defaultdict(create_empty_bucket)
    session_vip0_invoices = defaultdict(int)
    session_vip0_amount = defaultdict(lambda: Decimal(0))
    # NEW: Track returning invoices and amounts
    session_returning_invoices = defaultdict(int)
    session_returning_amount = defaultdict(lambda: Decimal(0))
    session_new = defaultdict(int)
    
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
        
        # purchases already sorted by build_customer_purchase_map
        all_purchases_sorted = purchases

        # Get customer info from the EARLIEST purchase (consistent with core.py)
        grade, reg_date, name = get_customer_info_fn(vip_id, all_purchases_sorted[0]['customer'])

        # Group by session
        by_sess = defaultdict(list)
        for p in all_purchases_sorted:
            by_sess[p['session']].append(p)

        for sk, sp in by_sess.items():
            # sp is date-ordered (iterating sorted all_purchases_sorted)
            session_first_date = sp[0]['date']
            sp_amount = sum(p['amount'] for p in sp)

            session_buckets[sk]['active'] += 1
            session_buckets[sk]['invoices'] += len(sp)
            session_buckets[sk]['amount'] += sp_amount

            _, is_ret_in_season = calculate_return_visits(sp, reg_date)
            # O(1): first ever purchase before first purchase in this bucket
            has_prior_purchases = all_purchases_sorted[0]['date'] < session_first_date

            if is_ret_in_season or has_prior_purchases:
                session_buckets[sk]['returning'] += 1
                session_returning_invoices[sk] += len(sp)
                session_returning_amount[sk] += sp_amount

            if new_members and vip_id in new_members:
                session_new[sk] += 1

    # Build stats list — include months that have VIP0-only transactions
    all_session_keys_union = set(session_buckets.keys()) | set(session_vip0_invoices.keys())
    session_stats = []
    for key in sorted(all_session_keys_union, key=session_sort_key):
        s = session_buckets[key]
        ac = s['active']
        rc = s['returning']

        vip0_inv = session_vip0_invoices.get(key, 0)
        vip0_amt = session_vip0_amount.get(key, Decimal(0))

        new_c = session_new.get(key, 0)
        session_stats.append({
            'session': key,
            'total_customers': ac,
            'new_customers': new_c,
            'new_rate': round(new_c / ac * 100, 2) if ac else 0,
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


def aggregate_by_month(customer_purchases, get_customer_info_fn, new_members=None):
    """
    Aggregate customer data by calendar month (YYYY-MM).
    Same logic as aggregate_by_season but uses the 'month' field.
    """
    month_buckets = defaultdict(create_empty_bucket)
    month_vip0_invoices = defaultdict(int)
    month_vip0_amount = defaultdict(lambda: Decimal(0))
    month_returning_invoices = defaultdict(int)
    month_returning_amount = defaultdict(lambda: Decimal(0))
    month_new = defaultdict(int)

    for vip_id, purchases in customer_purchases.items():
        if vip_id == '0':
            by_month = defaultdict(list)
            for p in purchases:
                by_month[p['month']].append(p)
            for mk, mp in by_month.items():
                month_vip0_invoices[mk] += len(mp)
                month_vip0_amount[mk] += sum(p['amount'] for p in mp)
            continue

        all_purchases_sorted = purchases  # pre-sorted
        _, reg_date, _ = get_customer_info_fn(vip_id, all_purchases_sorted[0]['customer'])

        by_month = defaultdict(list)
        for p in all_purchases_sorted:
            by_month[p['month']].append(p)

        for mk, mp in by_month.items():
            month_first_date = mp[0]['date']

            mp_amount = sum(p['amount'] for p in mp)
            month_buckets[mk]['active'] += 1
            month_buckets[mk]['invoices'] += len(mp)
            month_buckets[mk]['amount'] += mp_amount

            _, is_ret_in_month = calculate_return_visits(mp, reg_date)
            has_prior_purchases = all_purchases_sorted[0]['date'] < month_first_date

            if is_ret_in_month or has_prior_purchases:
                month_buckets[mk]['returning'] += 1
                month_returning_invoices[mk] += len(mp)
                month_returning_amount[mk] += mp_amount

            if new_members and vip_id in new_members:
                month_new[mk] += 1

    # Include months that have VIP0-only transactions
    all_month_keys_union = set(month_buckets.keys()) | set(month_vip0_invoices.keys())
    month_stats = []
    for key in sorted(all_month_keys_union, key=month_sort_key):
        s = month_buckets[key]
        ac = s['active']
        rc = s['returning']
        vip0_inv = month_vip0_invoices.get(key, 0)
        vip0_amt = month_vip0_amount.get(key, Decimal(0))
        new_c = month_new.get(key, 0)
        month_stats.append({
            'month': key,
            'total_customers': ac,
            'new_customers': new_c,
            'new_rate': round(new_c / ac * 100, 2) if ac else 0,
            'returning_customers': rc,
            'return_rate': round(rc / ac * 100 if ac else 0, 2),
            'returning_invoices': month_returning_invoices.get(key, 0),
            'returning_amount': float(month_returning_amount.get(key, Decimal(0))),
            'total_invoices': s['invoices'],
            'total_amount': float(s['amount']),
            'total_invoices_with_vip0': s['invoices'] + vip0_inv,
            'total_amount_with_vip0': float(s['amount'] + vip0_amt),
        })

    logger.info("month_stats: %d rows", len(month_stats))
    return month_stats


def aggregate_by_week(customer_purchases, get_customer_info_fn, new_members=None):
    """
    Aggregate customer data by week (week starting on first Monday of year).
    Same logic as aggregate_by_month but uses 'week_sort' and 'week_label' fields.
    Each row: {week_sort, week_label, total_customers, new_customers, ...}
    """
    week_buckets = defaultdict(create_empty_bucket)
    week_vip0_invoices = defaultdict(int)
    week_vip0_amount = defaultdict(lambda: Decimal(0))
    week_returning_invoices = defaultdict(int)
    week_returning_amount = defaultdict(lambda: Decimal(0))
    week_new = defaultdict(int)
    week_labels = {}  # week_sort -> week_label

    for vip_id, purchases in customer_purchases.items():
        if vip_id == '0':
            by_week = defaultdict(list)
            for p in purchases:
                by_week[p['week_sort']].append(p)
                week_labels[p['week_sort']] = p['week_label']
            for wk, wp in by_week.items():
                week_vip0_invoices[wk] += len(wp)
                week_vip0_amount[wk] += sum(p['amount'] for p in wp)
            continue

        all_purchases_sorted = purchases  # pre-sorted
        _, reg_date, _ = get_customer_info_fn(vip_id, all_purchases_sorted[0]['customer'])

        by_week = defaultdict(list)
        for p in all_purchases_sorted:
            by_week[p['week_sort']].append(p)
            week_labels[p['week_sort']] = p['week_label']

        for wk, wp in by_week.items():
            week_first_date = wp[0]['date']
            wp_amount = sum(p['amount'] for p in wp)

            week_buckets[wk]['active'] += 1
            week_buckets[wk]['invoices'] += len(wp)
            week_buckets[wk]['amount'] += wp_amount

            _, is_ret_in_week = calculate_return_visits(wp, reg_date)
            has_prior_purchases = all_purchases_sorted[0]['date'] < week_first_date

            if is_ret_in_week or has_prior_purchases:
                week_buckets[wk]['returning'] += 1
                week_returning_invoices[wk] += len(wp)
                week_returning_amount[wk] += wp_amount

            if new_members and vip_id in new_members:
                week_new[wk] += 1

    all_week_keys_union = set(week_buckets.keys()) | set(week_vip0_invoices.keys())
    week_stats = []
    for key in sorted(all_week_keys_union, key=week_sort_key):
        s = week_buckets[key]
        ac = s['active']
        rc = s['returning']
        vip0_inv = week_vip0_invoices.get(key, 0)
        vip0_amt = week_vip0_amount.get(key, Decimal(0))
        new_c = week_new.get(key, 0)
        week_stats.append({
            'week_sort':  key,
            'week_label': week_labels.get(key, key),
            'total_customers': ac,
            'new_customers': new_c,
            'new_rate': round(new_c / ac * 100, 2) if ac else 0,
            'returning_customers': rc,
            'return_rate': round(rc / ac * 100 if ac else 0, 2),
            'returning_invoices': week_returning_invoices.get(key, 0),
            'returning_amount': float(week_returning_amount.get(key, Decimal(0))),
            'total_invoices': s['invoices'],
            'total_amount': float(s['amount']),
            'total_invoices_with_vip0': s['invoices'] + vip0_inv,
            'total_amount_with_vip0': float(s['amount'] + vip0_amt),
        })

    logger.info("week_stats: %d rows", len(week_stats))
    return week_stats


def aggregate_by_year(customer_purchases, get_customer_info_fn, new_members=None):
    """
    Aggregate customer data by calendar year (YYYY).
    Same logic as aggregate_by_month but uses the 'year' field.
    Proper deduplication — no double-counting of returning/active customers.
    """
    year_buckets = defaultdict(create_empty_bucket)
    year_vip0_invoices = defaultdict(int)
    year_vip0_amount = defaultdict(lambda: Decimal(0))
    year_returning_invoices = defaultdict(int)
    year_returning_amount = defaultdict(lambda: Decimal(0))
    year_new = defaultdict(int)

    for vip_id, purchases in customer_purchases.items():
        if vip_id == '0':
            by_year = defaultdict(list)
            for p in purchases:
                by_year[p['year']].append(p)
            for yk, yp in by_year.items():
                year_vip0_invoices[yk] += len(yp)
                year_vip0_amount[yk] += sum(p['amount'] for p in yp)
            continue

        all_purchases_sorted = purchases  # pre-sorted
        _, reg_date, _ = get_customer_info_fn(vip_id, all_purchases_sorted[0]['customer'])

        by_year = defaultdict(list)
        for p in all_purchases_sorted:
            by_year[p['year']].append(p)

        for yk, yp in by_year.items():
            year_first_date = yp[0]['date']

            yp_amount = sum(p['amount'] for p in yp)
            year_buckets[yk]['active'] += 1
            year_buckets[yk]['invoices'] += len(yp)
            year_buckets[yk]['amount'] += yp_amount

            _, is_ret_in_year = calculate_return_visits(yp, reg_date)
            has_prior_purchases = all_purchases_sorted[0]['date'] < year_first_date

            if is_ret_in_year or has_prior_purchases:
                year_buckets[yk]['returning'] += 1
                year_returning_invoices[yk] += len(yp)
                year_returning_amount[yk] += yp_amount

            if new_members and vip_id in new_members:
                year_new[yk] += 1

    all_year_keys_union = set(year_buckets.keys()) | set(year_vip0_invoices.keys())
    year_stats = []
    for key in sorted(all_year_keys_union, key=year_sort_key):
        s = year_buckets[key]
        ac = s['active']
        rc = s['returning']
        vip0_inv = year_vip0_invoices.get(key, 0)
        vip0_amt = year_vip0_amount.get(key, Decimal(0))
        new_c = year_new.get(key, 0)
        year_stats.append({
            'year': key,
            'total_customers': ac,
            'new_customers': new_c,
            'new_rate': round(new_c / ac * 100, 2) if ac else 0,
            'returning_customers': rc,
            'return_rate': round(rc / ac * 100 if ac else 0, 2),
            'returning_invoices': year_returning_invoices.get(key, 0),
            'returning_amount': float(year_returning_amount.get(key, Decimal(0))),
            'total_invoices': s['invoices'],
            'total_amount': float(s['amount']),
            'total_invoices_with_vip0': s['invoices'] + vip0_inv,
            'total_amount_with_vip0': float(s['amount'] + vip0_amt),
        })

    logger.info("year_stats: %d rows", len(year_stats))
    return year_stats


def aggregate_by_shop(customer_purchases, get_customer_info_fn, all_session_keys, new_members=None, all_month_keys=None, all_year_keys=None, all_week_keys=None):
    """
    Aggregate customer data by shop with sub-breakdowns.

    Fixed v3.3: Shop→Season now counts within-season returns correctly.

    Args:
        customer_purchases: Dict[vip_id] -> List[purchase_dict]
        get_customer_info_fn: Function to get customer info
        all_session_keys: List of all season keys (for consistent shop sub-breakdowns)
        new_members: Set of vip_ids whose registration_date falls in the analysis period
        all_month_keys: List of all month keys (for consistent shop by-month breakdowns)

    Returns:
        List of shop stats dicts with by_grade, by_session, and by_month breakdowns
    """
    shop_customers = defaultdict(set)
    shop_invoices = defaultdict(int)
    shop_amount = defaultdict(Decimal)
    shop_returning = defaultdict(set)
    # NEW: Track returning invoices and amounts at shop level
    shop_returning_invoices = defaultdict(int)
    shop_returning_amount = defaultdict(lambda: Decimal(0))
    # Track new customers per shop / per shop-grade / per shop-session
    shop_new = defaultdict(int)
    shop_grade_new = defaultdict(lambda: defaultdict(int))
    shop_sess_new = defaultdict(lambda: defaultdict(int))
    
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

    # Month tracking per shop
    shop_month = defaultdict(lambda: defaultdict(create_empty_bucket))
    shop_month_returning = defaultdict(lambda: defaultdict(lambda: {'invoices': 0, 'amount': Decimal(0)}))
    shop_month_vip0 = defaultdict(lambda: defaultdict(lambda: {'invoices': 0, 'amount': Decimal(0)}))
    shop_month_new = defaultdict(lambda: defaultdict(int))

    # Year tracking per shop
    shop_year = defaultdict(lambda: defaultdict(create_empty_bucket))
    shop_year_returning = defaultdict(lambda: defaultdict(lambda: {'invoices': 0, 'amount': Decimal(0)}))
    shop_year_vip0 = defaultdict(lambda: defaultdict(lambda: {'invoices': 0, 'amount': Decimal(0)}))
    shop_year_new = defaultdict(lambda: defaultdict(int))

    # Week tracking per shop
    shop_week = defaultdict(lambda: defaultdict(create_empty_bucket))
    shop_week_returning = defaultdict(lambda: defaultdict(lambda: {'invoices': 0, 'amount': Decimal(0)}))
    shop_week_vip0 = defaultdict(lambda: defaultdict(lambda: {'invoices': 0, 'amount': Decimal(0)}))
    shop_week_new = defaultdict(lambda: defaultdict(int))
    shop_week_labels = {}  # week_sort -> week_label

    for vip_id, purchases in customer_purchases.items():
        # Track VIP 0
        if vip_id == '0':
            by_shop = defaultdict(list)
            for p in purchases:
                by_shop[p['shop']].append(p)
            
            for sh, sh_p in by_shop.items():
                shop_vip0_invoices[sh] += len(sh_p)
                shop_vip0_amount[sh] += sum(p['amount'] for p in sh_p)
                # Single pass: group by session and month simultaneously
                for p in sh_p:
                    amt = p['amount']
                    shop_sess_vip0[sh][p['session']]['invoices'] += 1
                    shop_sess_vip0[sh][p['session']]['amount'] += amt
                    shop_month_vip0[sh][p['month']]['invoices'] += 1
                    shop_month_vip0[sh][p['month']]['amount'] += amt
                    shop_year_vip0[sh][p['year']]['invoices'] += 1
                    shop_year_vip0[sh][p['year']]['amount'] += amt
                    shop_week_vip0[sh][p['week_sort']]['invoices'] += 1
                    shop_week_vip0[sh][p['week_sort']]['amount'] += amt
                    shop_week_labels[p['week_sort']] = p['week_label']
            continue
        
        # purchases already sorted; first purchase is purchases[0]
        grade, reg_date, name = get_customer_info_fn(vip_id, purchases[0]['customer'])

        # Group purchases by shop — iterate sorted list so sh_p is date-ordered
        by_shop_visits = defaultdict(list)
        for p in purchases:
            by_shop_visits[p['shop']].append(p)

        for sh, sh_p in by_shop_visits.items():
            # sh_p is already date-ordered (built from pre-sorted purchases)
            sh_p_sorted = sh_p
            sh_amount = sum(p['amount'] for p in sh_p)

            shop_customers[sh].add(vip_id)
            shop_invoices[sh] += len(sh_p)
            shop_amount[sh] += sh_amount

            # Shop-level returning calculation
            _, ret = calculate_return_visits(sh_p_sorted, reg_date)
            if ret:
                shop_returning[sh].add(vip_id)
                shop_returning_invoices[sh] += len(sh_p)
                shop_returning_amount[sh] += sh_amount

            # Track new members at shop level
            if new_members and vip_id in new_members:
                shop_new[sh] += 1
                shop_grade_new[sh][grade] += 1

            # Shop → By Grade breakdown
            shop_grade[sh][grade]['active'].add(vip_id)
            if ret:
                shop_grade[sh][grade]['returning'].add(vip_id)
                shop_grade[sh][grade]['returning_invoices'] += len(sh_p)
                shop_grade[sh][grade]['returning_amount'] += sh_amount
            shop_grade[sh][grade]['invoices'] += len(sh_p)
            shop_grade[sh][grade]['amount'] += sh_amount

            # Single pass: build session, month, year, and week groups simultaneously.
            # sh_p_sorted is already date-ordered, so sub-buckets are too.
            by_sess_shop = defaultdict(list)
            by_month_shop = defaultdict(list)
            by_year_shop = defaultdict(list)
            by_week_shop = defaultdict(list)
            for p in sh_p_sorted:
                by_sess_shop[p['session']].append(p)
                by_month_shop[p['month']].append(p)
                by_year_shop[p['year']].append(p)
                by_week_shop[p['week_sort']].append(p)
                shop_week_labels[p['week_sort']] = p['week_label']

            # Earliest purchase date at this shop — used for O(1) prior checks
            sh_first_date = sh_p_sorted[0]['date']

            # Shop → By Session
            for sk, sp in by_sess_shop.items():
                # sp is already date-ordered
                session_first_date = sp[0]['date']
                sp_amount = sum(p['amount'] for p in sp)

                shop_sess[sh][sk]['active'] += 1
                shop_sess[sh][sk]['invoices'] += len(sp)
                shop_sess[sh][sk]['amount'] += sp_amount

                _, is_ret_in_season = calculate_return_visits(sp, reg_date)
                has_prior_shop_purchases = sh_first_date < session_first_date

                if is_ret_in_season or has_prior_shop_purchases:
                    shop_sess[sh][sk]['returning'] += 1
                    shop_sess_returning[sh][sk]['invoices'] += len(sp)
                    shop_sess_returning[sh][sk]['amount'] += sp_amount

                if new_members and vip_id in new_members:
                    shop_sess_new[sh][sk] += 1

            # Shop → By Month
            for mk, mp in by_month_shop.items():
                month_first_date = mp[0]['date']
                mp_amount = sum(p['amount'] for p in mp)

                shop_month[sh][mk]['active'] += 1
                shop_month[sh][mk]['invoices'] += len(mp)
                shop_month[sh][mk]['amount'] += mp_amount

                _, is_ret_in_month = calculate_return_visits(mp, reg_date)
                has_prior_month = sh_first_date < month_first_date

                if is_ret_in_month or has_prior_month:
                    shop_month[sh][mk]['returning'] += 1
                    shop_month_returning[sh][mk]['invoices'] += len(mp)
                    shop_month_returning[sh][mk]['amount'] += mp_amount

                if new_members and vip_id in new_members:
                    shop_month_new[sh][mk] += 1

            # Shop → By Year
            for yk, yp in by_year_shop.items():
                year_first_date = yp[0]['date']
                yp_amount = sum(p['amount'] for p in yp)

                shop_year[sh][yk]['active'] += 1
                shop_year[sh][yk]['invoices'] += len(yp)
                shop_year[sh][yk]['amount'] += yp_amount

                _, is_ret_in_year = calculate_return_visits(yp, reg_date)
                has_prior_year = sh_first_date < year_first_date

                if is_ret_in_year or has_prior_year:
                    shop_year[sh][yk]['returning'] += 1
                    shop_year_returning[sh][yk]['invoices'] += len(yp)
                    shop_year_returning[sh][yk]['amount'] += yp_amount

                if new_members and vip_id in new_members:
                    shop_year_new[sh][yk] += 1

            # Shop → By Week
            for wk, wp in by_week_shop.items():
                week_first_date = wp[0]['date']
                wp_amount = sum(p['amount'] for p in wp)

                shop_week[sh][wk]['active'] += 1
                shop_week[sh][wk]['invoices'] += len(wp)
                shop_week[sh][wk]['amount'] += wp_amount

                _, is_ret_in_week = calculate_return_visits(wp, reg_date)
                has_prior_week = sh_first_date < week_first_date

                if is_ret_in_week or has_prior_week:
                    shop_week[sh][wk]['returning'] += 1
                    shop_week_returning[sh][wk]['invoices'] += len(wp)
                    shop_week_returning[sh][wk]['amount'] += wp_amount

                if new_members and vip_id in new_members:
                    shop_week_new[sh][wk] += 1

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
            grade_new_c = shop_grade_new[sh].get(grade, 0)
            by_grade_list.append({
                'grade': grade,
                'total_customers': a,
                'new_customers': grade_new_c,
                'new_rate': round(grade_new_c / a * 100, 2) if a else 0,
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
            sess_new_c = shop_sess_new[sh].get(key, 0)
            by_session_list.append({
                'session': key,
                'total_customers': a,
                'new_customers': sess_new_c,
                'new_rate': round(sess_new_c / a * 100, 2) if a else 0,
                'returning_customers': r,
                'return_rate': round(r / a * 100 if a else 0, 2),
                'returning_invoices': ret_sess['invoices'],  # NEW
                'returning_amount': float(ret_sess['amount']),  # NEW
                'total_invoices': sd['invoices'],
                'total_amount': float(sd['amount']),
                'total_invoices_with_vip0': sd['invoices'] + vip0_sess['invoices'],
                'total_amount_with_vip0': float(sd['amount'] + vip0_sess['amount']),
            })
        
        # By month list
        by_month_list = []
        for key in (all_month_keys or sorted(shop_month[sh].keys(), key=month_sort_key)):
            md = shop_month[sh].get(key)
            if md is None:
                md = create_empty_bucket()
            vip0_mo = shop_month_vip0[sh].get(key, {'invoices': 0, 'amount': Decimal(0)})
            ret_mo = shop_month_returning[sh].get(key, {'invoices': 0, 'amount': Decimal(0)})
            a = md['active']
            r = md['returning']
            mo_new_c = shop_month_new[sh].get(key, 0)
            by_month_list.append({
                'month': key,
                'total_customers': a,
                'new_customers': mo_new_c,
                'new_rate': round(mo_new_c / a * 100, 2) if a else 0,
                'returning_customers': r,
                'return_rate': round(r / a * 100 if a else 0, 2),
                'returning_invoices': ret_mo['invoices'],
                'returning_amount': float(ret_mo['amount']),
                'total_invoices': md['invoices'],
                'total_amount': float(md['amount']),
                'total_invoices_with_vip0': md['invoices'] + vip0_mo['invoices'],
                'total_amount_with_vip0': float(md['amount'] + vip0_mo['amount']),
            })

        # By year list
        by_year_list = []
        for key in (all_year_keys or sorted(shop_year[sh].keys(), key=year_sort_key)):
            yd = shop_year[sh].get(key)
            if yd is None:
                yd = create_empty_bucket()
            vip0_yr = shop_year_vip0[sh].get(key, {'invoices': 0, 'amount': Decimal(0)})
            ret_yr = shop_year_returning[sh].get(key, {'invoices': 0, 'amount': Decimal(0)})
            a = yd['active']
            r = yd['returning']
            yr_new_c = shop_year_new[sh].get(key, 0)
            by_year_list.append({
                'year': key,
                'total_customers': a,
                'new_customers': yr_new_c,
                'new_rate': round(yr_new_c / a * 100, 2) if a else 0,
                'returning_customers': r,
                'return_rate': round(r / a * 100 if a else 0, 2),
                'returning_invoices': ret_yr['invoices'],
                'returning_amount': float(ret_yr['amount']),
                'total_invoices': yd['invoices'],
                'total_amount': float(yd['amount']),
                'total_invoices_with_vip0': yd['invoices'] + vip0_yr['invoices'],
                'total_amount_with_vip0': float(yd['amount'] + vip0_yr['amount']),
            })

        # By week list
        by_week_list = []
        for key in (all_week_keys or sorted(shop_week[sh].keys(), key=week_sort_key)):
            wd = shop_week[sh].get(key)
            if wd is None:
                wd = create_empty_bucket()
            vip0_wk = shop_week_vip0[sh].get(key, {'invoices': 0, 'amount': Decimal(0)})
            ret_wk = shop_week_returning[sh].get(key, {'invoices': 0, 'amount': Decimal(0)})
            a = wd['active']
            r = wd['returning']
            wk_new_c = shop_week_new[sh].get(key, 0)
            by_week_list.append({
                'week_sort':  key,
                'week_label': shop_week_labels.get(key, key),
                'total_customers': a,
                'new_customers': wk_new_c,
                'new_rate': round(wk_new_c / a * 100, 2) if a else 0,
                'returning_customers': r,
                'return_rate': round(r / a * 100 if a else 0, 2),
                'returning_invoices': ret_wk['invoices'],
                'returning_amount': float(ret_wk['amount']),
                'total_invoices': wd['invoices'],
                'total_amount': float(wd['amount']),
                'total_invoices_with_vip0': wd['invoices'] + vip0_wk['invoices'],
                'total_amount_with_vip0': float(wd['amount'] + vip0_wk['amount']),
            })

        shop_new_c = shop_new.get(sh, 0)
        shop_stats.append({
            'shop_name': sh,
            'total_customers': ac,
            'new_customers': shop_new_c,
            'new_rate': round(shop_new_c / ac * 100, 2) if ac else 0,
            'returning_customers': rc,
            'return_rate': round(rc / ac * 100 if ac else 0, 2),
            'returning_invoices': shop_returning_invoices.get(sh, 0),
            'returning_amount': float(shop_returning_amount.get(sh, Decimal(0))),
            'total_invoices': shop_invoices[sh],
            'total_amount': float(shop_amount[sh]),
            'total_invoices_with_vip0': shop_invoices[sh] + shop_vip0_invoices.get(sh, 0),
            'total_amount_with_vip0': float(shop_amount[sh] + shop_vip0_amount.get(sh, Decimal(0))),
            'by_grade': by_grade_list,
            'by_session': by_session_list,
            'by_month': by_month_list,
            'by_year': by_year_list,
            'by_week': by_week_list,
        })
    
    # Sort by customer count
    shop_stats.sort(key=lambda x: x['total_customers'], reverse=True)
    return shop_stats


def calculate_buyer_without_info(vip_0_purchases_period, alltime_invoices, alltime_amount,
                                  date_from, date_to,
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
    
    # All-time stats — pre-computed via DB aggregate in core.py
    all_time_invoices = alltime_invoices
    all_time_amount   = alltime_amount
    
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


def get_comparison_data(shop_group=None):
    """
    All-time monthly invoice/amount totals per shop, for the year-over-year comparison chart.

    No date filtering, no customer deduplication — just a lightweight DB aggregation.
    Returns Dict[shop_name] -> Dict['YYYY-MM'] -> {'invoices': int, 'amount': float}

    Args:
        shop_group: Optional shop group filter string (same values as core.py)
    """
    from django.db.models import Count, Sum, Q
    from App.models import SalesTransaction

    VIP0 = Q(vip_id='') | Q(vip_id='0') | Q(vip_id__isnull=True)

    qs = (
        SalesTransaction.objects
        .filter(sales_date__isnull=False)
        .values('shop_name', 'sales_date__year', 'sales_date__month')
        .annotate(
            total_invoices_with_vip0=Count('id'),
            total_amount_with_vip0=Sum('sales_amount'),
            total_invoices=Count('id',         filter=~VIP0),
            total_amount  =Sum('sales_amount', filter=~VIP0),
            total_customers=Count('vip_id', distinct=True, filter=~VIP0),
        )
    )
    if shop_group == 'Bala Group':
        qs = qs.filter(Q(shop_name__icontains='Bala') | Q(shop_name__icontains='巴拉'))
    elif shop_group == 'Semir Group':
        qs = qs.filter(Q(shop_name__icontains='Semir') | Q(shop_name__icontains='森马'))
    elif shop_group == 'Others Group':
        qs = qs.exclude(
            Q(shop_name__icontains='Bala') | Q(shop_name__icontains='巴拉') |
            Q(shop_name__icontains='Semir') | Q(shop_name__icontains='森马')
        )

    result = {}
    for row in qs:
        sh     = row['shop_name'] or 'Unknown Shop'
        mo_key = f"{row['sales_date__year']}-{row['sales_date__month']:02d}"
        if sh not in result:
            result[sh] = {}
        result[sh][mo_key] = {
            'total_invoices_with_vip0': row['total_invoices_with_vip0'],
            'total_amount_with_vip0':   float(row['total_amount_with_vip0'] or 0),
            'total_invoices':           row['total_invoices'],
            'total_amount':             float(row['total_amount'] or 0),
            'total_customers':          row['total_customers'],
        }
    return result