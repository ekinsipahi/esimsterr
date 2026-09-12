from django.contrib import admin, messages
from django.utils.translation import gettext_lazy as _

from .models import Coupon, CouponRedemption


def _free_code(base: str) -> str:
    """A copy needs its own code; keep the original readable in it."""
    stem = f"{base[:26]}-COPY"
    code = stem[:32]
    n = 2
    while Coupon.objects.filter(code=code).exists():
        suffix = str(n)
        code = f"{stem[:31 - len(suffix)]}-{suffix}"
        n += 1
    return code


class RedemptionInline(admin.TabularInline):
    model = CouponRedemption
    extra = 0
    fields = ("created_at", "email", "user", "order", "discount_usd", "ip")
    readonly_fields = fields
    ordering = ("-created_at",)
    verbose_name = _("redemption")
    verbose_name_plural = _("recent redemptions")

    def get_queryset(self, request):
        return super().get_queryset(request).select_related("user", "order")

    def has_add_permission(self, request, obj=None):
        return False

    def has_change_permission(self, request, obj=None):
        return False


@admin.register(Coupon)
class CouponAdmin(admin.ModelAdmin):
    list_display = ("code", "discount", "applies_to", "window", "usage", "live", "is_public")
    list_filter = ("is_active", "is_public", "applies_to", "first_order_only", "once_per_customer")
    search_fields = ("code", "description")
    readonly_fields = ("redemptions", "created_at", "updated_at")
    ordering = ("-created_at",)
    inlines = (RedemptionInline,)
    actions = ("action_duplicate",)
    fieldsets = (
        (None, {
            "fields": ("code", "description", "is_active", "is_public"),
            "description": _(
                "The description is campaign copy shown on the public coupons page. "
                "Write it in the site's default language: it is edited here rather "
                "than translated, and the page labels it as such."
            ),
        }),
        (_("Discount"), {
            "fields": ("percent_off", "amount_off_usd", "max_discount_usd"),
            "description": _("Set a percentage or a fixed amount, never both."),
        }),
        (_("Conditions"), {
            "fields": ("applies_to", "min_order_usd", "once_per_customer",
                       "first_order_only", "stackable"),
        }),
        (_("Window and limits"), {
            "fields": ("valid_from", "valid_until", "max_redemptions", "redemptions"),
        }),
        (_("Record"), {"fields": ("created_at", "updated_at"), "classes": ("collapse",)}),
    )

    @admin.display(description=_("Discount"))
    def discount(self, obj):
        return obj.public_label

    @admin.display(description=_("Window"))
    def window(self, obj):
        start = obj.valid_from.strftime("%d %b %Y") if obj.valid_from else _("now")
        end = obj.valid_until.strftime("%d %b %Y") if obj.valid_until else _("open ended")
        return f"{start} - {end}"

    @admin.display(description=_("Used"), ordering="redemptions")
    def usage(self, obj):
        cap = obj.max_redemptions if obj.max_redemptions is not None else "-"
        return f"{obj.redemptions} / {cap}"

    @admin.display(description=_("Live"), boolean=True)
    def live(self, obj):
        return obj.is_live()

    @admin.action(description=_("Duplicate (inactive, counter reset)"))
    def action_duplicate(self, request, queryset):
        made = 0
        for coupon in queryset:
            clone = Coupon.objects.get(pk=coupon.pk)
            clone.pk = None
            clone._state.adding = True
            clone.code = _free_code(coupon.code)
            clone.redemptions = 0
            # A copy starts switched off and unlisted so an edit-in-progress is
            # never live on the coupons page.
            clone.is_active = False
            clone.is_public = False
            clone.save()
            made += 1
        self.message_user(
            request,
            _("Duplicated %(count)s coupon(s). The copies are inactive until you switch them on.")
            % {"count": made},
            level=messages.SUCCESS,
        )


@admin.register(CouponRedemption)
class CouponRedemptionAdmin(admin.ModelAdmin):
    list_display = ("created_at", "coupon", "email", "user", "order", "discount_usd", "ip")
    list_filter = ("coupon", "created_at")
    search_fields = ("email", "coupon__code", "order__ref", "user__email", "ip")
    readonly_fields = ("coupon", "order", "user", "email", "ip", "discount_usd", "created_at")
    list_select_related = ("coupon", "user", "order")
    date_hierarchy = "created_at"

    def has_add_permission(self, request):
        return False
