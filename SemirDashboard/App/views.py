from django.shortcuts import render, redirect
from django.contrib import messages
from django.http import HttpResponse
from datetime import datetime
from .forms import CustomerUploadForm, SalesUploadForm
from .utils import process_customer_file, process_sales_file
from .analytics import calculate_return_rate_analytics, export_analytics_to_excel


def home(request):
    """Home page with navigation"""
    return render(request, 'home.html')


def upload_customers(request):
    """Upload customer data"""
    if request.method == 'POST':
        form = CustomerUploadForm(request.POST, request.FILES)
        if form.is_valid():
            file = request.FILES['file']
            
            try:
                result = process_customer_file(file)
                
                messages.success(
                    request,
                    f'Successfully processed {result["total_processed"]} customers. '
                    f'Created: {result["created"]}, Updated: {result["updated"]}'
                )
                
                if result['errors']:
                    for error in result['errors'][:5]:  # Show first 5 errors
                        messages.warning(request, error)
                    if len(result['errors']) > 5:
                        messages.warning(request, f'...and {len(result["errors"]) - 5} more errors')
                
                return redirect('upload_customers')
                
            except Exception as e:
                messages.error(request, f'Error processing file: {str(e)}')
    else:
        form = CustomerUploadForm()
    
    return render(request, 'upload_customers.html', {'form': form})


def upload_sales(request):
    """Upload sales data"""
    if request.method == 'POST':
        form = SalesUploadForm(request.POST, request.FILES)
        if form.is_valid():
            file = request.FILES['file']
            
            try:
                result = process_sales_file(file)
                
                messages.success(
                    request,
                    f'Successfully imported {result["created"]} sales transactions. '
                    f'Skipped {result["skipped"]} duplicates.'
                )
                
                if result['errors']:
                    for error in result['errors'][:5]:
                        messages.warning(request, error)
                    if len(result['errors']) > 5:
                        messages.warning(request, f'...and {len(result["errors"]) - 5} more errors')
                
                return redirect('analytics_dashboard')
                
            except Exception as e:
                messages.error(request, f'Error processing file: {str(e)}')
    else:
        form = SalesUploadForm()
    
    return render(request, 'upload_sales.html', {'form': form})


def analytics_dashboard(request):
    """Display return rate analytics dashboard"""
    analytics_data = calculate_return_rate_analytics()
    
    if not analytics_data:
        messages.info(request, 'No sales data available. Please upload sales data first.')
        return redirect('upload_sales')
    
    context = {
        'analytics': analytics_data,
        'date_range': analytics_data['date_range'],
        'overview': analytics_data['overview'],
        'grade_stats': analytics_data['by_grade'],
        'customer_details': analytics_data['customer_details'][:100],  # Limit display to first 100
        'total_detail_count': len(analytics_data['customer_details'])
    }
    
    return render(request, 'analytics_dashboard.html', context)


def export_analytics(request):
    """Export analytics to Excel file"""
    analytics_data = calculate_return_rate_analytics()
    
    if not analytics_data:
        messages.error(request, 'No data available to export')
        return redirect('analytics_dashboard')
    
    try:
        wb = export_analytics_to_excel(analytics_data)
        
        # Create response
        response = HttpResponse(
            content_type='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'
        )
        
        filename = f'return_rate_analysis_{datetime.now().strftime("%Y%m%d_%H%M%S")}.xlsx'
        response['Content-Disposition'] = f'attachment; filename="{filename}"'
        
        wb.save(response)
        return response
        
    except Exception as e:
        messages.error(request, f'Error exporting data: {str(e)}')
        return redirect('analytics_dashboard')