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
    _create_month_sheet(wb, data, header_fill, header_font, header_align)
    _create_week_sheet(wb, data, header_fill, header_font, header_align)
    _create_shop_sheet(wb, data, header_fill, header_font, header_align)
    _create_shop_detail_sheet(wb, data, header_fill, header_font, header_align)
    _create_grade_comparison_sheet(wb, data, header_fill, header_font, header_align)
    _create_season_comparison_sheet(wb, data, header_fill, header_font, header_align)
    _create_month_comparison_sheet(wb, data, header_fill, header_font, header_align)
    _create_week_comparison_sheet(wb, data, header_fill, header_font, header_align)
    _create_details_sheet(wb, data, header_fill, header_font, header_align)
    _create_buyer_without_info_sheet(wb, data, header_fill, header_font, header_align)
    _create_reconciliation_sheet(wb, data, header_fill, header_font, header_align)

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
        (None, None),  # separator
        ("Total Customers (All Time)", ov['total_customers_in_db']),
        ("Member Active (All Time)", ov['member_active_all_time']),
        ("Member Inactive (All Time)", ov['member_inactive_all_time']),
        ("Return Rate (All Time)", f"{ov['return_rate_all_time']}%"),
    ]:
        if label is None:
            row += 1
            continue
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

    headers = ["Grade", "Active", "Returning", "Return Rate", "Total in DB", "Return Rate (AT)", "INV(RET)", "AMT(RET)", "Total Invoices", "Total Amount"]
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
        ws.cell(row=row_num, column=5, value=g.get('total_in_db', 0))
        ws.cell(row=row_num, column=6, value=f"{g.get('return_rate_all_time', 0)}%")
        ws.cell(row=row_num, column=7, value=g.get('returning_invoices', 0))
        ws.cell(row=row_num, column=8, value=g.get('returning_amount', 0))
        ws.cell(row=row_num, column=8).number_format = '#,##0'
        ws.cell(row=row_num, column=9, value=g['total_invoices'])
        ws.cell(row=row_num, column=10, value=g['total_amount'])
        ws.cell(row=row_num, column=10).number_format = '#,##0'

    ws.column_dimensions['A'].width = 12  # Grade
    for col in range(2, 7):
        ws.column_dimensions[get_column_letter(col)].width = 14  # Numeric
    for col in range(7, 11):
        ws.column_dimensions[get_column_letter(col)].width = 16  # Amount


def _create_season_sheet(wb, data, header_fill, header_font, header_align):
    """By Season sheet."""
    ws = wb.create_sheet("By Season")

    headers = ["Season", "Active", "New", "New Rate", "Returning", "Return Rate", "INV(RET)", "AMT(RET)", "INV(CUS)", "AMT(CUS)", "Total Invoices", "Total Amount"]
    for col_num, header in enumerate(headers, 1):
        cell = ws.cell(row=1, column=col_num, value=header)
        cell.fill = header_fill
        cell.font = header_font
        cell.alignment = header_align

    for row_num, s in enumerate(data['by_session'], 2):
        ws.cell(row=row_num, column=1, value=s['session'])
        ws.cell(row=row_num, column=2, value=s['total_customers'])
        ws.cell(row=row_num, column=3, value=s.get('new_customers', 0))
        ws.cell(row=row_num, column=4, value=f"{s.get('new_rate', 0)}%")
        ws.cell(row=row_num, column=5, value=s['returning_customers'])
        ws.cell(row=row_num, column=6, value=f"{s['return_rate']}%")
        ws.cell(row=row_num, column=7, value=s.get('returning_invoices', 0))
        ws.cell(row=row_num, column=8, value=s.get('returning_amount', 0))
        ws.cell(row=row_num, column=8).number_format = '#,##0'
        ws.cell(row=row_num, column=9, value=s['total_invoices'])
        ws.cell(row=row_num, column=10, value=s['total_amount'])
        ws.cell(row=row_num, column=10).number_format = '#,##0'
        ws.cell(row=row_num, column=11, value=s.get('total_invoices_with_vip0', 0))
        ws.cell(row=row_num, column=12, value=s.get('total_amount_with_vip0', 0))
        ws.cell(row=row_num, column=12).number_format = '#,##0'

    ws.column_dimensions['A'].width = 15  # Season
    for col in range(2, 7):
        ws.column_dimensions[get_column_letter(col)].width = 14  # Numeric
    for col in range(7, 13):
        ws.column_dimensions[get_column_letter(col)].width = 16  # Amount


def _create_month_sheet(wb, data, header_fill, header_font, header_align):
    """By Month sheet."""
    ws = wb.create_sheet("By Month")

    headers = ["Month", "Active", "New", "New Rate", "Returning", "Return Rate", "INV(RET)", "AMT(RET)", "INV(CUS)", "AMT(CUS)", "Total Invoices", "Total Amount"]
    for col_num, header in enumerate(headers, 1):
        cell = ws.cell(row=1, column=col_num, value=header)
        cell.fill = header_fill
        cell.font = header_font
        cell.alignment = header_align

    for row_num, m in enumerate(data.get('by_month', []), 2):
        ws.cell(row=row_num, column=1, value=m['month'])
        ws.cell(row=row_num, column=2, value=m['total_customers'])
        ws.cell(row=row_num, column=3, value=m.get('new_customers', 0))
        ws.cell(row=row_num, column=4, value=f"{m.get('new_rate', 0)}%")
        ws.cell(row=row_num, column=5, value=m['returning_customers'])
        ws.cell(row=row_num, column=6, value=f"{m['return_rate']}%")
        ws.cell(row=row_num, column=7, value=m.get('returning_invoices', 0))
        ws.cell(row=row_num, column=8, value=m.get('returning_amount', 0))
        ws.cell(row=row_num, column=8).number_format = '#,##0'
        ws.cell(row=row_num, column=9, value=m['total_invoices'])
        ws.cell(row=row_num, column=10, value=m['total_amount'])
        ws.cell(row=row_num, column=10).number_format = '#,##0'
        ws.cell(row=row_num, column=11, value=m.get('total_invoices_with_vip0', 0))
        ws.cell(row=row_num, column=12, value=m.get('total_amount_with_vip0', 0))
        ws.cell(row=row_num, column=12).number_format = '#,##0'

    ws.column_dimensions['A'].width = 12  # Month YYYY-MM
    for col in range(2, 7):
        ws.column_dimensions[get_column_letter(col)].width = 14
    for col in range(7, 13):
        ws.column_dimensions[get_column_letter(col)].width = 16


def _create_shop_sheet(wb, data, header_fill, header_font, header_align):
    """By Shop summary."""
    ws = wb.create_sheet("By Shop")

    headers = ["Shop", "Active", "New", "New Rate", "Returning", "Return Rate", "INV(RET)", "AMT(RET)", "INV(CUS)", "AMT(CUS)", "Total Invoices", "Total Amount"]
    for col_num, header in enumerate(headers, 1):
        cell = ws.cell(row=1, column=col_num, value=header)
        cell.fill = header_fill
        cell.font = header_font
        cell.alignment = header_align

    sorted_shops = sorted(data['by_shop'], key=lambda x: x['shop_name'])

    for row_num, shop in enumerate(sorted_shops, 2):
        ws.cell(row=row_num, column=1, value=shop['shop_name'])
        ws.cell(row=row_num, column=2, value=shop['total_customers'])
        ws.cell(row=row_num, column=3, value=shop.get('new_customers', 0))
        ws.cell(row=row_num, column=4, value=f"{shop.get('new_rate', 0)}%")
        ws.cell(row=row_num, column=5, value=shop['returning_customers'])
        ws.cell(row=row_num, column=6, value=f"{shop['return_rate']}%")
        ws.cell(row=row_num, column=7, value=shop.get('returning_invoices', 0))
        ws.cell(row=row_num, column=8, value=shop.get('returning_amount', 0))
        ws.cell(row=row_num, column=8).number_format = '#,##0'
        ws.cell(row=row_num, column=9, value=shop['total_invoices'])
        ws.cell(row=row_num, column=10, value=shop['total_amount'])
        ws.cell(row=row_num, column=10).number_format = '#,##0'
        ws.cell(row=row_num, column=11, value=shop.get('total_invoices_with_vip0', 0))
        ws.cell(row=row_num, column=12, value=shop.get('total_amount_with_vip0', 0))
        ws.cell(row=row_num, column=12).number_format = '#,##0'

    ws.column_dimensions['A'].width = 30  # Shop name
    for col in range(2, 7):
        ws.column_dimensions[get_column_letter(col)].width = 14  # Numeric
    for col in range(7, 13):
        ws.column_dimensions[get_column_letter(col)].width = 16  # Amount


