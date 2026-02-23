"""
App/analytics/coupon_analytics.py

Coupon usage analytics and Excel export.
Separate domain from customer analytics.

Version: 3.4 - FIXED: Total amount now uses invoice amounts, not face_value
All field names verified against Coupon model
"""
from collections import defaultdict
from decimal import Decimal

from django.db.models import Q
from openpyxl import Workbook
from openpyxl.styles import Font, PatternFill, Alignment
from openpyxl.utils import get_column_letter

from App.models import Coupon, Customer, SalesTransaction


def format_face_value(face_value):
    """
    Format face value for display.
    
    Rules:
    - If face_value > 1: Display as VND amount (e.g., "50,000 VND")
    - If 0 < face_value <= 1: Display as percentage (e.g., 0.95 → "95%")
    - If face_value = 0 or None: Display as "0"
    
    Args:
        face_value: Decimal or float value
    
    Returns:
        Formatted string
    """
    if not face_value or face_value == 0:
        return "0"
    
    if face_value > 1:
        # VND amount
        return f"{face_value:,.0f} VND"
    else:
        # Percentage (0.95 → 95%)
        percentage = face_value * 100
        return f"{percentage:.0f}%"


def calculate_coupon_analytics(date_from=None, date_to=None, coupon_id_prefix=None):
    """
    Calculate coupon usage analytics.
    
    IMPORTANT: Total amounts are calculated from INVOICE AMOUNTS, not face_value.
    
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
    
    # All-time stats - counts only (amounts calculated below)
    all_time_total = qs.count()
    all_time_used = qs.filter(using_date__isnull=False).count()
    all_time_unused = all_time_total - all_time_used
    all_time_usage_rate = round(all_time_used / all_time_total * 100 if all_time_total else 0, 2)
    
    # Period stats - counts only (amounts calculated below)
    period_total = period_qs.count()
    period_used = period_qs.filter(using_date__isnull=False).count()
    period_unused = period_total - period_used
    period_usage_rate = round(period_used / period_total * 100 if period_total else 0, 2)
    
    # ===========================================================================
    # CALCULATE AMOUNTS FROM INVOICE AMOUNTS (NOT face_value)
    # ===========================================================================
    
    all_time_amount = Decimal(0)
    period_amount = Decimal(0)
    shop_data = {}
    coupon_details = []
    
    # Helper function to get invoice amount for a coupon
    def get_invoice_amount(coupon):
        """Get invoice amount for a coupon, fallback to face_value if no invoice found."""
        if coupon.docket_number:
            try:
                txn = SalesTransaction.objects.get(invoice_number=coupon.docket_number)
                return txn.sales_amount or coupon.face_value or Decimal(0)
            except SalesTransaction.DoesNotExist:
                pass
        return coupon.face_value or Decimal(0)
    
    # Calculate all-time amount (process ALL used coupons)
    for coupon in qs.filter(using_date__isnull=False):
        inv_amount = get_invoice_amount(coupon)
        all_time_amount += inv_amount
    
    # ===========================================================================
    # PROCESS PERIOD COUPONS - Build details and calculate period amounts
    # ===========================================================================
    
    for coupon in period_qs.filter(using_date__isnull=False).order_by('-using_date'):
        # Get customer info from coupon
        vip_id = coupon.member_id or None
        vip_name = coupon.member_name or None
        phone = coupon.member_phone or None
        
        # Initialize transaction fields
        sales_date = None
        inv_shop = None
        inv_amount = None
        note = None
        
        # Try to get invoice/transaction info
        if coupon.docket_number:
            try:
                txn = SalesTransaction.objects.get(invoice_number=coupon.docket_number)
                
                # Get customer info from transaction if not in coupon
                if not vip_id:
                    vip_id = txn.vip_id
                if not vip_name and txn.vip_id and txn.vip_id != '0':
                    try:
                        cust = Customer.objects.get(vip_id=txn.vip_id)
                        vip_name = cust.name
                        phone = cust.phone
                    except Customer.DoesNotExist:
                        vip_name = txn.vip_name
                
                # Get transaction details
                sales_date = txn.sales_date
                inv_shop = txn.shop_name
                inv_amount = txn.sales_amount
                
                # Validate shop match
                if coupon.using_shop and inv_shop and coupon.using_shop != inv_shop:
                    note = f"Shop mismatch: Coupon@{coupon.using_shop} vs Invoice@{inv_shop}"
                    
            except SalesTransaction.DoesNotExist:
                note = f"Invoice {coupon.docket_number} not found"
        
        # Final amount (invoice amount or fallback to face_value)
        final_amount = inv_amount or coupon.face_value or Decimal(0)
        
        # Accumulate period amount
        period_amount += final_amount
        
        # Accumulate by shop
        shop = coupon.using_shop or 'Unknown'
        if shop not in shop_data:
            shop_data[shop] = {'total': 0, 'used': 0, 'amount': Decimal(0)}
        shop_data[shop]['used'] += 1
        shop_data[shop]['amount'] += final_amount
        
        # Build detail record
        coupon_details.append({
            'coupon_id': coupon.coupon_id,
            'creator': coupon.creator or '',
            'face_value': coupon.face_value or 0,
            'face_value_display': format_face_value(coupon.face_value),  # NEW: Formatted display
            'using_shop': coupon.using_shop or 'Unknown',
            'using_date': coupon.using_date,
            'docket_number': coupon.docket_number or '',
            'vip_id': vip_id or '',
            'customer_name': vip_name or '-',
            'customer_phone': phone or '-',
            'sales_day': sales_date,
            'inv_shop': inv_shop or '-',
            'amount': float(final_amount),  # THIS IS INVOICE AMOUNT
            'note': note or '',
        })
    
    # Add unused coupons to shop totals
    for coupon in period_qs.filter(using_date__isnull=True):
        shop = coupon.using_shop or 'Unknown'
        if shop not in shop_data:
            shop_data[shop] = {'total': 0, 'used': 0, 'amount': Decimal(0)}
        shop_data[shop]['total'] += 1
    
    # Update shop totals (add used to total for each shop)
    for shop_name in shop_data:
        shop_data[shop_name]['total'] += shop_data[shop_name]['used']
    
    # ===========================================================================
    # BUILD SHOP STATS
    # ===========================================================================
    
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
            'total': total,
            'used': used,
            'unused': total - used,
            'used_pct_period': pct_of_total,
            'used_pct_of_used': pct_of_used,
            'usage_rate': usage_rate,
            'total_amount': float(data['amount']),  # Sum of invoice amounts
        })
    
    shop_stats.sort(key=lambda x: x['used'], reverse=True)
    
    # Calculate percentages for template
    all_time_used_pct = round(all_time_used / all_time_total * 100, 2) if all_time_total else 0
    all_time_unused_pct = round(all_time_unused / all_time_total * 100, 2) if all_time_total else 0
    
    period_used_pct = round(period_used / period_total * 100, 2) if period_total else 0
    period_unused_pct = round(period_unused / period_total * 100, 2) if period_total else 0
    
    return {
        'all_time': {
            'total': all_time_total,
            'used': all_time_used,
            'unused': all_time_unused,
            'used_pct': all_time_used_pct,
            'unused_pct': all_time_unused_pct,
            'usage_rate': all_time_usage_rate,
            'total_amount': float(all_time_amount),  # Sum of ALL invoice amounts
        },
        'period': {
            'total': period_total,
            'used': period_used,
            'unused': period_unused,
            'used_pct': period_used_pct,
            'unused_pct': period_unused_pct,
            'usage_rate': period_usage_rate,
            'total_amount': float(period_amount),  # Sum of PERIOD invoice amounts
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
        ("Total Coupons", at['total']),
        ("Used", at['used']),
        ("Unused", at['unused']),
        ("Usage Rate", f"{at['usage_rate']}%"),
        ("Total Amount (Invoice)", f"{at['total_amount']:,.0f} VND"),
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
        ("Total Coupons", pd['total']),
        ("Used", pd['used']),
        ("Unused", pd['unused']),
        ("Usage Rate", f"{pd['usage_rate']}%"),
        ("Total Amount (Invoice)", f"{pd['total_amount']:,.0f} VND"),
    ]:
        ws[f'A{row}'] = label
        ws[f'B{row}'] = value
        row += 1
    
    ws.column_dimensions['A'].width = 25
    ws.column_dimensions['B'].width = 20
    
    # By Using Shop sheet
    ws_shop = wb.create_sheet("By Using Shop")
    
    headers = ["Using Shop", "Total", "Used", "Unused", "Usage Rate", "% of Total", "% of Used", "Amount (Invoice)"]
    for col_num, header in enumerate(headers, 1):
        cell = ws_shop.cell(row=1, column=col_num, value=header)
        cell.fill = header_fill
        cell.font = header_font
        cell.alignment = header_align
    
    for row_num, shop in enumerate(data['by_shop'], 2):
        ws_shop.cell(row=row_num, column=1, value=shop['shop_name'])
        ws_shop.cell(row=row_num, column=2, value=shop['total'])
        ws_shop.cell(row=row_num, column=3, value=shop['used'])
        ws_shop.cell(row=row_num, column=4, value=shop['unused'])
        ws_shop.cell(row=row_num, column=5, value=f"{shop['usage_rate']}%")
        ws_shop.cell(row=row_num, column=6, value=f"{shop['used_pct_period']}%")
        ws_shop.cell(row=row_num, column=7, value=f"{shop['used_pct_of_used']}%")
        ws_shop.cell(row=row_num, column=8, value=f"{shop['total_amount']:,.0f}")
    
    for col in range(1, 9):
        ws_shop.column_dimensions[get_column_letter(col)].width = 16
    
    # Details sheet
    ws_detail = wb.create_sheet("Coupon Details")
    
    headers = ["Coupon ID", "Creator", "Face Value", "Using Shop", "Using Date", "Docket Number", "VIP ID", "Name", "Phone", "Sales Date", "Invoice Shop", "Amount (Invoice)", "Note"]
    for col_num, header in enumerate(headers, 1):
        cell = ws_detail.cell(row=1, column=col_num, value=header)
        cell.fill = header_fill
        cell.font = header_font
        cell.alignment = header_align
    
    for row_num, detail in enumerate(data['details'], 2):
        ws_detail.cell(row=row_num, column=1, value=detail['coupon_id'])
        ws_detail.cell(row=row_num, column=2, value=detail['creator'])
        ws_detail.cell(row=row_num, column=3, value=detail['face_value_display'])  # Use formatted display
        ws_detail.cell(row=row_num, column=4, value=detail['using_shop'])
        ws_detail.cell(row=row_num, column=5, value=str(detail['using_date']) if detail['using_date'] else '')
        ws_detail.cell(row=row_num, column=6, value=detail['docket_number'])
        ws_detail.cell(row=row_num, column=7, value=detail['vip_id'])
        ws_detail.cell(row=row_num, column=8, value=detail['customer_name'])
        ws_detail.cell(row=row_num, column=9, value=detail['customer_phone'])
        ws_detail.cell(row=row_num, column=10, value=str(detail['sales_day']) if detail['sales_day'] else '')
        ws_detail.cell(row=row_num, column=11, value=detail['inv_shop'])
        ws_detail.cell(row=row_num, column=12, value=f"{detail['amount']:,.0f}")
        ws_detail.cell(row=row_num, column=13, value=detail['note'])
    
    for col in range(1, 14):
        ws_detail.column_dimensions[get_column_letter(col)].width = 18
    
    return wb