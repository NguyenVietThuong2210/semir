# Perf plan P1-10/P1-11: plain btree operations, identical and safe on every
# backend (SQLite dev and PostgreSQL prod) — no vendor conditioning needed.
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('App', '0019_coupon_id_unique'),
    ]

    operations = [
        # P1-11: coupon_id already has unique=True (migration 0019), which
        # creates its own unique index — this explicit one was a duplicate
        # since day 1 (migration 0002 created both on the same column).
        migrations.RemoveIndex(
            model_name='coupon',
            name='App_coupon_coupon__7e6b3d_idx',
        ),
        # P1-10: Shop Detail coupon tab filters using_shop + using_date
        # together on every AJAX partial load.
        migrations.AddIndex(
            model_name='coupon',
            index=models.Index(fields=['using_shop', 'using_date'], name='coupon_usingshop_usingdate_idx'),
        ),
    ]
