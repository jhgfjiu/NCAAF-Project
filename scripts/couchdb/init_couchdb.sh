#!/usr/bin/env bash
set -euo pipefail

HOST="${COUCHDB_HOST:-couchdb}"
PORT="${COUCHDB_PORT:-5984}"
ADMIN_USER="${COUCHDB_USER:-admin}"
ADMIN_PASS="${COUCHDB_PASSWORD:-password}"

echo "Waiting for CouchDB at http://${HOST}:${PORT}…"

until curl -s -o /dev/null -w "%{http_code}" \
    -u "${ADMIN_USER}:${ADMIN_PASS}" \
    "http://${HOST}:${PORT}/" | grep -q "200"; do
  echo "Waiting for CouchDB to be ready..."
  sleep 2
done

echo "CouchDB is online"

create_if_missing() {
  local db="$1"
  local code
  code=$(curl -s -o /dev/null -w "%{http_code}" \
    -u "${ADMIN_USER}:${ADMIN_PASS}" \
    "http://${HOST}:${PORT}/${db}")
  if [[ "$code" -eq 404 ]]; then
    echo "Creating database ${db}"
    curl -s -u "${ADMIN_USER}:${ADMIN_PASS}" \
         -X PUT "http://${HOST}:${PORT}/${db}" \
         && echo "${db} created"
  else
    echo "${db} exists (HTTP $code), skipping"
  fi
}

for SYSDB in _users _replicator _global_changes; do
  create_if_missing "$SYSDB"
done

echo "Initialization complete."