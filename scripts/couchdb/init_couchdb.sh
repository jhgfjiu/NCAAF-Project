#!/usr/bin/env bash
set -euo pipefail

#–– Configuration (override via env or args) ––
HOST="${COUCHDB_HOST:-127.0.0.1}"
PORT="${COUCHDB_PORT:-5984}"
ADMIN_USER="${COUCHDB_USER:-admin}"
ADMIN_PASS="${COUCHDB_PASSWORD:-password}"

#–– Wait for CouchDB to accept connections ––
echo "⏳ Waiting for CouchDB at http://${HOST}:${PORT}…"
until curl -s "http://${HOST}:${PORT}/" >/dev/null; do
  sleep 2
done
echo "✅ CouchDB is online"

#–– Helper: create a DB only if it doesn't exist ––
create_if_missing() {
  local db="$1"
  local code
  code=$(curl -s -o /dev/null -w "%{http_code}" \
    -u "${ADMIN_USER}:${ADMIN_PASS}" \
    "http://${HOST}:${PORT}/${db}")
  if [[ "$code" -eq 404 ]]; then
    echo "➕ Creating database ${db}"
    curl -s -u "${ADMIN_USER}:${ADMIN_PASS}" \
         -X PUT "http://${HOST}:${PORT}/${db}" \
         && echo "   ✔ ${db} created"
  else
    echo "ℹ️  ${db} exists (HTTP $code), skipping"
  fi
}

#–– Create the three system DBs ––
for SYSDB in _users _replicator _global_changes; do
  create_if_missing "$SYSDB"
done

echo "🎉 Initialization complete."
