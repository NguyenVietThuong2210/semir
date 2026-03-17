from .home import home, formulas_page
from .upload import upload_customers, upload_sales, upload_coupons, upload_used_points
from .analytics import analytics_dashboard, analytics_chart, export_analytics
from .coupon import coupon_dashboard, export_coupons, coupon_chart, manage_campaigns
from .customer import customer_detail
from . import auth, users

__all__ = [
    "home",
    "formulas_page",
    "upload_customers",
    "upload_sales",
    "upload_coupons",
    "upload_used_points",
    "analytics_dashboard",
    "analytics_chart",
    "export_analytics",
    "coupon_dashboard",
    "export_coupons",
    "coupon_chart",
    "manage_campaigns",
    "customer_detail",
]
