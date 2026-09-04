#!/usr/bin/env sh
# Container startup: wait for dependencies, migrate, bootstrap, then run the server.
# No destructive database operation is ever performed here.
set -eu

log() { echo "[entrypoint] $*"; }

wait_for() {
    name="$1"
    script="$2"
    attempts="${3:-30}"
    i=1
    while [ "$i" -le "$attempts" ]; do
        if python -c "$script" >/dev/null 2>&1; then
            log "$name is ready."
            return 0
        fi
        log "Waiting for $name ($i/$attempts)..."
        i=$((i + 1))
        sleep 2
    done
    log "WARNING: $name did not become ready in time."
    return 1
}

wait_for "MongoDB" "
import os, sys
from pymongo import MongoClient
uri = os.environ.get('MONGODB_URI', 'mongodb://mongodb:27017/')
MongoClient(uri, serverSelectionTimeoutMS=2000).admin.command('ping')
" 40 || true

wait_for "Redis" "
import os, sys, redis
url = os.environ.get('REDIS_URL', '')
sys.exit(0) if not url else redis.Redis.from_url(url, socket_connect_timeout=2).ping()
" 20 || true

log "Applying database migrations..."
python manage.py migrate --noinput

log "Ensuring MongoDB indexes..."
python manage.py ensure_indexes || log "Index creation skipped."

log "Collecting static files..."
python manage.py collectstatic --noinput --clear >/dev/null

log "Seeding roles and permissions..."
python manage.py sync_roles || log "Role sync skipped."

log "Bootstrapping administrator (skipped when APP_ADMIN_* is unset)..."
python manage.py bootstrap_admin --skip-if-missing || log "Bootstrap skipped; check APP_ADMIN_* and RANKVISTA_SECRET_KEY."

log "Starting application."
exec "$@"
