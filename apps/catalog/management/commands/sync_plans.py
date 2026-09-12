"""Mirror the Yesim catalogue into Country / Region / Plan and (re)compute prices.

Idempotent — safe to run on every deploy and on a schedule. Plans that vanish
from the feed are flagged provider_active=False (never deleted: orders reference them).
"""
from __future__ import annotations

import logging
from decimal import Decimal

from django.core.management.base import BaseCommand
from django.db import transaction
from django.db.models import Min
from django.utils import timezone
from django.utils.text import slugify

from apps.catalog.data import ISO_TO_CONTINENT, NAME_OVERRIDES, POPULAR_ISO2, region_key, region_meta
from apps.catalog.models import Country, Device, Plan, Region
from apps.catalog.pricing import compare_at_usd, retail_usd
from apps.providers.yesim import YesimError, client

log = logging.getLogger(__name__)


class Command(BaseCommand):
    help = "Sync plans, countries, regions and devices from the Yesim partner API."

    def add_arguments(self, parser):
        parser.add_argument("--no-devices", action="store_true")
        parser.add_argument("--reprice-only", action="store_true",
                            help="Skip the API; just recompute retail prices from stored costs")

    def handle(self, *args, **opts):
        if opts["reprice_only"]:
            n = self._reprice()
            self.stdout.write(self.style.SUCCESS(f"Repriced {n} plans"))
            self._refresh_aggregates()
            return
        c = client()
        try:
            feed = c.plans()
        except YesimError as e:
            self.stderr.write(f"Yesim error: {e}")
            return
        stats = self._sync(feed)
        self.stdout.write(self.style.SUCCESS(
            f"Plans: {stats['created']} new, {stats['updated']} updated, {stats['retired']} retired · "
            f"countries={Country.objects.count()} regions={Region.objects.count()}"
        ))
        self._refresh_aggregates()
        if not opts["no_devices"]:
            try:
                self._sync_devices(c.supported_devices())
            except YesimError as e:
                self.stderr.write(f"devices: {e}")

    # ------------------------------------------------------------------------
    @transaction.atomic
    def _sync(self, feed):
        now = timezone.now()
        seen, created, updated = set(), 0, 0
        countries, regions = {}, {}

        for p in feed:
            pid = str(p.get("id") or "")
            if not pid:
                continue
            seen.add(pid)
            kind = Plan.Kind.REGION if p.get("plan_type") == "region" else Plan.Kind.COUNTRY
            raw_data = str(p.get("data") or "")
            is_unlimited = raw_data.strip().lower().startswith("unlim")
            data_gb = None if is_unlimited else Decimal(raw_data or "0")
            days = int(p.get("days") or 0) or 1
            cost = Decimal(str(p.get("price") or "0"))
            cur = (p.get("currency") or "EUR").upper()
            price = retail_usd(cost, cur, is_unlimited=is_unlimited)

            country = region = None
            if kind == Plan.Kind.COUNTRY:
                iso2 = (p.get("countryIso2") or "").upper()[:2]
                if not iso2:
                    continue
                country = countries.get(iso2) or self._upsert_country(p, iso2)
                countries[iso2] = country
            else:
                key = region_key(p.get("name") or "")
                region = regions.get(key) or self._upsert_region(key, p)
                regions[key] = region

            defaults = dict(
                provider="yesim",
                provider_old_id=str(p.get("old_id") or ""),
                provider_name=p.get("name") or "",
                kind=kind, country=country, region=region,
                data_gb=data_gb, is_unlimited=is_unlimited, days=days,
                operators=(p.get("operators") or "").strip(),
                apn=p.get("apn") or "",
                countries_iso2=(p.get("countryIso2") or "").upper(),
                cost_amount=cost, cost_currency=cur, price_usd=price,
                provider_active=True, raw=p, last_seen_at=now,
            )
            obj, was_created = Plan.objects.get_or_create(provider_plan_id=pid, defaults=defaults)
            if was_created:
                obj.compare_at_usd = compare_at_usd(cost, cur)
                obj.save(update_fields=["compare_at_usd"])
                created += 1
            else:
                for k, v in defaults.items():
                    setattr(obj, k, v)
                if obj.compare_at_usd is None:
                    obj.compare_at_usd = compare_at_usd(cost, cur)
                obj.save()
                updated += 1

        retired = Plan.objects.filter(provider="yesim", provider_active=True).exclude(
            provider_plan_id__in=seen).update(provider_active=False)
        return {"created": created, "updated": updated, "retired": retired}

    def _upsert_country(self, p, iso2):
        name = (p.get("countries_included") or iso2).split(",")[0].strip()
        name = NAME_OVERRIDES.get(name, name)
        defaults = dict(
            name=name, iso3=(p.get("iso3") or "")[:3], flag_url=p.get("image") or "",
            continent=ISO_TO_CONTINENT.get(iso2, ""),
        )
        obj = Country.objects.filter(iso2=iso2).first()
        if obj is None:
            slug = slugify(name) or iso2.lower()
            if Country.objects.filter(slug=slug).exists():
                slug = f"{slug}-{iso2.lower()}"
            obj = Country.objects.create(iso2=iso2, slug=slug, is_popular=iso2 in POPULAR_ISO2, **defaults)
        else:
            for k, v in defaults.items():
                if v and not getattr(obj, k):
                    setattr(obj, k, v)
            obj.save()
        # Union of operators across the country's plans.
        ops = set(obj.operator_list) | {o.strip() for o in (p.get("operators") or "").split(",") if o.strip()}
        obj.operators = ", ".join(sorted(ops))
        obj.save(update_fields=["operators"])
        return obj

    def _upsert_region(self, key, p):
        name, slug, icon, order, blurb = region_meta(key)
        obj = Region.objects.filter(slug=slug).first()
        if obj is None:
            obj = Region.objects.create(key=key, name=name, slug=slug, icon=icon, sort_order=order,
                                        description=blurb)
        names = obj.country_name_list
        incoming = [n.strip() for n in (p.get("countries_included") or "").split(",") if n.strip()]
        if len(incoming) > len(names):
            obj.country_names = ", ".join(incoming)
            obj.save(update_fields=["country_names"])
            isos = [i.strip().upper() for i in (p.get("countryIso2") or "").split(",") if i.strip()]
            obj.countries.set(Country.objects.filter(iso2__in=isos))
        return obj

    def _reprice(self):
        n = 0
        for plan in Plan.objects.all():
            plan.price_usd = retail_usd(plan.cost_amount, plan.cost_currency,
                                        is_unlimited=plan.is_unlimited)
            plan.compare_at_usd = compare_at_usd(plan.cost_amount, plan.cost_currency)
            plan.save(update_fields=["price_usd", "compare_at_usd"])
            n += 1
        return n

    def _refresh_aggregates(self):
        for c in Country.objects.all():
            live = c.plans.live()
            c.plan_count = live.count()
            c.has_unlimited = live.filter(is_unlimited=True).exists()
            prices = [p.price for p in live]
            c.min_price_usd = min(prices) if prices else None
            c.is_active = c.plan_count > 0
            c.save(update_fields=["plan_count", "has_unlimited", "min_price_usd", "is_active"])
        for r in Region.objects.all():
            live = r.plans.live()
            r.plan_count = live.count()
            r.has_unlimited = live.filter(is_unlimited=True).exists()
            prices = [p.price for p in live]
            r.min_price_usd = min(prices) if prices else None
            r.is_active = r.plan_count > 0
            r.save(update_fields=["plan_count", "has_unlimited", "min_price_usd", "is_active"])
        # Auto badges per destination: cheapest per-GB → "Best value", mid 30-day → "Most popular".
        for group in list(Country.objects.all()) + list(Region.objects.all()):
            plans = list(group.plans.live())
            Plan.objects.filter(pk__in=[p.pk for p in plans]).update(badge="")
            data_plans = [p for p in plans if not p.is_unlimited and p.data_gb]
            if data_plans:
                best = min(data_plans, key=lambda p: p.per_gb_usd)
                best.badge = "Best value"
                best.save(update_fields=["badge"])
                pop = [p for p in data_plans if p.days == 30 and p != best]
                if pop:
                    pop = sorted(pop, key=lambda p: p.data_gb)[len(pop) // 2]
                    pop.badge = "Most popular"
                    pop.save(update_fields=["badge"])

    def _sync_devices(self, feed):
        n = 0
        for group in feed or []:
            dtype = group.get("type") or "PHONE"
            for b in group.get("brands") or []:
                brand = (b.get("brand") or "").strip()
                for m in b.get("models") or []:
                    model = (m.get("model") or "").strip()[:160]
                    if brand and model:
                        Device.objects.get_or_create(brand=brand, model=model, defaults={"device_type": dtype})
                        n += 1
        self.stdout.write(f"Devices: {n} in feed, {Device.objects.count()} stored")
