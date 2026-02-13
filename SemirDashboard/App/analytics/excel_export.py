"""
App/analytics/excel_export.py

Excel export functionality for analytics data.
Generates formatted Excel workbooks with multiple sheets.

Version: 3.3
"""
from openpyxl import Workbook
from openpyxl.styles import Font, PatternFill, Alignment
from openpyxl.utils import get_column_letter


def export_analytics_to_excel(data):
    """
    Export analytics data to Excel workbook.
    
    Creates 5 sheets:
    1. Overview - Summary metrics
    2. By VIP Grade - Grade breakdown
    3. By Season - Season breakdown
    4. By Shop - Shop summary
    5. Customer Details - Individual customer data
    
    Args:
        data: Analytics dict from calculate_return_rate_analytics()
    
    Returns:
        openpyxl Workbook object
    """
    wb = Workbook()
    
    # Define styles
    header_fill = PatternFill(start_color="366092", end_color="366092", fill_type="solid")
    header_font = Font(bold=True, color="FFFFFF")
    header_align = Alignment(horizontal="center", vertical="center")
    
    # Create sheets
    _create_overview_sheet(wb, data, header_fill, header_font, header_align)
    _create_grade_sheet(wb, data, header_fill, header_font, header_align)
    _create_season_sheet(wb, data, header_fill, header_font, header_align)
    _create_shop_sheet(wb, data, header_fill, header_font, header_align)
    _create_details_sheet(wb, data, header_fill, header_font, header_align)
    
    return wb


def _create_overview_sheet(wb, data, header_fill, header_font, header_align):
    """Create Overview sheet with summary metrics."""
    ws = wb.active
    ws.title = "Overview"
    
    ov = data['overview']
    dr = data['date_range']
    
    ws['A1'] = "Customer Analytics - Overview"
    ws['A1'].font = Font(bold=True, size=14)
    ws.merge_cells('A1:B1')
    
    ws['A3'] = "Date Range:"
    ws['B3'] = f"{dr['start']} to {dr['end']}"
    
    row = 5
    metrics = [
        ("Total Customers (All Time)", ov['total_customers_in_db']),
        ("Active Customers (Period)", ov['active_customers']),
        ("Returning Customers (Period)", ov['returning_customers']),
        ("Return Visit Rate (Period)", f"{ov['return_rate']}%"),
        ("Return Visit Rate (All Time)", f"{ov['return_rate_all_time']}%"),
        ("New Members (Period)", ov['new_members_in_period']),
        ("Buyer Without Info (Period)", ov['buyer_without_info']),
        ("Total Amount (Period)", f"{ov['total_amount_period']:,.0f} VND"),
    ]
    
    for label, value in metrics:
        ws[f'A{row}'] = label
        ws[f'B{row}'] = value
        row += 1
    
    ws.column_dimensions['A'].width = 35
    ws.column_dimensions['B'].width = 20


def _create_grade_sheet(wb, data, header_fill, header_font, header_align):
    """Create By VIP Grade sheet."""
    ws_grade = wb.create_sheet("By VIP Grade")
    
    headers = ["Grade", "Active", "Returning", "Return Rate", "Rate (All Time)", "Invoices", "Amount (VND)"]
    for col_num, header in enumerate(headers, 1):
        cell = ws_grade.cell(row=1, column=col_num, value=header)
        cell.fill = header_fill
        cell.font = header_font
        cell.alignment = header_align
    
    for row_num, grade_stat in enumerate(data['by_grade'], 2):
        ws_grade.cell(row=row_num, column=1, value=grade_stat['grade'])
        ws_grade.cell(row=row_num, column=2, value=grade_stat['total_customers'])
        ws_grade.cell(row=row_num, column=3, value=grade_stat['returning_customers'])
        ws_grade.cell(row=row_num, column=4, value=f"{grade_stat['return_rate']}%")
        ws_grade.cell(row=row_num, column=5, value=f"{grade_stat['return_rate_all_time']}%")
        ws_grade.cell(row=row_num, column=6, value=grade_stat['total_invoices'])
        ws_grade.cell(row=row_num, column=7, value=f"{grade_stat['total_amount']:,.0f}")
    
    for col in range(1, 8):
        ws_grade.column_dimensions[get_column_letter(col)].width = 18


