#!/bin/bash
# run.sh — start Raspi Status (with manage.py inside /statuspi)

set -e

# Resolve paths
PROJECT_DIR="$(cd "$(dirname "$0")" && pwd)"
VENV="$PROJECT_DIR/env"
APP_DIR="$PROJECT_DIR/statuspi"
PORT=${PORT:-8123}

# Check venv
if [ ! -d "$VENV" ]; then
  echo "❌ Virtual environment not found!"
  echo "Run: python3 -m venv env && source env/bin/activate && pip install -r requirements.txt"
  exit 1
fi

# Activate environment
source "$VENV/bin/activate"

# Go into project directory
cd "$APP_DIR"

# Apply migrations 
python manage.py migrate --noinput >/dev/null 2>&1 || true

# Collect static files 
python manage.py collectstatic --noinput >/dev/null 2>&1 || true

# Run Django dev server
echo "🚀 Starting Raspi Status at http://0.0.0.0:$PORT ..."
python manage.py runserver 0.0.0.0:$PORT
