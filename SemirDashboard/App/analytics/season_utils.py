"""
App/analytics/season_utils.py

Date and season handling utilities.
Pure functions with no database or model dependencies.

Version: 3.3
"""

# Season definitions
SEASON_DEFS = [
    ('M2-4',  [2, 3, 4]),      # Feb-Apr
    ('M5-7',  [5, 6, 7]),      # May-Jul
    ('M8-10', [8, 9, 10]),     # Aug-Oct
    ('M11-1', [11, 12, 1]),    # Nov-Jan (crosses year boundary)
]


def get_session_key(d):
    """
    Convert a date to a season label (year-aware).
    
    Handles cross-year seasons (M11-1) correctly.
    
    Args:
        d: datetime.date object
    
    Returns:
        String season label like "M2-4 2025" or "M11-1 2024-2025"
    
    Examples:
        2025-02-15 → "M2-4 2025"
        2025-06-10 → "M5-7 2025"
        2024-12-25 → "M11-1 2024-2025"
        2025-01-05 → "M11-1 2024-2025"
    """
    if not d:
        return 'Unknown'
    
    m, y = d.month, d.year
    
    for prefix, months in SEASON_DEFS:
        if m in months:
            if prefix == 'M11-1':
                # Cross-year season: Nov-Jan
                # If January, belongs to Nov-Dec of previous year
                return f"M11-1 {y-1}-{y}" if m == 1 else f"M11-1 {y}-{y+1}"
            return f"{prefix} {y}"
    
    return 'Unknown'


def session_sort_key(label):
    """
    Generate sort key for season labels to order chronologically.
    
    Args:
        label: Season label like "M2-4 2025"
    
    Returns:
        Tuple (year, season_order) for sorting
    
    Examples:
        "M2-4 2024" → (2024, 0)
        "M11-1 2024-2025" → (2024, 3)
        "M2-4 2025" → (2025, 0)
    """
    parts = label.rsplit(' ', 1)
    if len(parts) != 2:
        return (9999, 99)  # Unknown/invalid labels sort last
    
    prefix, years = parts[0], parts[1]
    
    try:
        # Extract first year from "2025" or "2024-2025"
        first_year = int(years.split('-')[0])
    except ValueError:
        return (9999, 99)
    
    # Season order within a year
    order_map = {'M2-4': 0, 'M5-7': 1, 'M8-10': 2, 'M11-1': 3}
    season_order = order_map.get(prefix, 99)
    
    return (first_year, season_order)


def get_session_for_range(date_from, date_to):
    """
    Determine if a date range corresponds to a single season.
    
    Args:
        date_from: Start date
        date_to: End date
    
    Returns:
        Season label if range fits in one season, None otherwise
    
    Examples:
        2025-02-01 to 2025-04-30 → "M2-4" (fits in one season)
        2025-02-01 to 2025-06-30 → None (spans multiple seasons)
    """
    if not date_from or not date_to:
        return None
    
    # Get all months in the range
    months = set()
    cur = date_from.replace(day=1)
    
    while cur <= date_to:
        months.add(cur.month)
        # Move to next month
        if cur.month == 12:
            cur = cur.replace(year=cur.year + 1, month=1)
        else:
            cur = cur.replace(month=cur.month + 1)
    
    # Check if all months fit in a single season
    for label, m_list in SEASON_DEFS:
        if months.issubset(set(m_list)):
            return label
    
    return None