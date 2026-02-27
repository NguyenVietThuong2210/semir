"""
App/cnv_sync/models.py

UPDATED: CNVCustomer model based on actual API response format
Includes membership level and points tracking

Changes:
- id: Auto-increment primary key (database internal)
- cnv_id: Customer ID from CNV API (unique)
"""
from django.db import models
from django.utils import timezone


class CNVCustomer(models.Model):
    """
    Synced customer data from CNV Loyalty API.
    Based on actual API response format from /loyalty/customers/{id}.json
    """
    # Database primary key (auto-increment)
    id = models.AutoField(primary_key=True)
    
    # CNV identifier (from API 'id' field)
    cnv_id = models.BigIntegerField(unique=True, db_index=True)
    
    # Basic info from customer endpoint
    last_name = models.CharField(max_length=255, null=True, blank=True)
    first_name = models.CharField(max_length=255, null=True, blank=True)
    phone = models.CharField(max_length=50, null=True, blank=True, db_index=True)
    email = models.EmailField(max_length=255, null=True, blank=True)
    gender = models.CharField(max_length=20, null=True, blank=True)
    
    # Birthday fields
    birthday_day = models.IntegerField(null=True, blank=True)
    birthday_month = models.IntegerField(null=True, blank=True)
    birthday_year = models.IntegerField(null=True, blank=True)
    
    # Tags and physical card
    tags = models.TextField(null=True, blank=True)
    physical_card_code = models.CharField(max_length=100, null=True, blank=True)
    
    # Points from customer endpoint
    points = models.DecimalField(max_digits=15, decimal_places=2, default=0)
    exp_points = models.DecimalField(max_digits=15, decimal_places=2, default=0)
    total_spending = models.DecimalField(max_digits=15, decimal_places=2, default=0)
    total_points = models.DecimalField(max_digits=15, decimal_places=2, default=0)
    
    # Membership info from /membership.json endpoint
    level_name = models.CharField(max_length=50, null=True, blank=True, db_index=True)
    used_points = models.DecimalField(max_digits=15, decimal_places=2, default=0)
    
    # Dates (renamed to avoid confusion)
    cnv_created_at = models.DateTimeField(null=True, blank=True)
    cnv_updated_at = models.DateTimeField(null=True, blank=True)
    
    # Internal tracking
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    last_synced_at = models.DateTimeField(default=timezone.now)
    
    class Meta:
        db_table = 'cnv_customers'
        verbose_name = 'CNV Customer'
        verbose_name_plural = 'CNV Customers'
        ordering = ['-last_synced_at']
        indexes = [
            models.Index(fields=['cnv_id']),
            models.Index(fields=['phone']),
            models.Index(fields=['level_name']),
            models.Index(fields=['-last_synced_at']),
            models.Index(fields=['-cnv_updated_at']),
        ]
    
    def __str__(self):
        full_name = f"{self.last_name or ''} {self.first_name or ''}".strip()
        return f"CNV#{self.cnv_id} - {full_name or self.phone or 'N/A'}"
    
    @property
    def full_name(self):
        """Convenience property for full name"""
        return f"{self.last_name or ''} {self.first_name or ''}".strip() or None
    
    @property
    def registration_date(self):
        """Alias for cnv_created_at to maintain compatibility"""
        return self.cnv_created_at


class CNVOrder(models.Model):
    """
    Synced order data from CNV Loyalty.
    Primary key: order_code from CNV
    """
    # CNV identifiers
    order_code = models.CharField(max_length=100, primary_key=True)
    order_id = models.CharField(max_length=100, null=True, blank=True, db_index=True)
    
    # Customer reference
    customer_code = models.CharField(max_length=100, db_index=True)
    customer_name = models.CharField(max_length=255, null=True, blank=True)
    customer_phone = models.CharField(max_length=50, null=True, blank=True)
    
    # Order info
    order_date = models.DateTimeField(db_index=True)
    order_status = models.CharField(max_length=50, null=True, blank=True)
    payment_status = models.CharField(max_length=50, null=True, blank=True)
    payment_method = models.CharField(max_length=100, null=True, blank=True)
    
    # Store info
    store_code = models.CharField(max_length=100, null=True, blank=True, db_index=True)
    store_name = models.CharField(max_length=255, null=True, blank=True)
    
    # Amounts
    subtotal = models.DecimalField(max_digits=15, decimal_places=2, default=0)
    discount_amount = models.DecimalField(max_digits=15, decimal_places=2, default=0)
    tax_amount = models.DecimalField(max_digits=15, decimal_places=2, default=0)
    shipping_fee = models.DecimalField(max_digits=15, decimal_places=2, default=0)
    total_amount = models.DecimalField(max_digits=15, decimal_places=2, default=0)
    
    # Points
    points_earned = models.IntegerField(default=0)
    points_used = models.IntegerField(default=0)
    
    # Items
    items = models.JSONField(null=True, blank=True)
    notes = models.TextField(null=True, blank=True)
    
    # Metadata
    raw_data = models.JSONField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    last_synced_at = models.DateTimeField(default=timezone.now)
    
    class Meta:
        db_table = 'cnv_orders'
        verbose_name = 'CNV Order'
        verbose_name_plural = 'CNV Orders'
        ordering = ['-order_date']
        indexes = [
            models.Index(fields=['-order_date']),
            models.Index(fields=['customer_code', '-order_date']),
            models.Index(fields=['store_code', '-order_date']),
        ]
    
    def __str__(self):
        return f"{self.order_code} - {self.customer_name or 'N/A'} - {self.total_amount}"


class CNVSyncLog(models.Model):
    """
    Track sync operations for monitoring and debugging.
    """
    SYNC_TYPE_CHOICES = [
        ('customers', 'Customers'),
        ('orders', 'Orders'),
        ('full', 'Full Sync'),
    ]
    
    STATUS_CHOICES = [
        ('running', 'Running'),
        ('completed', 'Completed'),
        ('failed', 'Failed'),
    ]
    
    sync_type = models.CharField(max_length=20, choices=SYNC_TYPE_CHOICES)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='running')
    
    started_at = models.DateTimeField(auto_now_add=True)
    completed_at = models.DateTimeField(null=True, blank=True)
    
    # Checkpoint for incremental sync
    checkpoint_updated_at = models.DateTimeField(
        null=True,
        blank=True,
        help_text="Latest updated_at from fetched records - used as starting point for next sync"
    )
    
    # Counters
    total_records = models.IntegerField(default=0)
    created_count = models.IntegerField(default=0)
    updated_count = models.IntegerField(default=0)
    failed_count = models.IntegerField(default=0)
    
    # Error tracking
    error_message = models.TextField(null=True, blank=True)
    error_details = models.JSONField(null=True, blank=True)
    
    class Meta:
        db_table = 'cnv_sync_logs'
        verbose_name = 'CNV Sync Log'
        verbose_name_plural = 'CNV Sync Logs'
        ordering = ['-started_at']
        indexes = [
            models.Index(fields=['sync_type', 'status']),
            models.Index(fields=['-started_at']),
            models.Index(fields=['sync_type', '-checkpoint_updated_at']),
        ]
    
    def __str__(self):
        return f"{self.sync_type} - {self.status} - {self.started_at}"
    
    def mark_completed(self):
        self.status = 'completed'
        self.completed_at = timezone.now()
        self.save()
    
    def mark_failed(self, error_msg):
        self.status = 'failed'
        self.completed_at = timezone.now()
        self.error_message = error_msg
        self.save()