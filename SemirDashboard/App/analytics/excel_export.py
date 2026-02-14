"""
App/analytics/excel_export.py

Excel export functionality for analytics data.
Generates formatted Excel workbooks with multiple sheets.

Version: 3.4 - Added shop details and comparison sheets
"""
from openpyxl import Workbook
from openpyxl.styles import Font, PatternFill, Alignment
from openpyxl.utils import get_column_letter


def export_analytics_to_excel(data):
    """
    Export analytics data to Excel workbook.
    
    Creates 8 sheets:
    1. Overview
    2. By VIP Grade
    3. By Season
    4. By Shop
    5. By Shop - Detail
    6. By Grade - All Shops
    7. By Season - All Shops
    8. Customer Details
    """
    wb = Workbook()
    
    header_fill = PatternFill(start_color="366092", end_color="366092", fill_type="solid")
    header_font = Font(bold=True, color="FFFFFF")
    header_align = Alignment(horizontal="center", vertical="center")
    
    _create_overview_sheet(wb, data, header_fill, header_font, header_align)
    _create_grade_sheet(wb, data, header_fill, header_font, header_align)
    _create_season_sheet(wb, data, header_fill, header_font, header_align)
    _create_shop_sheet(wb, data, header_fill, header_font, header_align)
    _create_shop_detail_sheet(wb, data, header_fill, header_font, header_align)
    _create_grade_comparison_sheet(wb, data, header_fill, header_font, header_align)
    _create_season_comparison_sheet(wb, data, header_fill, header_font, header_align)
    _create_details_sheet(wb, data, header_fill, header_font, header_align)
    
    return wb


def _create_overview_sheet(wb, data, header_fill, header_font, header_align):
    """Overview sheet."""
    ws = wb.active
    ws.title = "Overview"
    
    ws['A1'] = "Customer Analytics Overview"
    ws['A1'].font = Font(bold=True, size=14)
    
    ov = data['overview']
    row = 3
    for label, value in [
        ("New Members (Period)", ov['new_members_in_period']),
        ("Returning (Period)", ov['returning_customers']),
        ("Active (Period)", ov['active_customers']),
        ("Return Rate (Period)", f"{ov['return_rate']}%"),
        ("Invoices (Customers)", ov['total_invoices_without_vip0']),
        ("Amount (Customers)", f"{ov['total_amount_without_vip0']:,.0f} VND"),
        ("Total Invoices", ov['total_invoices_with_vip0']),
        ("Total Amount", f"{ov['total_amount_with_vip0']:,.0f} VND"),
    ]:
        ws[f'A{row}'] = label
        ws[f'B{row}'] = value
        row += 1
    
    ws.column_dimensions['A'].width = 35
    ws.column_dimensions['B'].width = 20


def _create_grade_sheet(wb, data, header_fill, header_font, header_align):
    """By VIP Grade sheet."""
    ws = wb.create_sheet("By VIP Grade")
    
    headers = ["Grade", "Active", "Returning", "Return Rate", "Invoices (Customers)", "Amount (Customers)", "Total Invoices", "Total Amount"]
    for col_num, header in enumerate(headers, 1):
        cell = ws.cell(row=1, column=col_num, value=header)
        cell.fill = header_fill
        cell.font = header_font
        cell.alignment = header_align
    
    for row_num, g in enumerate(data['by_grade'], 2):
        ws.cell(row=row_num, column=1, value=g['grade'])
        ws.cell(row=row_num, column=2, value=g['total_customers'])
        ws.cell(row=row_num, column=3, value=g['returning_customers'])
        ws.cell(row=row_num, column=4, value=f"{g['return_rate']}%")
        ws.cell(row=row_num, column=5, value=g['total_invoices'])
        ws.cell(row=row_num, column=6, value=f"{g['total_amount']:,.0f}")
        ws.cell(row=row_num, column=7, value=g.get('total_invoices_with_vip0', g['total_invoices']))
        ws.cell(row=row_num, column=8, value=f"{g.get('total_amount_with_vip0', g['total_amount']):,.0f}")
    
    for col in range(1, 9):
        ws.column_dimensions[get_column_letter(col)].width = 18


