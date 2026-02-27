"""
App/analytics/excel_export.py

Excel export functionality for analytics data.
Generates formatted Excel workbooks with multiple sheets.

Header Abbreviations:
    INV(RET) = Returning Invoices (invoices from customers who made return visits)
    AMT(RET) = Returning Amount (total amount from returning customers)
    INV(CUS) = Customer Invoices (all invoices excluding VIP ID = 0)
    AMT(CUS) = Customer Amount (total amount from customers excluding VIP ID = 0)

Version: 3.4 - Added shop details and comparison sheets
Version: 3.5 - Standardized headers to use abbreviations consistently
"""
from openpyxl import Workbook
from openpyxl.styles import Font, PatternFill, Alignment
from openpyxl.utils import get_column_letter


def export_analytics_to_excel(data, date_from=None, date_to=None, shop_group=None):
    """
    Export analytics data to Excel workbook.
    
    Creates 8 sheets:
    1. Overview (includes filter info)
    2. By VIP Grade
    3. By Season
    4. By Shop
    5. By Shop - Detail
    6. By Grade - All Shops
    7. By Season - All Shops
    8. Customer Details
    
    Args:
        data: Analytics data dict
        date_from: Start date filter (for display)
        date_to: End date filter (for display)
        shop_group: Shop group filter (for display)
    """
    wb = Workbook()
    
    header_fill = PatternFill(start_color="366092", end_color="366092", fill_type="solid")
    header_font = Font(bold=True, color="FFFFFF")
    header_align = Alignment(horizontal="center", vertical="center")
    
    _create_overview_sheet(wb, data, header_fill, header_font, header_align, date_from, date_to, shop_group)
    _create_grade_sheet(wb, data, header_fill, header_font, header_align)
    _create_season_sheet(wb, data, header_fill, header_font, header_align)
    _create_shop_sheet(wb, data, header_fill, header_font, header_align)
    _create_shop_detail_sheet(wb, data, header_fill, header_font, header_align)
    _create_grade_comparison_sheet(wb, data, header_fill, header_font, header_align)
    _create_season_comparison_sheet(wb, data, header_fill, header_font, header_align)
    _create_details_sheet(wb, data, header_fill, header_font, header_align)
    _create_reconciliation_sheet(wb, data, header_fill, header_font, header_align)  # NEW
    
    return wb


def _create_overview_sheet(wb, data, header_fill, header_font, header_align, date_from=None, date_to=None, shop_group=None):
    """Overview sheet with filter information."""
    ws = wb.active
    ws.title = "Overview"
    
    ws['A1'] = "Customer Analytics Overview"
    ws['A1'].font = Font(bold=True, size=14)
    
    # Show active filters
    row = 2
    if date_from and date_to:
        ws[f'A{row}'] = "Period Filter:"
        ws[f'B{row}'] = f"{date_from} to {date_to}"
        ws[f'B{row}'].font = Font(bold=True, color="0066CC")
        row += 1
    
    if shop_group:
        ws[f'A{row}'] = "Shop Group Filter:"
        ws[f'B{row}'] = shop_group
        ws[f'B{row}'].font = Font(bold=True, color="0066CC")
        row += 1
    
    row += 1  # Empty row
    
    ov = data['overview']
    for label, value in [
        ("New Members (Period)", ov['new_members_in_period']),
        ("Returning (Period)", ov['returning_customers']),
        ("Active (Period)", ov['active_customers']),
        ("Return Rate (Period)", f"{ov['return_rate']}%"),
        ("INV(RET)", ov.get('returning_invoices', 0)),
        ("AMT(RET)", ov.get('returning_amount', 0)),
        ("INV(CUS)", ov['total_invoices_without_vip0']),
        ("AMT(CUS)", ov['total_amount_without_vip0']),
        ("Total Invoices", ov['total_invoices_with_vip0']),
        ("Total Amount", ov['total_amount_with_vip0']),
    ]:
        ws[f'A{row}'] = label
        # Format amounts with number format instead of string
        if 'AMT' in label or 'Amount' in label:
            ws[f'B{row}'] = value
            ws[f'B{row}'].number_format = '#,##0'
        else:
            ws[f'B{row}'] = value
        row += 1
    
    # Add abbreviations explanation
    row += 1
    ws[f'A{row}'] = "Column Abbreviations:"
    ws[f'A{row}'].font = Font(bold=True, color="0066CC")
    row += 1
    
    abbrev_info = [
        ("INV(RET)", "= Returning Invoices"),
        ("AMT(RET)", "= Returning Amount"),
        ("INV(CUS)", "= Customer Invoices"),
        ("AMT(CUS)", "= Customer Amount"),
    ]
    
    for abbrev, meaning in abbrev_info:
        ws[f'A{row}'] = abbrev
        ws[f'A{row}'].font = Font(bold=True)
        ws[f'B{row}'] = meaning
        row += 1
    
    ws.column_dimensions['A'].width = 35
    ws.column_dimensions['B'].width = 25


