#!/bin/sh
set -e
# Dumps the database first when there are new migrations (app/migrate.py).
python -m app.migrate
python -m app.seed --if-empty
exec uvicorn app.main:app --host 0.0.0.0 --port 8000 --proxy-headers --forwarded-allow-ips='*'
