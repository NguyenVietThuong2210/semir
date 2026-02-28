"""
CNV Views
Handles CNV Loyalty integration pages
"""
from django.conf import settings
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
    from django.db.models import Subquery, OuterRef, IntegerField

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
    # BASE QUERYSETS (no phone__in on large sets)
    # ============================================

    # All POS customers (excluding VIP ID = 0)
    pos_all = POSCustomer.objects.filter(
        vip_id__isnull=False,
        phone__isnull=False,
    ).exclude(vip_id=0).exclude(phone='')

    # Total POS customers
    total_pos_all = POSCustomer.objects.filter(
        vip_id__isnull=False
    ).exclude(vip_id=0).count()

    # All CNV customers with phone
    cnv_all = CNVCustomer.objects.filter(
        phone__isnull=False
    ).exclude(phone='')

    total_cnv_all = CNVCustomer.objects.count()

    # Subquery helpers — avoids passing large Python sets into SQL
    cnv_phones_sq = CNVCustomer.objects.filter(
        phone=OuterRef('phone'), phone__isnull=False
    ).exclude(phone='').values('phone')[:1]

    pos_phones_sq = POSCustomer.objects.filter(
        phone=OuterRef('phone'), phone__isnull=False
    ).exclude(phone='').exclude(vip_id=0).values('phone')[:1]

    # ============================================
    # ALL TIME: counts (done in Python from small intermediate sets)
    # ============================================

    # Fetch phone sets — just phone strings, efficient
    pos_phones_all = set(pos_all.values_list('phone', flat=True))
    cnv_phones_all = set(cnv_all.values_list('phone', flat=True))

    pos_only_phones_all = pos_phones_all - cnv_phones_all
    cnv_only_phones_all = cnv_phones_all - pos_phones_all

    # (1) POS Only - All Time — use subquery, NOT __in with full set
    pos_only_all = pos_all.exclude(
        phone__in=Subquery(cnv_all.values('phone'))
    ).values(
        'vip_id', 'phone', 'name', 'vip_grade', 'email', 'registration_date', 'points'
    ).order_by('-registration_date')[:50]

    # (2) CNV Only - All Time — use subquery
    cnv_only_all = cnv_all.exclude(
        phone__in=Subquery(pos_all.values('phone'))
    ).values(
        'cnv_id', 'phone', 'last_name', 'first_name', 'level_name', 'email',
        'cnv_created_at', 'points', 'total_points', 'used_points'
    ).order_by('-cnv_created_at')[:50]

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
        pos_period = pos_all.filter(
            registration_date__gte=period_filter['start'],
            registration_date__lte=period_filter['end']
        )
        new_pos_count = pos_period.count()

        cnv_period = cnv_all.filter(
            cnv_created_at__gte=period_filter['start'],
            cnv_created_at__lte=period_filter['end']
        )
        new_cnv_count = cnv_period.count()

        # (3) New POS not in CNV at all — subquery
        pos_only_period_qs = pos_period.exclude(
            phone__in=Subquery(cnv_all.values('phone'))
        )
        pos_only_period_count = pos_only_period_qs.count()
        pos_only_period = pos_only_period_qs.values(
            'vip_id', 'phone', 'name', 'vip_grade', 'email', 'registration_date', 'points'
        ).order_by('-registration_date')[:50]

        # (4) New CNV not in POS at all — subquery
        cnv_only_period_qs = cnv_period.exclude(
            phone__in=Subquery(pos_all.values('phone'))
        )
        cnv_only_period_count = cnv_only_period_qs.count()
        cnv_only_period = cnv_only_period_qs.values(
            'cnv_id', 'phone', 'last_name', 'first_name', 'level_name', 'email',
            'cnv_created_at', 'points', 'total_points', 'used_points'
        ).order_by('-cnv_created_at')[:50]

    # ============================================
    # POINTS MISMATCH — fetch both tables fully, join in Python
    # No phone__in with large set; instead fetch all matched rows via subquery
    # ============================================

    # Fetch POS rows that have a matching CNV phone (subquery)
    pos_matched_qs = pos_all.filter(
        phone__in=Subquery(cnv_all.values('phone'))
    ).values('vip_id', 'phone', 'name', 'vip_grade', 'points', 'used_points')

    # Fetch CNV rows that have a matching POS phone (subquery)
    cnv_matched_qs = cnv_all.filter(
        phone__in=Subquery(pos_all.values('phone'))
    ).values('cnv_id', 'phone', 'last_name', 'first_name', 'level_name',
             'points', 'total_points', 'used_points')

    pos_map = {c['phone']: c for c in pos_matched_qs}
    cnv_map = {c['phone']: c for c in cnv_matched_qs}

    points_mismatch = []
    for phone, pos_c in pos_map.items():
        cnv_c = cnv_map.get(phone)
        if cnv_c:
            pos_pts      = int(pos_c.get('points') or 0)
            pos_used     = int(pos_c.get('used_points') or 0)
            pos_net      = pos_pts - pos_used          # effective POS points
            cnv_pts      = int(cnv_c.get('points') or 0)
            if pos_net != cnv_pts:
                points_mismatch.append({
                    'phone': phone,
                    'pos_vip_id': pos_c['vip_id'],
                    'pos_name': pos_c['name'],
                    'pos_grade': pos_c['vip_grade'],
                    'pos_points': pos_pts,
                    'pos_used_points': pos_used,
                    'pos_net_points': pos_net,
                    'cnv_id': cnv_c['cnv_id'],
                    'cnv_name': f"{cnv_c.get('last_name') or ''} {cnv_c.get('first_name') or ''}".strip(),
                    'cnv_level': cnv_c['level_name'],
                    'cnv_points': cnv_pts,
                    'cnv_total_points': cnv_c.get('total_points') or 0,
                    'cnv_used_points': cnv_c.get('used_points') or 0,
                    'diff': cnv_pts - pos_net,
                })

    points_mismatch.sort(key=lambda x: abs(x['diff']), reverse=True)
    points_mismatch_count = len(points_mismatch)

    # ============================================
    # TOTAL POINTS MISMATCH: POS.points != CNV.total_points (matched by phone)
    # ============================================
    total_points_mismatch = []
    for phone, pos_c in pos_map.items():
        cnv_c = cnv_map.get(phone)
        if cnv_c:
            pos_pts      = int(pos_c.get('points') or 0)
            pos_used     = int(pos_c.get('used_points') or 0)
            pos_net      = pos_pts - pos_used          # effective POS points
            cnv_total    = int(float(cnv_c.get('total_points') or 0))
            if pos_net != cnv_total:
                total_points_mismatch.append({
                    'phone': phone,
                    'pos_vip_id': pos_c['vip_id'],
                    'pos_name': pos_c['name'],
                    'pos_grade': pos_c['vip_grade'],
                    'pos_points': pos_pts,
                    'pos_used_points': pos_used,
                    'pos_net_points': pos_net,
                    'cnv_id': cnv_c['cnv_id'],
                    'cnv_name': f"{cnv_c.get('last_name') or ''} {cnv_c.get('first_name') or ''}".strip(),
                    'cnv_level': cnv_c['level_name'],
                    'cnv_points': int(cnv_c.get('points') or 0),
                    'cnv_total_points': cnv_total,
                    'cnv_used_points': int(float(cnv_c.get('used_points') or 0)),
                    'diff': cnv_total - pos_net,
                })

    total_points_mismatch.sort(key=lambda x: abs(x['diff']), reverse=True)
    total_points_mismatch_count = len(total_points_mismatch)

    # ============================================
    # CNV CUSTOMERS WITH USED_POINTS > 0
    # ============================================
    cnv_used_points_qs = cnv_all.filter(used_points__gt=0).values(
        'cnv_id', 'phone', 'last_name', 'first_name', 'level_name', 'email',
        'cnv_created_at', 'points', 'total_points', 'used_points'
    ).order_by('-used_points')[:200]
    cnv_used_points_count = cnv_all.filter(used_points__gt=0).count()

    # Annotate each row with in_pos flag (phone exists in POS)
    _used_phones = [r['phone'] for r in cnv_used_points_qs if r['phone']]
    _pos_phones_set = set(
        pos_all.filter(phone__in=_used_phones).values_list('phone', flat=True)
    )
    cnv_used_points_list = []
    for row in cnv_used_points_qs:
        row = dict(row)
        row['in_pos'] = row['phone'] in _pos_phones_set
        cnv_used_points_list.append(row)

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
        'total_pos': total_pos_all,
        'total_cnv': total_cnv_all,
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

        # New tables
        'points_mismatch': points_mismatch[:100],
        'points_mismatch_count': points_mismatch_count,
        'total_points_mismatch': total_points_mismatch[:100],
        'total_points_mismatch_count': total_points_mismatch_count,
        'cnv_used_points_list': list(cnv_used_points_list),
        'cnv_used_points_count': cnv_used_points_count,

        # Quick buttons
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

    # Build points mismatch — use subquery, NOT phone__in with large Python set
    from django.db.models import Subquery, OuterRef

    pos_base = Customer.objects.filter(phone__isnull=False).exclude(phone='')
    cnv_base = CNVCustomer.objects.filter(phone__isnull=False).exclude(phone='')

    # Fetch only matched rows via subquery
    pos_matched = pos_base.filter(
        phone__in=Subquery(cnv_base.values('phone'))
    ).values('vip_id', 'phone', 'name', 'vip_grade', 'points', 'used_points')

    cnv_matched = cnv_base.filter(
        phone__in=Subquery(pos_base.values('phone'))
    ).values('cnv_id', 'phone', 'last_name', 'first_name', 'level_name',
             'points', 'total_points', 'used_points')

    pos_map = {c['phone']: c for c in pos_matched}
    cnv_map = {c['phone']: c for c in cnv_matched}

    points_mismatch_export = []
    for phone, pos_c in pos_map.items():
        cnv_c = cnv_map.get(phone)
        if cnv_c:
            pos_pts  = int(pos_c.get('points') or 0)
            pos_used = int(pos_c.get('used_points') or 0)
            pos_net  = pos_pts - pos_used
            cnv_pts  = int(cnv_c.get('points') or 0)
            if pos_net != cnv_pts:
                points_mismatch_export.append({
                    'phone': phone,
                    'pos_vip_id': pos_c['vip_id'],
                    'pos_name': pos_c['name'],
                    'pos_grade': pos_c['vip_grade'],
                    'pos_points': pos_pts,
                    'pos_used_points': pos_used,
                    'pos_net_points': pos_net,
                    'cnv_id': cnv_c['cnv_id'],
                    'cnv_name': f"{cnv_c.get('last_name') or ''} {cnv_c.get('first_name') or ''}".strip(),
                    'cnv_level': cnv_c['level_name'],
                    'cnv_points': cnv_pts,
                    'cnv_total_points': float(cnv_c.get('total_points') or 0),
                    'cnv_used_points': float(cnv_c.get('used_points') or 0),
                    'diff': cnv_pts - pos_net,
                })
    points_mismatch_export.sort(key=lambda x: abs(x['diff']), reverse=True)

    # Total Points Mismatch export: (POS.points - POS.used_points) vs CNV.total_points
    total_points_mismatch_export = []
    for phone, pos_c in pos_map.items():
        cnv_c = cnv_map.get(phone)
        if cnv_c:
            pos_pts   = int(pos_c.get('points') or 0)
            pos_used  = int(pos_c.get('used_points') or 0)
            pos_net   = pos_pts - pos_used
            cnv_total = int(float(cnv_c.get('total_points') or 0))
            if pos_net != cnv_total:
                total_points_mismatch_export.append({
                    'phone': phone,
                    'pos_vip_id': pos_c['vip_id'],
                    'pos_name': pos_c['name'],
                    'pos_grade': pos_c['vip_grade'],
                    'pos_points': pos_pts,
                    'pos_used_points': pos_used,
                    'pos_net_points': pos_net,
                    'cnv_id': cnv_c['cnv_id'],
                    'cnv_name': f"{cnv_c.get('last_name') or ''} {cnv_c.get('first_name') or ''}".strip(),
                    'cnv_level': cnv_c['level_name'],
                    'cnv_points': int(cnv_c.get('points') or 0),
                    'cnv_total_points': cnv_total,
                    'cnv_used_points': int(float(cnv_c.get('used_points') or 0)),
                    'diff': cnv_total - pos_net,
                })
    total_points_mismatch_export.sort(key=lambda x: abs(x['diff']), reverse=True)

    cnv_used_points_export = list(CNVCustomer.objects.filter(used_points__gt=0).order_by('-used_points'))

    # Generate Excel workbook using excel_export module
    wb = export_customer_comparison_to_excel(
        pos_customers,
        cnv_customers,
        date_from,
        date_to,
        points_mismatch=points_mismatch_export,
        total_points_mismatch=total_points_mismatch_export,
        cnv_used_points=cnv_used_points_export,
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


@login_required
def sync_cnv_points(request):
    """
    AJAX endpoint: sync points for a list of CNV customer IDs.
    POST body JSON: { "cnv_ids": [123, 456, ...] }
    Returns JSON: { "results": [ {cnv_id, status, points, total_points, used_points, level_name}, ... ] }
    """
    import json
    from django.http import JsonResponse
    from decimal import Decimal
    from App.cnv.api_client import CNVAPIClient

    if request.method != 'POST':
        return JsonResponse({'error': 'POST required'}, status=405)

    try:
        body = json.loads(request.body)
        cnv_ids = body.get('cnv_ids', [])
    except Exception:
        return JsonResponse({'error': 'Invalid JSON'}, status=400)

    if not cnv_ids:
        return JsonResponse({'error': 'No cnv_ids provided'}, status=400)

    client = CNVAPIClient(settings.CNV_USERNAME, settings.CNV_PASSWORD)
    results = []

    for cnv_id in cnv_ids:
        try:
            response = client.get_customer_membership(int(cnv_id))
            if response and 'membership' in response:
                m = response['membership']
                points      = Decimal(str(m.get('points', 0)))
                total_pts   = Decimal(str(m.get('total_points', 0)))
                used_pts    = Decimal(str(m.get('used_points', 0)))
                level_name  = m.get('level_name')

                CNVCustomer.objects.filter(cnv_id=cnv_id).update(
                    points=points,
                    total_points=total_pts,
                    used_points=used_pts,
                    level_name=level_name,
                )
                results.append({
                    'cnv_id': cnv_id,
                    'status': 'ok',
                    'points': float(points),
                    'total_points': float(total_pts),
                    'used_points': float(used_pts),
                    'level_name': level_name,
                })
            else:
                results.append({'cnv_id': cnv_id, 'status': 'no_data'})
        except Exception as e:
            results.append({'cnv_id': cnv_id, 'status': 'error', 'error': str(e)})

    return JsonResponse({'results': results})