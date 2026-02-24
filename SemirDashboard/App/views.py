"""
views.py - Customer Analytics Application

Version: 3.1
- Added database statistics with date ranges to upload pages
- Shows min/max dates and total counts for better UX
"""

import logging
from django.shortcuts import render, redirect
from django.contrib import messages
from django.http import HttpResponse
from django.contrib.auth.decorators import login_required
from django.db.models import Min, Max, Count
from datetime import datetime

from App.analytics.core import calculate_return_rate_analytics
from App.analytics.coupon_analytics import calculate_coupon_analytics, export_coupon_to_excel
from App.analytics.excel_export import export_analytics_to_excel
from .forms import CustomerUploadForm, SalesUploadForm
from .utils import process_customer_file, process_sales_file
from .models import Customer, SalesTransaction

logger = logging.getLogger('customer_analytics')

QUICK_BTNS = [
    ('Last 7 Days',  7),
    ('Last 30 Days', 30),
    ('Last 90 Days', 90),
    ('Last Year',    365),
]

YEAR_BTNS = [2024, 2025, 2026]


def _parse_date(val, label, request):
    """Parse date string to date object."""
    if not val:
        return None
    try:
        return datetime.strptime(val, '%Y-%m-%d').date()
    except ValueError:
        messages.warning(request, f'Invalid {label} format')
        return None


def home(request):
    """Home page view."""
    return render(request, 'home.html')


@login_required
def upload_customers(request):
    """
    Upload customer data from Excel/CSV file.
    Now includes database statistics showing date ranges.
    """
    if request.method == 'POST':
        form = CustomerUploadForm(request.POST, request.FILES)
        if form.is_valid():
            f = request.FILES['file']
            logger.info("upload_customers: %s user=%s", f.name, request.user)
            try:
                result = process_customer_file(f)
                messages.success(request,
                    f"Processed {result['total_processed']} customers – "
                    f"Created: {result['created']}, Updated: {result['updated']}")
                for err in result.get('errors', [])[:5]:
                    messages.warning(request, err)
                return redirect('upload_customers')
            except Exception as e:
                logger.exception("upload_customers error")
                messages.error(request, f'Error: {e}')
    else:
        form = CustomerUploadForm()
    
    # Get database statistics with date ranges
    date_stats = Customer.objects.aggregate(
        min_date=Min('registration_date'),
        max_date=Max('registration_date'),
        total_count=Count('id')
    )
    
    return render(request, 'upload_customers.html', {
        'form': form,
        'date_stats': date_stats
    })


@login_required
def upload_sales(request):
    """
    Upload sales transaction data from Excel/CSV file.
    Now includes database statistics showing date ranges.
    """
    if request.method == 'POST':
        form = SalesUploadForm(request.POST, request.FILES)
        if form.is_valid():
            f = request.FILES['file']
            logger.info("upload_sales: %s user=%s", f.name, request.user)
            try:
                result = process_sales_file(f)
                messages.success(request,
                    f"Imported {result['created']} new transactions. "
                    f"Updated (overwritten) {result['updated']} existing.")
                for err in result.get('errors', [])[:5]:
                    messages.warning(request, err)
                return redirect('analytics_dashboard')
            except Exception as e:
                logger.exception("upload_sales error")
                messages.error(request, f'Error: {e}')
    else:
        form = SalesUploadForm()
    
    # Get database statistics with date ranges
    date_stats = SalesTransaction.objects.aggregate(
        min_date=Min('sales_date'),
        max_date=Max('sales_date'),
        total_count=Count('id')
    )
    
    return render(request, 'upload_sales.html', {
        'form': form,
        'date_stats': date_stats
    })


@login_required
def upload_coupons(request):
    """Upload coupon data from Excel/CSV file."""
    if request.method == 'POST' and request.FILES.get('file'):
        f = request.FILES['file']
        logger.info("upload_coupons: %s user=%s", f.name, request.user)
        try:
            from .utils import process_coupon_file
            result = process_coupon_file(f)
            messages.success(request,
                f"Coupon import complete – Created: {result['created']}, "
                f"Updated (overwritten): {result['updated']}, Errors: {result['errors']}")
        except Exception as e:
            logger.exception("upload_coupons error")
            messages.error(request, f'Error: {e}')
        return redirect('upload_coupons')
    return render(request, 'upload_coupons.html')


