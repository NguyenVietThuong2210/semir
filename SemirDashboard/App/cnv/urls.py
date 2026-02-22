"""
App/cnv/urls.py

URL configuration for CNV sync views.
Add to your main urls.py:
    path('cnv/', include('App.cnv.urls')),
"""
from django.urls import path
from . import views

app_name = 'cnv'

urlpatterns = [
    # Page 1: Sync log history
    path('sync-status/', views.sync_status, name='sync_status'),
    
    # Page 2: Customer comparison
    path('customer-comparison/', views.customer_comparison, name='customer_comparison'),
]