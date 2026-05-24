from .home import home, formulas_page
from .upload import (
    upload_customers, upload_sales, upload_coupons, upload_used_points,
    upload_sale_detail, upload_inventory,
    upload_jobs_list, upload_job_status,
)
from .analytics import analytics_dashboard, analytics_chart, export_analytics, analytics_tab, export_sales_chart_excel
from .coupon import coupon_dashboard, export_coupons, coupon_chart, manage_campaigns, coupon_tab, export_coupon_chart_excel
from .customer import customer_detail
from .admin_logs import admin_logs
from .shop_detail import (
    shop_detail, export_shop_detail_excel,
    shop_detail_sales_partial, shop_detail_customer_partial, shop_detail_coupon_partial,
    shop_detail_inventory_partial,
)
from .product import product_dashboard, product_tab
from . import auth, users

__all__ = [
    "home",
    "formulas_page",
    "upload_customers",
    "upload_sales",
    "upload_coupons",
    "upload_used_points",
    "upload_sale_detail",
    "upload_inventory",
    "upload_jobs_list",
    "upload_job_status",
    "analytics_dashboard",
    "analytics_chart",
    "export_analytics",
    "analytics_tab",
    "export_sales_chart_excel",
    "coupon_dashboard",
    "export_coupons",
    "coupon_chart",
    "manage_campaigns",
    "coupon_tab",
    "export_coupon_chart_excel",
    "customer_detail",
    "admin_logs",
    "shop_detail",
    "export_shop_detail_excel",
    "shop_detail_sales_partial",
    "shop_detail_customer_partial",
    "shop_detail_coupon_partial",
    "shop_detail_inventory_partial",
    "product_dashboard",
    "product_tab",
]