def _create_shop_detail_sheet(wb, data, header_fill, header_font, header_align):
    """By Shop - Detail with grade and season breakdowns."""
    ws = wb.create_sheet("By Shop - Detail")
    
    current_row = 1
    sorted_shops = sorted(data['by_shop'], key=lambda x: x['shop_name'])
    
    for shop in sorted_shops:
        ws.cell(row=current_row, column=1, value=f"SHOP: {shop['shop_name']}")
        ws.cell(row=current_row, column=1).font = Font(bold=True, size=12)
        ws.merge_cells(f'A{current_row}:L{current_row}')
        current_row += 1

        # By Grade
        ws.cell(row=current_row, column=1, value="By VIP Grade").font = Font(bold=True)
        current_row += 1

        grade_headers = ["Grade", "Active", "Returning", "Return Rate", "INV(RET)", "AMT(RET)", "INV(CUS)", "AMT(CUS)"]
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

        season_headers = ["Season", "Active", "New", "New Rate", "Returning", "Return Rate", "INV(RET)", "AMT(RET)", "INV(CUS)", "AMT(CUS)", "Total Invoices", "Total Amount"]
        for col_num, header in enumerate(season_headers, 1):
            cell = ws.cell(row=current_row, column=col_num, value=header)
            cell.fill = header_fill
            cell.font = header_font
        current_row += 1

        for s in shop.get('by_session', []):
            if not s.get('total_invoices_with_vip0', 0):
                continue
            ws.cell(row=current_row, column=1, value=s['session'])
            ws.cell(row=current_row, column=2, value=s['total_customers'])
            ws.cell(row=current_row, column=3, value=s.get('new_customers', 0))
            ws.cell(row=current_row, column=4, value=f"{s.get('new_rate', 0)}%")
            ws.cell(row=current_row, column=5, value=s['returning_customers'])
            ws.cell(row=current_row, column=6, value=f"{s['return_rate']}%")
            ws.cell(row=current_row, column=7, value=s.get('returning_invoices', 0))
            ws.cell(row=current_row, column=8, value=s.get('returning_amount', 0))
            ws.cell(row=current_row, column=8).number_format = '#,##0'
            ws.cell(row=current_row, column=9, value=s['total_invoices'])
            ws.cell(row=current_row, column=10, value=s['total_amount'])
            ws.cell(row=current_row, column=10).number_format = '#,##0'
            ws.cell(row=current_row, column=11, value=s.get('total_invoices_with_vip0', 0))
            ws.cell(row=current_row, column=12, value=s.get('total_amount_with_vip0', 0))
            ws.cell(row=current_row, column=12).number_format = '#,##0'
            current_row += 1

        current_row += 1

        # By Month
        ws.cell(row=current_row, column=1, value="By Month").font = Font(bold=True)
        current_row += 1

        month_headers = ["Month", "Active", "New", "New Rate", "Returning", "Return Rate", "INV(RET)", "AMT(RET)", "INV(CUS)", "AMT(CUS)", "Total Invoices", "Total Amount"]
        for col_num, header in enumerate(month_headers, 1):
            cell = ws.cell(row=current_row, column=col_num, value=header)
            cell.fill = header_fill
            cell.font = header_font
        current_row += 1

        for m in shop.get('by_month', []):
            if not m.get('total_invoices_with_vip0', 0):
                continue
            ws.cell(row=current_row, column=1, value=m['month'])
            ws.cell(row=current_row, column=2, value=m['total_customers'])
            ws.cell(row=current_row, column=3, value=m.get('new_customers', 0))
            ws.cell(row=current_row, column=4, value=f"{m.get('new_rate', 0)}%")
            ws.cell(row=current_row, column=5, value=m['returning_customers'])
            ws.cell(row=current_row, column=6, value=f"{m['return_rate']}%")
            ws.cell(row=current_row, column=7, value=m.get('returning_invoices', 0))
            ws.cell(row=current_row, column=8, value=m.get('returning_amount', 0))
            ws.cell(row=current_row, column=8).number_format = '#,##0'
            ws.cell(row=current_row, column=9, value=m['total_invoices'])
            ws.cell(row=current_row, column=10, value=m['total_amount'])
            ws.cell(row=current_row, column=10).number_format = '#,##0'
            ws.cell(row=current_row, column=11, value=m.get('total_invoices_with_vip0', 0))
            ws.cell(row=current_row, column=12, value=m.get('total_amount_with_vip0', 0))
            ws.cell(row=current_row, column=12).number_format = '#,##0'
            current_row += 1

        current_row += 1

        # By Week
        ws.cell(row=current_row, column=1, value="By Week").font = Font(bold=True)
        current_row += 1

        week_headers = ["Week", "Active", "New", "New Rate", "Returning", "Return Rate", "INV(RET)", "AMT(RET)", "INV(CUS)", "AMT(CUS)", "Total Invoices", "Total Amount"]
        for col_num, header in enumerate(week_headers, 1):
            cell = ws.cell(row=current_row, column=col_num, value=header)
            cell.fill = header_fill
            cell.font = header_font
        current_row += 1

        for w in shop.get('by_week', []):
            if not w.get('total_invoices_with_vip0', 0):
                continue
            ws.cell(row=current_row, column=1, value=w['week_label'])
            ws.cell(row=current_row, column=2, value=w['total_customers'])
            ws.cell(row=current_row, column=3, value=w.get('new_customers', 0))
            ws.cell(row=current_row, column=4, value=f"{w.get('new_rate', 0)}%")
            ws.cell(row=current_row, column=5, value=w['returning_customers'])
            ws.cell(row=current_row, column=6, value=f"{w['return_rate']}%")
            ws.cell(row=current_row, column=7, value=w.get('returning_invoices', 0))
            ws.cell(row=current_row, column=8, value=w.get('returning_amount', 0))
            ws.cell(row=current_row, column=8).number_format = '#,##0'
            ws.cell(row=current_row, column=9, value=w['total_invoices'])
            ws.cell(row=current_row, column=10, value=w['total_amount'])
            ws.cell(row=current_row, column=10).number_format = '#,##0'
            ws.cell(row=current_row, column=11, value=w.get('total_invoices_with_vip0', 0))
            ws.cell(row=current_row, column=12, value=w.get('total_amount_with_vip0', 0))
            ws.cell(row=current_row, column=12).number_format = '#,##0'
            current_row += 1

        current_row += 2

    # Column widths
    ws.column_dimensions['A'].width = 22  # Week label is longer
    for col in range(2, 7):
        ws.column_dimensions[get_column_letter(col)].width = 14  # Numeric
    for col in range(7, 13):
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

    # Pre-build lookup: {shop_name: {grade: g_data}} — O(1) per lookup vs O(n) next()
    shop_grade_map = {
        shop['shop_name']: {g['grade']: g for g in shop.get('by_grade', [])}
        for shop in sorted_shops
    }

    current_row = 1

    for grade in sorted_grades:
        ws.cell(row=current_row, column=1, value=f"GRADE: {grade}")
        ws.cell(row=current_row, column=1).font = Font(bold=True, size=12)
        ws.merge_cells(f'A{current_row}:H{current_row}')
        current_row += 1

        headers = ["Shop", "Active", "Returning", "Return Rate", "INV(RET)", "AMT(RET)", "INV(CUS)", "AMT(CUS)"]
        for col_num, header in enumerate(headers, 1):
            cell = ws.cell(row=current_row, column=col_num, value=header)
            cell.fill = header_fill
            cell.font = header_font
        current_row += 1

        for shop in sorted_shops:
            g = shop_grade_map[shop['shop_name']].get(grade)
            if g and g.get('total_invoices', 0) > 0:
                ws.cell(row=current_row, column=1, value=shop['shop_name'])
                ws.cell(row=current_row, column=2, value=g['total_customers'])
                ws.cell(row=current_row, column=3, value=g['returning_customers'])
                ws.cell(row=current_row, column=4, value=f"{g['return_rate']}%")
                ws.cell(row=current_row, column=5, value=g.get('returning_invoices', 0))
                ws.cell(row=current_row, column=6, value=g.get('returning_amount', 0))
                ws.cell(row=current_row, column=6).number_format = '#,##0'
                ws.cell(row=current_row, column=7, value=g['total_invoices'])
                ws.cell(row=current_row, column=8, value=g['total_amount'])
                ws.cell(row=current_row, column=8).number_format = '#,##0'
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

    # Pre-build lookup: {shop_name: {season: s_data}}
    shop_session_map = {
        shop['shop_name']: {s['session']: s for s in shop.get('by_session', [])}
        for shop in sorted_shops
    }

    current_row = 1

    for season in all_seasons:
        ws.cell(row=current_row, column=1, value=f"SEASON: {season}")
        ws.cell(row=current_row, column=1).font = Font(bold=True, size=12)
        ws.merge_cells(f'A{current_row}:L{current_row}')
        current_row += 1

        headers = ["Shop", "Active", "New", "New Rate", "Returning", "Return Rate", "INV(RET)", "AMT(RET)", "INV(CUS)", "AMT(CUS)", "Total Invoices", "Total Amount"]
        for col_num, header in enumerate(headers, 1):
            cell = ws.cell(row=current_row, column=col_num, value=header)
            cell.fill = header_fill
            cell.font = header_font
        current_row += 1

        for shop in sorted_shops:
            s = shop_session_map[shop['shop_name']].get(season)
            if s and s.get('total_invoices_with_vip0', 0) > 0:
                ws.cell(row=current_row, column=1, value=shop['shop_name'])
                ws.cell(row=current_row, column=2, value=s['total_customers'])
                ws.cell(row=current_row, column=3, value=s.get('new_customers', 0))
                ws.cell(row=current_row, column=4, value=f"{s.get('new_rate', 0)}%")
                ws.cell(row=current_row, column=5, value=s['returning_customers'])
                ws.cell(row=current_row, column=6, value=f"{s['return_rate']}%")
                ws.cell(row=current_row, column=7, value=s.get('returning_invoices', 0))
                ws.cell(row=current_row, column=8, value=s.get('returning_amount', 0))
                ws.cell(row=current_row, column=8).number_format = '#,##0'
                ws.cell(row=current_row, column=9, value=s['total_invoices'])
                ws.cell(row=current_row, column=10, value=s['total_amount'])
                ws.cell(row=current_row, column=10).number_format = '#,##0'
                ws.cell(row=current_row, column=11, value=s.get('total_invoices_with_vip0', 0))
                ws.cell(row=current_row, column=12, value=s.get('total_amount_with_vip0', 0))
                ws.cell(row=current_row, column=12).number_format = '#,##0'
                current_row += 1

        current_row += 1

    ws.column_dimensions['A'].width = 30
    for col in range(2, 13):
        ws.column_dimensions[get_column_letter(col)].width = 16


