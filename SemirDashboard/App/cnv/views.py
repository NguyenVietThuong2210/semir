"""
CNV Views
Handles CNV Loyalty integration pages
"""
from django.shortcuts import render
from django.contrib.auth.decorators import login_required
from django.db.models import Q
from datetime import datetime
from django.utils import timezone

from App.models import Customer as POSCustomer
from App.models_cnv import CNVCustomer, CNVOrder, CNVSyncLog
from django.http import HttpResponse
from django.contrib.auth.decorators import login_required
from datetime import datetime

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
    recent_syncs = CNVSyncLog.objects.order_by('-started_at')[:10]
    
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
    Focus on phone number matching
    """
    # Get date filters
    start_date = request.GET.get('start_date')
    end_date = request.GET.get('end_date')
    
    # Parse dates
    period_filter = {}
    period_label = "All Time"
    has_filter = False
    
    if start_date and end_date:
        try:
            start = datetime.strptime(start_date, '%Y-%m-%d')
            end = datetime.strptime(end_date, '%Y-%m-%d')
            period_filter = {
                'start': timezone.make_aware(start),
                'end': timezone.make_aware(end)
            }
            period_label = f"{start_date} to {end_date}"
            has_filter = True
        except ValueError:
            pass
    
    # ============================================
    # ALL TIME DATA
    # ============================================
    
    # All POS customers (excluding VIP ID = 0)
    pos_all = POSCustomer.objects.filter(
        vip_id__isnull=False,
        phone__isnull=False
    ).exclude(
        vip_id=0
    ).exclude(
        phone=''
    )
    
    # Total POS customers (for accurate total, before phone filter)
    total_pos_all = POSCustomer.objects.filter(
        vip_id__isnull=False
    ).exclude(
        vip_id=0
    ).count()
    
    # All CNV customers
    cnv_all = CNVCustomer.objects.filter(
        phone__isnull=False
    ).exclude(
        phone=''
    )
    
    # Total CNV customers (without phone filter for accurate total)
    total_cnv_all = CNVCustomer.objects.count()
    
    # Get phone sets for comparison
    pos_phones_all = set(pos_all.values_list('phone', flat=True))
    cnv_phones_all = set(cnv_all.values_list('phone', flat=True))
    
    # (1) In POS but not in CNV
    pos_only_phones_all = pos_phones_all - cnv_phones_all
    pos_only_all = pos_all.filter(phone__in=pos_only_phones_all).values(
        'vip_id', 'phone', 'name', 'vip_grade', 'email', 'registration_date', 'points'
    ).order_by('-registration_date')[:50]
    
    # (2) In CNV but not in POS
    cnv_only_phones_all = cnv_phones_all - pos_phones_all
    cnv_only_all = cnv_all.filter(phone__in=cnv_only_phones_all).values(
        'customer_id', 'phone', 'full_name', 'email', 'registration_date',
        'total_points_earned', 'total_points_spent'
    ).order_by('-registration_date')[:50]
    
    # ============================================
    # PERIOD DATA
    # ============================================
    
    pos_only_period = []
    cnv_only_period = []
    new_pos_count = 0
    new_cnv_count = 0
    pos_only_period_count = 0
    cnv_only_period_count = 0
    
    if period_filter:
        # New POS customers in period
        pos_period = pos_all.filter(
            registration_date__gte=period_filter['start'],
            registration_date__lte=period_filter['end']
        )
        new_pos_count = pos_period.count()
        
        # New CNV customers in period
        cnv_period = cnv_all.filter(
            registration_date__gte=period_filter['start'],
            registration_date__lte=period_filter['end']
        )
        new_cnv_count = cnv_period.count()
        
        # Get phone sets for period
        pos_phones_period = set(pos_period.values_list('phone', flat=True))
        cnv_phones_period = set(cnv_period.values_list('phone', flat=True))
        
        # (3) New in POS but not in CNV
        pos_only_phones_period = pos_phones_period - cnv_phones_all
        pos_only_period_count = len(pos_only_phones_period)
        pos_only_period = pos_period.filter(phone__in=pos_only_phones_period).values(
            'vip_id', 'phone', 'name', 'vip_grade', 'email', 'registration_date', 'points'
        ).order_by('-registration_date')[:50]
        
        # (4) New in CNV but not in POS
        cnv_only_phones_period = cnv_phones_period - pos_phones_all
        cnv_only_period_count = len(cnv_only_phones_period)
        cnv_only_period = cnv_period.filter(phone__in=cnv_only_phones_period).values(
            'customer_id', 'phone', 'full_name', 'email', 'registration_date',
            'total_points_earned', 'total_points_spent'
        ).order_by('-registration_date')[:50]
    
    # ============================================
    # CONTEXT
    # ============================================
    
    context = {
        # Filter info
        'start_date': start_date or '',
        'end_date': end_date or '',
        'period_label': period_label,
        'has_filter': has_filter,
        
        # All time counts
        'total_pos': total_pos_all,  # Total excluding VIP ID = 0
        'total_cnv': total_cnv_all,  # Total from CNV (no filters)
        'pos_only_all_count': len(pos_only_phones_all),
        'cnv_only_all_count': len(cnv_only_phones_all),
        
        # Period counts
        'new_pos_count': new_pos_count,
        'new_cnv_count': new_cnv_count,
        'pos_only_period_count': pos_only_period_count,
        'cnv_only_period_count': cnv_only_period_count,
        
        # Tables data
        'pos_only_all': list(pos_only_all),
        'cnv_only_all': list(cnv_only_all),
        'pos_only_period': list(pos_only_period),
        'cnv_only_period': list(cnv_only_period),
        
        # Quick buttons (similar to analytics)
        'quick_btns': [
            ('Last 7 Days', 7),
            ('Last 30 Days', 30),
            ('Last 90 Days', 90),
        ],
    }
    
    return render(request, 'cnv/customer_comparison.html', context)


@login_required
def export_customer_comparison(request):
    """
    Export Customer Analytics (POS vs CNV comparison) to Excel.
    Uses export_customer_comparison_to_excel() from excel_export module.
    """
    from App.models import Customer
    from App.analytics.excel_export import export_customer_comparison_to_excel
    
    start_date = request.GET.get('start_date', '')
    end_date = request.GET.get('end_date', '')
    
    # Parse dates
    date_from = None
    date_to = None
    if start_date:
        try:
            date_from = datetime.strptime(start_date, '%Y-%m-%d').date()
        except ValueError:
            pass
    if end_date:
        try:
            date_to = datetime.strptime(end_date, '%Y-%m-%d').date()
        except ValueError:
            pass
    
    # Get all customers
    pos_customers = Customer.objects.all()
    cnv_customers = CNVCustomer.objects.all()
    
    # Generate Excel workbook using excel_export module
    wb = export_customer_comparison_to_excel(
        pos_customers,
        cnv_customers,
        date_from,
        date_to
    )
    
    # Generate filename
    if date_from and date_to:
        filename = f"customer_analytics_{date_from}_{date_to}_{datetime.now().strftime('%H%M%S')}.xlsx"
    else:
        filename = f"customer_analytics_{datetime.now().strftime('%Y%m%d_%H%M%S')}.xlsx"
    
    # Return response
    response = HttpResponse(
        content_type='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'
    )
    response['Content-Disposition'] = f'attachment; filename="{filename}"'
    wb.save(response)
    
    return response