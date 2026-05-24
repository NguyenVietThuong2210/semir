"""
App/urls.py — URL configuration for the main application.
"""
from django.urls import path
from .views import auth, users
from . import views

urlpatterns = [
    # ── Authentication ────────────────────────────────────────────────────────
    path("login/",    auth.login_view,    name="login"),
    path("logout/",   auth.logout_view,   name="logout"),
    path("register/", auth.register_view, name="register"),

    # ── Home & Static ─────────────────────────────────────────────────────────
    path("",           views.home,          name="home"),
    path("formulas/",  views.formulas_page, name="formulas"),

    # ── Data Upload ───────────────────────────────────────────────────────────
    path("upload/customers/",   views.upload_customers,   name="upload_customers"),
    path("upload/used-points/", views.upload_used_points, name="upload_used_points"),
    path("upload/sales/",       views.upload_sales,       name="upload_sales"),
    path("upload/sale-detail/", views.upload_sale_detail, name="upload_sale_detail"),
    path("upload/inventory/",   views.upload_inventory,   name="upload_inventory"),
    path("upload/coupons/",     views.upload_coupons,     name="upload_coupons"),
    path("upload/jobs/",                    views.upload_jobs_list,  name="upload_jobs_list"),
    path("upload/jobs/<str:job_id>/",       views.upload_job_status, name="upload_job_status"),

    # ── Sales Analytics ───────────────────────────────────────────────────────
    path("analytics/",                views.analytics_dashboard,     name="analytics_dashboard"),
    path("analytics/export/",         views.export_analytics,        name="export_analytics"),
    path("analytics/chart/",          views.analytics_chart,         name="analytics_chart"),
    path("analytics/chart/export/",   views.export_sales_chart_excel, name="export_sales_chart_excel"),
    path("analytics/tab/<str:tab>/",  views.analytics_tab,           name="analytics_tab"),

    # ── Coupon Analytics ──────────────────────────────────────────────────────
    path("coupons/",                  views.coupon_dashboard,          name="coupon_dashboard"),
    path("coupons/export/",           views.export_coupons,            name="export_coupons"),
    path("coupons/chart/",            views.coupon_chart,              name="coupon_chart"),
    path("coupons/chart/export/",     views.export_coupon_chart_excel, name="export_coupon_chart_excel"),
    path("coupons/campaigns/",        views.manage_campaigns,          name="manage_campaigns"),
    path("coupons/tab/<str:tab>/",    views.coupon_tab,                name="coupon_tab"),

    # ── Product Analytics ─────────────────────────────────────────────────────
    path("products/",               views.product_dashboard, name="product_dashboard"),
    path("products/tab/<str:tab>/", views.product_tab,       name="product_tab"),

    # ── Customer ──────────────────────────────────────────────────────────────
    path("customer-detail/", views.customer_detail, name="customer_detail"),

    # ── Shop Detail ───────────────────────────────────────────────────────────
    path("shop-detail/",                  views.shop_detail,                   name="shop_detail"),
    path("shop-detail/export/",           views.export_shop_detail_excel,      name="export_shop_detail_excel"),
    path("shop-detail/partial/sales/",    views.shop_detail_sales_partial,     name="shop_detail_sales_partial"),
    path("shop-detail/partial/customer/", views.shop_detail_customer_partial,  name="shop_detail_customer_partial"),
    path("shop-detail/partial/coupon/",     views.shop_detail_coupon_partial,     name="shop_detail_coupon_partial"),
    path("shop-detail/partial/inventory/", views.shop_detail_inventory_partial,  name="shop_detail_inventory_partial"),

    # ── Admin ─────────────────────────────────────────────────────────────────
    path("users/",       users.user_management, name="user_management"),
    path("admin-logs/",  views.admin_logs,       name="admin_logs"),
]