def _create_grade_sheet(wb, data, header_fill, header_font, header_align):
    """By VIP Grade sheet."""
    ws = wb.create_sheet("By VIP Grade")
    
    headers = ["Grade", "Returning", "Active", "Return Rate", "INV(RET)", "AMT(RET)", "INV(CUS)", "AMT(CUS)", "Total Invoices", "Total Amount"]
    for col_num, header in enumerate(headers, 1):
        cell = ws.cell(row=1, column=col_num, value=header)
        cell.fill = header_fill
        cell.font = header_font
        cell.alignment = header_align
    
    for row_num, g in enumerate(data['by_grade'], 2):
        ws.cell(row=row_num, column=1, value=g['grade'])
        ws.cell(row=row_num, column=2, value=g['returning_customers'])
        ws.cell(row=row_num, column=3, value=g['total_customers'])
        ws.cell(row=row_num, column=4, value=f"{g['return_rate']}%")
        ws.cell(row=row_num, column=5, value=g.get('returning_invoices', 0))
        ws.cell(row=row_num, column=6, value=g.get('returning_amount', 0))
        ws.cell(row=row_num, column=6).number_format = '#,##0'
        ws.cell(row=row_num, column=7, value=g['total_invoices'])
        ws.cell(row=row_num, column=8, value=g['total_amount'])
        ws.cell(row=row_num, column=8).number_format = '#,##0'
        ws.cell(row=row_num, column=9, value=g.get('total_invoices_with_vip0', g['total_invoices']))
        ws.cell(row=row_num, column=10, value=g.get('total_amount_with_vip0', g['total_amount']))
        ws.cell(row=row_num, column=10).number_format = '#,##0'
    
    ws.column_dimensions['A'].width = 12  # Grade
    for col in range(2, 5):
        ws.column_dimensions[get_column_letter(col)].width = 14  # Numeric
    for col in range(5, 11):
        ws.column_dimensions[get_column_letter(col)].width = 16  # Amount


def _create_season_sheet(wb, data, header_fill, header_font, header_align):
    """By Season sheet."""
    ws = wb.create_sheet("By Season")
    
    headers = ["Season", "Returning", "Active", "Return Rate", "INV(RET)", "AMT(RET)", "INV(CUS)", "AMT(CUS)", "Total Invoices", "Total Amount"]
    for col_num, header in enumerate(headers, 1):
        cell = ws.cell(row=1, column=col_num, value=header)
        cell.fill = header_fill
        cell.font = header_font
        cell.alignment = header_align
    
    for row_num, s in enumerate(data['by_session'], 2):
        ws.cell(row=row_num, column=1, value=s['session'])
        ws.cell(row=row_num, column=2, value=s['returning_customers'])
        ws.cell(row=row_num, column=3, value=s['total_customers'])
        ws.cell(row=row_num, column=4, value=f"{s['return_rate']}%")
        ws.cell(row=row_num, column=5, value=s.get('returning_invoices', 0))
        ws.cell(row=row_num, column=6, value=s.get('returning_amount', 0))
        ws.cell(row=row_num, column=6).number_format = '#,##0'
        ws.cell(row=row_num, column=7, value=s['total_invoices'])
        ws.cell(row=row_num, column=8, value=s['total_amount'])
        ws.cell(row=row_num, column=8).number_format = '#,##0'
        ws.cell(row=row_num, column=9, value=s.get('total_invoices_with_vip0', 0))
        ws.cell(row=row_num, column=10, value=s.get('total_amount_with_vip0', 0))
        ws.cell(row=row_num, column=10).number_format = '#,##0'
    
    ws.column_dimensions['A'].width = 15  # Season
    for col in range(2, 5):
        ws.column_dimensions[get_column_letter(col)].width = 14  # Numeric
    for col in range(5, 11):
        ws.column_dimensions[get_column_letter(col)].width = 16  # Amount


def _create_shop_sheet(wb, data, header_fill, header_font, header_align):
    """By Shop summary."""
    ws = wb.create_sheet("By Shop")
    
    headers = ["Shop", "Returning", "Active", "Return Rate", "INV(RET)", "AMT(RET)", "INV(CUS)", "AMT(CUS)", "Total Invoices", "Total Amount"]
    for col_num, header in enumerate(headers, 1):
        cell = ws.cell(row=1, column=col_num, value=header)
        cell.fill = header_fill
        cell.font = header_font
        cell.alignment = header_align
    
    sorted_shops = sorted(data['by_shop'], key=lambda x: x['shop_name'])
    
    for row_num, shop in enumerate(sorted_shops, 2):
        ws.cell(row=row_num, column=1, value=shop['shop_name'])
        ws.cell(row=row_num, column=2, value=shop['returning_customers'])
        ws.cell(row=row_num, column=3, value=shop['total_customers'])
        ws.cell(row=row_num, column=4, value=f"{shop['return_rate']}%")
        ws.cell(row=row_num, column=5, value=shop.get('returning_invoices', 0))
        ws.cell(row=row_num, column=6, value=shop.get('returning_amount', 0))
        ws.cell(row=row_num, column=6).number_format = '#,##0'
        ws.cell(row=row_num, column=7, value=shop['total_invoices'])
        ws.cell(row=row_num, column=8, value=shop['total_amount'])
        ws.cell(row=row_num, column=8).number_format = '#,##0'
        ws.cell(row=row_num, column=9, value=shop.get('total_invoices_with_vip0', 0))
        ws.cell(row=row_num, column=10, value=shop.get('total_amount_with_vip0', 0))
        ws.cell(row=row_num, column=10).number_format = '#,##0'
    
    ws.column_dimensions['A'].width = 30  # Shop name
    for col in range(2, 5):
        ws.column_dimensions[get_column_letter(col)].width = 14  # Numeric
    for col in range(5, 11):
        ws.column_dimensions[get_column_letter(col)].width = 16  # Amount


