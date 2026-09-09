#!/usr/bin/env bash
# Render build step for the Django app.
set -o errexit

pip install -r requirements.txt
python manage.py collectstatic --no-input
python manage.py migrate

# Mirror the provider catalogue. Safe and idempotent on every deploy; skipped
# automatically when YESIM_API_TOKEN is not set (e.g. a preview environment).
python manage.py sync_plans || echo "sync_plans skipped/failed — the site still boots"
