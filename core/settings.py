"""
Django settings for eSIMsterr — single-project Django site (templates + JSON API).

Config comes from environment variables (Render) or a local .env file.
"""
from datetime import timedelta
from pathlib import Path
import os

BASE_DIR = Path(__file__).resolve().parent.parent


# ---- Dependency-free .env loader: reads BASE_DIR/.env if present and never
#      overrides variables that are already set (Render injects env directly).
def _load_env(path):
    try:
        with open(path, encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line or line.startswith("#") or "=" not in line:
                    continue
                k, _, v = line.partition("=")
                os.environ.setdefault(k.strip(), v.strip().strip('"').strip("'"))
    except FileNotFoundError:
        pass


_load_env(BASE_DIR / ".env")


def env(key, default=""):
    return os.environ.get(key, default)


def env_bool(key, default=False):
    v = os.environ.get(key)
    if v is None:
        return default
    return v.strip().lower() in ("1", "true", "yes", "on")


def env_list(key, default=None):
    v = os.environ.get(key, "")
    return [x.strip() for x in v.split(",") if x.strip()] or (default or [])


SECRET_KEY = env("DJANGO_SECRET_KEY", "dev-only-insecure-change-me")
DEBUG = env_bool("DEBUG", True)

# ---- Site identity -----------------------------------------------------------
SITE_NAME = env("SITE_NAME", "eSIMsterr")
COMPANY_LEGAL_NAME = env("COMPANY_LEGAL_NAME", "Sterr Technologies")
SUPPORT_EMAIL = env("SUPPORT_EMAIL", "support@esimsterr.com")
SITE_URL = env("SITE_URL", "http://127.0.0.1:8000").rstrip("/")
CANONICAL_HOST = env("CANONICAL_HOST", "esimsterr.com")
# Old/alias hosts 301 → canonical (e.g. www.esimsterr.com, onrender.com host).
REDIRECT_HOSTS = env_list("REDIRECT_HOSTS", [])
DEFAULT_DESCRIPTION = (
    "Prepaid travel eSIM data plans for 148+ countries. Instant QR delivery, "
    "unlimited plans, pay by card or crypto. Cheaper than roaming — and cheaper than the other eSIM apps."
)
SITE_SAMEAS = env_list("SITE_SAMEAS", [])
# Shown as "last updated" on the legal pages. Bump it when a policy really
# changes; rendering today's date would claim a daily revision that never happened.
LEGAL_UPDATED = env("LEGAL_UPDATED", "12 September 2026")
APP_STORE_URL = env("APP_STORE_URL", "")
PLAY_STORE_URL = env("PLAY_STORE_URL", "")

ALLOWED_HOSTS = env_list("ALLOWED_HOSTS", ["localhost", "127.0.0.1"])
CSRF_TRUSTED_ORIGINS = env_list("CSRF_TRUSTED_ORIGINS", [])
_PROD_HOSTS = [CANONICAL_HOST, f"www.{CANONICAL_HOST}", "esimsterr.onrender.com"]
for _h in _PROD_HOSTS:
    if _h not in ALLOWED_HOSTS:
        ALLOWED_HOSTS.append(_h)
    _o = f"https://{_h}"
    if _o not in CSRF_TRUSTED_ORIGINS:
        CSRF_TRUSTED_ORIGINS.append(_o)
# Render sets RENDER_EXTERNAL_HOSTNAME automatically.
if env("RENDER_EXTERNAL_HOSTNAME"):
    ALLOWED_HOSTS.append(env("RENDER_EXTERNAL_HOSTNAME"))
    CSRF_TRUSTED_ORIGINS.append("https://" + env("RENDER_EXTERNAL_HOSTNAME"))

# ---- Sentry ------------------------------------------------------------------
SENTRY_DSN = env("SENTRY_DSN", "")
if SENTRY_DSN:
    import sentry_sdk

    sentry_sdk.init(
        dsn=SENTRY_DSN,
        environment="development" if DEBUG else "production",
        send_default_pii=True,
        traces_sample_rate=float(env("SENTRY_TRACES_SAMPLE_RATE", "0.2")),
    )

# ---- Applications ------------------------------------------------------------
INSTALLED_APPS = [
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
    "django.contrib.sitemaps",
    "django.contrib.humanize",
    # third-party
    "rest_framework",
    "rest_framework_simplejwt",
    "corsheaders",
    # local
    "apps.common",
    "apps.accounts",
    "apps.catalog",
    "apps.orders",
    "apps.payments",
    "apps.providers",
    "apps.api",
    "apps.blog",
    "apps.support",
    "apps.coupons",
    "apps.subscriptions",
    "apps.seo",
]

MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    "core.middleware.DomainRedirectMiddleware",
    "whitenoise.middleware.WhiteNoiseMiddleware",
    "corsheaders.middleware.CorsMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.locale.LocaleMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
    "core.middleware.CoopAllowPopupsMiddleware",
]