def _create_month_comparison_sheet(wb, data, header_fill, header_font, header_align):
    """By Month - All Shops comparison."""
    ws = wb.create_sheet("By Month - All Shops")

    all_months = [m['month'] for m in data.get('by_month', [])]
    sorted_shops = sorted(data['by_shop'], key=lambda x: x['shop_name'])

    # Pre-build lookup: {shop_name: {month: m_data}}
    shop_month_map = {
        shop['shop_name']: {m['month']: m for m in shop.get('by_month', [])}
        for shop in sorted_shops
    }

    current_row = 1

    for month in all_months:
        ws.cell(row=current_row, column=1, value=f"MONTH: {month}").font = Font(bold=True, size=12)
        ws.merge_cells(f'A{current_row}:L{current_row}')
        current_row += 1

        headers = ["Shop", "Active", "New", "New Rate", "Returning", "Return Rate", "INV(RET)", "AMT(RET)", "INV(CUS)", "AMT(CUS)", "Total Invoices", "Total Amount"]
        for col_num, header in enumerate(headers, 1):
            cell = ws.cell(row=current_row, column=col_num, value=header)
            cell.fill = header_fill
            cell.font = header_font
        current_row += 1

        for shop in sorted_shops:
            m = shop_month_map[shop['shop_name']].get(month)
            if m and m.get('total_invoices_with_vip0', 0) > 0:
                ws.cell(row=current_row, column=1, value=shop['shop_name'])
                ws.cell(row=current_row, column=2, value=m['total_customers'])
                ws.cell(row=current_row, column=3, value=m.get('new_customers', 0))
                ws.cell(row=current_row, column=4, value=f"{m.get('new_rate', 0)}%")
                ws.cell(row=current_row, column=5, value=m['returning_customers'])
                ws.cell(row=current_row, column=6, value=f"{m['return_rate']}%")
                ws.cell(row=current_row, column=7, value=m.get('returning_invoices', 0))
                ws.cell(row=current_row, column=8, value=m.get('returning_amount', 0))
                ws.cell(row=current_row, column=8).number_format = '#,##0'
                ws.cell(row=current_row, column=9, value=m['total_invoices'])
                ws.cell(row=current_row, column=10, value=m['total_amount'])
                ws.cell(row=current_row, column=10).number_format = '#,##0'
                ws.cell(row=current_row, column=11, value=m.get('total_invoices_with_vip0', 0))
                ws.cell(row=current_row, column=12, value=m.get('total_amount_with_vip0', 0))
                ws.cell(row=current_row, column=12).number_format = '#,##0'
                current_row += 1

        current_row += 1

    ws.column_dimensions['A'].width = 30
    for col in range(2, 7):
        ws.column_dimensions[get_column_letter(col)].width = 14
    for col in range(7, 13):
        ws.column_dimensions[get_column_letter(col)].width = 16


def _create_week_sheet(wb, data, header_fill, header_font, header_align):
    """By Week sheet."""
    ws = wb.create_sheet("By Week")

    headers = ["Week", "Active", "New", "New Rate", "Returning", "Return Rate", "INV(RET)", "AMT(RET)", "INV(CUS)", "AMT(CUS)", "Total Invoices", "Total Amount"]
    for col_num, header in enumerate(headers, 1):
        cell = ws.cell(row=1, column=col_num, value=header)
        cell.fill = header_fill
        cell.font = header_font
        cell.alignment = header_align

    for row_num, w in enumerate(data.get('by_week', []), 2):
        ws.cell(row=row_num, column=1, value=w['week_label'])
        ws.cell(row=row_num, column=2, value=w['total_customers'])
        ws.cell(row=row_num, column=3, value=w.get('new_customers', 0))
        ws.cell(row=row_num, column=4, value=f"{w.get('new_rate', 0)}%")
        ws.cell(row=row_num, column=5, value=w['returning_customers'])
        ws.cell(row=row_num, column=6, value=f"{w['return_rate']}%")
        ws.cell(row=row_num, column=7, value=w.get('returning_invoices', 0))
        ws.cell(row=row_num, column=8, value=w.get('returning_amount', 0))
        ws.cell(row=row_num, column=8).number_format = '#,##0'
        ws.cell(row=row_num, column=9, value=w['total_invoices'])
        ws.cell(row=row_num, column=10, value=w['total_amount'])
        ws.cell(row=row_num, column=10).number_format = '#,##0'
        ws.cell(row=row_num, column=11, value=w.get('total_invoices_with_vip0', 0))
        ws.cell(row=row_num, column=12, value=w.get('total_amount_with_vip0', 0))
        ws.cell(row=row_num, column=12).number_format = '#,##0'

    ws.column_dimensions['A'].width = 22  # Week label e.g. "Week 1 (1/1-7/1)"
    for col in range(2, 7):
        ws.column_dimensions[get_column_letter(col)].width = 14
    for col in range(7, 13):
        ws.column_dimensions[get_column_letter(col)].width = 16


