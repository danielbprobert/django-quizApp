#!/usr/bin/env bash
set -Eeuo pipefail

# --- Auto-detect project root (where this script lives) ---
APP_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
VENV_DIR="$APP_DIR/venv"
MANAGE_PY="$APP_DIR/manage.py"
SERVICE_APP="quizapp"
SERVICE_WEB="nginx"
# -----------------------------------------------------------

cd "$APP_DIR"

echo "[$(date)] Pulling latest code…"
git pull --rebase --autostash

# Activate virtual environment
if [[ -f "$VENV_DIR/bin/activate" ]]; then
  # shellcheck disable=SC1090
  source "$VENV_DIR/bin/activate"
else
  echo "❌ Virtualenv not found at: $VENV_DIR" >&2
  exit 1
fi

# Always deactivate on exit
deactivate_venv() { deactivate || true; }
trap deactivate_venv EXIT

# Django management commands
python "$MANAGE_PY" migrate --noinput
python "$MANAGE_PY" collectstatic --noinput

# Restart services
SUDO=""
if [[ "$(id -u)" -ne 0 ]] && command -v sudo >/dev/null 2>&1; then
  SUDO="sudo"
fi

echo "[$(date)] Restarting services…"
$SUDO systemctl restart "$SERVICE_APP"
$SUDO systemctl restart "$SERVICE_WEB"

echo "[$(date)] ✅ Deployment complete."