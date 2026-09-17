#!/usr/bin/env bash
# Render build step for the Django app.
set -o errexit

pip install -r requirements.txt
python manage.py collectstatic --no-input
python manage.py migrate

# The cache lives in Postgres so the two gunicorn workers share it. Creating
# the table is idempotent and has to happen before anything rate-limits.
python manage.py createcachetable

# Fail the build if a legal document's text changed without its version being
# bumped. The acceptance ledger records version + content hash together; if the
# two can drift, every record already written becomes a claim about text the
# customer may never have seen.
python manage.py check_legal

# Say in the deploy log whether the bot check is actually protecting anything.
# Not strict: missing keys must not block a deploy, but they must not be silent
# either -- "off" and "working" look identical from outside.
python manage.py check_turnstile || true

# Compile any translated locales. No .po files yet means a no-op.
python manage.py compilemessages 2>/dev/null || true

# Mirror the provider catalogue, then give every destination its own copy.
# Both are idempotent, and a failure here must not stop the site from booting
# (a preview environment has no YESIM_API_TOKEN).
python manage.py sync_plans || echo "sync_plans skipped or failed; the site still boots"
python manage.py seed_country_seo || echo "seed_country_seo skipped"

# Every subscribable plan needs a Stripe price before anyone tries to subscribe.
# Creating them here makes a failure a build problem rather than a customer
# seeing "something broke on our side" and leaving.
python manage.py sync_stripe_prices || echo "sync_stripe_prices skipped or failed"
