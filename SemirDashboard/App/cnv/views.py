"""
CNV Customer Comparison View
Compares internal POS system customers with CNV Loyalty system customers
"""
from django.shortcuts import render
from django.contrib.auth.decorators import login_required
from django.db.models import Q, Count, Sum
from datetime import datetime, timedelta
from django.utils import timezone

from App.models import Customer as POSCustomer, SalesTransaction
from App.models_cnv import CNVCustomer, CNVOrder, CNVSyncLog


@login_required
def sync_status(request):
    """
    CNV Sync Status Dashboard
    Shows latest sync logs and statistics
    """
    # Get latest sync logs
    latest_customer_sync = CNVSyncLog.objects.filter(
        sync_type='customers'
    ).order_by('-completed_at').first()
    
    latest_order_sync = CNVSyncLog.objects.filter(
        sync_type='orders'
    ).order_by('-completed_at').first()
    
    # Get statistics
    total_customers = CNVCustomer.objects.count()
    total_orders = CNVOrder.objects.count()
    
    # Recent sync history (last 10)
    recent_syncs = CNVSyncLog.objects.order_by('-completed_at')[:10]
    
    context = {
        'latest_customer_sync': latest_customer_sync,
        'latest_order_sync': latest_order_sync,
        'total_customers': total_customers,
        'total_orders': total_orders,
        'recent_syncs': recent_syncs,
    }
    
    return render(request, 'cnv/sync_status.html', context)


@login_required
def customer_comparison(request):
    """
    Compare POS System vs CNV Loyalty customers
    Shows 4 tables: All Time + Period for both systems
    """
    # Get date filters
    start_date = request.GET.get('start_date')
    end_date = request.GET.get('end_date')
    
    # Parse dates
    period_filter = {}
    period_label = "All Time"
    
    if start_date and end_date:
        try:
            start = datetime.strptime(start_date, '%Y-%m-%d')
            end = datetime.strptime(end_date, '%Y-%m-%d')
            period_filter = {
                'start': timezone.make_aware(start),
                'end': timezone.make_aware(end)
            }
            period_label = f"{start_date} to {end_date}"
        except ValueError:
            pass
    
    # ============================================
    # ALL TIME DATA
    # ============================================
    
    # POS System - All Time
    pos_all_time = POSCustomer.objects.filter(
        vip_id__isnull=False
    ).exclude(
        vip_id=0
    ).values(
        'vip_id', 
        'phone', 
        'name', 
        'vip_grade', 
        'email', 
        'registration_date',
        'points'  # Use points field directly
    ).order_by('-registration_date')
    
    # CNV - All Time  
    cnv_all_time = CNVCustomer.objects.values(
        'customer_id',
        'phone',
        'full_name',
        'email',
        'registration_date',
        'points_balance',
        'total_points_earned'
    ).order_by('-registration_date')
    
    # ============================================
    # PERIOD DATA (if filtered)
    # ============================================
    
    pos_period = []
    cnv_period = []
    
    if period_filter:
        # POS System - Period
        pos_period = POSCustomer.objects.filter(
            vip_id__isnull=False,
            registration_date__gte=period_filter['start'],
            registration_date__lte=period_filter['end']
        ).exclude(
            vip_id=0
        ).values(
            'vip_id',
            'phone',
            'name',
            'vip_grade',
            'email',
            'registration_date',
            'points'  # Use points field directly
        ).order_by('-registration_date')
        
        # CNV - Period
        cnv_period = CNVCustomer.objects.filter(
            registration_date__gte=period_filter['start'],
            registration_date__lte=period_filter['end']
        ).values(
            'customer_id',
            'phone',
            'full_name',
            'email',
            'registration_date',
            'points_balance',
            'total_points_earned'
        ).order_by('-registration_date')
    
    # ============================================
    # STATISTICS
    # ============================================
    
    stats = {
        'pos_all_time_count': pos_all_time.count(),
        'cnv_all_time_count': cnv_all_time.count(),
        'pos_period_count': len(pos_period) if period_filter else 0,
        'cnv_period_count': len(cnv_period) if period_filter else 0,
        'period_label': period_label,
        'has_period_filter': bool(period_filter)
    }
    
    context = {
        'pos_all_time': list(pos_all_time),
        'cnv_all_time': list(cnv_all_time),
        'pos_period': list(pos_period),
        'cnv_period': list(cnv_period),
        'stats': stats,
        'start_date': start_date or '',
        'end_date': end_date or '',
    }
    
    return render(request, 'cnv/customer_comparison.html', context)