def _create_shop_detail_sheet(wb, data, header_fill, header_font, header_align):
    """By Shop - Detail with grade and season breakdowns."""
    ws = wb.create_sheet("By Shop - Detail")
    
    current_row = 1
    sorted_shops = sorted(data['by_shop'], key=lambda x: x['shop_name'])
    
    for shop in sorted_shops:
        ws.cell(row=current_row, column=1, value=f"SHOP: {shop['shop_name']}")
        ws.cell(row=current_row, column=1).font = Font(bold=True, size=12)
        ws.merge_cells(f'A{current_row}:H{current_row}')
        current_row += 1
        
        # By Grade
        ws.cell(row=current_row, column=1, value="By VIP Grade").font = Font(bold=True)
        current_row += 1
        
        grade_headers = ["Grade", "Returning", "Active", "Return Rate", "INV(RET)", "AMT(RET)", "INV(CUS)", "AMT(CUS)"]
        for col_num, header in enumerate(grade_headers, 1):
            cell = ws.cell(row=current_row, column=col_num, value=header)
            cell.fill = header_fill
            cell.font = header_font
        current_row += 1
        
        for g in shop.get('by_grade', []):
            ws.cell(row=current_row, column=1, value=g['grade'])
            ws.cell(row=current_row, column=2, value=g['returning_customers'])
            ws.cell(row=current_row, column=3, value=g['total_customers'])
            ws.cell(row=current_row, column=4, value=f"{g['return_rate']}%")
            ws.cell(row=current_row, column=5, value=g.get('returning_invoices', 0))
            ws.cell(row=current_row, column=6, value=g.get('returning_amount', 0))
            ws.cell(row=current_row, column=6).number_format = '#,##0'
            ws.cell(row=current_row, column=7, value=g['total_invoices'])
            ws.cell(row=current_row, column=8, value=g['total_amount'])
            ws.cell(row=current_row, column=8).number_format = '#,##0'
            current_row += 1
        
        current_row += 1
        
        # By Season
        ws.cell(row=current_row, column=1, value="By Season").font = Font(bold=True)
        current_row += 1
        
        season_headers = ["Season", "Returning", "Active", "Return Rate", "INV(RET)", "AMT(RET)", "INV(CUS)", "AMT(CUS)", "Total Invoices", "Total Amount"]
        for col_num, header in enumerate(season_headers, 1):
            cell = ws.cell(row=current_row, column=col_num, value=header)
            cell.fill = header_fill
            cell.font = header_font
        current_row += 1
        
        for s in shop.get('by_session', []):
            ws.cell(row=current_row, column=1, value=s['session'])
            ws.cell(row=current_row, column=2, value=s['returning_customers'])
            ws.cell(row=current_row, column=3, value=s['total_customers'])
            ws.cell(row=current_row, column=4, value=f"{s['return_rate']}%")
            ws.cell(row=current_row, column=5, value=s.get('returning_invoices', 0))
            ws.cell(row=current_row, column=6, value=s.get('returning_amount', 0))
            ws.cell(row=current_row, column=6).number_format = '#,##0'
            ws.cell(row=current_row, column=7, value=s['total_invoices'])
            ws.cell(row=current_row, column=8, value=s['total_amount'])
            ws.cell(row=current_row, column=8).number_format = '#,##0'
            ws.cell(row=current_row, column=9, value=s.get('total_invoices_with_vip0', 0))
            ws.cell(row=current_row, column=10, value=s.get('total_amount_with_vip0', 0))
            ws.cell(row=current_row, column=10).number_format = '#,##0'
            current_row += 1
        
        current_row += 2
    
    # Column widths
    ws.column_dimensions['A'].width = 12  # Grade/Season
    for col in range(2, 5):
        ws.column_dimensions[get_column_letter(col)].width = 14  # Numeric
    for col in range(5, 11):
        ws.column_dimensions[get_column_letter(col)].width = 16  # Amount


def _create_grade_comparison_sheet(wb, data, header_fill, header_font, header_align):
    """By Grade - All Shops comparison."""
    ws = wb.create_sheet("By Grade - All Shops")
    
    all_grades = set()
    for shop in data['by_shop']:
        for g in shop.get('by_grade', []):
            all_grades.add(g['grade'])
    
    GRADE_ORDER = {'No Grade': 0, 'Member': 1, 'Silver': 2, 'Gold': 3, 'Diamond': 4}
    sorted_grades = sorted(all_grades, key=lambda x: GRADE_ORDER.get(x, 99))
    sorted_shops = sorted(data['by_shop'], key=lambda x: x['shop_name'])
    
    current_row = 1
    
    for grade in sorted_grades:
        ws.cell(row=current_row, column=1, value=f"GRADE: {grade}")
        ws.cell(row=current_row, column=1).font = Font(bold=True, size=12)
        ws.merge_cells(f'A{current_row}:H{current_row}')
        current_row += 1
        
        headers = ["Shop", "Returning", "Active", "Return Rate", "INV(RET)", "AMT(RET)", "INV(CUS)", "AMT(CUS)"]
        for col_num, header in enumerate(headers, 1):
            cell = ws.cell(row=current_row, column=col_num, value=header)
            cell.fill = header_fill
            cell.font = header_font
        current_row += 1
        
        for shop in sorted_shops:
            g = next((g for g in shop.get('by_grade', []) if g['grade'] == grade), None)
            if g:
                ws.cell(row=current_row, column=1, value=shop['shop_name'])
                ws.cell(row=current_row, column=2, value=g['returning_customers'])
                ws.cell(row=current_row, column=3, value=g['total_customers'])
                ws.cell(row=current_row, column=4, value=f"{g['return_rate']}%")
                ws.cell(row=current_row, column=5, value=g.get('returning_invoices', 0))
                ws.cell(row=current_row, column=6, value=f"{g.get('returning_amount', 0):,.0f}")
                ws.cell(row=current_row, column=7, value=g['total_invoices'])
                ws.cell(row=current_row, column=8, value=f"{g['total_amount']:,.0f}")
                current_row += 1
        
        current_row += 1
    
    ws.column_dimensions['A'].width = 30
    for col in range(2, 9):
        ws.column_dimensions[get_column_letter(col)].width = 16


