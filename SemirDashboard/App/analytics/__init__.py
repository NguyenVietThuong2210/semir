"""
App/analytics package

Modular analytics system for customer return rate and coupon analysis.

Main entry points:
- calculate_return_rate_analytics() - Customer analytics
- calculate_coupon_analytics() - Coupon analytics
- export_analytics_to_excel() - Excel export
- export_coupon_to_excel() - Coupon Excel export

Version: 3.3
"""

from .core import calculate_return_rate_analytics
from .coupon_analytics import calculate_coupon_analytics, export_coupon_to_excel
from .excel_export import export_analytics_to_excel

__version__ = '3.3'

__all__ = [
    'calculate_return_rate_analytics',
    'calculate_coupon_analytics',
    'export_analytics_to_excel',
    'export_coupon_to_excel',
]