"""
App/analytics/customer_utils.py

Customer data fetching, processing, and caching utilities.
Handles all customer-related operations.

Version: 3.4 - Added per-bucket invoice bucket maps for consistent NEW INV / NEW NO INV
"""
import logging
from collections import defaultdict

logger = logging.getLogger('customer_analytics')


# ---------------------------------------------------------------------------
# VIP ID helpers — shared by Sales Analytics and Customer Analytics
# ---------------------------------------------------------------------------

def _norm_vid(vid):
    """Normalize vip_id: strip whitespace, convert float-notation '12345.0' → '12345'."""
    v = (str(vid) or '').strip()
    if '.' in v:
        try:
            v = str(int(float(v)))
        except (ValueError, OverflowError):
            pass
    return v


def get_inv_lookups_for_period(date_from, date_to):
    """
    Build lookup sets for "customer has SalesTransactions in [date_from, date_to]".

    Returns:
        pks_with_inv  (set[int])  — Customer PKs via FK (format-agnostic).
        vids_with_inv (set[str])  — Normalized SalesTransaction.vip_id strings
                                    (fallback for transactions without FK).

    Usage:
        has_inv = (customer_pk in pks_with_inv) or (_norm_vid(vip_id) in vids_with_inv)
    """
    from App.models import SalesTransaction
    qs = (
        SalesTransaction.objects
        .filter(sales_date__gte=date_from, sales_date__lte=date_to)
        .exclude(vip_id__isnull=True).exclude(vip_id='').exclude(vip_id='0')
    )
    pks_with_inv = set(
        qs.filter(customer__isnull=False)
        .values_list('customer_id', flat=True)
        .distinct()
    )
    vids_with_inv = {
        _norm_vid(v)
        for v in qs.values_list('vip_id', flat=True).distinct()
        if v
    } - {'', '0'}
    return pks_with_inv, vids_with_inv


# Global cache for customer lookups to avoid repeated DB queries
_customer_cache = {}

# Grade standardization constants
GRADE_ORDER = {'No Grade': 0, 'Member': 1, 'Silver': 2, 'Gold': 3, 'Diamond': 4}


def normalize_grade(raw):
    """
    Normalize grade names to standard values.
    
    Handles common typos and variations:
    - 'Olden', 'Golden' → 'Gold'
    - Empty/None → 'No Grade'
    
    Args:
        raw: Raw grade string from database
    
    Returns:
        Normalized grade string
    """
    if not raw:
        return 'No Grade'
    raw = raw.strip()
    if raw.lower() in ('olden', 'gold', 'golden'):
        return 'Gold'
    return raw


def get_customer_info(vip_id, customer_obj=None):
    """
    🔑 UNIFIED CUSTOMER LOOKUP - Single source of truth
    
    Get customer grade, registration date, and name.
    Used EVERYWHERE for consistency across all analytics calculations.
    
    Features:
    - Smart caching (reduces DB queries by ~50%)
    - Fallback to DB if foreign key is None
    - Handles VIP ID = 0 specially
    - Single source of truth for customer data
    
    Args:
        vip_id: Customer VIP ID string
        customer_obj: Customer object from foreign key (may be None)
    
    Returns:
        (grade, reg_date, name) tuple
        - grade: Normalized grade string
        - reg_date: Registration date or None
        - name: Customer name or 'Unknown'
    """
    global _customer_cache
    
    # Special case: VIP ID = 0 (no customer info)
    if vip_id == '0':
        return ('No Grade', None, 'Unknown (No VIP)')
    
    # Try to use provided customer object first
    cust = customer_obj
    
    # If customer object is None, lookup from database (with caching)
    if not cust:
        if vip_id in _customer_cache:
            cust = _customer_cache[vip_id]
        else:
            # Import here to avoid circular dependency
            from App.models import Customer
            try:
                cust = Customer.objects.only(
                    'id', 'vip_id', 'vip_grade', 'registration_date', 'name'
                ).get(vip_id=vip_id)
                _customer_cache[vip_id] = cust
            except Customer.DoesNotExist:
                _customer_cache[vip_id] = None
                cust = None
    
    # Extract info
    if cust:
        grade = normalize_grade(cust.vip_grade)
        reg_date = cust.registration_date
        name = cust.name or 'Unknown'
    else:
        # Customer not found in database
        grade = 'No Grade'
        reg_date = None
        name = 'Unknown'
    
    return (grade, reg_date, name)


