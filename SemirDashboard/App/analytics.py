from django.db.models import Count, Q, Min, Max
from collections import defaultdict
from datetime import datetime
from .models import Customer, SalesTransaction
import pandas as pd
from openpyxl import Workbook
from openpyxl.styles import Font, PatternFill, Alignment, Border, Side
from openpyxl.utils import get_column_letter


def calculate_return_rate_analytics():
    """
    Calculate comprehensive return rate analytics
    
    Logic:
    - Total Purchases: Tổng số lần mua hàng của customer (bao gồm cả lần đầu)
    - Return Visits: Số lần quay lại mua (không tính lần đầu)
    - Return Visits = Total Purchases - 1
    
    Example:
    - Customer mua 1 lần: Total Purchases = 1, Return Visits = 0
    - Customer mua 5 lần: Total Purchases = 5, Return Visits = 4
    
    - A customer is considered "new" if their first purchase date matches their registration date
    - A customer is considered "returning" for any purchase after their first purchase
    """
    
    # Get total customers in database (all time)
    total_customers_in_db = Customer.objects.count()
    
    # Get all sales with customer info
    sales = SalesTransaction.objects.select_related('customer').order_by('vip_id', 'sales_date')
    
    if not sales.exists():
        return None
    
    # Get date range
    date_stats = sales.aggregate(
        start_date=Min('sales_date'),
        end_date=Max('sales_date')
    )
    
    # Group sales by customer
    customer_purchases = defaultdict(list)
    for sale in sales:
        customer_purchases[sale.vip_id].append({
            'date': sale.sales_date,
            'invoice': sale.invoice_number,
            'amount': sale.sales_amount,
            'customer': sale.customer
        })
    
    # Analytics data
    total_customers = len(customer_purchases)  # Active customers in period
    returning_customers = set()
    customer_details = []
    
    # Analyze each customer's purchases
    for vip_id, purchases in customer_purchases.items():
        purchases_sorted = sorted(purchases, key=lambda x: x['date'])
        first_purchase = purchases_sorted[0]
        customer = first_purchase['customer']
        
        # Count return visits
        return_count = 0
        
        # Check if customer has registration date
        if customer and customer.registration_date:
            # Check each purchase after the first one
            for i, purchase in enumerate(purchases_sorted):
                # If this is not the first purchase on the registration date
                if i == 0 and purchase['date'] == customer.registration_date:
                    # This is the first visit (registration)
                    continue
                else:
                    # This is a return visit
                    return_count += 1
        else:
            # No registration date, count all purchases after first as returns
            return_count = len(purchases_sorted) - 1
        
        if return_count > 0:
            returning_customers.add(vip_id)
        
        customer_details.append({
            'vip_id': vip_id,
            'name': first_purchase.get('customer').name if first_purchase.get('customer') else 'Unknown',
            'vip_grade': first_purchase.get('customer').vip_grade if first_purchase.get('customer') else '',
            'registration_date': customer.registration_date if customer else None,
            'first_purchase_date': first_purchase['date'],
            'total_purchases': len(purchases_sorted),
            'return_visits': return_count,
            'total_spent': sum(p['amount'] for p in purchases_sorted),
            'customer_obj': customer
        })
    
    # Calculate return rate for active customers
    return_rate = (len(returning_customers) / total_customers * 100) if total_customers > 0 else 0
    
    # Calculate active rate (% of DB customers who made purchases in period)
    active_rate = (total_customers / total_customers_in_db * 100) if total_customers_in_db > 0 else 0
    
    # Group by VIP grade - for ALL customers in DB
    all_customers_by_grade = Customer.objects.values('vip_grade').annotate(
        total=Count('id')
    )
    
    grade_distribution_db = {}
    for item in all_customers_by_grade:
        grade = item['vip_grade'] or 'No Grade'
        grade_distribution_db[grade] = item['total']
    
    # Group by VIP grade - for active customers in period
    grade_analysis = defaultdict(lambda: {'total': 0, 'returning': 0})
    for detail in customer_details:
        grade = detail['vip_grade'] or 'No Grade'
        grade_analysis[grade]['total'] += 1
        if detail['return_visits'] > 0:
            grade_analysis[grade]['returning'] += 1
    
    # Define grade order: No Grade < Bronze < Member < Silver < Gold < Platinum < Diamond
    grade_order = {
        'No Grade': 0,
        'Bronze': 1,
        'Member': 2,
        'Silver': 3,
        'Gold': 4,
        'Platinum': 5,
        'Diamond': 6
    }
    
    grade_stats = []
    for grade, stats in grade_analysis.items():
        rate = (stats['returning'] / stats['total'] * 100) if stats['total'] > 0 else 0
        percentage_of_active = (stats['total'] / total_customers * 100) if total_customers > 0 else 0
        
        # Get total in DB for this grade
        total_in_db = grade_distribution_db.get(grade, 0)
        percentage_of_db = (total_in_db / total_customers_in_db * 100) if total_customers_in_db > 0 else 0
        
        # Calculate active rate for this grade
        grade_active_rate = (stats['total'] / total_in_db * 100) if total_in_db > 0 else 0
        
        grade_stats.append({
            'grade': grade,
            'total_customers': stats['total'],  # Active in period
            'total_in_db': total_in_db,  # Total in database
            'returning_customers': stats['returning'],
            'return_rate': rate,
            'percentage_of_active': percentage_of_active,  # % of active customers
            'percentage_of_db': percentage_of_db,  # % of all DB customers
            'active_rate': grade_active_rate,  # % of this grade that was active
            'sort_order': grade_order.get(grade, 99)
        })
    
    # Sort by grade order
    grade_stats_sorted = sorted(grade_stats, key=lambda x: x['sort_order'])
    
    # Sort customer details by return visits
    customer_details_sorted = sorted(customer_details, key=lambda x: x['return_visits'], reverse=True)
    
    return {
        'date_range': {
            'start': date_stats['start_date'],
            'end': date_stats['end_date']
        },
        'overview': {
            'total_customers_in_db': total_customers_in_db,  # Total in database
            'active_customers': total_customers,  # Active in period
            'active_rate': round(active_rate, 2),  # % of DB that was active
            'returning_customers': len(returning_customers),
            'new_customers': total_customers - len(returning_customers),
            'return_rate': round(return_rate, 2)
        },
        'by_grade': grade_stats_sorted,
        'customer_details': customer_details_sorted
    }