def _create_season_comparison_sheet(wb, data, header_fill, header_font, header_align):
    """By Season - All Shops comparison."""
    ws = wb.create_sheet("By Season - All Shops")
    
    all_seasons = [s['session'] for s in data['by_session']]
    sorted_shops = sorted(data['by_shop'], key=lambda x: x['shop_name'])
    
    current_row = 1
    
    for season in all_seasons:
        ws.cell(row=current_row, column=1, value=f"SEASON: {season}")
        ws.cell(row=current_row, column=1).font = Font(bold=True, size=12)
        ws.merge_cells(f'A{current_row}:J{current_row}')
        current_row += 1
        
        headers = ["Shop", "Returning", "Active", "Return Rate", "INV(RET)", "AMT(RET)", "INV(CUS)", "AMT(CUS)", "Total Invoices", "Total Amount"]
        for col_num, header in enumerate(headers, 1):
            cell = ws.cell(row=current_row, column=col_num, value=header)
            cell.fill = header_fill
            cell.font = header_font
        current_row += 1
        
        for shop in sorted_shops:
            s = next((s for s in shop.get('by_session', []) if s['session'] == season), None)
            if s:
                ws.cell(row=current_row, column=1, value=shop['shop_name'])
                ws.cell(row=current_row, column=2, value=s['returning_customers'])
                ws.cell(row=current_row, column=3, value=s['total_customers'])
                ws.cell(row=current_row, column=4, value=f"{s['return_rate']}%")
                ws.cell(row=current_row, column=5, value=s.get('returning_invoices', 0))
                ws.cell(row=current_row, column=6, value=f"{s.get('returning_amount', 0):,.0f}")
                ws.cell(row=current_row, column=7, value=s['total_invoices'])
                ws.cell(row=current_row, column=8, value=f"{s['total_amount']:,.0f}")
                ws.cell(row=current_row, column=9, value=s.get('total_invoices_with_vip0', 0))
                ws.cell(row=current_row, column=10, value=f"{s.get('total_amount_with_vip0', 0):,.0f}")
                current_row += 1
        
        current_row += 1
    
    ws.column_dimensions['A'].width = 30
    for col in range(2, 11):
        ws.column_dimensions[get_column_letter(col)].width = 16


def _create_details_sheet(wb, data, header_fill, header_font, header_align):
    """Customer Details sheet."""
    ws = wb.create_sheet("Customer Details")
    
    headers = ["VIP ID", "Name", "Grade", "Reg Date", "First Purchase", "Purchases", "Return Visits", "Total Spent"]
    for col_num, header in enumerate(headers, 1):
        cell = ws.cell(row=1, column=col_num, value=header)
        cell.fill = header_fill
        cell.font = header_font
        cell.alignment = header_align
    
    for row_num, c in enumerate(data['customer_details'], 2):
        ws.cell(row=row_num, column=1, value=c['vip_id'])
        ws.cell(row=row_num, column=2, value=c['name'])
        ws.cell(row=row_num, column=3, value=c.get('vip_grade', ''))
        ws.cell(row=row_num, column=4, value=str(c.get('registration_date', '')) if c.get('registration_date') else '')
        ws.cell(row=row_num, column=5, value=str(c['first_purchase_date']))
        ws.cell(row=row_num, column=6, value=c['total_purchases'])
        ws.cell(row=row_num, column=7, value=c['return_visits'])
        ws.cell(row=row_num, column=8, value=f"{c['total_spent']:,.0f}")
    
    for col in range(1, 9):
        ws.column_dimensions[get_column_letter(col)].width = 18

"""
ULTIMATE FIX - Uses customer_utils.get_customer_info() for proper lookup
"""

