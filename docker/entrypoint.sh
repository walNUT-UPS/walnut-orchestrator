#!/usr/bin/env sh
set -e

# Ensure WALNUT_DB_KEY is set and strong enough; the app will also enforce it,
# but this gives a clearer early error.
if [ -z "${WALNUT_DB_KEY}" ]; then
  echo "ERROR: WALNUT_DB_KEY is not set. It must be >=32 chars (SQLCipher key)." >&2
  exit 1
fi
if [ ${#WALNUT_DB_KEY} -lt 32 ]; then
  echo "ERROR: WALNUT_DB_KEY must be >=32 characters." >&2
  exit 1
fi

# Provide sensible defaults
export HOST="${HOST:-0.0.0.0}"
export PORT="${PORT:-8000}"

exec "$@"

