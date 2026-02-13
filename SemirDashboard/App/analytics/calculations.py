"""
App/analytics/calculations.py

Pure calculation functions with NO side effects or database access.
All return visit formulas and mathematical calculations.

⚠️ RETURN VISIT FORMULA - DO NOT CHANGE WITHOUT USER APPROVAL
This formula counts INVOICES, not unique days (user-confirmed).

Version: 3.3
"""
from decimal import Decimal


def calculate_return_visits(purchases_sorted, reg_date):
    """
    🎯 RETURN VISIT CALCULATION - By INVOICES (user-confirmed formula)
    
    ⚠️ DO NOT CHANGE THIS FORMULA WITHOUT USER APPROVAL
    
    This is the SINGLE source of truth for return visit calculations.
    Formula counts INVOICES, not unique days.
    
    Rule:
      - If reg_date == first_purchase_date:
          First invoice = first visit (NOT a return)
          Subsequent invoices = return visits
          return_visits = total_purchases - 1
      
      - If reg_date != first_purchase_date (or no reg):
          Customer already visited to register
          ALL invoices are return visits
          return_visits = total_purchases
      
      - is_returning = return_visits > 0
    
    Example 1: Registration day purchases
      Reg: 2025-01-01
      Purchases: 2025-01-01 (3 invoices)
      first_date == reg_date → return_visits = 3 - 1 = 2
      is_returning = True ✅
    
    Example 2: Registered before, now buying
      Reg: 2025-01-01
      Purchases: 2025-02-15 (2 invoices)
      first_date != reg_date → return_visits = 2
      is_returning = True ✅
    
    Args:
        purchases_sorted: List of purchase dicts sorted by date
        reg_date: Customer registration date (datetime.date or None)
    
    Returns:
        (return_visits, is_returning) tuple
        - return_visits: int, number of return visit invoices
        - is_returning: bool, True if customer has any return visits
    """
    n = len(purchases_sorted)
    if n == 0:
        return (0, False)
    
    first_date = purchases_sorted[0]['date']
    
    # Apply the formula
    if reg_date and first_date == reg_date:
        # First invoice on registration day = NOT a return
        # Subsequent invoices = return visits
        return_visits = n - 1
    else:
        # Customer registered before first purchase (or no reg date)
        # ALL invoices count as return visits
        return_visits = n
    
    is_returning = (return_visits > 0)
    
    return (return_visits, is_returning)


def calculate_return_rate(returning_count, total_count):
    """
    Calculate return rate percentage.
    
    Args:
        returning_count: Number of returning customers
        total_count: Total number of customers
    
    Returns:
        Float percentage rounded to 2 decimal places
    """
    if total_count == 0:
        return 0.0
    return round(returning_count / total_count * 100, 2)


def create_empty_bucket():
    """
    Create empty bucket for data aggregation.
    
    Returns:
        Dict with default values for aggregation
    """
    return {
        'active': 0,
        'returning': 0,
        'invoices': 0,
        'amount': Decimal(0)
    }


def create_empty_grade_bucket():
    """
    Create empty bucket for grade aggregation with sets.
    
    Returns:
        Dict with sets for customer tracking
    """
    return {
        'active': set(),
        'returning': set(),
        'invoices': 0,
        'amount': Decimal(0)
    }