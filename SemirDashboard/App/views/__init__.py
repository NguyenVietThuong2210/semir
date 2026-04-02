from .home import home, formulas_page
from .upload import upload_customers, upload_sales, upload_coupons, upload_used_points, upload_jobs_list, upload_job_status
from .analytics import analytics_dashboard, analytics_chart, export_analytics, analytics_tab
from .coupon import coupon_dashboard, export_coupons, coupon_chart, manage_campaigns, coupon_tab
from .customer import customer_detail
from . import auth, users

__all__ = [
    "home",
    "formulas_page",
    "upload_customers",
    "upload_sales",
    "upload_coupons",
    "upload_used_points",
    "upload_jobs_list",
    "upload_job_status",
    "analytics_dashboard",
    "analytics_chart",
    "export_analytics",
    "analytics_tab",
    "coupon_dashboard",
    "export_coupons",
    "coupon_chart",
    "manage_campaigns",
    "coupon_tab",
    "customer_detail",
]
