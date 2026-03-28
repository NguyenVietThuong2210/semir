"""
App/urls.py — URL configuration for the main application.
"""
from django.urls import path
from .views import auth, users
from . import views
from .views import shop_names

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
    path("upload/coupons/",     views.upload_coupons,     name="upload_coupons"),
    path("upload/jobs/",                    views.upload_jobs_list,  name="upload_jobs_list"),
    path("upload/jobs/<str:job_id>/",       views.upload_job_status, name="upload_job_status"),

    # ── Sales Analytics ───────────────────────────────────────────────────────
    path("analytics/",         views.analytics_dashboard, name="analytics_dashboard"),
    path("analytics/export/",  views.export_analytics,    name="export_analytics"),
    path("analytics/chart/",   views.analytics_chart,     name="analytics_chart"),

    # ── Coupon Analytics ──────────────────────────────────────────────────────
    path("coupons/",            views.coupon_dashboard,  name="coupon_dashboard"),
    path("coupons/export/",     views.export_coupons,    name="export_coupons"),
    path("coupons/chart/",      views.coupon_chart,      name="coupon_chart"),
    path("coupons/campaigns/",  views.manage_campaigns,  name="manage_campaigns"),

    # ── Customer ──────────────────────────────────────────────────────────────
    path("customer-detail/", views.customer_detail, name="customer_detail"),

    # ── Admin ─────────────────────────────────────────────────────────────────
    path("users/", users.user_management, name="user_management"),

    # ── Shop Name Management (CRUD) ───────────────────────────────────────────
    path("shop-names/",                              shop_names.shop_titles_list,   name="shop_titles_list"),
    path("shop-names/raw/",                          shop_names.shop_raw_names,     name="shop_raw_names"),
    path("shop-names/title/create/",                 shop_names.shop_title_create,  name="shop_title_create"),
    path("shop-names/title/<int:title_id>/update/",  shop_names.shop_title_update,  name="shop_title_update"),
    path("shop-names/title/<int:title_id>/delete/",  shop_names.shop_title_delete,  name="shop_title_delete"),
    path("shop-names/alias/create/",                 shop_names.shop_alias_create,  name="shop_alias_create"),
    path("shop-names/alias/<int:alias_id>/update/",  shop_names.shop_alias_update,  name="shop_alias_update"),
    path("shop-names/alias/<int:alias_id>/delete/",  shop_names.shop_alias_delete,  name="shop_alias_delete"),
    path("shop-names/seed/",                         shop_names.shop_seed_titles,   name="shop_seed_titles"),
]
