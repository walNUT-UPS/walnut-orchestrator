#!/usr/bin/env bash

set -euo pipefail

# Simple launcher for walNUT backend (FastAPI/uvicorn) and frontend (Vite).
#
# Env overrides:
# - BACKEND_HOST (default: 0.0.0.0)
# - BACKEND_PORT (default: 8000)
# - BACKEND_RELOAD=1 to enable uvicorn --reload
# - VITE_PORT (default: 3000)
# - BACKEND_LOG (default: backend.log)
# - FRONTEND_LOG (default: frontend.log)

BACKEND_HOST=${BACKEND_HOST:-0.0.0.0}
BACKEND_PORT=${BACKEND_PORT:-8000}
VITE_PORT=${VITE_PORT:-3000}
BACKEND_LOG=${BACKEND_LOG:-backend.log}
FRONTEND_LOG=${FRONTEND_LOG:-frontend.log}

# Required walNUT env (use provided development secrets)
# These can be overridden by exporting them before calling this script.
export WALNUT_DB_KEY=${WALNUT_DB_KEY:-"test_key_32_characters_minimum_length"}
export WALNUT_JWT_SECRET=${WALNUT_JWT_SECRET:-"your_32_character_jwt_secret_here_abcd"}
export WALNUT_SECURE_COOKIES=${WALNUT_SECURE_COOKIES:-false}
# Allow frontend origins; emit as JSON array for robust parsing
ORIGINS_JSON=${WALNUT_ALLOWED_ORIGINS:-"[\"http://localhost:${VITE_PORT}\",\"http://127.0.0.1:${VITE_PORT}\"]"}
export WALNUT_ALLOWED_ORIGINS="$ORIGINS_JSON"
export WALNUT_LOG_LEVEL=${WALNUT_LOG_LEVEL:-INFO}
export WALNUT_LOG_FORMAT=${WALNUT_LOG_FORMAT:-text}

# Prefer local venv python if available
if [[ -x ".venv/bin/python" ]]; then
  PYTHON=".venv/bin/python"
else
  PYTHON="${PYTHON:-python3}"
fi

echo "walNUT env configured:"
echo "- WALNUT_DB_KEY: (set, length ${#WALNUT_DB_KEY})"
echo "- WALNUT_JWT_SECRET: (set, length ${#WALNUT_JWT_SECRET})"
echo "- WALNUT_SECURE_COOKIES: ${WALNUT_SECURE_COOKIES}"
echo "- WALNUT_ALLOWED_ORIGINS: ${WALNUT_ALLOWED_ORIGINS}"

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

echo "Starting backend (uvicorn) on ${BACKEND_HOST}:${BACKEND_PORT}..."
(
  exec "$PYTHON" -m uvicorn walnut.app:app \
    --host "$BACKEND_HOST" \
    --port "$BACKEND_PORT" \
    ${BACKEND_RELOAD:+--reload}
) >> "$BACKEND_LOG" 2>&1 &
pids+=($!)

echo "Starting frontend (Vite) on port ${VITE_PORT}..."
(
  cd frontend
  export VITE_PORT
  # Run Vite dev server; assumes dependencies are already installed.
  exec npm run dev
) >> "$FRONTEND_LOG" 2>&1 &
pids+=($!)

echo "Servers started. Logs: $BACKEND_LOG (backend), $FRONTEND_LOG (frontend)"
echo "- Backend:  http://localhost:${BACKEND_PORT}"
echo "- Frontend: http://localhost:${VITE_PORT}"
echo "Press Ctrl+C to stop both."

# Wait for any process to exit, then trigger cleanup via trap
wait -n "${pids[@]}" || true
