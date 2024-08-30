#!/bin/bash

# Set path to the src folder
export PYTHONPATH=$PYTHONPATH:$(pwd)/src

if [ -z "$ENABLED_MODULES" ]; then
  echo "No modules enabled in the .env file."
  exit 1
fi

# Convert the comma-separated list into an array
IFS=',' read -ra MODULES <<< "$ENABLED_MODULES"

# Loop through the array and run each module in the background
for module in "${MODULES[@]}"; do
  echo "Running $module..."
  python3 -m "$module" &
done

# Wait for all background processes to finish
wait
