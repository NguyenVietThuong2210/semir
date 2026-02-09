from django.contrib import admin
from .models import Customer, SalesTransaction


@admin.register(Customer)
class CustomerAdmin(admin.ModelAdmin):
    list_display = ('vip_id', 'name', 'phone', 'vip_grade', 'registration_date', 'points')
    list_filter = ('vip_grade', 'gender', 'country', 'registration_date')
    search_fields = ('vip_id', 'name', 'phone', 'email')
    date_hierarchy = 'registration_date'
    ordering = ('-registration_date',)


@admin.register(SalesTransaction)
class SalesTransactionAdmin(admin.ModelAdmin):
    list_display = ('invoice_number', 'vip_name', 'sales_date', 'sales_amount', 'shop_name', 'country')
    list_filter = ('sales_date', 'country', 'shop_name')
    search_fields = ('invoice_number', 'vip_id', 'vip_name')
    date_hierarchy = 'sales_date'
    ordering = ('-sales_date',)
    raw_id_fields = ('customer',)