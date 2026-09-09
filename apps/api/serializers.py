from rest_framework import serializers

from apps.catalog.models import Country, Plan, Region
from apps.orders.models import Esim, Order


class PlanSerializer(serializers.ModelSerializer):
    price = serializers.DecimalField(max_digits=10, decimal_places=2, read_only=True)
    data_label = serializers.CharField(read_only=True)
    title = serializers.CharField(read_only=True)
    per_gb_usd = serializers.DecimalField(max_digits=10, decimal_places=2, read_only=True)
    target_name = serializers.CharField(read_only=True)

    class Meta:
        model = Plan
        fields = ("id", "title", "target_name", "kind", "data_label", "data_gb",
                  "is_unlimited", "days", "price", "compare_at_usd", "per_gb_usd",
                  "badge", "operators", "apn")


class CountrySerializer(serializers.ModelSerializer):
    flag_emoji = serializers.CharField(read_only=True)

    class Meta:
        model = Country
        fields = ("iso2", "iso3", "name", "slug", "flag_url", "flag_emoji", "continent",
                  "is_popular", "min_price_usd", "plan_count", "has_unlimited")


class RegionSerializer(serializers.ModelSerializer):
    country_count = serializers.IntegerField(read_only=True)

    class Meta:
        model = Region
        fields = ("id", "name", "slug", "icon", "description", "country_count",
                  "min_price_usd", "plan_count", "has_unlimited")


class EsimSerializer(serializers.ModelSerializer):
    display_name = serializers.CharField(read_only=True)
    data_used_pct = serializers.IntegerField(read_only=True)
    data_left_gb = serializers.FloatField(read_only=True)
    data_package_gb = serializers.FloatField(read_only=True)
    days_left = serializers.IntegerField(read_only=True)
    is_active = serializers.BooleanField(read_only=True)
    android_manual = serializers.DictField(read_only=True)

    class Meta:
        model = Esim
        fields = ("id", "iccid", "display_name", "label", "plan_title", "status_qr",
                  "lpa_code", "ios_tap_link", "apn", "android_manual",
                  "is_unlimited", "data_package_mb", "data_used_mb", "data_left_mb",
                  "data_package_gb", "data_left_gb", "data_used_pct",
                  "plan_activated_at", "plan_expires_at", "days_left", "is_active",
                  "network_info", "created_at")


class OrderSerializer(serializers.ModelSerializer):
    class Meta:
        model = Order
        fields = ("ref", "status", "kind", "plan_title", "plan_data_label", "plan_days",
                  "amount_usd", "currency", "created_at", "completed_at")
