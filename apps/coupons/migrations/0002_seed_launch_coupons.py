"""Launch coupons.

Written by hand and kept idempotent (get_or_create on the code) so it is safe on
a database that already has these codes -- for example one seeded by hand before
this migration existed.

The descriptions are plain English rather than translated strings on purpose:
they are campaign copy that operators rewrite from the admin, so they belong in
the database with the rest of the coupon, not in a .po file that the first edit
would make a lie. The coupons page marks them with their source language instead
of passing them off as translated (see apps/coupons/views.coupons_page).
"""
from decimal import Decimal

from django.db import migrations

SEEDS = [
    {
        "code": "BORDERLESS20",
        "description": "20 percent off the normal price on any plan of $9.99 or more. "
                       "Our standing traveller discount.",
        "percent_off": 20,
        "min_order_usd": Decimal("9.99"),
        # A cap keeps a 20 percent code from swallowing the margin on a long
        # unlimited plan; it is printed on the coupon card, never hidden.
        "max_discount_usd": Decimal("12.00"),
        "once_per_customer": True,
        "is_public": True,
    },
    {
        "code": "WELCOME10",
        "description": "10 percent off your first eSIM, any destination, any plan.",
        "percent_off": 10,
        "first_order_only": True,
        "once_per_customer": True,
        "is_public": True,
    },
    {
        "code": "CRYPTO5",
        "description": "5 percent off any plan. A thank-you to everyone who pays in crypto "
                       "and keeps card fees out of the price.",
        "percent_off": 5,
        # Deliberately repeatable: this is an ongoing perk, not a one-off hook.
        "once_per_customer": False,
        "is_public": True,
    },
]


def seed(apps, schema_editor):
    Coupon = apps.get_model("coupons", "Coupon")
    for row in SEEDS:
        code = row["code"]
        Coupon.objects.get_or_create(code=code, defaults={k: v for k, v in row.items() if k != "code"})


def unseed(apps, schema_editor):
    Coupon = apps.get_model("coupons", "Coupon")
    # Only remove codes nobody has spent: rolling a migration back must not erase
    # the record of a discount a customer was actually given.
    (Coupon.objects
     .filter(code__in=[row["code"] for row in SEEDS], redemptions=0, uses__isnull=True)
     .delete())


class Migration(migrations.Migration):

    dependencies = [
        ("coupons", "0001_initial"),
    ]

    operations = [
        migrations.RunPython(seed, unseed),
    ]
