"""
App/analytics/coupon_analytics.py

Coupon usage analytics and Excel export.
Separate domain from customer analytics.

Version: 3.3
"""
from collections import defaultdict
from decimal import Decimal

from django.db.models import Q
from openpyxl import Workbook
from openpyxl.styles import Font, PatternFill, Alignment
from openpyxl.utils import get_column_letter

from App.models import Coupon, Customer, SalesTransaction


def calculate_coupon_analytics(date_from=None, date_to=None, coupon_id_prefix=None):
    """
    Calculate coupon usage analytics.
    
    Args:
        date_from: Start date for period filter
        date_to: End date for period filter
        coupon_id_prefix: Filter by coupon ID prefix (case-insensitive)
    
    Returns:
        Dict with all_time, period, by_shop, and details data
    """
    qs = Coupon.objects.all()
    
    # Filter by usage date if specified
    if date_from or date_to:
        usage_filter = Q(using_date__isnull=False)
        if date_from:
            usage_filter &= Q(using_date__gte=date_from)
        if date_to:
            usage_filter &= Q(using_date__lte=date_to)
        period_qs = qs.filter(usage_filter)
    else:
        period_qs = qs
    
    # Filter by coupon ID prefix if specified
    if coupon_id_prefix:
        qs = qs.filter(coupon_id__istartswith=coupon_id_prefix)
        period_qs = period_qs.filter(coupon_id__istartswith=coupon_id_prefix)
    
    # All-time stats
    all_time_total = qs.count()
    all_time_used = qs.filter(using_date__isnull=False).count()
    all_time_unused = all_time_total - all_time_used
    all_time_usage_rate = round(all_time_used / all_time_total * 100 if all_time_total else 0, 2)
    all_time_amount = sum(c.face_value or 0 for c in qs.filter(using_date__isnull=False))
    
    # Period stats
    period_total = period_qs.count()
    period_used = period_qs.filter(using_date__isnull=False).count()
    period_unused = period_total - period_used
    period_usage_rate = round(period_used / period_total * 100 if period_total else 0, 2)
    period_amount = sum(c.face_value or 0 for c in period_qs.filter(using_date__isnull=False))
    
    # By shop
    shop_data = {}
    
    for coupon in period_qs.filter(using_date__isnull=False):
        shop = coupon.shop_name or 'Unknown'
        if shop not in shop_data:
            shop_data[shop] = {'total': 0, 'used': 0, 'amount': Decimal(0)}
        shop_data[shop]['used'] += 1
        shop_data[shop]['amount'] += coupon.face_value or Decimal(0)
    
    # Add unused coupons to shop totals
    for coupon in period_qs.filter(using_date__isnull=True):
        shop = coupon.shop_name or 'Unknown'
        if shop not in shop_data:
            shop_data[shop] = {'total': 0, 'used': 0, 'amount': Decimal(0)}
        shop_data[shop]['total'] += 1
    
    # Update totals
    for shop_name in shop_data:
        shop_data[shop_name]['total'] += shop_data[shop_name]['used']
    
    total_used_all_shops = period_used
    
    shop_stats = []
    for shop_name, data in shop_data.items():
        total = data['total']
        used = data['used']
        pct_of_total = round(used / period_total * 100 if period_total else 0, 2)
        pct_of_used = round(used / total_used_all_shops * 100 if total_used_all_shops else 0, 2)
        usage_rate = round(used / total * 100 if total else 0, 2)
        
        shop_stats.append({
            'shop_name': shop_name,
            'total_coupons': total,
            'used_coupons': used,
            'unused_coupons': total - used,
            'usage_rate': usage_rate,
            'pct_of_total': pct_of_total,
            'pct_of_used': pct_of_used,
            'total_amount': float(data['amount']),
        })
    
    shop_stats.sort(key=lambda x: x['used_coupons'], reverse=True)
    
    # Coupon details
    coupon_details = []
    for coupon in period_qs.filter(using_date__isnull=False).order_by('-using_date'):
        vip_id = None
        vip_name = None
        phone = None
        
        if coupon.invoice_number:
            try:
                txn = SalesTransaction.objects.get(invoice_number=coupon.invoice_number)
                vip_id = txn.vip_id
                if vip_id and vip_id != '0':
                    try:
                        cust = Customer.objects.get(vip_id=vip_id)
                        vip_name = cust.name
                        phone = cust.phone_number
                    except Customer.DoesNotExist:
                        pass
            except SalesTransaction.DoesNotExist:
                pass
        
        coupon_details.append({
            'coupon_id': coupon.coupon_id,
            'face_value': coupon.face_value or 0,
            'using_date': coupon.using_date,
            'shop_name': coupon.shop_name or 'Unknown',
            'invoice_number': coupon.invoice_number or '',
            'vip_id': vip_id or '',
            'vip_name': vip_name or '-',
            'phone': phone or '-',
            'amount': coupon.face_value or 0,
        })
    
    return {
        'all_time': {
            'total_coupons': all_time_total,
            'used_coupons': all_time_used,
            'unused_coupons': all_time_unused,
            'usage_rate': all_time_usage_rate,
            'total_amount': float(all_time_amount),
        },
        'period': {
            'total_coupons': period_total,
            'used_coupons': period_used,
            'unused_coupons': period_unused,
            'usage_rate': period_usage_rate,
            'total_amount': float(period_amount),
        },
        'by_shop': shop_stats,
        'details': coupon_details,
    }