def _create_reconciliation_sheet(wb, data, header_fill, header_font, header_align):
    """
    ULTIMATE FIX: Use customer_utils.get_customer_info() instead of manual lookup
    """
    from openpyxl.styles import Font, PatternFill, Alignment
    from collections import defaultdict
    from App.analytics.season_utils import get_session_key
    from App.analytics.customer_utils import get_customer_info  # CRITICAL IMPORT
    
    customer_purchases = data.get('customer_purchases', {})
    
    if not customer_purchases:
        ws = wb.create_sheet("⚠️ Reconciliation")
        ws['A1'] = "⚠️ Customer purchase data not available"
        ws['A1'].font = Font(bold=True, size=14, color="FF0000")
        return
    
    # ============================================================================
    # Helper Functions
    # ============================================================================
    
    def to_date(d):
        """Convert datetime to date for comparison"""
        if d is None:
            return None
        return d.date() if hasattr(d, 'date') else d
    
    def calculate_return_visits_local(purchases_sorted, reg_date):
        """Calculate return visits with proper date comparison"""
        n = len(purchases_sorted)
        if n == 0:
            return (0, False)
        
        # Convert to dates for comparison
        first_date = to_date(purchases_sorted[0]['date'])
        reg_date_cmp = to_date(reg_date)
        
        # Apply formula
        if reg_date_cmp and first_date == reg_date_cmp:
            return_visits = n - 1
        else:
            return_visits = n
        
        is_returning = (return_visits > 0)
        return (return_visits, is_returning)
    
    # ============================================================================
    # Get Summary Data
    # ============================================================================
    
    ov = data.get('overview', {})
    overview_total = ov.get('returning_invoices', 0)
    shop_sum = sum(s.get('returning_invoices', 0) for s in data.get('by_shop', []))
    season_sum = sum(s.get('returning_invoices', 0) for s in data.get('by_session', []))
    
    shop_diff = overview_total - shop_sum
    season_diff = overview_total - season_sum
    
    # ============================================================================
    # SHEET 1: SHOP RECONCILIATION
    # ============================================================================
    
    ws_shop = wb.create_sheet("Reconciliation - Shops")
    
    # Title
    ws_shop['A1'] = "SHOP RECONCILIATION"
    ws_shop['A1'].font = Font(bold=True, size=14, color="FF0000")
    ws_shop.merge_cells('A1:I1')
    
    row = 3
    
    # Summary
    ws_shop[f'A{row}'] = "Global Returning Invoices:"
    ws_shop[f'B{row}'] = overview_total
    ws_shop[f'B{row}'].font = Font(bold=True, color="0066CC")
    row += 1
    
    ws_shop[f'A{row}'] = "Sum of Shop Returning Invoices:"
    ws_shop[f'B{row}'] = shop_sum
    row += 1
    
    ws_shop[f'A{row}'] = "Difference:"
    ws_shop[f'B{row}'] = shop_diff
    ws_shop[f'B{row}'].font = Font(bold=True, size=12, color="FF0000")
    row += 2
    
    # Find shop problem customers
    shop_problems = []
    
    for vip_id, purchases in customer_purchases.items():
        if vip_id == '0' or not purchases:
            continue
        
        # CRITICAL FIX: Use customer_utils.get_customer_info() with customer object
        # Get customer object from first purchase
        customer_obj = purchases[0].get('customer') if purchases else None
        grade, reg_date, name = get_customer_info(vip_id, customer_obj)
        
        purchases_sorted = sorted(purchases, key=lambda x: x['date'])
        
        # Global calculation
        global_rv, global_is_ret = calculate_return_visits_local(purchases_sorted, reg_date)
        
        if not global_is_ret:
            continue
        
        global_ret_inv = len(purchases)
        
        # Shop calculation
        shop_total = 0
        by_shop = defaultdict(list)
        
        for p in purchases:
            shop = p.get('shop', 'Unknown')
            by_shop[shop].append(p)
        
        for shop, shop_purch in by_shop.items():
            shop_sorted = sorted(shop_purch, key=lambda x: x['date'])
            _, is_ret = calculate_return_visits_local(shop_sorted, reg_date)
            
            if is_ret:
                shop_total += len(shop_purch)
        
        diff = global_ret_inv - shop_total
        
        if diff > 0:
            # Find reg day purchases
            reg_date_cmp = to_date(reg_date)
            if reg_date_cmp:
                reg_day_purch = [p for p in purchases if to_date(p['date']) == reg_date_cmp]
                reg_day_shops = set([p.get('shop', 'Unknown') for p in reg_day_purch])
            else:
                reg_day_purch = []
                reg_day_shops = set()
            
            # Determine pattern
            if len(reg_day_shops) >= 2:
                pattern = "Multi-shop reg day"
            elif len(reg_day_purch) >= 1 and len(by_shop) >= 2:
                pattern = "Reg day → other shops"
            else:
                pattern = "Other"
            
            # Build shop details
            shop_details = []
            for shop, shop_purch in list(by_shop.items())[:3]:
                shop_sorted_temp = sorted(shop_purch, key=lambda x: x['date'])
                _, shop_is_ret = calculate_return_visits_local(shop_sorted_temp, reg_date)
                shop_details.append(f"{shop[:25]}({len(shop_purch)},ret={shop_is_ret})")
            
            shop_problems.append({
                'vip_id': vip_id,
                'name': name,
                'reg_date': reg_date,
                'total_purchases': len(purchases),
                'global_ret_inv': global_ret_inv,
                'shop_total': shop_total,
                'difference': diff,
                'pattern': pattern,
                'details': "; ".join(shop_details)
            })
    
    shop_problems.sort(key=lambda x: x['difference'], reverse=True)
    
    # Pattern summary
    pattern1 = [c for c in shop_problems if c['pattern'] == "Multi-shop reg day"]
    pattern2 = [c for c in shop_problems if c['pattern'] == "Reg day → other shops"]
    
    ws_shop[f'A{row}'] = "PATTERNS:"
    ws_shop[f'A{row}'].font = Font(bold=True)
    row += 1
    
    ws_shop[f'A{row}'] = f"Pattern 1 (Multi-shop reg day): {len(pattern1)} customers, {sum(c['difference'] for c in pattern1)} invoices"
    row += 1
    
    ws_shop[f'A{row}'] = f"Pattern 2 (Reg day → other shops): {len(pattern2)} customers, {sum(c['difference'] for c in pattern2)} invoices"
    row += 2
    
    # Table
    ws_shop[f'A{row}'] = f"ALL {len(shop_problems)} CUSTOMERS WITH SHOP DIFFERENCES:"
    ws_shop[f'A{row}'].font = Font(bold=True, size=11)
    ws_shop.merge_cells(f'A{row}:I{row}')
    row += 1
    
    # Headers
    headers = ["VIP ID", "Name", "Reg Date", "Total Purch", "Global", "Shop Sum", "Diff", "Pattern", "Details"]
    for col_idx, header in enumerate(headers, start=1):
        cell = ws_shop.cell(row=row, column=col_idx, value=header)
        cell.font = header_font
        cell.fill = header_fill
        cell.alignment = Alignment(horizontal="center")
    row += 1
    
    # Data rows
    for c in shop_problems:
        ws_shop.cell(row=row, column=1, value=c['vip_id'])
        ws_shop.cell(row=row, column=2, value=c['name'])
        ws_shop.cell(row=row, column=3, value=c['reg_date'].strftime('%Y-%m-%d') if c['reg_date'] else 'NULL')
        ws_shop.cell(row=row, column=4, value=c['total_purchases'])
        ws_shop.cell(row=row, column=5, value=c['global_ret_inv'])
        ws_shop.cell(row=row, column=6, value=c['shop_total'])
        
        diff_cell = ws_shop.cell(row=row, column=7, value=c['difference'])
        diff_cell.font = Font(bold=True, color="FF0000")
        
        pattern_cell = ws_shop.cell(row=row, column=8, value=c['pattern'])
        if c['pattern'] == "Multi-shop reg day":
            pattern_cell.fill = PatternFill(start_color="FFE0E0", end_color="FFE0E0", fill_type="solid")
        else:
            pattern_cell.fill = PatternFill(start_color="E0FFE0", end_color="E0FFE0", fill_type="solid")
        
        ws_shop.cell(row=row, column=9, value=c['details'])
        row += 1
    
    # Column widths
    ws_shop.column_dimensions['A'].width = 12
    ws_shop.column_dimensions['B'].width = 25
    ws_shop.column_dimensions['C'].width = 12
    ws_shop.column_dimensions['D'].width = 12
    ws_shop.column_dimensions['E'].width = 10
    ws_shop.column_dimensions['F'].width = 10
    ws_shop.column_dimensions['G'].width = 8
    ws_shop.column_dimensions['H'].width = 22
    ws_shop.column_dimensions['I'].width = 50
    
    # ============================================================================
    # SHEET 2: SEASON RECONCILIATION
    # ============================================================================
    
    ws_season = wb.create_sheet("Reconciliation - Seasons")
    
    # Title
    ws_season['A1'] = "SEASON RECONCILIATION"
    ws_season['A1'].font = Font(bold=True, size=14, color="FF0000")
    ws_season.merge_cells('A1:I1')
    
    row = 3
    
    # Summary
    ws_season[f'A{row}'] = "Global Returning Invoices:"
    ws_season[f'B{row}'] = overview_total
    ws_season[f'B{row}'].font = Font(bold=True, color="0066CC")
    row += 1
    
    ws_season[f'A{row}'] = "Sum of Season Returning Invoices:"
    ws_season[f'B{row}'] = season_sum
    row += 1
    
    ws_season[f'A{row}'] = "Difference:"
    ws_season[f'B{row}'] = season_diff
    ws_season[f'B{row}'].font = Font(bold=True, size=12, color="FF0000")
    row += 2
    
    # Find season problem customers
    season_problems = []
    
    for vip_id, purchases in customer_purchases.items():
        if vip_id == '0' or not purchases:
            continue
        
        # CRITICAL FIX: Use customer_utils.get_customer_info()
        customer_obj = purchases[0].get('customer') if purchases else None
        grade, reg_date, name = get_customer_info(vip_id, customer_obj)
        
        purchases_sorted = sorted(purchases, key=lambda x: x['date'])
        
        # Global calculation
        global_rv, global_is_ret = calculate_return_visits_local(purchases_sorted, reg_date)
        
        if not global_is_ret:
            continue
        
        global_ret_inv = len(purchases)
        
        # Season calculation
        season_total = 0
        by_season = defaultdict(list)
        
        for p in purchases:
            season = get_session_key(p['date'])
            by_season[season].append(p)
        
        for season, season_purch in by_season.items():
            season_sorted = sorted(season_purch, key=lambda x: x['date'])
            _, is_ret = calculate_return_visits_local(season_sorted, reg_date)
            
            if is_ret:
                season_total += len(season_purch)
        
        diff = global_ret_inv - season_total
        
        if diff > 0:
            # Build season details
            season_details = []
            for season, season_purch in list(by_season.items())[:3]:
                season_sorted_temp = sorted(season_purch, key=lambda x: x['date'])
                _, season_is_ret = calculate_return_visits_local(season_sorted_temp, reg_date)
                season_details.append(f"{season}({len(season_purch)},ret={season_is_ret})")
            
            season_problems.append({
                'vip_id': vip_id,
                'name': name,
                'reg_date': reg_date,
                'total_purchases': len(purchases),
                'global_ret_inv': global_ret_inv,
                'season_total': season_total,
                'difference': diff,
                'num_seasons': len(by_season),
                'details': "; ".join(season_details)
            })
    
    season_problems.sort(key=lambda x: x['difference'], reverse=True)
    
    # Pattern explanation
    ws_season[f'A{row}'] = f"Pattern: {len(season_problems)} customers, {sum(c['difference'] for c in season_problems)} invoices"
    ws_season[f'A{row}'].font = Font(bold=True)
    row += 1
    
    ws_season[f'A{row}'] = "First purchase on reg day in Season 1 → NOT returning in Season 1"
    row += 1
    ws_season[f'A{row}'] = "Then purchases in other seasons → IS returning in those seasons"
    row += 1
    ws_season[f'A{row}'] = "Each customer loses exactly 1 invoice from first season"
    row += 2
    
    # Table
    ws_season[f'A{row}'] = f"ALL {len(season_problems)} CUSTOMERS WITH SEASON DIFFERENCES:"
    ws_season[f'A{row}'].font = Font(bold=True, size=11)
    ws_season.merge_cells(f'A{row}:I{row}')
    row += 1
    
    # Headers
    headers = ["VIP ID", "Name", "Reg Date", "Total Purch", "Global", "Season Sum", "Diff", "Num Seasons", "Details"]
    for col_idx, header in enumerate(headers, start=1):
        cell = ws_season.cell(row=row, column=col_idx, value=header)
        cell.font = header_font
        cell.fill = header_fill
        cell.alignment = Alignment(horizontal="center")
    row += 1
    
    # Data rows (ALL season problems)
    for c in season_problems:
        ws_season.cell(row=row, column=1, value=c['vip_id'])
        ws_season.cell(row=row, column=2, value=c['name'])
        ws_season.cell(row=row, column=3, value=c['reg_date'].strftime('%Y-%m-%d') if c['reg_date'] else 'NULL')
        ws_season.cell(row=row, column=4, value=c['total_purchases'])
        ws_season.cell(row=row, column=5, value=c['global_ret_inv'])
        ws_season.cell(row=row, column=6, value=c['season_total'])
        
        diff_cell = ws_season.cell(row=row, column=7, value=c['difference'])
        diff_cell.font = Font(bold=True, color="FF0000")
        
        ws_season.cell(row=row, column=8, value=c['num_seasons'])
        ws_season.cell(row=row, column=9, value=c['details'])
        row += 1
    
    # Column widths
    ws_season.column_dimensions['A'].width = 12
    ws_season.column_dimensions['B'].width = 25
    ws_season.column_dimensions['C'].width = 12
    ws_season.column_dimensions['D'].width = 12
    ws_season.column_dimensions['E'].width = 10
    ws_season.column_dimensions['F'].width = 10
    ws_season.column_dimensions['G'].width = 8
    ws_season.column_dimensions['H'].width = 12
    ws_season.column_dimensions['I'].width = 50
    


