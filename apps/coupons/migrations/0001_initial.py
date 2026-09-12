# Hand-written to match apps/coupons/models.py.
import decimal

import django.core.validators
import django.db.models.deletion
from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):

    initial = True

    dependencies = [
        ("orders", "0001_initial"),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.CreateModel(
            name="Coupon",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("code", models.CharField(max_length=32, unique=True, verbose_name="code")),
                ("description", models.CharField(blank=True, help_text="Shown on the public coupons page. One plain sentence.", max_length=180, verbose_name="description")),
                ("percent_off", models.PositiveSmallIntegerField(blank=True, null=True, validators=[django.core.validators.MinValueValidator(1), django.core.validators.MaxValueValidator(90)], verbose_name="percent off")),
                ("amount_off_usd", models.DecimalField(blank=True, decimal_places=2, max_digits=8, null=True, verbose_name="fixed amount off (USD)")),
                ("applies_to", models.CharField(choices=[("all", "Any plan"), ("country_plans", "Country plans only"), ("region_plans", "Regional plans only"), ("unlimited_only", "Unlimited plans only")], default="all", max_length=20, verbose_name="applies to")),
                ("min_order_usd", models.DecimalField(decimal_places=2, default=decimal.Decimal("0.00"), max_digits=8, verbose_name="minimum order (USD)")),
                ("max_discount_usd", models.DecimalField(blank=True, decimal_places=2, help_text="Caps a percentage coupon so a large order cannot run away with it.", max_digits=8, null=True, verbose_name="maximum discount (USD)")),
                ("valid_from", models.DateTimeField(blank=True, null=True, verbose_name="valid from")),
                ("valid_until", models.DateTimeField(blank=True, help_text="Leave empty for a code with no end date.", null=True, verbose_name="valid until")),
                ("max_redemptions", models.PositiveIntegerField(blank=True, help_text="Leave empty for unlimited redemptions.", null=True, verbose_name="redemption limit")),
                ("redemptions", models.PositiveIntegerField(default=0, editable=False, verbose_name="redemptions used")),
                ("once_per_customer", models.BooleanField(default=True, verbose_name="once per customer")),
                ("first_order_only", models.BooleanField(default=False, verbose_name="first order only")),
                ("is_active", models.BooleanField(db_index=True, default=True, verbose_name="active")),
                ("is_public", models.BooleanField(db_index=True, default=False, help_text="Public codes appear on the coupons page. Leave off for private codes.", verbose_name="listed publicly")),
                ("stackable", models.BooleanField(default=False, help_text="Reserved: checkout accepts one code per order.", verbose_name="stackable")),
                ("created_at", models.DateTimeField(auto_now_add=True, verbose_name="created")),
                ("updated_at", models.DateTimeField(auto_now=True, verbose_name="updated")),
            ],
            options={
                "verbose_name": "coupon",
                "verbose_name_plural": "coupons",
                "ordering": ("-is_public", "code"),
            },
        ),
        migrations.CreateModel(
            name="CouponRedemption",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("email", models.EmailField(blank=True, max_length=254, verbose_name="email")),
                ("ip", models.GenericIPAddressField(blank=True, null=True, verbose_name="IP address")),
                ("discount_usd", models.DecimalField(decimal_places=2, default=decimal.Decimal("0.00"), max_digits=8, verbose_name="discount (USD)")),
                ("created_at", models.DateTimeField(auto_now_add=True, db_index=True, verbose_name="redeemed")),
                ("coupon", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="uses", to="coupons.coupon", verbose_name="coupon")),
                ("order", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name="coupon_redemptions", to="orders.order", verbose_name="order")),
                ("user", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name="coupon_redemptions", to=settings.AUTH_USER_MODEL, verbose_name="account")),
            ],
            options={
                "verbose_name": "coupon redemption",
                "verbose_name_plural": "coupon redemptions",
                "ordering": ("-created_at",),
            },
        ),
        migrations.AddIndex(
            model_name="coupon",
            index=models.Index(fields=["is_active", "is_public"], name="coupon_live_idx"),
        ),
        migrations.AddConstraint(
            model_name="coupon",
            constraint=models.CheckConstraint(
                condition=models.Q(
                    models.Q(("amount_off_usd__isnull", True), ("percent_off__isnull", False)),
                    models.Q(("amount_off_usd__isnull", False), ("percent_off__isnull", True)),
                    _connector="OR",
                ),
                name="coupon_one_discount_kind",
                violation_error_message="Set either a percentage or a fixed amount, not both and not neither.",
            ),
        ),
        migrations.AddConstraint(
            model_name="coupon",
            constraint=models.CheckConstraint(
                condition=models.Q(
                    ("percent_off__isnull", True),
                    models.Q(("percent_off__gte", 1), ("percent_off__lte", 90)),
                    _connector="OR",
                ),
                name="coupon_percent_range",
                violation_error_message="A percentage coupon must be between 1 and 90.",
            ),
        ),
        migrations.AddConstraint(
            model_name="coupon",
            constraint=models.CheckConstraint(
                condition=models.Q(("amount_off_usd__isnull", True), ("amount_off_usd__gt", 0), _connector="OR"),
                name="coupon_amount_positive",
                violation_error_message="A fixed discount must be more than zero.",
            ),
        ),
        migrations.AddIndex(
            model_name="couponredemption",
            index=models.Index(fields=["coupon", "email"], name="couponuse_email_idx"),
        ),
        migrations.AddIndex(
            model_name="couponredemption",
            index=models.Index(fields=["coupon", "-created_at"], name="couponuse_recent_idx"),
        ),
        migrations.AddConstraint(
            model_name="couponredemption",
            constraint=models.UniqueConstraint(fields=("coupon", "order"), name="coupon_once_per_order"),
        ),
    ]