ROOT_URLCONF = "core.urls"

TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "DIRS": [BASE_DIR / "templates"],
        "APP_DIRS": True,
        "OPTIONS": {
            "context_processors": [
                "django.template.context_processors.debug",
                "django.template.context_processors.request",
                "django.contrib.auth.context_processors.auth",
                "django.contrib.messages.context_processors.messages",
                "core.context_processors.site",
            ],
        },
    },
]

WSGI_APPLICATION = "core.wsgi.application"
ASGI_APPLICATION = "core.asgi.application"

# ---- Database ----------------------------------------------------------------
# Priority: DATABASE_URL → Supabase parts (DB_HOST/DB_USER/DB_PASSWORD) → SQLite.
# Supabase pooler: DB_USER = postgres.<project-ref>, SESSION pooler port 5432.
if env("DATABASE_URL"):
    import dj_database_url

    DATABASES = {"default": dj_database_url.parse(env("DATABASE_URL"))}
elif env("DB_HOST"):
    DATABASES = {
        "default": {
            "ENGINE": "django.db.backends.postgresql",
            "NAME": env("DB_NAME", "postgres"),
            "USER": env("DB_USER", "postgres"),
            "PASSWORD": env("DB_PASSWORD", ""),
            "HOST": env("DB_HOST"),
            "PORT": env("DB_PORT", "5432"),
        }
    }
else:
    DATABASES = {
        "default": {
            "ENGINE": "django.db.backends.sqlite3",
            "NAME": BASE_DIR / "db.sqlite3",
        }
    }
DATABASES["default"]["CONN_MAX_AGE"] = int(env("DB_CONN_MAX_AGE", "60"))
_db_host = str(DATABASES["default"].get("HOST", ""))
if "supabase" in _db_host:
    DATABASES["default"].setdefault("OPTIONS", {})["sslmode"] = env("DB_SSLMODE", "require")
    DATABASES["default"]["DISABLE_SERVER_SIDE_CURSORS"] = True

# ---- Auth --------------------------------------------------------------------
AUTH_USER_MODEL = "accounts.User"
LOGIN_URL = "/login/"
LOGIN_REDIRECT_URL = "/dashboard/"
LOGOUT_REDIRECT_URL = "/"

AUTH_PASSWORD_VALIDATORS = [
    {"NAME": "django.contrib.auth.password_validation.UserAttributeSimilarityValidator"},
    {"NAME": "django.contrib.auth.password_validation.MinimumLengthValidator", "OPTIONS": {"min_length": 8}},
    {"NAME": "django.contrib.auth.password_validation.CommonPasswordValidator"},
    {"NAME": "django.contrib.auth.password_validation.NumericPasswordValidator"},
]

GOOGLE_CLIENT_ID = env("GOOGLE_CLIENT_ID", "")
GOOGLE_CLIENT_SECRET = env("GOOGLE_CLIENT_SECRET", "")

# Django defaults to three days, which is a long time for a link that grants
# account access from an inbox. Three hours matches what the reset pages tell
# the customer, and a fresh link is one click away.
PASSWORD_RESET_TIMEOUT = int(env("PASSWORD_RESET_TIMEOUT", str(60 * 60 * 3)))

# ---- I18N / TZ ---------------------------------------------------------------
LANGUAGE_CODE = "en"
TIME_ZONE = "UTC"
USE_I18N = True
USE_TZ = True
LOCALE_PATHS = [BASE_DIR / "locale"]

