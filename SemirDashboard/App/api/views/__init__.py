"""
App/api/views/__init__.py — FACADE (R4 refactor, 2026-07-12).

Implementation lives in the sibling modules; every historical import path
(`from App.api.views import X`, settings dotted-paths, urls.py) keeps working.
"""
from .helpers import (  # noqa: F401
    _fmt, _fmtd, _pct, _pct_cell,
    custom_exception_handler, _get_user_permissions, _parse_date, _LoginThrottle,
)
from .auth import LoginView, TokenRefreshView, LogoutView  # noqa: F401
from .analytics import (  # noqa: F401
    SalesAnalyticsView, CustomerAnalyticsView, CouponAnalyticsView,
    _compute_grade_rows,
    _sales_grade_table, _sales_season_table, _sales_month_table,
    _sales_week_table, _sales_shop_table,
    _cnv_shop_table, _cnv_month_table, _cnv_season_table, _cnv_week_table,
    _cnv_grade_table, _cnv_pos_only_table, _cnv_cnv_only_table, _cnv_both_table,
    _cnv_zalo_stats_table,
    _coupon_shop_table, _coupon_detail_table, _coupon_dup_table,
)
from .shops import (  # noqa: F401
    ShopsListView, ShopDetailView,
    _kpi_dict, _build_shop_sales, _build_shop_customer, _build_shop_coupon,
    _zalo_active_table, _cnv_period_table,
)
from .detail import CustomerDetailView, _mask_phone  # noqa: F401
from .charts import (  # noqa: F401
    SalesChartView, CustomerChartView, CouponChartView,
    DONUT_PALETTE, _sales_donut, _sales_trend,
)