def clear_customer_cache():
    """
    Clear the customer lookup cache.
    Called at the start of each analytics calculation.
    """
    global _customer_cache
    _customer_cache = {}


def build_customer_purchase_map(sales_list, shop_map=None):
    """
    Group sales transactions by customer VIP ID.

    Converts flat list of sales into a map of purchases by customer.
    VIP ID blank/0 → key='0'

    Args:
        sales_list: List of SalesTransaction objects
        shop_map: Optional pre-built alias→(title_id, display) dict from get_shop_map().
                  When provided, shop names are normalized to canonical titles.

    Returns:
        Dict[vip_id] -> List[purchase_dict]
        Each purchase_dict contains:
        - date: Purchase date
        - invoice: Invoice number
        - amount: Purchase amount
        - shop: Canonical shop title (normalized via shop_map if provided)
        - customer: Customer object (or None)
        - session: Season label
    """
    from .season_utils import get_session_key, get_month_key, get_year_key, get_week_info
    from .shop_utils import normalize_shop_display

    customer_purchases = defaultdict(list)

    for s in sales_list:
        vid = _norm_vid(s.vip_id or '')
        key = '0' if vid in ('', '0', 'None') else vid
        _wk = get_week_info(s.sales_date)
        customer_purchases[key].append({
            'date':       s.sales_date,
            'invoice':    s.invoice_number,
            'amount':     s.sales_amount or 0,
            'shop':       normalize_shop_display(s.shop_name, shop_map) or 'Unknown Shop',
            'customer':   s.customer if key != '0' else None,
            'session':    get_session_key(s.sales_date),
            'month':      get_month_key(s.sales_date),
            'year':       get_year_key(s.sales_date),
            'week_sort':  _wk[0],
            'week_label': _wk[1],
        })
    
    # Sort each customer's purchases by date once — all aggregators rely on this
    for lst in customer_purchases.values():
        lst.sort(key=lambda x: x['date'])
    return customer_purchases


def get_all_time_grade_counts():
    """
    Get customer counts by grade from database (all-time).

    Returns:
        Dict[grade] -> count
    """
    from App.models import Customer
    from django.db.models import Count

    grade_db = {}
    for row in Customer.objects.values('vip_grade').annotate(cnt=Count('id')):
        g = normalize_grade(row['vip_grade'])
        grade_db[g] = grade_db.get(g, 0) + row['cnt']

    return grade_db


def _make_inv_entry():
    return {
        'sessions': set(), 'months': set(), 'years': set(), 'weeks': set(), 'shops': set(),
        'session_shops': set(), 'month_shops': set(), 'year_shops': set(), 'week_shops': set(),
    }


def build_inv_bucket_map(customer_purchases):
    """
    Build per-customer invoice-bucket presence from customer_purchases (already in memory).

    For each vip_id, records which season/month/week/shop buckets contain invoices.
    Used by Sales Analytics aggregators to compute NEW (INV) / NEW (NO INV) per bucket.

    Returns dict[normalized_vip_id] → {
        'sessions': set of session keys,
        'months': set of month keys,
        'weeks': set of week_sort keys,
        'shops': set of shop names,
        'session_shops': set of (session, shop) tuples,
        'month_shops': set of (month, shop) tuples,
        'week_shops': set of (week_sort, shop) tuples,
    }
    """
    result = {}
    for vip_id, purchases in customer_purchases.items():
        if vip_id == '0':
            continue
        entry = _make_inv_entry()
        for p in purchases:
            sk, mk, yk, wk, shop = p['session'], p['month'], p.get('year'), p['week_sort'], p['shop']
            entry['sessions'].add(sk)
            entry['months'].add(mk)
            if yk:
                entry['years'].add(yk)
                entry['year_shops'].add((yk, shop))
            entry['weeks'].add(wk)
            entry['shops'].add(shop)
            entry['session_shops'].add((sk, shop))
            entry['month_shops'].add((mk, shop))
            entry['week_shops'].add((wk, shop))
        result[vip_id] = entry
    return result


