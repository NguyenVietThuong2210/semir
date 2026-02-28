from django.db import models
from django.core.validators import EmailValidator


class Customer(models.Model):
    vip_id = models.CharField(max_length=1000, db_index=True)
    id_number = models.CharField(max_length=1000, blank=True, null=True)
    birthday_month = models.IntegerField(blank=True, null=True)
    vip_grade = models.CharField(max_length=1000, blank=True, null=True)
    name = models.CharField(max_length=1000)
    phone = models.CharField(max_length=1000, db_index=True)
    race = models.CharField(max_length=1000, blank=True, null=True)
    gender = models.CharField(max_length=1000, blank=True, null=True)
    birthday = models.DateField(blank=True, null=True)
    city_state = models.CharField(max_length=1000, blank=True, null=True)
    postal_code = models.CharField(max_length=1000, blank=True, null=True)
    country = models.CharField(max_length=1000, blank=True, null=True)
    email = models.EmailField(validators=[EmailValidator()], blank=True, null=True)
    contact_address = models.TextField(blank=True, null=True)
    registration_store = models.CharField(max_length=1000, blank=True, null=True)
    registration_date = models.DateField(blank=True, null=True)
    points = models.IntegerField(default=0)
    used_points = models.IntegerField(default=0, null=True, blank=True)
    used_points_note = models.TextField(blank=True, null=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        unique_together = ('vip_id', 'phone')
        indexes = [
            models.Index(fields=['vip_id', 'phone']),
            models.Index(fields=['registration_date']),
        ]

    def __str__(self):
        return f"{self.name} ({self.vip_id})"


class SalesTransaction(models.Model):
    invoice_number = models.CharField(max_length=1000, unique=True, db_index=True)
    shop_id = models.CharField(max_length=1000)
    shop_name = models.CharField(max_length=1000)
    country = models.CharField(max_length=1000)
    bu = models.CharField(max_length=1000, blank=True, null=True)
    sales_date = models.DateField(db_index=True)
    vip_id = models.CharField(max_length=1000, db_index=True)
    vip_name = models.CharField(max_length=1000)
    quantity = models.IntegerField()
    settlement_amount = models.DecimalField(max_digits=12, decimal_places=2)
    sales_amount = models.DecimalField(max_digits=12, decimal_places=2)
    tag_amount = models.DecimalField(max_digits=12, decimal_places=2, blank=True, null=True)
    per_customer_transaction = models.DecimalField(max_digits=12, decimal_places=2, blank=True, null=True)
    discount = models.DecimalField(max_digits=12, decimal_places=2, blank=True, null=True)
    rounding = models.DecimalField(max_digits=12, decimal_places=2, blank=True, null=True)
    customer = models.ForeignKey(Customer, on_delete=models.SET_NULL, null=True, blank=True, related_name='transactions')
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['sales_date', 'invoice_number']
        indexes = [
            models.Index(fields=['vip_id', 'sales_date']),
            models.Index(fields=['sales_date']),
        ]

    def __str__(self):
        return f"{self.invoice_number} - {self.vip_name}"


class Coupon(models.Model):
    department      = models.CharField(max_length=1000, blank=True, null=True)
    creator         = models.CharField(max_length=1000, blank=True, null=True)
    document_number = models.CharField(max_length=1000, blank=True, null=True)
    coupon_id       = models.CharField(max_length=1000, db_index=True)
    face_value      = models.DecimalField(max_digits=12, decimal_places=2, blank=True, null=True)
    used            = models.IntegerField(default=0)   # 0=unused, 1=used
    begin_date      = models.DateField(blank=True, null=True)
    end_date        = models.DateField(blank=True, null=True)
    using_shop      = models.CharField(max_length=1000, blank=True, null=True)
    using_date      = models.DateField(blank=True, null=True)
    push            = models.CharField(max_length=1000, blank=True, null=True)
    member_id       = models.CharField(max_length=1000, blank=True, null=True)
    member_name     = models.CharField(max_length=1000, blank=True, null=True)
    member_phone    = models.CharField(max_length=1000, blank=True, null=True)
    docket_number   = models.CharField(max_length=1000, blank=True, null=True, db_index=True)
    created_at      = models.DateTimeField(auto_now_add=True)
    updated_at      = models.DateTimeField(auto_now=True)

    class Meta:
        indexes = [
            models.Index(fields=['coupon_id']),
            models.Index(fields=['docket_number']),
            models.Index(fields=['using_date']),
            models.Index(fields=['used']),
        ]

    def __str__(self):
        return f"{self.coupon_id} ({'Used' if self.used else 'Unused'})"