def _create_season_sheet(wb, data, header_fill, header_font, header_align):
    """Create By Season sheet."""
    ws_session = wb.create_sheet("By Season")
    
    headers = ["Season", "Active", "Returning", "Return Rate", "Invoices", "Amount (VND)"]
    for col_num, header in enumerate(headers, 1):
        cell = ws_session.cell(row=1, column=col_num, value=header)
        cell.fill = header_fill
        cell.font = header_font
        cell.alignment = header_align
    
    for row_num, session_stat in enumerate(data['by_session'], 2):
        ws_session.cell(row=row_num, column=1, value=session_stat['session'])
        ws_session.cell(row=row_num, column=2, value=session_stat['total_customers'])
        ws_session.cell(row=row_num, column=3, value=session_stat['returning_customers'])
        ws_session.cell(row=row_num, column=4, value=f"{session_stat['return_rate']}%")
        ws_session.cell(row=row_num, column=5, value=session_stat['total_invoices'])
        ws_session.cell(row=row_num, column=6, value=f"{session_stat['total_amount']:,.0f}")
    
    for col in range(1, 7):
        ws_session.column_dimensions[get_column_letter(col)].width = 18


def _create_shop_sheet(wb, data, header_fill, header_font, header_align):
    """Create By Shop sheet."""
    ws_shop = wb.create_sheet("By Shop")
    
    headers = ["Shop", "Active", "Returning", "Return Rate", "Invoices", "Amount (VND)"]
    for col_num, header in enumerate(headers, 1):
        cell = ws_shop.cell(row=1, column=col_num, value=header)
        cell.fill = header_fill
        cell.font = header_font
        cell.alignment = header_align
    
    for row_num, shop_stat in enumerate(data['by_shop'], 2):
        ws_shop.cell(row=row_num, column=1, value=shop_stat['shop_name'])
        ws_shop.cell(row=row_num, column=2, value=shop_stat['total_customers'])
        ws_shop.cell(row=row_num, column=3, value=shop_stat['returning_customers'])
        ws_shop.cell(row=row_num, column=4, value=f"{shop_stat['return_rate']}%")
        ws_shop.cell(row=row_num, column=5, value=shop_stat['total_invoices'])
        ws_shop.cell(row=row_num, column=6, value=f"{shop_stat['total_amount']:,.0f}")
    
    ws_shop.column_dimensions['A'].width = 30
    for col in range(2, 7):
        ws_shop.column_dimensions[get_column_letter(col)].width = 16


def _create_details_sheet(wb, data, header_fill, header_font, header_align):
    """Create Customer Details sheet."""
    ws_detail = wb.create_sheet("Customer Details")
    
    headers = ["VIP ID", "Name", "Grade", "Reg Date", "First Purchase", "Purchases", "Return Visits", "Total Spent"]
    for col_num, header in enumerate(headers, 1):
        cell = ws_detail.cell(row=1, column=col_num, value=header)
        cell.fill = header_fill
        cell.font = header_font
        cell.alignment = header_align
    
    for row_num, customer in enumerate(data['customer_details'], 2):
        ws_detail.cell(row=row_num, column=1, value=customer['vip_id'])
        ws_detail.cell(row=row_num, column=2, value=customer['name'])
        ws_detail.cell(row=row_num, column=3, value=customer['vip_grade'])
        ws_detail.cell(row=row_num, column=4, value=str(customer['registration_date']) if customer['registration_date'] else '')
        ws_detail.cell(row=row_num, column=5, value=str(customer['first_purchase_date']))
        ws_detail.cell(row=row_num, column=6, value=customer['total_purchases'])
        ws_detail.cell(row=row_num, column=7, value=customer['return_visits'])
        ws_detail.cell(row=row_num, column=8, value=f"{customer['total_spent']:,.0f}")
    
    for col in range(1, 9):
        ws_detail.column_dimensions[get_column_letter(col)].width = 18