def export_customer_comparison_to_excel(
    pos_customers,
    cnv_customers,
    date_from=None,
    date_to=None
):
    """
    Export Customer Analytics (POS vs CNV comparison) to Excel.
    
    Creates up to 5 sheets:
    1. Overview - Summary metrics and filter info
    2. POS Only - All Time - Customers in POS but not CNV
    3. CNV Only - All Time - Customers in CNV but not POS
    4. POS Only - Period - New POS customers not in CNV (if date filtered)
    5. CNV Only - Period - New CNV customers not in POS (if date filtered)
    
    Args:
        pos_customers: QuerySet of Customer objects from POS system
        cnv_customers: QuerySet of CNVCustomer objects from CNV
        date_from: Start date for period filter (optional)
        date_to: End date for period filter (optional)
    
    Returns:
        openpyxl Workbook object
    """
    wb = Workbook()
    
    # Styling
    header_fill = PatternFill(start_color="366092", end_color="366092", fill_type="solid")
    header_font = Font(bold=True, color="FFFFFF")
    header_align = Alignment(horizontal="center", vertical="center")
    
    # Build phone sets for comparison
    pos_phones = set(c.phone for c in pos_customers if c.phone)
    cnv_phones = set(c.phone for c in cnv_customers if c.phone)
    
    # All-time comparisons
    pos_only_all = pos_phones - cnv_phones
    cnv_only_all = cnv_phones - pos_phones
    
    # Period comparisons (if filtered)
    pos_only_period = []
    cnv_only_period = []
    new_pos_count = 0
    new_cnv_count = 0
    
    if date_from and date_to:
        # New POS customers in period
        new_pos = pos_customers.filter(
            registration_date__gte=date_from,
            registration_date__lte=date_to
        )
        new_pos_count = new_pos.count()
        new_pos_phones = set(c.phone for c in new_pos if c.phone)
        pos_only_period = list(new_pos_phones - cnv_phones)
        
        # New CNV customers in period
        new_cnv = cnv_customers.filter(
            registration_date__gte=date_from,
            registration_date__lte=date_to
        )
        new_cnv_count = new_cnv.count()
        new_cnv_phones = set(c.phone for c in new_cnv if c.phone)
        cnv_only_period = list(new_cnv_phones - pos_phones)
    
    # ========================================================================
    # OVERVIEW SHEET
    # ========================================================================
    ws = wb.active
    ws.title = "Overview"
    
    ws['A1'] = "Customer Analytics - POS vs CNV Comparison"
    ws['A1'].font = Font(bold=True, size=14)
    ws.merge_cells('A1:B1')
    
    row = 3
    
    # Filter info
    if date_from and date_to:
        ws[f'A{row}'] = "Period Filter:"
        ws[f'B{row}'] = f"{date_from} to {date_to}"
        ws[f'B{row}'].font = Font(bold=True, color="0066CC")
        row += 1
    
    row += 1
    
    # All-Time Metrics
    ws[f'A{row}'] = "All-Time Metrics"
    ws[f'A{row}'].font = Font(bold=True)
    row += 1
    
    metrics_all = [
        ("Total Customers (POS System)", len(pos_phones)),
        ("Total CNV Customers", len(cnv_phones)),
        ("POS Only (Not in CNV)", len(pos_only_all)),
        ("CNV Only (Not in POS)", len(cnv_only_all)),
    ]
    
    for label, value in metrics_all:
        ws[f'A{row}'] = label
        ws[f'B{row}'] = value
        row += 1
    
    # Period Metrics (if filtered)
    if date_from and date_to:
        row += 1
        ws[f'A{row}'] = "Period Metrics"
        ws[f'A{row}'].font = Font(bold=True)
        row += 1
        
        metrics_period = [
            ("New Customers (POS)", new_pos_count),
            ("New CNV Customers", new_cnv_count),
            ("New POS Only (Period)", len(pos_only_period)),
            ("New CNV Only (Period)", len(cnv_only_period)),
        ]
        
        for label, value in metrics_period:
            ws[f'A{row}'] = label
            ws[f'B{row}'] = value
            row += 1
    
    ws.column_dimensions['A'].width = 35
    ws.column_dimensions['B'].width = 20
    
    # ========================================================================
    # POS ONLY - ALL TIME SHEET
    # ========================================================================
    ws_pos_all = wb.create_sheet("POS Only - All Time")
    
    # Header
    headers = ['VIP ID', 'Phone', 'Name', 'Grade', 'Email', 'Registration Date', 'Points']
    for col_idx, header in enumerate(headers, 1):
        cell = ws_pos_all.cell(1, col_idx, header)
        cell.fill = header_fill
        cell.font = header_font
        cell.alignment = header_align
    
    # Data
    pos_only_customers = pos_customers.filter(phone__in=pos_only_all).order_by('registration_date')
    row = 2
    for cust in pos_only_customers:
        ws_pos_all.cell(row, 1, cust.vip_id)
        ws_pos_all.cell(row, 2, cust.phone)
        ws_pos_all.cell(row, 3, cust.name)
        ws_pos_all.cell(row, 4, cust.vip_grade or '-')
        ws_pos_all.cell(row, 5, cust.email or '-')
        ws_pos_all.cell(row, 6, str(cust.registration_date) if cust.registration_date else '-')
        ws_pos_all.cell(row, 7, cust.points or 0)
        row += 1
    
    # Column widths
    ws_pos_all.column_dimensions['A'].width = 12  # VIP ID
    ws_pos_all.column_dimensions['B'].width = 15  # Phone
    ws_pos_all.column_dimensions['C'].width = 25  # Name
    ws_pos_all.column_dimensions['D'].width = 12  # Grade
    ws_pos_all.column_dimensions['E'].width = 30  # Email
    ws_pos_all.column_dimensions['F'].width = 18  # Registration Date
    ws_pos_all.column_dimensions['G'].width = 10  # Points
    
    # ========================================================================
    # CNV ONLY - ALL TIME SHEET
    # ========================================================================
    ws_cnv_all = wb.create_sheet("CNV Only - All Time")
    
    # Header
    headers = ['Customer Code', 'Phone', 'Name', 'Email', 'Registration Date', 'Points Earned', 'Points Spent']
    for col_idx, header in enumerate(headers, 1):
        cell = ws_cnv_all.cell(1, col_idx, header)
        cell.fill = header_fill
        cell.font = header_font
        cell.alignment = header_align
    
    # Data
    cnv_only_customers = cnv_customers.filter(phone__in=cnv_only_all).order_by('registration_date')
    row = 2
    for cust in cnv_only_customers:
        ws_cnv_all.cell(row, 1, cust.customer_code)
        ws_cnv_all.cell(row, 2, cust.phone)
        ws_cnv_all.cell(row, 3, cust.full_name or '-')
        ws_cnv_all.cell(row, 4, cust.email or '-')
        ws_cnv_all.cell(row, 5, str(cust.registration_date.date()) if cust.registration_date else '-')
        ws_cnv_all.cell(row, 6, cust.total_points_earned or 0)
        ws_cnv_all.cell(row, 7, cust.total_points_spent or 0)
        row += 1
    
    # Column widths
    ws_cnv_all.column_dimensions['A'].width = 15  # Customer Code
    ws_cnv_all.column_dimensions['B'].width = 15  # Phone
    ws_cnv_all.column_dimensions['C'].width = 25  # Name
    ws_cnv_all.column_dimensions['D'].width = 30  # Email
    ws_cnv_all.column_dimensions['E'].width = 18  # Registration Date
    ws_cnv_all.column_dimensions['F'].width = 15  # Points Earned
    ws_cnv_all.column_dimensions['G'].width = 15  # Points Spent
    
    # ========================================================================
    # PERIOD SHEETS (if filtered)
    # ========================================================================
    if date_from and date_to and pos_only_period:
        ws_pos_period = wb.create_sheet("POS Only - Period")
        
        # Header
        headers = ['VIP ID', 'Phone', 'Name', 'Grade', 'Email', 'Registration Date', 'Points']
        for col_idx, header in enumerate(headers, 1):
            cell = ws_pos_period.cell(1, col_idx, header)
            cell.fill = header_fill
            cell.font = header_font
            cell.alignment = header_align
        
        # Data
        pos_period_customers = pos_customers.filter(
            phone__in=pos_only_period,
            registration_date__gte=date_from,
            registration_date__lte=date_to
        ).order_by('registration_date')
        row = 2
        for cust in pos_period_customers:
            ws_pos_period.cell(row, 1, cust.vip_id)
            ws_pos_period.cell(row, 2, cust.phone)
            ws_pos_period.cell(row, 3, cust.name)
            ws_pos_period.cell(row, 4, cust.vip_grade or '-')
            ws_pos_period.cell(row, 5, cust.email or '-')
            ws_pos_period.cell(row, 6, str(cust.registration_date) if cust.registration_date else '-')
            ws_pos_period.cell(row, 7, cust.points or 0)
            row += 1
        
        # Column widths
        ws_pos_period.column_dimensions['A'].width = 12  # VIP ID
        ws_pos_period.column_dimensions['B'].width = 15  # Phone
        ws_pos_period.column_dimensions['C'].width = 25  # Name
        ws_pos_period.column_dimensions['D'].width = 12  # Grade
        ws_pos_period.column_dimensions['E'].width = 30  # Email
        ws_pos_period.column_dimensions['F'].width = 18  # Registration Date
        ws_pos_period.column_dimensions['G'].width = 10  # Points
    
    if date_from and date_to and cnv_only_period:
        ws_cnv_period = wb.create_sheet("CNV Only - Period")
        
        # Header
        headers = ['Customer Code', 'Phone', 'Name', 'Email', 'Registration Date', 'Points Earned', 'Points Spent']
        for col_idx, header in enumerate(headers, 1):
            cell = ws_cnv_period.cell(1, col_idx, header)
            cell.fill = header_fill
            cell.font = header_font
            cell.alignment = header_align
        
        # Data
        cnv_period_customers = cnv_customers.filter(
            phone__in=cnv_only_period,
            registration_date__gte=date_from,
            registration_date__lte=date_to
        ).order_by('registration_date')
        row = 2
        for cust in cnv_period_customers:
            ws_cnv_period.cell(row, 1, cust.customer_code)
            ws_cnv_period.cell(row, 2, cust.phone)
            ws_cnv_period.cell(row, 3, cust.full_name or '-')
            ws_cnv_period.cell(row, 4, cust.email or '-')
            ws_cnv_period.cell(row, 5, str(cust.registration_date.date()) if cust.registration_date else '-')
            ws_cnv_period.cell(row, 6, cust.total_points_earned or 0)
            ws_cnv_period.cell(row, 7, cust.total_points_spent or 0)
            row += 1
        
        # Column widths
        ws_cnv_period.column_dimensions['A'].width = 15  # Customer Code
        ws_cnv_period.column_dimensions['B'].width = 15  # Phone
        ws_cnv_period.column_dimensions['C'].width = 25  # Name
        ws_cnv_period.column_dimensions['D'].width = 30  # Email
        ws_cnv_period.column_dimensions['E'].width = 18  # Registration Date
        ws_cnv_period.column_dimensions['F'].width = 15  # Points Earned
        ws_cnv_period.column_dimensions['G'].width = 15  # Points Spent
    
    return wb