#!/bin/bash
# entrypoint.sh

# Example: you can add pre-run logic here, like echoing args, setting defaults, etc.
echo "Starting main.py with args: $@"

# Run your Python script with all passed arguments
python3 main.py "$@"