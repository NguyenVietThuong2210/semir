"""
App/analytics.py

Entry point for analytics functionality.
This module provides a clean interface to the analytics submodule.

All actual logic is in App/analytics/ subdirectory.
This file exists for backward compatibility with existing views code.

Version: 3.3 - Refactored modular structure
"""

# Import main functions from submodules
from .analytics.core import calculate_return_rate_analytics
from .analytics.coupon_analytics import (
    calculate_coupon_analytics,
    export_coupon_to_excel,
)
from .analytics.excel_export import export_analytics_to_excel

# Public API - these are what views.py imports
__all__ = [
    'calculate_return_rate_analytics',
    'calculate_coupon_analytics',
    'export_analytics_to_excel',
    'export_coupon_to_excel',
]