def _create_week_comparison_sheet(wb, data, header_fill, header_font, header_align):
    """By Week - All Shops comparison."""
    ws = wb.create_sheet("By Week - All Shops")

    all_weeks = [w['week_label'] for w in data.get('by_week', [])]
    sorted_shops = sorted(data['by_shop'], key=lambda x: x['shop_name'])

    # Pre-build lookup: {shop_name: {week_label: w_data}}
    shop_week_map = {
        shop['shop_name']: {w['week_label']: w for w in shop.get('by_week', [])}
        for shop in sorted_shops
    }

    current_row = 1

    for week_label in all_weeks:
        ws.cell(row=current_row, column=1, value=f"WEEK: {week_label}").font = Font(bold=True, size=12)
        ws.merge_cells(f'A{current_row}:L{current_row}')
        current_row += 1

        headers = ["Shop", "Active", "New", "New Rate", "Returning", "Return Rate", "INV(RET)", "AMT(RET)", "INV(CUS)", "AMT(CUS)", "Total Invoices", "Total Amount"]
        for col_num, header in enumerate(headers, 1):
            cell = ws.cell(row=current_row, column=col_num, value=header)
            cell.fill = header_fill
            cell.font = header_font
        current_row += 1

        for shop in sorted_shops:
            w = shop_week_map[shop['shop_name']].get(week_label)
            if w and w.get('total_invoices_with_vip0', 0) > 0:
                ws.cell(row=current_row, column=1, value=shop['shop_name'])
                ws.cell(row=current_row, column=2, value=w['total_customers'])
                ws.cell(row=current_row, column=3, value=w.get('new_customers', 0))
                ws.cell(row=current_row, column=4, value=f"{w.get('new_rate', 0)}%")
                ws.cell(row=current_row, column=5, value=w['returning_customers'])
                ws.cell(row=current_row, column=6, value=f"{w['return_rate']}%")
                ws.cell(row=current_row, column=7, value=w.get('returning_invoices', 0))
                ws.cell(row=current_row, column=8, value=w.get('returning_amount', 0))
                ws.cell(row=current_row, column=8).number_format = '#,##0'
                ws.cell(row=current_row, column=9, value=w['total_invoices'])
                ws.cell(row=current_row, column=10, value=w['total_amount'])
                ws.cell(row=current_row, column=10).number_format = '#,##0'
                ws.cell(row=current_row, column=11, value=w.get('total_invoices_with_vip0', 0))
                ws.cell(row=current_row, column=12, value=w.get('total_amount_with_vip0', 0))
                ws.cell(row=current_row, column=12).number_format = '#,##0'
                current_row += 1

        current_row += 1

    ws.column_dimensions['A'].width = 30
    for col in range(2, 7):
        ws.column_dimensions[get_column_letter(col)].width = 14
    for col in range(7, 13):
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
        ws.cell(row=row_num, column=8, value=c['total_spent'])
        ws.cell(row=row_num, column=8).number_format = '#,##0'
    
    for col in range(1, 9):
        ws.column_dimensions[get_column_letter(col)].width = 18

def _create_buyer_without_info_sheet(wb, data, header_fill, header_font, header_align):
    """Buyer Without Info (VIP ID = 0) sheet."""
    bwi = data.get('buyer_without_info_stats')
    if not bwi:
        return

    ws = wb.create_sheet("Buyer Without Info")
    row = 1

    # Period summary
    ws.cell(row=row, column=1, value="Period Summary").font = Font(bold=True)
    row += 1
    period = bwi.get('period', {})
    for label, value in [
        ("Total Invoices (Period)", period.get('total_invoices', 0)),
        ("Total Amount (Period)", period.get('total_amount', 0)),
        ("% of All Invoices", f"{period.get('pct_of_all_invoices', 0)}%"),
        ("% of All Amount", f"{period.get('pct_of_all_amount', 0)}%"),
    ]:
        ws.cell(row=row, column=1, value=label)
        ws.cell(row=row, column=2, value=value)
        if 'Amount' in label:
            ws.cell(row=row, column=2).number_format = '#,##0'
        row += 1

    row += 1  # spacer

    # All-time summary
    ws.cell(row=row, column=1, value="All-Time Summary").font = Font(bold=True)
    row += 1
    alltime = bwi.get('all_time', {})
    for label, value in [
        ("Total Invoices (All Time)", alltime.get('total_invoices', 0)),
        ("Total Amount (All Time)", alltime.get('total_amount', 0)),
    ]:
        ws.cell(row=row, column=1, value=label)
        ws.cell(row=row, column=2, value=value)
        if 'Amount' in label:
            ws.cell(row=row, column=2).number_format = '#,##0'
        row += 1

    row += 1  # spacer

    # By shop breakdown
    ws.cell(row=row, column=1, value="By Shop (Period)").font = Font(bold=True)
    row += 1
    shop_headers = ["Shop", "Invoices", "Amount", "% Inv (All Period)", "% Amt (All Period)"]
    for col_num, header in enumerate(shop_headers, 1):
        cell = ws.cell(row=row, column=col_num, value=header)
        cell.fill = header_fill
        cell.font = header_font
        cell.alignment = header_align
    row += 1
    for s in bwi.get('by_shop', []):
        ws.cell(row=row, column=1, value=s['shop_name'])
        ws.cell(row=row, column=2, value=s['invoices'])
        ws.cell(row=row, column=3, value=s['amount'])
        ws.cell(row=row, column=3).number_format = '#,##0'
        ws.cell(row=row, column=4, value=f"{s['pct_of_period_invoices']}%")
        ws.cell(row=row, column=5, value=f"{s['pct_of_period_amount']}%")
        row += 1

    ws.column_dimensions['A'].width = 30
    ws.column_dimensions['B'].width = 14
    ws.column_dimensions['C'].width = 18
    ws.column_dimensions['D'].width = 18
    ws.column_dimensions['E'].width = 18


"""
ULTIMATE FIX - Uses customer_utils.get_customer_info() for proper lookup
"""

