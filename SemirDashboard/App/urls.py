from django.urls import path
from . import views, auth_views

urlpatterns = [
    path('login/',           auth_views.login_view,       name='login'),
    path('logout/',          auth_views.logout_view,      name='logout'),
    path('register/',        auth_views.register_view,    name='register'),
    path('',                 views.home,                  name='home'),
    path('formulas/',        views.formulas_page,         name='formulas'),
    path('upload/customers/',   views.upload_customers,    name='upload_customers'),
    path('upload/used-points/', views.upload_used_points,  name='upload_used_points'),
    path('upload/sales/',       views.upload_sales,        name='upload_sales'),
    path('upload/coupons/',  views.upload_coupons,        name='upload_coupons'),
    path('analytics/',       views.analytics_dashboard,   name='analytics_dashboard'),
    path('analytics/export/',views.export_analytics,      name='export_analytics'),
    path('coupons/',         views.coupon_dashboard,      name='coupon_dashboard'),
    path('coupons/export/',  views.export_coupons,        name='export_coupons'),
    path('customer-detail/', views.customer_detail,       name='customer_detail'),
]