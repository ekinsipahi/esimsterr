from decimal import Decimal

from django.db import models
from django.urls import reverse


class Country(models.Model):
    """A destination with its own local plans (Yesim plan_type=country)."""

    iso2 = models.CharField(max_length=2, unique=True)
    iso3 = models.CharField(max_length=3, blank=True)
    name = models.CharField(max_length=80)
    slug = models.SlugField(max_length=90, unique=True)
    flag_url = models.URLField(blank=True)
    operators = models.TextField(blank=True, help_text="Comma-separated operator names from the provider")
    continent = models.CharField(max_length=32, blank=True, db_index=True)
    is_popular = models.BooleanField(default=False, db_index=True)
    is_active = models.BooleanField(default=True, db_index=True)
    # Cached "from" price (USD) for listings; refreshed by sync_plans.
    min_price_usd = models.DecimalField(max_digits=8, decimal_places=2, null=True, blank=True)
    plan_count = models.PositiveIntegerField(default=0)
    has_unlimited = models.BooleanField(default=False)
    # Optional editorial copy (SEO) — falls back to generated text in templates.
    intro = models.TextField(blank=True)
    seo_title = models.CharField(max_length=140, blank=True)
    seo_description = models.CharField(max_length=300, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["name"]
        verbose_name_plural = "countries"

    def __str__(self):
        return self.name

    def get_absolute_url(self):
        return reverse("country_detail", kwargs={"slug": self.slug})

    @property
    def operator_list(self):
        return [o.strip() for o in self.operators.split(",") if o.strip()]

    @property
    def flag_emoji(self):
        return "".join(chr(0x1F1E6 + ord(c) - ord("A")) for c in self.iso2.upper())


class Region(models.Model):
    """A multi-country bundle (Yesim plan_type=region), e.g. Europe, Global."""

    key = models.CharField(max_length=40, unique=True, help_text="Normalised provider label")
    name = models.CharField(max_length=80)
    slug = models.SlugField(max_length=90, unique=True)
    description = models.TextField(blank=True)
    icon = models.CharField(max_length=8, default="🌍")
    countries = models.ManyToManyField(Country, blank=True, related_name="regions")
    country_names = models.TextField(blank=True, help_text="Comma-separated, as reported by provider")
    is_active = models.BooleanField(default=True, db_index=True)
    sort_order = models.PositiveIntegerField(default=100)
    min_price_usd = models.DecimalField(max_digits=8, decimal_places=2, null=True, blank=True)
    plan_count = models.PositiveIntegerField(default=0)
    has_unlimited = models.BooleanField(default=False)
    seo_title = models.CharField(max_length=140, blank=True)
    seo_description = models.CharField(max_length=300, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["sort_order", "name"]

    def __str__(self):
        return self.name

    def get_absolute_url(self):
        return reverse("region_detail", kwargs={"slug": self.slug})

    @property
    def country_name_list(self):
        return [c.strip() for c in self.country_names.split(",") if c.strip()]

    @property
    def country_count(self):
        return len(self.country_name_list)


class PlanQuerySet(models.QuerySet):
    def live(self):
        return self.filter(is_active=True, provider_active=True)


class Plan(models.Model):
    """A sellable data package, mirrored from the provider catalogue."""

    class Kind(models.TextChoices):
        COUNTRY = "country", "Country"
        REGION = "region", "Region"

    provider = models.CharField(max_length=20, default="yesim")
    provider_plan_id = models.CharField(max_length=64, unique=True)
    provider_old_id = models.CharField(max_length=32, blank=True)
    provider_name = models.CharField(max_length=140)
    kind = models.CharField(max_length=10, choices=Kind.choices, db_index=True)
    country = models.ForeignKey(Country, null=True, blank=True, on_delete=models.CASCADE, related_name="plans")
    region = models.ForeignKey(Region, null=True, blank=True, on_delete=models.CASCADE, related_name="plans")

    data_gb = models.DecimalField(max_digits=7, decimal_places=2, null=True, blank=True,
                                  help_text="NULL = unlimited")
    is_unlimited = models.BooleanField(default=False, db_index=True)
    days = models.PositiveIntegerField()
    operators = models.TextField(blank=True)
    apn = models.CharField(max_length=32, blank=True)
    countries_iso2 = models.TextField(blank=True, help_text="Comma-separated ISO2 list covered")

    # Money
    cost_amount = models.DecimalField(max_digits=10, decimal_places=2, help_text="Wholesale price")
    cost_currency = models.CharField(max_length=3, default="EUR")
    price_usd = models.DecimalField(max_digits=10, decimal_places=2, help_text="Computed retail price")
    price_override_usd = models.DecimalField(max_digits=10, decimal_places=2, null=True, blank=True,
                                             help_text="Manual retail price; wins over the formula")
    compare_at_usd = models.DecimalField(max_digits=10, decimal_places=2, null=True, blank=True,
                                         help_text="Typical competitor price for the strike-through")

    is_active = models.BooleanField(default=True, db_index=True)
    provider_active = models.BooleanField(default=True, db_index=True,
                                          help_text="False when the plan disappeared from the provider feed")
    is_featured = models.BooleanField(default=False)
    badge = models.CharField(max_length=24, blank=True, help_text="e.g. Best value / Most popular")
    raw = models.JSONField(default=dict, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    last_seen_at = models.DateTimeField(null=True, blank=True)

    objects = PlanQuerySet.as_manager()

    class Meta:
        ordering = ["is_unlimited", "days", "data_gb"]
        indexes = [models.Index(fields=["kind", "is_active", "provider_active"])]

    def __str__(self):
        return f"{self.title} — ${self.price}"

    # ---- presentation ----------------------------------------------------------
    @property
    def price(self) -> Decimal:
        return self.price_override_usd if self.price_override_usd is not None else self.price_usd

    @property
    def target(self):
        return self.country if self.kind == self.Kind.COUNTRY else self.region

    @property
    def target_name(self):
        t = self.target
        return t.name if t else self.provider_name

    @property
    def data_label(self):
        if self.is_unlimited:
            return "Unlimited"
        d = self.data_gb or Decimal("0")
        if d < 1:
            return f"{int(d * 1024)} MB"
        return f"{d.normalize():f} GB"

    @property
    def title(self):
        return f"{self.target_name} · {self.data_label} · {self.days} days"

    @property
    def per_gb_usd(self):
        if self.is_unlimited or not self.data_gb:
            return None
        return (self.price / self.data_gb).quantize(Decimal("0.01"))

    @property
    def per_day_usd(self):
        return (self.price / Decimal(self.days)).quantize(Decimal("0.01"))

    @property
    def savings_pct(self):
        if self.compare_at_usd and self.compare_at_usd > self.price:
            return int(round((1 - self.price / self.compare_at_usd) * 100))
        return None

    def get_absolute_url(self):
        return reverse("checkout", kwargs={"plan_id": self.pk})


class Device(models.Model):
    """eSIM-compatible device list (provider /supported_devices)."""

    device_type = models.CharField(max_length=20, default="PHONE")
    brand = models.CharField(max_length=60, db_index=True)
    model = models.CharField(max_length=160)

    class Meta:
        ordering = ["brand", "model"]
        unique_together = ("brand", "model")

    def __str__(self):
        return f"{self.brand} {self.model}"
