#!/bin/sh
set -eu

# Commands supplied to `compose run` do not replace an explicit entrypoint.
# Reject them BEFORE any database or runtime access. Diagnostics/tests must
# explicitly choose --entrypoint, or use the isolated release-test launcher.
if [ "$#" -ne 0 ]; then
    echo "backend: unexpected arguments; use --entrypoint for diagnostics or test-release.ps1" >&2
    exit 64
fi

echo "backend-entrypoint v0.30.0-hotfix5 uid=$(id -u) gid=$(id -g)"

if [ "$(id -u)" = "0" ]; then
    echo "Backend refuses to run as root" >&2
    exit 1
fi

RUNTIME_DIR_VALUE=${RUNTIME_DIR:-/app/runtime}
[ -d "$RUNTIME_DIR_VALUE" ] || { echo "Runtime directory is missing: $RUNTIME_DIR_VALUE" >&2; exit 1; }
[ -w "$RUNTIME_DIR_VALUE" ] || { echo "Runtime directory is not writable by uid $(id -u): $RUNTIME_DIR_VALUE" >&2; exit 1; }

python -m scripts.wait_for_db
exec uvicorn app.main:app --host 0.0.0.0 --port 8000 --workers "${BACKEND_WORKERS:-3}" --no-proxy-headers
