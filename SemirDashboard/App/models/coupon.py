from django.db import models


class Coupon(models.Model):
    department = models.CharField(max_length=1000, blank=True, null=True)
    creator = models.CharField(max_length=1000, blank=True, null=True)
    document_number = models.CharField(max_length=1000, blank=True, null=True)
    coupon_id = models.CharField(max_length=1000, db_index=True)
    face_value = models.DecimalField(
        max_digits=12, decimal_places=2, blank=True, null=True
    )
    used = models.IntegerField(default=0)  # 0=unused, 1=used
    begin_date = models.DateField(blank=True, null=True)
    end_date = models.DateField(blank=True, null=True)
    using_shop = models.CharField(max_length=1000, blank=True, null=True)
    using_date = models.DateField(blank=True, null=True)
    push = models.CharField(max_length=1000, blank=True, null=True)
    member_id = models.CharField(max_length=1000, blank=True, null=True)
    member_name = models.CharField(max_length=1000, blank=True, null=True)
    member_phone = models.CharField(max_length=1000, blank=True, null=True)
    docket_number = models.CharField(
        max_length=1000, blank=True, null=True, db_index=True
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        indexes = [
            models.Index(fields=["coupon_id"]),
            models.Index(fields=["docket_number"]),
            models.Index(fields=["using_date"]),
            models.Index(fields=["used"]),
        ]

    def __str__(self):
        return f"{self.coupon_id} ({'Used' if self.used else 'Unused'})"


class CouponCampaign(models.Model):
    """Named coupon campaign grouping coupons by ID prefix."""

    name = models.CharField(max_length=200, unique=True)
    prefix = models.TextField()          # comma-separated prefixes, e.g. "ABC,DEF,XYZ"
    detail = models.TextField(blank=True, null=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["name"]

    def __str__(self):
        return f"{self.name} ({self.prefix})"