def build_inv_bucket_map_from_db(date_from=None, date_to=None):
    """
    Build per-customer invoice-bucket presence directly from the SalesTransaction table.
    Used by _compute_cnv_breakdown (which doesn't hold customer_purchases in memory).

    Returns (vid_map, pk_map):
        vid_map: dict[normalized_vip_id] → {sessions, months, weeks, shops, ...}
        pk_map:  dict[customer_pk (int)]  → same entry object (shared reference)
    """
    from App.models import SalesTransaction
    from .season_utils import get_session_key, get_month_key, get_year_key, get_week_info
    from .shop_utils import get_shop_map, normalize_shop_display
    _shop_map = get_shop_map()

    qs = (
        SalesTransaction.objects
        .filter(vip_id__isnull=False)
        .exclude(vip_id='').exclude(vip_id='0')
        .order_by()
    )
    if date_from:
        qs = qs.filter(sales_date__gte=date_from)
    if date_to:
        qs = qs.filter(sales_date__lte=date_to)

    vid_map = {}
    pk_map = {}

    for tx in qs.values('vip_id', 'customer_id', 'sales_date', 'shop_name'):
        vid = _norm_vid(tx['vip_id'])
        if not vid or vid == '0':
            continue

        if vid not in vid_map:
            vid_map[vid] = _make_inv_entry()
        entry = vid_map[vid]

        sk    = get_session_key(tx['sales_date'])
        mk    = get_month_key(tx['sales_date'])
        yk    = get_year_key(tx['sales_date'])
        wk, _ = get_week_info(tx['sales_date'])
        shop  = normalize_shop_display((tx['shop_name'] or '').strip(), _shop_map) or 'Unknown'

        entry['sessions'].add(sk)
        entry['months'].add(mk)
        if yk:
            entry['years'].add(yk)
            entry['year_shops'].add((yk, shop))
        entry['weeks'].add(wk)
        entry['shops'].add(shop)
        entry['session_shops'].add((sk, shop))
        entry['month_shops'].add((mk, shop))
        entry['week_shops'].add((wk, shop))

        if tx['customer_id']:
            pk_map[tx['customer_id']] = entry   # shared reference — read-only

    return vid_map, pk_map


def classify_new_inv(inv_info, reg_sk=None, reg_mk=None, reg_yk=None, reg_wk=None):
    """
    ── SHARED FORMULA ──────────────────────────────────────────────────────────
    Used by BOTH Customer Analytics (aggregators.py) and CNV page (cnv/views.py)
    to guarantee identical NEW (INV) / NEW (NO INV) classification.

    Formula:
        new_members_inv[bucket]    = new member AND has invoice in same TIME bucket
                                     (any shop — shop is NEVER part of the inv check)
        new_members_no_inv[bucket] = new_members[bucket] − new_members_inv[bucket]

    For by-shop tables, shop attribution is via registration_store (separate step).
    The invoice check is ALWAYS time-bucket only.

    Args:
        inv_info : {} if no invoices in period; else entry from build_inv_bucket_map*
                   ({sessions, months, years, weeks, ...} with populated sets)
        reg_sk   : registration season key  (e.g. "2024-S2")
        reg_mk   : registration month key   (e.g. "2024-08")
        reg_yk   : registration year key    (e.g. "2024")
        reg_wk   : registration week sort   (e.g. (2024, 32))

    Returns dict:
        'any'    : bool — has ANY invoice in period (used for flat-by-shop top level)
        'season' : bool — has invoice in registration season (any shop)
        'month'  : bool — has invoice in registration month  (any shop)
        'year'   : bool — has invoice in registration year   (any shop)
        'week'   : bool — has invoice in registration week   (any shop)
    """
    return {
        'any':    bool(inv_info),
        'season': reg_sk is not None and reg_sk in inv_info.get('sessions', set()),
        'month':  reg_mk is not None and reg_mk in inv_info.get('months',   set()),
        'year':   reg_yk is not None and reg_yk in inv_info.get('years',    set()),
        'week':   reg_wk is not None and reg_wk in inv_info.get('weeks',    set()),
    }