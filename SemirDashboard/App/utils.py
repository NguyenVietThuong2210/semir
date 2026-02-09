import pandas as pd
from datetime import datetime
from decimal import Decimal
from django.db import transaction
from .models import Customer, SalesTransaction


def read_file(file):
    """Read CSV or Excel file and return DataFrame"""
    if file.name.endswith('.csv'):
        return pd.read_csv(file)
    else:
        return pd.read_excel(file)


def parse_date(date_value):
    """Parse date from various formats"""
    if pd.isna(date_value):
        return None
    
    if isinstance(date_value, datetime):
        return date_value.date()
    
    try:
        return pd.to_datetime(date_value).date()
    except:
        return None


def safe_decimal(value, default=0):
    """Safely convert value to Decimal"""
    if pd.isna(value):
        return Decimal(default)
    try:
        return Decimal(str(value))
    except:
        return Decimal(default)


def safe_int(value, default=0):
    """Safely convert value to int"""
    if pd.isna(value):
        return default
    try:
        return int(value)
    except:
        return default


def safe_str(value):
    """Safely convert value to string"""
    if pd.isna(value):
        return ''
    return str(value).strip()


@transaction.atomic
def process_customer_file(file):
    """Process customer data file and save to database"""
    df = read_file(file)
    
    # Normalize column names
    df.columns = df.columns.str.strip().str.upper()
    
    created_count = 0
    updated_count = 0
    errors = []
    
    for idx, row in df.iterrows():
        try:
            vip_id = safe_str(row.get('VIP ID', ''))
            phone = safe_str(row.get('PHONE NO.', ''))
            
            if not vip_id or not phone:
                errors.append(f"Row {idx + 2}: Missing VIP ID or Phone")
                continue
            
            customer_data = {
                'vip_id': vip_id,
                'phone': phone,
                'id_number': safe_str(row.get('ID', '')),
                'birthday_month': safe_int(row.get('BIRTHDAY MONTH')),
                'vip_grade': safe_str(row.get('VIP GRADE', '')),
                'name': safe_str(row.get('NAME', '')),
                'race': safe_str(row.get('RACE', '')),
                'gender': safe_str(row.get('GENDER', '')),
                'birthday': parse_date(row.get('BIRTHDAY')),
                'city_state': safe_str(row.get('CITY/STATE', '')),
                'postal_code': safe_str(row.get('POSTAL CODE', '')),
                'country': safe_str(row.get('COUNTRY', '')),
                'email': safe_str(row.get('EMAIL', '')),
                'contact_address': safe_str(row.get('CONTACT ADDRESS', '')),
                'registration_store': safe_str(row.get('REGISTRATION STORE', '')),
                'registration_date': parse_date(row.get('REGISTRATION DATE')),
                'points': safe_int(row.get('POINTS', 0))
            }
            
            # Update or create customer
            customer, created = Customer.objects.update_or_create(
                vip_id=vip_id,
                phone=phone,
                defaults=customer_data
            )
            
            if created:
                created_count += 1
            else:
                updated_count += 1
                
        except Exception as e:
            errors.append(f"Row {idx + 2}: {str(e)}")
    
    return {
        'created': created_count,
        'updated': updated_count,
        'errors': errors,
        'total_processed': created_count + updated_count
    }


@transaction.atomic
def process_sales_file(file):
    """Process sales data file and save to database"""
    df = read_file(file)
    
    # Normalize column names
    df.columns = df.columns.str.strip().str.upper()
    
    created_count = 0
    skipped_count = 0
    errors = []
    
    for idx, row in df.iterrows():
        try:
            invoice_number = safe_str(row.get('INVOICE NUMBER', ''))
            
            if not invoice_number:
                errors.append(f"Row {idx + 2}: Missing Invoice Number")
                continue
            
            # Check if invoice already exists
            if SalesTransaction.objects.filter(invoice_number=invoice_number).exists():
                skipped_count += 1
                continue
            
            vip_id = safe_str(row.get('VIP ID', ''))
            
            # Try to find customer
            customer = None
            if vip_id:
                customer = Customer.objects.filter(vip_id=vip_id).first()
            
            sales_data = {
                'invoice_number': invoice_number,
                'shop_id': safe_str(row.get('SHOP ID', '')),
                'shop_name': safe_str(row.get('SHOP NAME', '')),
                'country': safe_str(row.get('COUNTRY', '')),
                'bu': safe_str(row.get('BU', '')),
                'sales_date': parse_date(row.get('SALES DATE')),
                'vip_id': vip_id,
                'vip_name': safe_str(row.get('VIP NAME', '')),
                'quantity': safe_int(row.get('QUANTITY', 0)),
                'settlement_amount': safe_decimal(row.get('SETTLEMENT AMOUNT', 0)),
                'sales_amount': safe_decimal(row.get('SALES AMOUNT', 0)),
                'tag_amount': safe_decimal(row.get('TAG AMOUNT', 0)),
                'per_customer_transaction': safe_decimal(row.get('PER CUSTOMER TRANSACTION', 0)),
                'discount': safe_decimal(row.get('DISCOUNT', 0)),
                'rounding': safe_decimal(row.get('ROUNDING', 0)),
                'customer': customer
            }
            
            SalesTransaction.objects.create(**sales_data)
            created_count += 1
                
        except Exception as e:
            errors.append(f"Row {idx + 2}: {str(e)}")
    
    return {
        'created': created_count,
        'skipped': skipped_count,
        'errors': errors
    }