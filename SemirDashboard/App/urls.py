from django.urls import path
from . import views

urlpatterns = [
    path('', views.home, name='home'),
    path('upload/customers/', views.upload_customers, name='upload_customers'),
    path('upload/sales/', views.upload_sales, name='upload_sales'),
    path('analytics/', views.analytics_dashboard, name='analytics_dashboard'),
    path('analytics/export/', views.export_analytics, name='export_analytics'),
]