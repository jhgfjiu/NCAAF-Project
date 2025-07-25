#!/bin/bash
# entrypoint.sh
set -e

echo "Waiting for CouchDB to start..."
until curl --silent --fail "http://couchdb:5984/"; do
  echo "CouchDB unavailable - retrying in 3 seconds..."
  sleep 3
done
echo "CouchDB is ready."

# Example: you can add pre-run logic here, like echoing args, setting defaults, etc.
echo "Starting main.py with args: $@"

# Run your Python script with all passed arguments
export STORAGE_MODE=couchdb
python3 main.py "$@"