def _create_season_sheet(wb, data, header_fill, header_font, header_align):
    """By Season sheet."""
    ws = wb.create_sheet("By Season")
    
    headers = ["Season", "Active", "Returning", "Return Rate", "Invoices (Customers)", "Amount (Customers)", "Total Invoices", "Total Amount"]
    for col_num, header in enumerate(headers, 1):
        cell = ws.cell(row=1, column=col_num, value=header)
        cell.fill = header_fill
        cell.font = header_font
        cell.alignment = header_align
    
    for row_num, s in enumerate(data['by_session'], 2):
        ws.cell(row=row_num, column=1, value=s['session'])
        ws.cell(row=row_num, column=2, value=s['total_customers'])
        ws.cell(row=row_num, column=3, value=s['returning_customers'])
        ws.cell(row=row_num, column=4, value=f"{s['return_rate']}%")
        ws.cell(row=row_num, column=5, value=s['total_invoices'])
        ws.cell(row=row_num, column=6, value=f"{s['total_amount']:,.0f}")
        ws.cell(row=row_num, column=7, value=s.get('total_invoices_with_vip0', 0))
        ws.cell(row=row_num, column=8, value=f"{s.get('total_amount_with_vip0', 0):,.0f}")
    
    for col in range(1, 9):
        ws.column_dimensions[get_column_letter(col)].width = 18


