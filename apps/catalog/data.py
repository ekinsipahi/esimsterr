"""Static helpers for the catalogue: region normalisation, continents, popular list."""
import re

# Provider region labels → (display name, slug, icon, sort order, blurb)
REGION_MAP = {
    "europe": ("Europe", "europe", "🇪🇺", 10, "One eSIM for 33+ European countries — EU, UK, Switzerland, Norway, Balkans."),
    "asia pacific": ("Asia Pacific", "asia-pacific", "🌏", 20, "Japan, Korea, Australia, Singapore, Thailand and more on a single plan."),
    # The provider ships "Asia" and "Asia Pacific" with an identical country list,
    # so both collapse onto one destination page instead of competing with each other.
    "asia": ("Asia Pacific", "asia-pacific", "🌏", 20, "Japan, Korea, Australia, Singapore, Thailand and more on a single plan."),
    "sea": ("Southeast Asia", "southeast-asia", "🌴", 30, "Thailand, Vietnam, Indonesia, Malaysia, Singapore, Philippines and more."),
    "north america": ("North America", "north-america", "🇺🇸", 40, "United States, Canada and Mexico on one eSIM."),
    "latam": ("Latin America", "latin-america", "🌎", 50, "Mexico to Argentina — 20+ countries on one plan."),
    "latin america": ("Latin America", "latin-america", "🌎", 50, "Mexico to Argentina — 20+ countries on one plan."),
    "middle east": ("Middle East", "middle-east", "🕌", 60, "UAE, Saudi Arabia, Qatar, Jordan, Egypt and neighbours."),
    "balkans": ("Balkans", "balkans", "⛰️", 70, "Serbia, Bosnia, Montenegro, Albania, North Macedonia and more."),
    "cis": ("CIS & Caucasus", "cis", "🏔️", 80, "Kazakhstan, Georgia, Armenia, Uzbekistan and neighbours."),
    "global lite": ("Global", "global", "🌐", 5, "One eSIM for 100+ countries — the plan for round-the-world trips."),
    "global package": ("Global", "global", "🌐", 5, "One eSIM for 100+ countries — the plan for round-the-world trips."),
    "global": ("Global", "global", "🌐", 5, "One eSIM for 100+ countries — the plan for round-the-world trips."),
}

# Provider plan names carry the size/duration in the label and sometimes a dated
# suffix ("Europe 10GB_20250318", "Balkans 30 days unlim", "Global Lite 10Gb 365").
# Strip those trailing tokens so every variant collapses onto one region.
_DATED_SUFFIX = re.compile(r"_\d{4,}")
_SIZE_TOKEN = re.compile(r"^(\d+(\.\d+)?gb|\d+|unlim|unlimited|days?)$")


def region_key(provider_name: str) -> str:
    """'Europe 10GB_20250318' -> 'europe'; 'Global Lite 10Gb 365' -> 'global lite'."""
    text = _DATED_SUFFIX.sub(" ", (provider_name or "").lower())
    parts = [p for p in text.split() if p]
    while parts and _SIZE_TOKEN.match(parts[-1]):
        parts.pop()
    return " ".join(parts) or (provider_name or "").lower()


def region_meta(key: str):
    if key in REGION_MAP:
        return REGION_MAP[key]
    name = key.title()
    return (name, re.sub(r"[^a-z0-9]+", "-", key).strip("-"), "🌍", 100, "")


# ISO2 → continent bucket (for the destination browser filters)
CONTINENTS = {
    "Europe": "AD AL AT BA BE BG BY CH CY CZ DE DK EE ES FI FO FR GB GI GR HR HU IE IS IT LI LT LU LV MD ME MK MT NL NO PL PT RO RS RU SE SI SK UA XK".split(),
    "Asia": "AF AM AZ BD BH BN BT CN GE HK ID IL IN IQ IR JO JP KG KH KR KW KZ LA LB LK MM MN MO MV MY NP OM PH PK PS QA SA SG SY TH TJ TM TR TW UZ VN YE AE".split(),
    "Americas": "AG AI AR AW BB BO BR BS BZ CA CL CO CR CU DM DO EC GD GF GP GT GY HN HT JM KN KY LC MQ MS MX NI PA PE PR PY SR SV TC TT US UY VC VE VG VI AN".split(),
    "Africa": "AO BF BI BJ BW CD CF CG CI CM CV DJ DZ EG ER ET GA GH GM GN GQ GW KE LR LS LY MA MG ML MR MU MW MZ NA NE NG RE RW SC SD SL SN SO SS ST SZ TD TG TN TZ UG ZA ZM ZW".split(),
    "Oceania": "AU FJ GU NZ PG WS TO VU NC PF".split(),
}
ISO_TO_CONTINENT = {iso: c for c, isos in CONTINENTS.items() for iso in isos}

# Shown in the homepage "Popular destinations" grid (order matters).
POPULAR_ISO2 = ["US", "TR", "IT", "ES", "FR", "GB", "JP", "TH", "AE", "DE", "MX", "PT",
                "GR", "ID", "KR", "EG", "CA", "AU", "VN", "MA"]

# Friendlier names for a few provider labels.
NAME_OVERRIDES = {
    "United States": "United States",
    "Czech Republic": "Czechia",
    "Russia": "Russia",
    "Netherlands Antilles": "Curaçao & Caribbean Netherlands",
    "Vatican City": "Vatican City",
}