def export_analytics_to_excel(analytics_data):
    """Export analytics data to Excel file with professional formatting"""
    
    if not analytics_data:
        return None
    
    wb = Workbook()
    
    # Remove default sheet
    if 'Sheet' in wb.sheetnames:
        wb.remove(wb['Sheet'])
    
    # Create sheets
    ws_summary = wb.create_sheet('Summary')
    ws_by_grade = wb.create_sheet('By VIP Grade')
    ws_details = wb.create_sheet('Customer Details')
    
    # Styling
    header_font = Font(bold=True, color='FFFFFF', size=12)
    header_fill = PatternFill(start_color='366092', end_color='366092', fill_type='solid')
    title_font = Font(bold=True, size=14)
    border = Border(
        left=Side(style='thin'),
        right=Side(style='thin'),
        top=Side(style='thin'),
        bottom=Side(style='thin')
    )
    
    # === SUMMARY SHEET ===
    ws_summary['A1'] = 'Return Rate Analysis Report'
    ws_summary['A1'].font = title_font
    
    ws_summary['A3'] = 'Analysis Period'
    ws_summary['A3'].font = Font(bold=True)
    ws_summary['A4'] = 'Start Date'
    ws_summary['B4'] = analytics_data['date_range']['start']
    ws_summary['A5'] = 'End Date'
    ws_summary['B5'] = analytics_data['date_range']['end']
    
    ws_summary['A7'] = 'Overall Statistics'
    ws_summary['A7'].font = Font(bold=True)
    
    ws_summary['A8'] = 'Metric'
    ws_summary['B8'] = 'Value'
    ws_summary['A8'].font = header_font
    ws_summary['B8'].font = header_font
    ws_summary['A8'].fill = header_fill
    ws_summary['B8'].fill = header_fill
    
    overview = analytics_data['overview']
    ws_summary['A9'] = 'Total Customers in Database (All Time)'
    ws_summary['B9'] = overview['total_customers_in_db']
    ws_summary['A10'] = 'Active Customers in Period'
    ws_summary['B10'] = overview['active_customers']
    ws_summary['A11'] = 'Active Rate (%)'
    ws_summary['B11'] = overview['active_rate']
    ws_summary['B11'].number_format = '0.00'
    ws_summary['A12'] = ''
    ws_summary['A13'] = 'New Customers (First Visit Only)'
    ws_summary['B13'] = overview['new_customers']
    ws_summary['A14'] = 'Returning Customers'
    ws_summary['B14'] = overview['returning_customers']
    ws_summary['A15'] = 'Return Rate (%)'
    ws_summary['B15'] = overview['return_rate']
    ws_summary['B15'].number_format = '0.00'
    
    # Add explanation section
    ws_summary['A17'] = 'Understanding Metrics'
    ws_summary['A17'].font = Font(bold=True)
    
    ws_summary['A18'] = 'Active Customers:'
    ws_summary['B18'] = 'Customers who made purchases during the analysis period'
    ws_summary['A19'] = 'Active Rate:'
    ws_summary['B19'] = 'Percentage of total DB customers who were active in period'
    ws_summary['A20'] = 'Total Purchases:'
    ws_summary['B20'] = 'Total number of times a customer made a purchase (includes first visit)'
    ws_summary['A21'] = 'Return Visits:'
    ws_summary['B21'] = 'Number of times a customer returned after first visit (Total Purchases - 1)'
    ws_summary['A22'] = 'Example:'
    ws_summary['B22'] = 'Customer buys 5 times → Total Purchases = 5, Return Visits = 4'
    
    for row in [18, 19, 20, 21, 22]:
        ws_summary[f'A{row}'].font = Font(bold=True, size=9)
        ws_summary[f'B{row}'].font = Font(size=9, italic=True)
    
    # Column widths
    ws_summary.column_dimensions['A'].width = 30
    ws_summary.column_dimensions['B'].width = 20
    
    # === BY GRADE SHEET ===
    ws_by_grade['A1'] = 'Return Rate by VIP Grade'
    ws_by_grade['A1'].font = title_font
    
    # Add explanation
    ws_by_grade['A2'] = 'Sorted by grade level: No Grade < Bronze < Member < Silver < Gold < Platinum < Diamond'
    ws_by_grade['A2'].font = Font(italic=True, size=10, color='666666')
    
    headers = ['VIP Grade', 'Total in DB', '% of DB', 'Active in Period', '% Active', 'Returning', 'Return Rate (%)']
    for col, header in enumerate(headers, 1):
        cell = ws_by_grade.cell(row=4, column=col)
        cell.value = header
        cell.font = header_font
        cell.fill = header_fill
        cell.alignment = Alignment(horizontal='center', wrap_text=True)
    
    for row, grade_data in enumerate(analytics_data['by_grade'], 5):
        ws_by_grade.cell(row=row, column=1).value = grade_data['grade']
        ws_by_grade.cell(row=row, column=2).value = grade_data['total_in_db']
        ws_by_grade.cell(row=row, column=3).value = grade_data['percentage_of_db']
        ws_by_grade.cell(row=row, column=3).number_format = '0.00'
        ws_by_grade.cell(row=row, column=4).value = grade_data['total_customers']
        ws_by_grade.cell(row=row, column=5).value = grade_data['active_rate']
        ws_by_grade.cell(row=row, column=5).number_format = '0.00'
        ws_by_grade.cell(row=row, column=6).value = grade_data['returning_customers']
        ws_by_grade.cell(row=row, column=7).value = grade_data['return_rate']
        ws_by_grade.cell(row=row, column=7).number_format = '0.00'
    
    column_widths = [15, 13, 10, 15, 12, 12, 15]
    for idx, width in enumerate(column_widths, 1):
        ws_by_grade.column_dimensions[get_column_letter(idx)].width = width
    
    # === CUSTOMER DETAILS SHEET ===
    ws_details['A1'] = 'Customer Return Visit Details'
    ws_details['A1'].font = title_font
    
    detail_headers = ['VIP ID', 'Name', 'VIP Grade', 'Registration Date', 
                      'First Purchase', 'Total Purchases', 'Return Visits', 'Total Spent']
    for col, header in enumerate(detail_headers, 1):
        cell = ws_details.cell(row=3, column=col)
        cell.value = header
        cell.font = header_font
        cell.fill = header_fill
        cell.alignment = Alignment(horizontal='center')
    
    for row, customer in enumerate(analytics_data['customer_details'], 4):
        ws_details.cell(row=row, column=1).value = customer['vip_id']
        ws_details.cell(row=row, column=2).value = customer['name']
        ws_details.cell(row=row, column=3).value = customer['vip_grade']
        ws_details.cell(row=row, column=4).value = customer['registration_date']
        ws_details.cell(row=row, column=5).value = customer['first_purchase_date']
        ws_details.cell(row=row, column=6).value = customer['total_purchases']
        ws_details.cell(row=row, column=7).value = customer['return_visits']
        ws_details.cell(row=row, column=8).value = float(customer['total_spent'])
        ws_details.cell(row=row, column=8).number_format = '#,##0.00'
    
    # Column widths for details
    column_widths = [15, 25, 15, 18, 18, 16, 14, 16]
    for idx, width in enumerate(column_widths, 1):
        ws_details.column_dimensions[get_column_letter(idx)].width = width
    
    return wb