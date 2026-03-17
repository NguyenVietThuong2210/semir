"""
App/cnv/urls.py

URL configuration for CNV Loyalty integration views.
"""
from django.urls import path
from . import views

app_name = 'cnv'

urlpatterns = [
    # CNV Sync
    path('sync-status/', views.sync_status, name='sync_status'),

    # Customer Analytics (POS ↔ CNV comparison)
    path('customer-analytics/', views.customer_analytics, name='customer_analytics'),
    path('export-customer-analytics/', views.export_customer_analytics, name='export_customer_analytics'),

    # AJAX: Sync CNV points for selected customers
    path('sync-cnv-points/', views.sync_cnv_points, name='sync_cnv_points'),

    # AJAX: Manual sync triggers
    path('trigger-sync/', views.trigger_sync, name='trigger_sync'),
    path('trigger-zalo-sync/', views.trigger_zalo_sync, name='trigger_zalo_sync'),
]
