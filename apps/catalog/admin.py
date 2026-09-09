from django.contrib import admin
from django.utils.html import format_html

from .models import Country, Device, Plan, Region


class PlanInline(admin.TabularInline):
    model = Plan
    extra = 0
    fields = ("provider_name", "data_gb", "is_unlimited", "days", "cost_amount",
              "price_usd", "price_override_usd", "badge", "is_active", "provider_active")
    readonly_fields = ("provider_name", "data_gb", "is_unlimited", "days", "cost_amount",
                       "price_usd", "provider_active")
    show_change_link = True
    can_delete = False

    def has_add_permission(self, request, obj=None):
        return False


@admin.register(Country)
class CountryAdmin(admin.ModelAdmin):
    list_display = ("name", "iso2", "continent", "plan_count", "min_price_usd",
                    "has_unlimited", "is_popular", "is_active")
    list_filter = ("continent", "is_popular", "is_active", "has_unlimited")
    list_editable = ("is_popular", "is_active")
    search_fields = ("name", "iso2", "iso3", "slug")
    prepopulated_fields = {"slug": ("name",)}
    readonly_fields = ("plan_count", "min_price_usd", "has_unlimited", "created_at", "updated_at")
    inlines = [PlanInline]
    fieldsets = (
        (None, {"fields": ("name", "slug", "iso2", "iso3", "continent", "flag_url", "operators")}),
        ("Merchandising", {"fields": ("is_popular", "is_active", "intro")}),
        ("SEO", {"fields": ("seo_title", "seo_description")}),
        ("Computed", {"fields": ("plan_count", "min_price_usd", "has_unlimited",
                                 "created_at", "updated_at")}),
    )


@admin.register(Region)
class RegionAdmin(admin.ModelAdmin):
    list_display = ("name", "icon", "country_count", "plan_count", "min_price_usd",
                    "sort_order", "is_active")
    list_editable = ("sort_order", "is_active")
    search_fields = ("name", "key", "slug")
    prepopulated_fields = {"slug": ("name",)}
    filter_horizontal = ("countries",)
    readonly_fields = ("key", "plan_count", "min_price_usd", "has_unlimited",
                       "created_at", "updated_at")
    inlines = [PlanInline]


@admin.register(Plan)
class PlanAdmin(admin.ModelAdmin):
    list_display = ("provider_name", "kind", "data_label_col", "days", "cost_col",
                    "price_col", "price_override_usd", "badge", "is_active", "provider_active")
    list_filter = ("kind", "is_unlimited", "is_active", "provider_active", "days", "provider")
    list_editable = ("price_override_usd", "badge", "is_active")
    search_fields = ("provider_name", "provider_plan_id", "provider_old_id",
                     "country__name", "region__name")
    autocomplete_fields = ("country", "region")
    readonly_fields = ("provider_plan_id", "provider_old_id", "cost_amount", "cost_currency",
                       "price_usd", "raw", "created_at", "updated_at", "last_seen_at")
    list_select_related = ("country", "region")

    @admin.display(description="Data", ordering="data_gb")
    def data_label_col(self, obj):
        return obj.data_label

    @admin.display(description="Cost", ordering="cost_amount")
    def cost_col(self, obj):
        return f"{obj.cost_amount} {obj.cost_currency}"

    @admin.display(description="Retail", ordering="price_usd")
    def price_col(self, obj):
        margin = obj.price - (obj.cost_amount * 11 / 10)
        colour = "#16a34a" if margin > 0 else "#dc2626"
        return format_html('<b>${}</b> <span style="color:{}">(+${})</span>',
                           f"{obj.price:.2f}", colour, f"{margin:.2f}")


@admin.register(Device)
class DeviceAdmin(admin.ModelAdmin):
    list_display = ("brand", "model", "device_type")
    list_filter = ("brand", "device_type")
    search_fields = ("brand", "model")
