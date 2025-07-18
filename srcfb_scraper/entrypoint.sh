#!/bin/bash
# entrypoint.sh
set -e

# Example: you can add pre-run logic here, like echoing args, setting defaults, etc.
echo "Starting main.py with args: $@"

# Run your Python script with all passed arguments
export STORAGE_MODE=couchdb
python3 main.py "$@"