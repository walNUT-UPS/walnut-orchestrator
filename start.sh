#!/usr/bin/env bash

set -euo pipefail

# Simple launcher for walNUT backend (FastAPI/uvicorn) and frontend (Vite).
#
# Env overrides:
# - BACKEND_HOST (default: 0.0.0.0)
# - BACKEND_PORT (default: 8000)
# - BACKEND_RELOAD=1 to enable uvicorn --reload
# - VITE_PORT (default: 3000)
# - BACKEND_LOG (default: .tmp/back.log)
# - FRONTEND_LOG (default: .tmp/front.log)

BACKEND_HOST=${BACKEND_HOST:-0.0.0.0}
BACKEND_PORT=${BACKEND_PORT:-8000}
VITE_PORT=${VITE_PORT:-3000}
BACKEND_LOG=${BACKEND_LOG:-.tmp/back.log}
FRONTEND_LOG=${FRONTEND_LOG:-.tmp/front.log}
# Set to 1 to skip launching Vite frontend (backend-only mode)
NO_FRONTEND=${NO_FRONTEND:-0}

# Required walNUT env (use provided development secrets)
# These can be overridden by exporting them before calling this script.
export WALNUT_DB_KEY=${WALNUT_DB_KEY:-"dev_dev_dev_dev_dev_dev_dev_dev_32chars"}
export WALNUT_JWT_SECRET=${WALNUT_JWT_SECRET:-"test_jwt_secret_32_characters_long_12345"}
export WALNUT_SECURE_COOKIES=${WALNUT_SECURE_COOKIES:-false}
export WALNUT_POLICY_V1_ENABLED=${WALNUT_POLICY_V1_ENABLED:-true}
# Allow frontend origins; emit as JSON array for robust parsing
ORIGINS_JSON=${WALNUT_ALLOWED_ORIGINS:-"[\"http://localhost:${VITE_PORT}\",\"http://127.0.0.1:${VITE_PORT}\"]"}
export WALNUT_ALLOWED_ORIGINS="$ORIGINS_JSON"
export WALNUT_LOG_LEVEL=${WALNUT_LOG_LEVEL:-INFO}
export WALNUT_LOG_FORMAT=${WALNUT_LOG_FORMAT:-text}

# Prefer local venv python if available
if [[ -x "./venv/bin/python" ]]; then
  PYTHON="./venv/bin/python"
elif [[ -x ".venv/bin/python" ]]; then
  PYTHON=".venv/bin/python"
else
  PYTHON="${PYTHON:-python3}"
fi

echo "walNUT env configured:"
echo "- WALNUT_DB_KEY: (set, length ${#WALNUT_DB_KEY})"
echo "- WALNUT_JWT_SECRET: (set, length ${#WALNUT_JWT_SECRET})"
echo "- WALNUT_SECURE_COOKIES: ${WALNUT_SECURE_COOKIES}"
echo "- WALNUT_ALLOWED_ORIGINS: ${WALNUT_ALLOWED_ORIGINS}"
echo "- WALNUT_POLICY_V1_ENABLED: ${WALNUT_POLICY_V1_ENABLED}"

pids=()

cleanup() {
  echo "\nShutting down servers..."
  for pid in "${pids[@]:-}"; do
    if [[ -n "${pid}" ]] && kill -0 "$pid" 2>/dev/null; then
      kill "$pid" 2>/dev/null || true
      wait "$pid" 2>/dev/null || true
    fi
  done
}

trap cleanup INT TERM EXIT

# Create .tmp directory if it doesn't exist
mkdir -p .tmp

echo "Starting backend (uvicorn) on ${BACKEND_HOST}:${BACKEND_PORT}..."
(
  exec "$PYTHON" -m uvicorn walnut.app:app \
    --host "$BACKEND_HOST" \
    --port "$BACKEND_PORT" \
    ${BACKEND_RELOAD:+--reload}
) &> "$BACKEND_LOG" &
pids+=($!)

# Provide a restart command for backend to exec when /api/system/restart is called
export WALNUT_RESTART_CMD="${PYTHON} -m uvicorn walnut.app:app --host ${BACKEND_HOST} --port ${BACKEND_PORT} ${BACKEND_RELOAD:+--reload}"

if [[ "$NO_FRONTEND" != "1" ]]; then
  echo "Starting frontend (Vite) on port ${VITE_PORT}..."
  (
    cd frontend
    export VITE_PORT
    # Run Vite dev server; assumes dependencies are already installed.
    exec npm run dev
  ) &> "../$FRONTEND_LOG" &
  pids+=($!)
  echo "Servers started. Logs: $BACKEND_LOG (backend), $FRONTEND_LOG (frontend)"
  echo "- Backend:  http://localhost:${BACKEND_PORT}"
  echo "- Frontend: http://localhost:${VITE_PORT}"
  echo "Press Ctrl+C to stop both."
else
  echo "Backend started (frontend disabled by NO_FRONTEND=1). Log: $BACKEND_LOG"
  echo "- Backend:  http://localhost:${BACKEND_PORT}"
fi

# Wait for any process to exit, then trigger cleanup via trap
wait -n "${pids[@]}" || true