def _create_shop_sheet(wb, data, header_fill, header_font, header_align):
    """By Shop summary."""
    ws = wb.create_sheet("By Shop")
    
    headers = ["Shop", "Active", "Returning", "Return Rate", "Invoices (Customers)", "Amount (Customers)", "Total Invoices", "Total Amount"]
    for col_num, header in enumerate(headers, 1):
        cell = ws.cell(row=1, column=col_num, value=header)
        cell.fill = header_fill
        cell.font = header_font
        cell.alignment = header_align
    
    sorted_shops = sorted(data['by_shop'], key=lambda x: x['shop_name'])
    
    for row_num, shop in enumerate(sorted_shops, 2):
        ws.cell(row=row_num, column=1, value=shop['shop_name'])
        ws.cell(row=row_num, column=2, value=shop['total_customers'])
        ws.cell(row=row_num, column=3, value=shop['returning_customers'])
        ws.cell(row=row_num, column=4, value=f"{shop['return_rate']}%")
        ws.cell(row=row_num, column=5, value=shop['total_invoices'])
        ws.cell(row=row_num, column=6, value=f"{shop['total_amount']:,.0f}")
        ws.cell(row=row_num, column=7, value=shop.get('total_invoices_with_vip0', 0))
        ws.cell(row=row_num, column=8, value=f"{shop.get('total_amount_with_vip0', 0):,.0f}")
    
    ws.column_dimensions['A'].width = 30
    for col in range(2, 9):
        ws.column_dimensions[get_column_letter(col)].width = 16


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
        
        grade_headers = ["Grade", "Active", "Returning", "Return Rate", "Invoices", "Amount"]
        for col_num, header in enumerate(grade_headers, 1):
            cell = ws.cell(row=current_row, column=col_num, value=header)
            cell.fill = header_fill
            cell.font = header_font
        current_row += 1
        
        for g in shop.get('by_grade', []):
            ws.cell(row=current_row, column=1, value=g['grade'])
            ws.cell(row=current_row, column=2, value=g['total_customers'])
            ws.cell(row=current_row, column=3, value=g['returning_customers'])
            ws.cell(row=current_row, column=4, value=f"{g['return_rate']}%")
            ws.cell(row=current_row, column=5, value=g['total_invoices'])
            ws.cell(row=current_row, column=6, value=f"{g['total_amount']:,.0f}")
            current_row += 1
        
        current_row += 1
        
        # By Season
        ws.cell(row=current_row, column=1, value="By Season").font = Font(bold=True)
        current_row += 1
        
        season_headers = ["Season", "Active", "Returning", "Return Rate", "Invoices (Customers)", "Amount (Customers)", "Total Invoices", "Total Amount"]
        for col_num, header in enumerate(season_headers, 1):
            cell = ws.cell(row=current_row, column=col_num, value=header)
            cell.fill = header_fill
            cell.font = header_font
        current_row += 1
        
        for s in shop.get('by_session', []):
            ws.cell(row=current_row, column=1, value=s['session'])
            ws.cell(row=current_row, column=2, value=s['total_customers'])
            ws.cell(row=current_row, column=3, value=s['returning_customers'])
            ws.cell(row=current_row, column=4, value=f"{s['return_rate']}%")
            ws.cell(row=current_row, column=5, value=s['total_invoices'])
            ws.cell(row=current_row, column=6, value=f"{s['total_amount']:,.0f}")
            ws.cell(row=current_row, column=7, value=s.get('total_invoices_with_vip0', 0))
            ws.cell(row=current_row, column=8, value=f"{s.get('total_amount_with_vip0', 0):,.0f}")
            current_row += 1
        
        current_row += 2
    
    for col in range(1, 9):
        ws.column_dimensions[get_column_letter(col)].width = 18


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
        ws.merge_cells(f'A{current_row}:F{current_row}')
        current_row += 1
        
        headers = ["Shop", "Active", "Returning", "Return Rate", "Invoices", "Amount"]
        for col_num, header in enumerate(headers, 1):
            cell = ws.cell(row=current_row, column=col_num, value=header)
            cell.fill = header_fill
            cell.font = header_font
        current_row += 1
        
        for shop in sorted_shops:
            g = next((g for g in shop.get('by_grade', []) if g['grade'] == grade), None)
            if g:
                ws.cell(row=current_row, column=1, value=shop['shop_name'])
                ws.cell(row=current_row, column=2, value=g['total_customers'])
                ws.cell(row=current_row, column=3, value=g['returning_customers'])
                ws.cell(row=current_row, column=4, value=f"{g['return_rate']}%")
                ws.cell(row=current_row, column=5, value=g['total_invoices'])
                ws.cell(row=current_row, column=6, value=f"{g['total_amount']:,.0f}")
                current_row += 1
        
        current_row += 1
    
    ws.column_dimensions['A'].width = 30
    for col in range(2, 7):
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
        ws.merge_cells(f'A{current_row}:H{current_row}')
        current_row += 1
        
        headers = ["Shop", "Active", "Returning", "Return Rate", "Invoices (Customers)", "Amount (Customers)", "Total Invoices", "Total Amount"]
        for col_num, header in enumerate(headers, 1):
            cell = ws.cell(row=current_row, column=col_num, value=header)
            cell.fill = header_fill
            cell.font = header_font
        current_row += 1
        
        for shop in sorted_shops:
            s = next((s for s in shop.get('by_session', []) if s['session'] == season), None)
            if s:
                ws.cell(row=current_row, column=1, value=shop['shop_name'])
                ws.cell(row=current_row, column=2, value=s['total_customers'])
                ws.cell(row=current_row, column=3, value=s['returning_customers'])
                ws.cell(row=current_row, column=4, value=f"{s['return_rate']}%")
                ws.cell(row=current_row, column=5, value=s['total_invoices'])
                ws.cell(row=current_row, column=6, value=f"{s['total_amount']:,.0f}")
                ws.cell(row=current_row, column=7, value=s.get('total_invoices_with_vip0', 0))
                ws.cell(row=current_row, column=8, value=f"{s.get('total_amount_with_vip0', 0):,.0f}")
                current_row += 1
        
        current_row += 1
    
    ws.column_dimensions['A'].width = 30
    for col in range(2, 9):
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