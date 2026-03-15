from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("App", "0009_add_coupon_campaign"),
    ]

    operations = [
        migrations.AlterField(
            model_name="couponcampaign",
            name="prefix",
            field=models.TextField(),
        ),
    ]
