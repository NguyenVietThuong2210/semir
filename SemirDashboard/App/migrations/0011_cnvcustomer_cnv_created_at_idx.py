"""Add index on CNVCustomer.cnv_created_at (used in date-range filters on customer analytics page)."""
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("App", "0010_alter_couponcampaign_prefix"),
    ]

    operations = [
        migrations.AddIndex(
            model_name="cnvcustomer",
            index=models.Index(fields=["cnv_created_at"], name="cnv_customer_created_idx"),
        ),
    ]