# Every string in the project is wrapped for translation, but a locale only goes
# live once its .po file is actually translated: publishing /tr/ pages full of
# English is duplicate content, not localisation. So the catalogue of languages
# we are prepared to serve lives here, and ENABLED_LANGUAGES decides which of
# them Django actually offers. Translate a locale, add its code to the env var,
# redeploy — no code change.
SUPPORTED_LANGUAGES = {
    "en": "English", "tr": "Türkçe", "es": "Español", "pt": "Português",
    "fr": "Français", "de": "Deutsch", "it": "Italiano", "ru": "Русский",
    "ar": "العربية", "fa": "فارسی", "hi": "हिन्दी", "id": "Bahasa Indonesia",
    "ms": "Bahasa Melayu", "vi": "Tiếng Việt", "th": "ไทย", "ko": "한국어",
    "ja": "日本語", "zh-hans": "简体中文", "zh-hant": "繁體中文", "pl": "Polski",
    "nl": "Nederlands", "uk": "Українська", "ro": "Română", "cs": "Čeština",
    "el": "Ελληνικά", "sv": "Svenska", "he": "עברית", "az": "Azərbaycanca",
    "kk": "Қазақша", "uz": "Oʻzbekcha", "bn": "বাংলা", "ur": "اردو",
}
_enabled = [c for c in env_list("ENABLED_LANGUAGES", ["en"]) if c in SUPPORTED_LANGUAGES]
if "en" not in _enabled:
    _enabled.insert(0, "en")
LANGUAGES = [(code, SUPPORTED_LANGUAGES[code]) for code in _enabled]
RTL_LANGUAGES = {"ar", "fa", "he", "ur"}
LANGUAGE_COOKIE_NAME = "esimsterr_lang"
LANGUAGE_COOKIE_SAMESITE = "Lax"

# ---- Static / media ------------------------------------------------------------
STATIC_URL = "/static/"
STATICFILES_DIRS = [BASE_DIR / "static"]
STATIC_ROOT = BASE_DIR / "staticfiles"
STORAGES = {
    "default": {"BACKEND": "django.core.files.storage.FileSystemStorage"},
    "staticfiles": {"BACKEND": "whitenoise.storage.CompressedManifestStaticFilesStorage"},
}
WHITENOISE_MAX_AGE = 60 * 60 * 24 * 30
MEDIA_URL = "/media/"
MEDIA_ROOT = BASE_DIR / "media"
DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"

# ---- DRF / JWT (mobile app API) ------------------------------------------------
REST_FRAMEWORK = {
    "DEFAULT_AUTHENTICATION_CLASSES": (
        "rest_framework_simplejwt.authentication.JWTAuthentication",
    ),
    "DEFAULT_PERMISSION_CLASSES": ("rest_framework.permissions.IsAuthenticated",),
    "DEFAULT_RENDERER_CLASSES": ("rest_framework.renderers.JSONRenderer",),
    "DEFAULT_THROTTLE_CLASSES": (
        "rest_framework.throttling.AnonRateThrottle",
        "rest_framework.throttling.UserRateThrottle",
    ),
    "DEFAULT_THROTTLE_RATES": {
        "anon": env("THROTTLE_ANON", "120/min"),
        "user": env("THROTTLE_USER", "300/min"),
        "auth": env("THROTTLE_AUTH", "10/min"),
        "checkout": env("THROTTLE_CHECKOUT", "20/hour"),
    },
}
SIMPLE_JWT = {
    "ACCESS_TOKEN_LIFETIME": timedelta(minutes=int(env("JWT_ACCESS_MIN", "60"))),
    "REFRESH_TOKEN_LIFETIME": timedelta(days=int(env("JWT_REFRESH_DAYS", "60"))),
    "AUTH_HEADER_TYPES": ("Bearer",),
}
CORS_ALLOWED_ORIGINS = env_list("CORS_ALLOWED_ORIGINS", [])
CORS_URLS_REGEX = r"^/api/.*$"

# ---- Email (Resend HTTP API; console fallback in dev) --------------------------
RESEND_API_KEY = env("RESEND_API_KEY", "").strip()
EMAIL_BACKEND = (
    "apps.accounts.resend_backend.ResendEmailBackend"
    if RESEND_API_KEY
    else "django.core.mail.backends.console.EmailBackend"
)
DEFAULT_FROM_EMAIL = env("DEFAULT_FROM_EMAIL", f"{SITE_NAME} <noreply@esimsterr.com>")
ADMIN_NOTIFY_EMAILS = env_list("ADMIN_NOTIFY_EMAILS", [])