def export_coupon_to_excel(data, date_from=None, date_to=None):
    """
    Export coupon analytics to Excel workbook.
    
    Args:
        data: Coupon analytics dict from calculate_coupon_analytics()
        date_from: Period start date (for display)
        date_to: Period end date (for display)
    
    Returns:
        openpyxl Workbook object
    """
    wb = Workbook()
    
    header_fill = PatternFill(start_color="6F42C1", end_color="6F42C1", fill_type="solid")
    header_font = Font(bold=True, color="FFFFFF")
    header_align = Alignment(horizontal="center", vertical="center")
    
    # Summary sheet
    ws = wb.active
    ws.title = "Summary"
    
    ws['A1'] = "Coupon Analytics Summary"
    ws['A1'].font = Font(bold=True, size=14)
    ws.merge_cells('A1:B1')
    
    if date_from and date_to:
        ws['A3'] = "Period:"
        ws['B3'] = f"{date_from} to {date_to}"
    
    row = 5
    ws[f'A{row}'] = "All-Time Statistics"
    ws[f'A{row}'].font = Font(bold=True)
    row += 1
    
    at = data['all_time']
    for label, value in [
        ("Total Coupons", at['total_coupons']),
        ("Used", at['used_coupons']),
        ("Unused", at['unused_coupons']),
        ("Usage Rate", f"{at['usage_rate']}%"),
        ("Total Amount", f"{at['total_amount']:,.0f} VND"),
    ]:
        ws[f'A{row}'] = label
        ws[f'B{row}'] = value
        row += 1
    
    row += 1
    ws[f'A{row}'] = "Period Statistics"
    ws[f'A{row}'].font = Font(bold=True)
    row += 1
    
    pd = data['period']
    for label, value in [
        ("Total Coupons", pd['total_coupons']),
        ("Used", pd['used_coupons']),
        ("Unused", pd['unused_coupons']),
        ("Usage Rate", f"{pd['usage_rate']}%"),
        ("Total Amount", f"{pd['total_amount']:,.0f} VND"),
    ]:
        ws[f'A{row}'] = label
        ws[f'B{row}'] = value
        row += 1
    
    ws.column_dimensions['A'].width = 25
    ws.column_dimensions['B'].width = 20
    
    # By Shop sheet
    ws_shop = wb.create_sheet("By Shop")
    
    headers = ["Shop", "Total", "Used", "Unused", "Usage Rate", "% of Total", "% of Used", "Amount (VND)"]
    for col_num, header in enumerate(headers, 1):
        cell = ws_shop.cell(row=1, column=col_num, value=header)
        cell.fill = header_fill
        cell.font = header_font
        cell.alignment = header_align
    
    for row_num, shop in enumerate(data['by_shop'], 2):
        ws_shop.cell(row=row_num, column=1, value=shop['shop_name'])
        ws_shop.cell(row=row_num, column=2, value=shop['total_coupons'])
        ws_shop.cell(row=row_num, column=3, value=shop['used_coupons'])
        ws_shop.cell(row=row_num, column=4, value=shop['unused_coupons'])
        ws_shop.cell(row=row_num, column=5, value=f"{shop['usage_rate']}%")
        ws_shop.cell(row=row_num, column=6, value=f"{shop['pct_of_total']}%")
        ws_shop.cell(row=row_num, column=7, value=f"{shop['pct_of_used']}%")
        ws_shop.cell(row=row_num, column=8, value=f"{shop['total_amount']:,.0f}")
    
    for col in range(1, 9):
        ws_shop.column_dimensions[get_column_letter(col)].width = 16
    
    # Details sheet
    ws_detail = wb.create_sheet("Coupon Details")
    
    headers = ["Coupon ID", "Face Value", "Using Date", "Shop", "Invoice", "VIP ID", "Name", "Phone"]
    for col_num, header in enumerate(headers, 1):
        cell = ws_detail.cell(row=1, column=col_num, value=header)
        cell.fill = header_fill
        cell.font = header_font
        cell.alignment = header_align
    
    for row_num, detail in enumerate(data['details'], 2):
        ws_detail.cell(row=row_num, column=1, value=detail['coupon_id'])
        ws_detail.cell(row=row_num, column=2, value=f"{detail['face_value']:,.0f}")
        ws_detail.cell(row=row_num, column=3, value=str(detail['using_date']) if detail['using_date'] else '')
        ws_detail.cell(row=row_num, column=4, value=detail['shop_name'])
        ws_detail.cell(row=row_num, column=5, value=detail['invoice_number'])
        ws_detail.cell(row=row_num, column=6, value=detail['vip_id'])
        ws_detail.cell(row=row_num, column=7, value=detail['vip_name'])
        ws_detail.cell(row=row_num, column=8, value=detail['phone'])
    
    for col in range(1, 9):
        ws_detail.column_dimensions[get_column_letter(col)].width = 18
    
    return wb