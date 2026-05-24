from django.contrib import admin
from .models import Customer, SalesTransaction, SaleDetail, InventorySnapshot


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


@admin.register(SaleDetail)
class SaleDetailAdmin(admin.ModelAdmin):
    list_display = ('invoice_number', 'product_name', 'brand', 'sales_date', 'shop_name', 'quantity', 'sales_amount')
    list_filter = ('brand', 'sales_date', 'shop_name', 'season', 'year')
    search_fields = ('invoice_number', 'product_code', 'barcode', 'salesmen')
    date_hierarchy = 'sales_date'
    ordering = ('-sales_date',)
    raw_id_fields = ('transaction',)


@admin.register(InventorySnapshot)
class InventorySnapshotAdmin(admin.ModelAdmin):
    list_display = ('shop_name', 'brand', 'product_code', 'product_name', 'inventory_qty', 'total_qty', 'uploaded_at')
    list_filter = ('brand', 'shop_name', 'year', 'season', 'category_l1')
    search_fields = ('product_code', 'product_name', 'barcode', 'sku')
    ordering = ('-uploaded_at', 'shop_name')