# ---- Yesim partner API (eSIM provider) -----------------------------------------
YESIM_API_TOKEN = env("YESIM_API_TOKEN", "").strip()
YESIM_API_BASE = env("YESIM_API_BASE", "https://partners-api.yesim.biz").rstrip("/")
YESIM_WEBHOOK_SECRET = env("YESIM_WEBHOOK_SECRET", "")  # random path segment for the notification URL

# ---- Pricing strategy (see apps/catalog/pricing.py) -----------------------------
# Wholesale prices come in EUR; we sell in USD. Retail = max(cost*markup, cost+min_margin),
# rounded to a "charm" ending, then any per-plan admin override wins.
EUR_USD_RATE = env("EUR_USD_RATE", "1.10")
PRICING_MARKUP = env("PRICING_MARKUP", "1.65")
PRICING_MIN_MARGIN_USD = env("PRICING_MIN_MARGIN_USD", "0.60")
PRICING_MIN_PRICE_USD = env("PRICING_MIN_PRICE_USD", "1.49")
# The struck-through list price is cost x this. It represents the going retail
# rate for the same wholesale data (the big eSIM apps run roughly 4x), which is
# what the advertised discount percentage is measured against.
PRICING_COMPARE_MULTIPLIER = env("PRICING_COMPARE_MULTIPLIER", "4.0")
DISPLAY_CURRENCY = "USD"

# Subscriptions: a standing discount is the reason to subscribe rather than
# re-buy an unlimited plan every month.
SUBSCRIPTION_DISCOUNT_PCT = env("SUBSCRIPTION_DISCOUNT_PCT", "15")
SUBSCRIPTIONS_ENABLED = env_bool("SUBSCRIPTIONS_ENABLED", True)

# ---- Payments ------------------------------------------------------------------
STRIPE_SECRET_KEY = env("STRIPE_SECRET_KEY", "")
STRIPE_PUBLISHABLE_KEY = env("STRIPE_PUBLISHABLE_KEY", "") or env("STRIPE_PUBLISH_KEY", "")
STRIPE_WEBHOOK_SECRET = env("STRIPE_WEBHOOK_SECRET", "")

NOWPAYMENTS_API_KEY = env("NOWPAYMENTS_API_KEY", "")
NOWPAYMENTS_IPN_SECRET = env("NOWPAYMENTS_IPN_SECRET", "")
NOWPAYMENTS_API_BASE = env("NOWPAYMENTS_API_BASE", "https://api.nowpayments.io/v1")

# Shared secret for the HTTP cron trigger (/cron/<task>/?token=...).
CRON_SECRET = env("CRON_SECRET", "")

# --- In-site AI assistant (signed-in customers only) -------------------------
# Every reply costs money, so the endpoint is behind authentication and an
# hourly cap. Without a key the widget still renders and falls back to "the team
# has been notified", so nothing breaks when it is unset.
ANTHROPIC_API_KEY = env("ANTHROPIC_API_KEY", "").strip()
ASSISTANT_MODEL = env("ASSISTANT_MODEL", "claude-haiku-4-5-20251001").strip()
ASSISTANT_ENABLED = env_bool("ASSISTANT_ENABLED", True)
SUPPORT_FORWARD_EMAIL = env("SUPPORT_FORWARD_EMAIL", "") or SUPPORT_EMAIL

# ---- Analytics -----------------------------------------------------------------
GA_MEASUREMENT_ID = env("GA_MEASUREMENT_ID", "")

# ---- Production hardening ------------------------------------------------------
if not DEBUG:
    SECURE_SSL_REDIRECT = env_bool("SECURE_SSL_REDIRECT", True)
    SECURE_PROXY_SSL_HEADER = ("HTTP_X_FORWARDED_PROTO", "https")
    SESSION_COOKIE_SECURE = True
    CSRF_COOKIE_SECURE = True
    SECURE_HSTS_SECONDS = int(env("SECURE_HSTS_SECONDS", "31536000"))
    SECURE_HSTS_INCLUDE_SUBDOMAINS = True
    SECURE_HSTS_PRELOAD = True

LOGGING = {
    "version": 1,
    "disable_existing_loggers": False,
    "handlers": {"console": {"class": "logging.StreamHandler"}},
    "root": {"handlers": ["console"], "level": env("LOG_LEVEL", "INFO")},
}
