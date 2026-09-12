#!/usr/bin/env bash
# Render build step for the Django app.
set -o errexit

pip install -r requirements.txt
python manage.py collectstatic --no-input
python manage.py migrate

# Compile any translated locales. No .po files yet means a no-op.
python manage.py compilemessages 2>/dev/null || true

# Mirror the provider catalogue, then give every destination its own copy.
# Both are idempotent, and a failure here must not stop the site from booting
# (a preview environment has no YESIM_API_TOKEN).
python manage.py sync_plans || echo "sync_plans skipped or failed; the site still boots"
python manage.py seed_country_seo || echo "seed_country_seo skipped"
