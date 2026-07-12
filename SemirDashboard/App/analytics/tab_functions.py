"""
App/analytics/tab_functions.py
──────────────────────────────
FACADE (R3 refactor, 2026-07-12): implementation now lives in the four domain
modules below; every historical import path keeps working unchanged.

  sales_tabs.py        — get_sales_tab, _load_sales, SALES_TABS
  coupon_tabs.py       — get_coupon_tab, COUPON_TABS
  customer_tabs.py     — get_customer_tab, CUSTOMER_TABS (bd_* + ca_*)
  shop_detail_data.py  — get_shop_detail_{sales,customer,coupon}_data
"""
from .sales_tabs import (  # noqa: F401
    SALES_TABS,
    get_sales_tab,
    _load_sales,
    _group_periods,
    _group_flat_by_period,
    _get_cached_by_shop,
    _sales_grade_with_overview,
    _get_period_keys,
    _build_customer_details,
)
from .coupon_tabs import (  # noqa: F401
    COUPON_TABS,
    get_coupon_tab,
    _build_coupon_qs,
    _coupon_shop_tab,
    _coupon_detail_tab,
    _coupon_duplicates_tab,
)
from .customer_tabs import (  # noqa: F401
    BD_TABS,
    CA_TABS,
    CUSTOMER_TABS,
    get_customer_tab,
    _parse_cnv_period_filter,
    _get_cnv_phone_sets,
    _BD_DIMS,
    _customer_bd_tab,
    _customer_ca_points,
    _customer_ca_zalo,
    _customer_ca_pos_cnv,
)
from .shop_detail_data import (  # noqa: F401
    get_shop_detail_sales_data,
    get_shop_detail_customer_data,
    get_shop_detail_coupon_data,
)