@login_required
def analytics_dashboard(request):
    """
    Main analytics dashboard showing return visit rate statistics.
    Supports date range filtering and shop group filtering via query parameters.
    """
    start_date = request.GET.get('start_date', '')
    end_date   = request.GET.get('end_date', '')
    shop_group = request.GET.get('shop_group', '')  # New: Bala Group, Semir Group, Others Group
    
    date_from  = _parse_date(start_date, 'start date', request)
    date_to    = _parse_date(end_date,   'end date',   request)

    if date_from and date_to and date_from > date_to:
        messages.error(request, 'Start date must be before end date')
        date_from = date_to = None

    logger.info("analytics_dashboard: from=%s to=%s shop_group=%s user=%s", 
                date_from, date_to, shop_group, request.user)
    data = calculate_return_rate_analytics(
        date_from=date_from, 
        date_to=date_to,
        shop_group=shop_group or None
    )

    if not data:
        messages.info(request, 'No sales data. Please upload sales data first.')
        return redirect('upload_sales')

    return render(request, 'analytics_dashboard.html', {
        'date_range':         data['date_range'],
        'session_label':      data.get('session_label'),
        'overview':           data['overview'],
        'grade_stats':        data['by_grade'],
        'session_stats':      data['by_session'],
        'shop_stats':         data['by_shop'],
        'by_shop':            data['by_shop'],  # For comparison tabs
        'customer_details':   data['customer_details'][:100],
        'total_detail_count': len(data['customer_details']),
        'buyer_without_info_stats': data.get('buyer_without_info_stats', {}),
        'start_date':         start_date,
        'end_date':           end_date,
        'shop_group':         shop_group,  # New: pass to template
        'quick_btns':         QUICK_BTNS,
        'year_btns':          YEAR_BTNS,
        'currency':           'VND',  # Currency constant
    })


@login_required
def export_analytics(request):
    """Export analytics data to Excel file."""
    start_date = request.GET.get('start_date', '')
    end_date   = request.GET.get('end_date', '')
    shop_group = request.GET.get('shop_group', '')  # New: include shop_group in export
    
    date_from  = _parse_date(start_date, 'start date', request)
    date_to    = _parse_date(end_date,   'end date',   request)
    
    data = calculate_return_rate_analytics(
        date_from=date_from, 
        date_to=date_to,
        shop_group=shop_group or None
    )
    if not data:
        messages.error(request, 'No data to export')
        return redirect('analytics_dashboard')
    
    # Pass filter info to export
    wb = export_analytics_to_excel(data, date_from=date_from, date_to=date_to, shop_group=shop_group)
    
    fn = (f"return_visit_rate_{date_from}_{date_to}_{datetime.now().strftime('%H%M%S')}.xlsx"
          if date_from and date_to else
          f"return_visit_rate_{datetime.now().strftime('%Y%m%d_%H%M%S')}.xlsx")
    resp = HttpResponse(content_type='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet')
    resp['Content-Disposition'] = f'attachment; filename="{fn}"'
    wb.save(resp)
    return resp


@login_required
def coupon_dashboard(request):
    """
    Coupon analytics dashboard.
    Supports date range filtering and coupon ID prefix search.
    """
    start_date       = request.GET.get('start_date', '')
    end_date         = request.GET.get('end_date', '')
    coupon_id_prefix = request.GET.get('coupon_id_prefix', '').strip()
    date_from  = _parse_date(start_date, 'start date', request)
    date_to    = _parse_date(end_date,   'end date',   request)

    logger.info("coupon_dashboard: from=%s to=%s prefix=%s user=%s",
                date_from, date_to, coupon_id_prefix, request.user)
    data = calculate_coupon_analytics(
        date_from=date_from, date_to=date_to,
        coupon_id_prefix=coupon_id_prefix or None)

    return render(request, 'coupon_dashboard.html', {
        'all_time':          data['all_time'],
        'period':            data['period'],
        'by_shop':           data['by_shop'],
        'details':           data['details'],
        'start_date':        start_date,
        'end_date':          end_date,
        'coupon_id_prefix':  coupon_id_prefix,
        'quick_btns':        QUICK_BTNS,
    })


@login_required
def export_coupons(request):
    """Export coupon analytics to Excel file."""
    start_date       = request.GET.get('start_date', '')
    end_date         = request.GET.get('end_date', '')
    coupon_id_prefix = request.GET.get('coupon_id_prefix', '').strip()
    date_from  = _parse_date(start_date, 'start date', request)
    date_to    = _parse_date(end_date,   'end date',   request)
    data = calculate_coupon_analytics(
        date_from=date_from, date_to=date_to,
        coupon_id_prefix=coupon_id_prefix or None)
    wb = export_coupon_to_excel(data, date_from=date_from, date_to=date_to)
    fn = (f"coupon_{date_from}_{date_to}_{datetime.now().strftime('%H%M%S')}.xlsx"
          if date_from and date_to else
          f"coupon_{datetime.now().strftime('%Y%m%d_%H%M%S')}.xlsx")
    resp = HttpResponse(content_type='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet')
    resp['Content-Disposition'] = f'attachment; filename="{fn}"'
    wb.save(resp)
    return resp


@login_required
def formulas_page(request):
    """Display formulas and definitions used in analytics."""
    return render(request, 'formulas.html')