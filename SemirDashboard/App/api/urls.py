"""
App/api/urls.py — SemirPhone JSON API URL routes.
Mounted at /api/v1/ via SemirDashboard/urls.py.
"""
from django.urls import path

from .views import (
    LoginView,
    TokenRefreshView,
    LogoutView,
    SalesAnalyticsView,
    CustomerAnalyticsView,
    CouponAnalyticsView,
    ShopsListView,
    ShopDetailView,
    CustomerDetailView,
    SalesChartView,
    CustomerChartView,
    CouponChartView,
)

urlpatterns = [
    # Auth
    path('auth/token/', LoginView.as_view(), name='api-login'),
    path('auth/token/refresh/', TokenRefreshView.as_view(), name='api-token-refresh'),
    path('auth/logout/', LogoutView.as_view(), name='api-logout'),

    # Analytics
    path('analytics/sales/', SalesAnalyticsView.as_view(), name='api-sales'),
    path('analytics/customer/', CustomerAnalyticsView.as_view(), name='api-customer'),
    path('analytics/coupon/', CouponAnalyticsView.as_view(), name='api-coupon'),
    path('analytics/shops/', ShopsListView.as_view(), name='api-shops'),
    path('analytics/shop-detail/', ShopDetailView.as_view(), name='api-shop-detail'),
    path('analytics/customer-detail/', CustomerDetailView.as_view(), name='api-customer-detail'),

    # Charts
    path('charts/sales/', SalesChartView.as_view(), name='api-charts-sales'),
    path('charts/customer/', CustomerChartView.as_view(), name='api-charts-customer'),
    path('charts/coupon/', CouponChartView.as_view(), name='api-charts-coupon'),
]