def _create_reconciliation_sheet(wb, data, header_fill, header_font, header_align):
    """
    ULTIMATE FIX: Use customer_utils.get_customer_info() instead of manual lookup
    """
    from openpyxl.styles import Font, PatternFill, Alignment
    from collections import defaultdict
    from App.analytics.customer_utils import get_customer_info
    
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
    
    # Single pass: compute both shop_problems and season_problems simultaneously.
    # purchases lists are already sorted by build_customer_purchase_map — no re-sort needed.
    shop_problems = []
    season_problems = []

    for vip_id, purchases in customer_purchases.items():
        if vip_id == '0' or not purchases:
            continue

        # purchases already sorted; use directly
        customer_obj = purchases[0].get('customer')
        grade, reg_date, name = get_customer_info(vip_id, customer_obj)

        global_rv, global_is_ret = calculate_return_visits_local(purchases, reg_date)
        if not global_is_ret:
            continue

        global_ret_inv = len(purchases)

        # Build per-shop and per-season sub-lists in one scan (sub-lists inherit sort order)
        by_shop = defaultdict(list)
        by_season = defaultdict(list)
        for p in purchases:
            by_shop[p.get('shop', 'Unknown')].append(p)
            by_season[p.get('session', 'Unknown')].append(p)

        # ── Shop diff ──────────────────────────────────────────────────────────
        shop_total = 0
        for shop_purch in by_shop.values():
            _, is_ret = calculate_return_visits_local(shop_purch, reg_date)
            if is_ret:
                shop_total += len(shop_purch)

        cust_shop_diff = global_ret_inv - shop_total
        if cust_shop_diff > 0:
            reg_date_cmp = to_date(reg_date)
            if reg_date_cmp:
                reg_day_purch = [p for p in purchases if to_date(p['date']) == reg_date_cmp]
                reg_day_shops = {p.get('shop', 'Unknown') for p in reg_day_purch}
            else:
                reg_day_purch = []
                reg_day_shops = set()

            if len(reg_day_shops) >= 2:
                pattern = "Multi-shop reg day"
            elif len(reg_day_purch) >= 1 and len(by_shop) >= 2:
                pattern = "Reg day → other shops"
            else:
                pattern = "Other"

            # sub-lists already in date order; first element is earliest
            shop_details = []
            by_shop_sorted = sorted(by_shop.items(), key=lambda kv: kv[1][0]['date'])
            for sh, sh_purch in by_shop_sorted[:3]:
                _, sh_is_ret = calculate_return_visits_local(sh_purch, reg_date)
                shop_details.append(f"{sh[:25]}({len(sh_purch)},ret={sh_is_ret})")

            shop_problems.append({
                'vip_id': vip_id, 'name': name, 'reg_date': reg_date,
                'total_purchases': global_ret_inv, 'global_ret_inv': global_ret_inv,
                'shop_total': shop_total, 'difference': cust_shop_diff,
                'pattern': pattern, 'details': "; ".join(shop_details),
            })

        # ── Season diff ────────────────────────────────────────────────────────
        season_total = 0
        for season_purch in by_season.values():
            _, is_ret = calculate_return_visits_local(season_purch, reg_date)
            if is_ret:
                season_total += len(season_purch)

        cust_season_diff = global_ret_inv - season_total
        if cust_season_diff > 0:
            season_details = []
            by_season_sorted = sorted(by_season.items(), key=lambda kv: kv[1][0]['date'])
            for ssn, ssn_purch in by_season_sorted[:3]:
                _, ssn_is_ret = calculate_return_visits_local(ssn_purch, reg_date)
                season_details.append(f"{ssn}({len(ssn_purch)},ret={ssn_is_ret})")

            season_problems.append({
                'vip_id': vip_id, 'name': name, 'reg_date': reg_date,
                'total_purchases': global_ret_inv, 'global_ret_inv': global_ret_inv,
                'season_total': season_total, 'difference': cust_season_diff,
                'num_seasons': len(by_season), 'details': "; ".join(season_details),
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
    


# Add this function to the END of excel_export.py

def export_customer_analytics_to_excel(
    pos_customers,
    cnv_customers,
    date_from=None,
    date_to=None,
    points_mismatch=None,
    total_points_mismatch=None,
    cnv_used_points=None,
    zalo_mini_app_list=None,
    zalo_oa_list=None,
    zalo_stats=None,
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

    from django.db.models import Subquery

    # Base querysets with phone
    pos_base = pos_customers.filter(phone__isnull=False).exclude(phone='')
    cnv_base = cnv_customers.filter(phone__isnull=False).exclude(phone='')

    # Count sets (done via DB, no Python set needed for this)
    pos_phones_sq = Subquery(cnv_base.values('phone'))
    cnv_phones_sq = Subquery(pos_base.values('phone'))

    pos_only_count = pos_base.exclude(phone__in=pos_phones_sq).count()
    cnv_only_count = cnv_base.exclude(phone__in=cnv_phones_sq).count()
    total_pos = pos_base.count()
    total_cnv = cnv_base.count()

    # Period comparisons (if filtered)
    new_pos_count = 0
    new_cnv_count = 0
    pos_only_period_count = 0
    cnv_only_period_count = 0

    if date_from and date_to:
        new_pos = pos_base.filter(registration_date__gte=date_from, registration_date__lte=date_to)
        new_pos_count = new_pos.count()
        pos_only_period_count = new_pos.exclude(phone__in=Subquery(cnv_base.values('phone'))).count()

        new_cnv = cnv_base.filter(cnv_created_at__gte=date_from, cnv_created_at__lte=date_to)
        new_cnv_count = new_cnv.count()
        cnv_only_period_count = new_cnv.exclude(phone__in=Subquery(pos_base.values('phone'))).count()
    
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
        ("Total Customers (POS System)", total_pos),
        ("Total CNV Customers", total_cnv),
        ("POS Only (Not in CNV)", pos_only_count),
        ("CNV Only (Not in POS)", cnv_only_count),
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
            ("New POS Only (Period)", pos_only_period_count),
            ("New CNV Only (Period)", cnv_only_period_count),
        ]
        
        for label, value in metrics_period:
            ws[f'A{row}'] = label
            ws[f'B{row}'] = value
            row += 1
    
    # Zalo All-Time Metrics
    if zalo_stats:
        row += 1
        ws[f'A{row}'] = "Zalo Metrics (All-Time)"
        ws[f'A{row}'].font = Font(bold=True, color="0068FF")
        row += 1
        zalo_metrics = [
            ("Active Zalo Mini App", zalo_stats.get('zalo_app_all_count', 0)),
            ("% Active Zalo / CNV", f"{zalo_stats.get('zalo_app_all_pct', 0)}%"),
            ("Follow Zalo OA", zalo_stats.get('zalo_oa_all_count', 0)),
            ("% Follow OA / CNV", f"{zalo_stats.get('zalo_oa_all_pct', 0)}%"),
        ]
        for label, value in zalo_metrics:
            ws[f'A{row}'] = label
            ws[f'B{row}'] = value
            row += 1

        if date_from and date_to:
            row += 1
            ws[f'A{row}'] = "Zalo Metrics (Period)"
            ws[f'A{row}'].font = Font(bold=True, color="0068FF")
            row += 1
            zalo_period_metrics = [
                ("Active Zalo Mini App (Period)", zalo_stats.get('zalo_app_period_count', 0)),
                ("% Zalo App / CNV (Period)", f"{zalo_stats.get('zalo_app_period_pct', 0)}%"),
                ("Follow Zalo OA (Period)", zalo_stats.get('zalo_oa_period_count', 0)),
                ("% Follow OA / CNV (Period)", f"{zalo_stats.get('zalo_oa_period_pct', 0)}%"),
            ]
            for label, value in zalo_period_metrics:
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
    headers = ['VIP ID', 'Phone', 'Name', 'VIP Grade', 'Email', 'Registration Date', 'Points']
    for col_idx, header in enumerate(headers, 1):
        cell = ws_pos_all.cell(1, col_idx, header)
        cell.fill = header_fill
        cell.font = header_font
        cell.alignment = header_align

    # Data — subquery, no large __in set
    pos_only_customers = pos_base.exclude(
        phone__in=Subquery(cnv_base.values('phone'))
    ).order_by('registration_date')
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
    ws_pos_all.column_dimensions['A'].width = 12
    ws_pos_all.column_dimensions['B'].width = 15
    ws_pos_all.column_dimensions['C'].width = 25
    ws_pos_all.column_dimensions['D'].width = 12
    ws_pos_all.column_dimensions['E'].width = 30
    ws_pos_all.column_dimensions['F'].width = 18
    ws_pos_all.column_dimensions['G'].width = 10
    
    # ========================================================================
    # CNV ONLY - ALL TIME SHEET
    # ========================================================================
    ws_cnv_all = wb.create_sheet("CNV Only - All Time")
    
    # Header (8 columns)
    headers = ['CNV ID', 'Phone', 'Name', 'Level', 'Email', 'Registration Date', 'Points', 'Used Points']
    for col_idx, header in enumerate(headers, 1):
        cell = ws_cnv_all.cell(1, col_idx, header)
        cell.fill = header_fill
        cell.font = header_font
        cell.alignment = header_align
    
    # Data — subquery
    cnv_only_customers = cnv_base.exclude(
        phone__in=Subquery(pos_base.values('phone'))
    ).order_by('cnv_created_at')
    row = 2
    for cust in cnv_only_customers:
        ws_cnv_all.cell(row, 1, cust.cnv_id)
        ws_cnv_all.cell(row, 2, cust.phone)
        ws_cnv_all.cell(row, 3, cust.full_name or '-')
        ws_cnv_all.cell(row, 4, cust.level_name or '-')
        ws_cnv_all.cell(row, 5, cust.email or '-')
        ws_cnv_all.cell(row, 6, str(cust.cnv_created_at.date()) if cust.cnv_created_at else '-')
        ws_cnv_all.cell(row, 7, float(cust.total_points) if cust.total_points else 0)
        ws_cnv_all.cell(row, 8, float(cust.used_points) if cust.used_points else 0)
        row += 1
    
    # Column widths
    ws_cnv_all.column_dimensions['A'].width = 15
    ws_cnv_all.column_dimensions['B'].width = 15
    ws_cnv_all.column_dimensions['C'].width = 25
    ws_cnv_all.column_dimensions['D'].width = 12
    ws_cnv_all.column_dimensions['E'].width = 30
    ws_cnv_all.column_dimensions['F'].width = 18
    ws_cnv_all.column_dimensions['G'].width = 12
    ws_cnv_all.column_dimensions['H'].width = 12
    
    # ========================================================================
    # PERIOD SHEETS (if filtered)
    # ========================================================================
    if date_from and date_to:
        # POS Only - Period
        pos_period_qs = pos_base.filter(
            registration_date__gte=date_from,
            registration_date__lte=date_to
        ).exclude(phone__in=Subquery(cnv_base.values('phone'))).order_by('registration_date')

        if pos_period_qs.exists():
            ws_pos_period = wb.create_sheet("POS Only - Period")
            headers = ['VIP ID', 'Phone', 'Name', 'VIP Grade', 'Email', 'Registration Date', 'Points']
            for col_idx, header in enumerate(headers, 1):
                cell = ws_pos_period.cell(1, col_idx, header)
                cell.fill = header_fill
                cell.font = header_font
                cell.alignment = header_align
            row = 2
            for cust in pos_period_qs:
                ws_pos_period.cell(row, 1, cust.vip_id)
                ws_pos_period.cell(row, 2, cust.phone)
                ws_pos_period.cell(row, 3, cust.name)
                ws_pos_period.cell(row, 4, cust.vip_grade or '-')
                ws_pos_period.cell(row, 5, cust.email or '-')
                ws_pos_period.cell(row, 6, str(cust.registration_date) if cust.registration_date else '-')
                ws_pos_period.cell(row, 7, cust.points or 0)
                row += 1
            for col, w in zip('ABCDEFG', [12, 15, 25, 12, 30, 18, 10]):
                ws_pos_period.column_dimensions[col].width = w

        # CNV Only - Period
        cnv_period_qs = cnv_base.filter(
            cnv_created_at__gte=date_from,
            cnv_created_at__lte=date_to
        ).exclude(phone__in=Subquery(pos_base.values('phone'))).order_by('cnv_created_at')

        if cnv_period_qs.exists():
            ws_cnv_period = wb.create_sheet("CNV Only - Period")
            headers = ['CNV ID', 'Phone', 'Name', 'Level', 'Email', 'Registration Date', 'Points', 'Used Points']
            for col_idx, header in enumerate(headers, 1):
                cell = ws_cnv_period.cell(1, col_idx, header)
                cell.fill = header_fill
                cell.font = header_font
                cell.alignment = header_align
            row = 2
            for cust in cnv_period_qs:
                ws_cnv_period.cell(row, 1, cust.cnv_id)
                ws_cnv_period.cell(row, 2, cust.phone)
                ws_cnv_period.cell(row, 3, cust.full_name or '-')
                ws_cnv_period.cell(row, 4, cust.level_name or '-')
                ws_cnv_period.cell(row, 5, cust.email or '-')
                ws_cnv_period.cell(row, 6, str(cust.cnv_created_at.date()) if cust.cnv_created_at else '-')
                ws_cnv_period.cell(row, 7, float(cust.total_points) if cust.total_points else 0)
                ws_cnv_period.cell(row, 8, float(cust.used_points) if cust.used_points else 0)
                row += 1
            for col, w in zip('ABCDEFGH', [15, 15, 25, 12, 30, 18, 12, 12]):
                ws_cnv_period.column_dimensions[col].width = w

    # ========================================================================
    # POINTS MISMATCH SHEET
    # ========================================================================
    ws_mismatch = wb.create_sheet("Points Mismatch")

    mismatch_headers = [
        'Phone', 'POS VIP ID', 'POS Name', 'POS Grade', 'POS Points', 'POS Used Points',
        'CNV ID', 'CNV Name', 'CNV Level', 'CNV Points', 'CNV Total Points', 'CNV Used Points',
        'Diff Value', 'Diff Note'
    ]
    orange_fill = PatternFill(start_color="C65911", end_color="C65911", fill_type="solid")
    for col_idx, header in enumerate(mismatch_headers, 1):
        cell = ws_mismatch.cell(1, col_idx, header)
        cell.fill = orange_fill
        cell.font = header_font
        cell.alignment = header_align

    row = 2
    for m in (points_mismatch or []):
        ws_mismatch.cell(row, 1, m.get('phone', ''))
        ws_mismatch.cell(row, 2, m.get('pos_vip_id', ''))
        ws_mismatch.cell(row, 3, m.get('pos_name', ''))
        ws_mismatch.cell(row, 4, m.get('pos_grade', ''))
        ws_mismatch.cell(row, 5, m.get('pos_points', 0))
        ws_mismatch.cell(row, 6, m.get('pos_used_points', 0))
        ws_mismatch.cell(row, 7, m.get('cnv_id', ''))
        ws_mismatch.cell(row, 8, m.get('cnv_name', ''))
        ws_mismatch.cell(row, 9, m.get('cnv_level', ''))
        ws_mismatch.cell(row, 10, m.get('cnv_points', 0))
        ws_mismatch.cell(row, 11, m.get('cnv_total_points', 0))
        ws_mismatch.cell(row, 12, m.get('cnv_used_points', 0))
        diff = m.get('diff', 0)
        diff_cell = ws_mismatch.cell(row, 13, diff)
        diff_cell.font = Font(bold=True, color="16A34A" if diff > 0 else "DC2626")
        note = "Run camp to reduce point in CNV" if diff > 0 else "Run camp to increase point in CNV"
        ws_mismatch.cell(row, 14, note)
        row += 1

    for col_letter, width in zip('ABCDEFGHIJKLMN', [15, 12, 25, 12, 10, 12, 12, 25, 12, 10, 14, 12, 10, 35]):
        ws_mismatch.column_dimensions[col_letter].width = width

    # ========================================================================
    # CNV USED POINTS > 0 SHEET
    # ========================================================================
    ws_used = wb.create_sheet("CNV Used Points")

    green_fill = PatternFill(start_color="166534", end_color="166534", fill_type="solid")
    used_headers = ['CNV ID', 'Phone', 'Name', 'Level', 'Email', 'Registration Date', 'Points', 'Used Points', 'Total Points']
    for col_idx, header in enumerate(used_headers, 1):
        cell = ws_used.cell(1, col_idx, header)
        cell.fill = green_fill
        cell.font = header_font
        cell.alignment = header_align

    row = 2
    for cust in (cnv_used_points or []):
        ws_used.cell(row, 1, cust.cnv_id)
        ws_used.cell(row, 2, cust.phone)
        ws_used.cell(row, 3, cust.full_name or '-')
        ws_used.cell(row, 4, cust.level_name or '-')
        ws_used.cell(row, 5, cust.email or '-')
        ws_used.cell(row, 6, str(cust.cnv_created_at.date()) if cust.cnv_created_at else '-')
        ws_used.cell(row, 7, float(cust.points or 0))
        used_cell = ws_used.cell(row, 8, float(cust.used_points or 0))
        used_cell.font = Font(bold=True, color="166534")
        ws_used.cell(row, 9, float(cust.total_points or 0))
        row += 1

    ws_used.column_dimensions['A'].width = 15
    ws_used.column_dimensions['B'].width = 15
    ws_used.column_dimensions['C'].width = 25
    ws_used.column_dimensions['D'].width = 12
    ws_used.column_dimensions['E'].width = 30
    ws_used.column_dimensions['F'].width = 18
    ws_used.column_dimensions['G'].width = 12
    ws_used.column_dimensions['H'].width = 14
    ws_used.column_dimensions['I'].width = 14

    # ========================================================================
    # TOTAL POINTS MISMATCH SHEET  (POS.net_points vs CNV.total_points)
    # ========================================================================
    ws_total_mismatch = wb.create_sheet("Total Points Mismatch")

    total_mismatch_headers = [
        'Phone', 'POS VIP ID', 'POS Name', 'POS Grade', 'POS Points', 'POS Used Points',
        'CNV ID', 'CNV Name', 'CNV Level', 'CNV Points', 'CNV Total Points', 'CNV Used Points',
        'Diff Value', 'Diff Note'
    ]
    purple_fill = PatternFill(start_color="7C3AED", end_color="7C3AED", fill_type="solid")
    for col_idx, header in enumerate(total_mismatch_headers, 1):
        cell = ws_total_mismatch.cell(1, col_idx, header)
        cell.fill = purple_fill
        cell.font = header_font
        cell.alignment = header_align

    row = 2
    for m in (total_points_mismatch or []):
        ws_total_mismatch.cell(row, 1, m.get('phone', ''))
        ws_total_mismatch.cell(row, 2, m.get('pos_vip_id', ''))
        ws_total_mismatch.cell(row, 3, m.get('pos_name', ''))
        ws_total_mismatch.cell(row, 4, m.get('pos_grade', ''))
        ws_total_mismatch.cell(row, 5, m.get('pos_points', 0))
        ws_total_mismatch.cell(row, 6, m.get('pos_used_points', 0))
        ws_total_mismatch.cell(row, 7, m.get('cnv_id', ''))
        ws_total_mismatch.cell(row, 8, m.get('cnv_name', ''))
        ws_total_mismatch.cell(row, 9, m.get('cnv_level', ''))
        ws_total_mismatch.cell(row, 10, m.get('cnv_points', 0))
        ws_total_mismatch.cell(row, 11, m.get('cnv_total_points', 0))
        ws_total_mismatch.cell(row, 12, m.get('cnv_used_points', 0))
        diff = m.get('diff', 0)
        diff_cell = ws_total_mismatch.cell(row, 13, diff)
        diff_cell.font = Font(bold=True, color="16A34A" if diff > 0 else "DC2626")
        note = "Run camp to reduce point in CNV" if diff > 0 else "Run camp to increase point in CNV"
        ws_total_mismatch.cell(row, 14, note)
        row += 1

    for col_letter, width in zip('ABCDEFGHIJKLMN', [15, 12, 25, 12, 10, 12, 12, 25, 12, 10, 14, 12, 10, 35]):
        ws_total_mismatch.column_dimensions[col_letter].width = width

    # ========================================================================
    # ZALO MINI APP SHEET
    # ========================================================================
    zalo_blue_fill = PatternFill(start_color="0068FF", end_color="0068FF", fill_type="solid")
    zalo_headers = [
        'CNV ID', 'Phone', 'Full Name', 'Level', 'Email',
        'Reg Date', 'Points', 'Mini App', 'Follow OA', 'In POS'
    ]

    ws_zalo_app = wb.create_sheet("Zalo Mini App")
    for col_idx, header in enumerate(zalo_headers, 1):
        cell = ws_zalo_app.cell(1, col_idx, header)
        cell.fill = zalo_blue_fill
        cell.font = header_font
        cell.alignment = header_align
    row = 2
    for c in (zalo_mini_app_list or []):
        full_name = f"{c.get('last_name') or ''} {c.get('first_name') or ''}".strip()
        reg_date = c.get('cnv_created_at')
        reg_date_str = str(reg_date.date()) if hasattr(reg_date, 'date') else (str(reg_date)[:10] if reg_date else '-')
        ws_zalo_app.cell(row, 1, c.get('cnv_id', ''))
        ws_zalo_app.cell(row, 2, c.get('phone', ''))
        ws_zalo_app.cell(row, 3, full_name or '-')
        ws_zalo_app.cell(row, 4, c.get('level_name') or '-')
        ws_zalo_app.cell(row, 5, c.get('email') or '-')
        ws_zalo_app.cell(row, 6, reg_date_str)
        ws_zalo_app.cell(row, 7, float(c.get('points') or 0))
        ws_zalo_app.cell(row, 8, 'Yes' if c.get('zalo_app_id') else 'No')
        ws_zalo_app.cell(row, 9, 'Yes' if c.get('zalo_oa_id') else 'No')
        ws_zalo_app.cell(row, 10, 'Yes' if c.get('in_pos') else 'No')
        row += 1
    for col, w in zip('ABCDEFGHIJ', [15, 15, 25, 12, 30, 12, 10, 10, 10, 8]):
        ws_zalo_app.column_dimensions[col].width = w

    # ========================================================================
    # ZALO FOLLOW OA SHEET
    # ========================================================================
    zalo_cyan_fill = PatternFill(start_color="00AAFF", end_color="00AAFF", fill_type="solid")
    ws_zalo_oa = wb.create_sheet("Zalo Follow OA")
    for col_idx, header in enumerate(zalo_headers, 1):
        cell = ws_zalo_oa.cell(1, col_idx, header)
        cell.fill = zalo_cyan_fill
        cell.font = header_font
        cell.alignment = header_align
    row = 2
    for c in (zalo_oa_list or []):
        full_name = f"{c.get('last_name') or ''} {c.get('first_name') or ''}".strip()
        reg_date = c.get('cnv_created_at')
        reg_date_str = str(reg_date.date()) if hasattr(reg_date, 'date') else (str(reg_date)[:10] if reg_date else '-')
        ws_zalo_oa.cell(row, 1, c.get('cnv_id', ''))
        ws_zalo_oa.cell(row, 2, c.get('phone', ''))
        ws_zalo_oa.cell(row, 3, full_name or '-')
        ws_zalo_oa.cell(row, 4, c.get('level_name') or '-')
        ws_zalo_oa.cell(row, 5, c.get('email') or '-')
        ws_zalo_oa.cell(row, 6, reg_date_str)
        ws_zalo_oa.cell(row, 7, float(c.get('points') or 0))
        ws_zalo_oa.cell(row, 8, 'Yes' if c.get('zalo_app_id') else 'No')
        ws_zalo_oa.cell(row, 9, 'Yes' if c.get('zalo_oa_id') else 'No')
        ws_zalo_oa.cell(row, 10, 'Yes' if c.get('in_pos') else 'No')
        row += 1
    for col, w in zip('ABCDEFGHIJ', [15, 15, 25, 12, 30, 12, 10, 10, 10, 8]):
        ws_zalo_oa.column_dimensions[col].width = w

    # ========================================================================
    # ALL CNV CUSTOMERS SHEET (filtered by period if dates provided)
    # ========================================================================
    cnv_all_fill = PatternFill(start_color="1D3557", end_color="1D3557", fill_type="solid")
    cnv_all_headers = [
        'CNV ID', 'Phone', 'Full Name', 'Level', 'Email',
        'Reg Date', 'Points', 'Used Points', 'Total Points',
        'Zalo App ID', 'Zalo OA ID', 'Zalo Created At'
    ]

    sheet_title = f"CNV {date_from} to {date_to}" if (date_from and date_to) else "All CNV Customers"
    if len(sheet_title) > 31:
        sheet_title = sheet_title[:31]

    ws_cnv_all_full = wb.create_sheet(sheet_title)
    for col_idx, header in enumerate(cnv_all_headers, 1):
        cell = ws_cnv_all_full.cell(1, col_idx, header)
        cell.fill = cnv_all_fill
        cell.font = header_font
        cell.alignment = header_align

    cnv_all_qs = cnv_base.order_by('cnv_created_at')
    if date_from and date_to:
        cnv_all_qs = cnv_all_qs.filter(cnv_created_at__gte=date_from, cnv_created_at__lte=date_to)

    row = 2
    for cust in cnv_all_qs:
        full_name = getattr(cust, 'full_name', None) or (
            f"{cust.last_name or ''} {cust.first_name or ''}".strip()
        )
        ws_cnv_all_full.cell(row, 1, cust.cnv_id)
        ws_cnv_all_full.cell(row, 2, cust.phone or '-')
        ws_cnv_all_full.cell(row, 3, full_name or '-')
        ws_cnv_all_full.cell(row, 4, cust.level_name or '-')
        ws_cnv_all_full.cell(row, 5, cust.email or '-')
        ws_cnv_all_full.cell(row, 6, str(cust.cnv_created_at.date()) if cust.cnv_created_at else '-')
        ws_cnv_all_full.cell(row, 7, float(cust.points or 0))
        ws_cnv_all_full.cell(row, 8, float(cust.used_points or 0))
        ws_cnv_all_full.cell(row, 9, float(cust.total_points or 0))
        ws_cnv_all_full.cell(row, 10, cust.zalo_app_id or '')
        ws_cnv_all_full.cell(row, 11, cust.zalo_oa_id or '')
        zalo_dt = cust.zalo_app_created_at
        ws_cnv_all_full.cell(row, 12, str(zalo_dt.date()) if zalo_dt else '')
        row += 1

    for col, w in zip('ABCDEFGHIJKL', [15, 15, 25, 12, 30, 12, 10, 12, 12, 15, 15, 16]):
        ws_cnv_all_full.column_dimensions[col].width = w


# ── Per-tab export ─────────────────────────────────────────────────────────────
# Must be defined AFTER all _create_* functions.

_TAB_SHEETS = {
    "grade":      ([_create_grade_sheet],                           "By VIP Grade"),
    "season":     ([_create_season_sheet],                          "By Season"),
    "month":      ([_create_month_sheet],                           "By Month"),
    "week":       ([_create_week_sheet],                            "By Week"),
    "shop":       ([_create_shop_sheet, _create_shop_detail_sheet], "By Shop"),
    "grade_all":  ([_create_grade_comparison_sheet],                "By Grade - All Shops"),
    "season_all": ([_create_season_comparison_sheet],               "By Season - All Shops"),
    "month_all":  ([_create_month_comparison_sheet],                "By Month - All Shops"),
    "week_all":   ([_create_week_comparison_sheet],                 "By Week - All Shops"),
}


def _prepend_filter_info(wb, date_from=None, date_to=None, shop_group=None):
    """Insert a filter-info row at the top of every sheet in the workbook."""
    parts = []
    if date_from and date_to:
        parts.append(f"Period: {date_from} → {date_to}")
    if shop_group:
        parts.append(f"Shop Group: {shop_group}")
    if not parts:
        return
    line = "  |  ".join(parts)
    for ws in wb.worksheets:
        ws.insert_rows(1)
        ws["A1"] = line
        ws["A1"].font = Font(italic=True, color="888888", size=9)


def export_tab_to_excel(tab, data, date_from=None, date_to=None, shop_group=None):
    """Export a single analytics tab to Excel (tab sheet(s) only, with filter row)."""
    if tab not in _TAB_SHEETS:
        return None

    wb = Workbook()
    wb.remove(wb.active)  # drop default blank sheet
    header_fill = PatternFill(start_color="366092", end_color="366092", fill_type="solid")
    header_font = Font(bold=True, color="FFFFFF")
    header_align = Alignment(horizontal="center", vertical="center")

    creators, _ = _TAB_SHEETS[tab]
    for fn in creators:
        fn(wb, data, header_fill, header_font, header_align)

    _prepend_filter_info(wb, date_from=date_from, date_to=date_to, shop_group=shop_group)
    return wb


# ── CNV per-tab export ────────────────────────────────────────────────────────

def _cnv_hdr(ws, headers, fill, font, align):
    for i, h in enumerate(headers, 1):
        c = ws.cell(row=1, column=i, value=h)
        c.fill = fill; c.font = font; c.alignment = align


def _build_cnv_used_points_ws(wb, data, hf, font, align):
    ws = wb.create_sheet("CNV Used Points")
    _cnv_hdr(ws, ["CNV ID", "Phone", "Full Name", "Level", "Email",
                  "Reg Date", "Points", "Used Pts", "Total Pts", "In POS"], hf, font, align)
    for r, c in enumerate(data.get("cnv_used_points_list") or [], 2):
        ws.cell(r, 1, c.get("cnv_id", ""))
        ws.cell(r, 2, c.get("phone", ""))
        ws.cell(r, 3, f"{c.get('last_name') or ''} {c.get('first_name') or ''}".strip())
        ws.cell(r, 4, c.get("level_name", ""))
        ws.cell(r, 5, c.get("email", "") or "")
        ws.cell(r, 6, str(c["cnv_created_at"].date()) if c.get("cnv_created_at") else "")
        ws.cell(r, 7, c.get("points") or 0)
        ws.cell(r, 8, c.get("used_points") or 0)
        ws.cell(r, 9, c.get("total_points") or 0)
        ws.cell(r, 10, "Yes" if c.get("in_pos") else "No")
    for col, w in zip("ABCDEFGHIJ", [14, 14, 22, 10, 28, 12, 10, 10, 10, 8]):
        ws.column_dimensions[col].width = w


def _build_mismatch_ws(wb, data, key, title, hf, font, align):
    ws = wb.create_sheet(title)
    _cnv_hdr(ws, ["Phone", "POS VIP ID", "POS Name", "POS Grade", "POS Pts", "POS Used Pts",
                  "CNV ID", "CNV Name", "CNV Level", "CNV Pts", "CNV Total Pts", "CNV Used Pts", "Diff"],
             hf, font, align)
    for r, c in enumerate(data.get(key) or [], 2):
        ws.cell(r, 1, c.get("phone", ""))
        ws.cell(r, 2, c.get("pos_vip_id", ""))
        ws.cell(r, 3, c.get("pos_name", ""))
        ws.cell(r, 4, c.get("pos_grade", ""))
        ws.cell(r, 5, c.get("pos_points") or 0)
        ws.cell(r, 6, c.get("pos_used_points") or 0)
        ws.cell(r, 7, c.get("cnv_id", ""))
        ws.cell(r, 8, c.get("cnv_name", ""))
        ws.cell(r, 9, c.get("cnv_level", ""))
        ws.cell(r, 10, c.get("cnv_points") or 0)
        ws.cell(r, 11, c.get("cnv_total_points") or 0)
        ws.cell(r, 12, c.get("cnv_used_points") or 0)
        ws.cell(r, 13, c.get("diff") or 0)
    for col, w in zip("ABCDEFGHIJKLM", [14, 12, 22, 10, 10, 12, 14, 22, 10, 10, 12, 12, 10]):
        ws.column_dimensions[col].width = w


def _build_zalo_ws(wb, data, key, title, hf, font, align):
    ws = wb.create_sheet(title)
    _cnv_hdr(ws, ["CNV ID", "Phone", "Full Name", "Level", "Email",
                  "Reg Date", "Points", "Zalo App ID", "Zalo OA ID", "In POS"], hf, font, align)
    for r, c in enumerate(data.get(key) or [], 2):
        ws.cell(r, 1, c.get("cnv_id", ""))
        ws.cell(r, 2, c.get("phone", ""))
        ws.cell(r, 3, f"{c.get('last_name') or ''} {c.get('first_name') or ''}".strip())
        ws.cell(r, 4, c.get("level_name", ""))
        ws.cell(r, 5, c.get("email", "") or "")
        ws.cell(r, 6, str(c["cnv_created_at"].date()) if c.get("cnv_created_at") else "")
        ws.cell(r, 7, c.get("points") or 0)
        ws.cell(r, 8, c.get("zalo_app_id", "") or "")
        ws.cell(r, 9, c.get("zalo_oa_id", "") or "")
        ws.cell(r, 10, "Yes" if c.get("in_pos") else "No")
    for col, w in zip("ABCDEFGHIJ", [14, 14, 22, 10, 28, 12, 10, 20, 20, 8]):
        ws.column_dimensions[col].width = w


def _build_pos_only_ws(wb, data, key, title, hf, font, align):
    ws = wb.create_sheet(title)
    _cnv_hdr(ws, ["VIP ID", "Phone", "Name", "VIP Grade", "Email", "Reg Date", "Points"],
             hf, font, align)
    for r, c in enumerate(data.get(key) or [], 2):
        ws.cell(r, 1, c.get("vip_id", ""))
        ws.cell(r, 2, c.get("phone", ""))
        ws.cell(r, 3, c.get("name", ""))
        ws.cell(r, 4, c.get("vip_grade", ""))
        ws.cell(r, 5, c.get("email", "") or "")
        ws.cell(r, 6, str(c["registration_date"]) if c.get("registration_date") else "")
        ws.cell(r, 7, c.get("points") or 0)
    for col, w in zip("ABCDEFG", [12, 14, 22, 10, 28, 12, 10]):
        ws.column_dimensions[col].width = w


def _build_cnv_only_ws(wb, data, key, title, hf, font, align):
    ws = wb.create_sheet(title)
    _cnv_hdr(ws, ["CNV ID", "Phone", "Full Name", "Level", "Email",
                  "Reg Date", "Points", "Used Pts", "Total Pts"], hf, font, align)
    for r, c in enumerate(data.get(key) or [], 2):
        ws.cell(r, 1, c.get("cnv_id", ""))
        ws.cell(r, 2, c.get("phone", ""))
        ws.cell(r, 3, f"{c.get('last_name') or ''} {c.get('first_name') or ''}".strip())
        ws.cell(r, 4, c.get("level_name", ""))
        ws.cell(r, 5, c.get("email", "") or "")
        ws.cell(r, 6, str(c["cnv_created_at"].date()) if c.get("cnv_created_at") else "")
        ws.cell(r, 7, c.get("points") or 0)
        ws.cell(r, 8, c.get("used_points") or 0)
        ws.cell(r, 9, c.get("total_points") or 0)
    for col, w in zip("ABCDEFGHI", [14, 14, 22, 10, 28, 12, 10, 10, 10]):
        ws.column_dimensions[col].width = w


_CNV_TAB_SHEETS = {
    "points":  ["cnv_used_points", "points_mismatch", "total_points_mismatch"],
    "zalo":    ["zalo_mini_app",   "zalo_oa"],
    "pos_cnv": ["pos_only_all",    "cnv_only_all", "pos_only_period", "cnv_only_period"],
}


def export_cnv_tab_to_excel(tab, data, date_from=None, date_to=None):
    """Export a single CNV customer-comparison tab (1 sheet per table)."""
    if tab not in _CNV_TAB_SHEETS:
        return None

    wb = Workbook()
    wb.remove(wb.active)
    hf  = PatternFill(start_color="2c3e50", end_color="2c3e50", fill_type="solid")
    fnt = Font(bold=True, color="FFFFFF")
    aln = Alignment(horizontal="center", vertical="center")

    builders = {
        "cnv_used_points":     lambda: _build_cnv_used_points_ws(wb, data, hf, fnt, aln),
        "points_mismatch":     lambda: _build_mismatch_ws(wb, data, "points_mismatch",       "Points Mismatch",       hf, fnt, aln),
        "total_points_mismatch": lambda: _build_mismatch_ws(wb, data, "total_points_mismatch", "Total Points Mismatch", hf, fnt, aln),
        "zalo_mini_app":       lambda: _build_zalo_ws(wb, data, "zalo_mini_app_list", "Zalo Mini App", hf, fnt, aln),
        "zalo_oa":             lambda: _build_zalo_ws(wb, data, "zalo_oa_list",       "Zalo Follow OA",  hf, fnt, aln),
        "pos_only_all":        lambda: _build_pos_only_ws(wb, data, "pos_only_all",    "POS Only - All Time",    hf, fnt, aln),
        "cnv_only_all":        lambda: _build_cnv_only_ws(wb, data, "cnv_only_all",    "CNV Only - All Time",    hf, fnt, aln),
        "pos_only_period":     lambda: _build_pos_only_ws(wb, data, "pos_only_period", "POS Only - Period",      hf, fnt, aln),
        "cnv_only_period":     lambda: _build_cnv_only_ws(wb, data, "cnv_only_period", "CNV Only - Period",      hf, fnt, aln),
    }

    for key in _CNV_TAB_SHEETS[tab]:
        # skip period sheets if no data (no date filter applied)
        if key.endswith("_period") and not data.get(key):
            continue
        builders[key]()

    # filter info row
    parts = []
    if date_from and date_to:
        parts.append(f"Period: {date_from} → {date_to}")
    if parts:
        line = "  |  ".join(parts)
        for ws in wb.worksheets:
            ws.insert_rows(1)
            ws["A1"] = line
            ws["A1"].font = Font(italic=True, color="888888", size=9)

    return wb