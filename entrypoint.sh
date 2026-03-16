#!/bin/bash
# Exit on any error
set -e

echo "Starting Pipeline..."
python3 /app/converter.py

echo "Starting Integrity Check..."
python3 /app/check.py

echo "Pipeline Finished Successfully."
