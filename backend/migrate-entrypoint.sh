#!/bin/sh
set -eu

# Commands supplied to `compose run` do not replace an explicit entrypoint.
# Reject them BEFORE any database or runtime access. Diagnostics/tests must
# explicitly choose --entrypoint, or use the isolated release-test launcher.
if [ "$#" -ne 0 ]; then
    echo "migrate: unexpected arguments; use --entrypoint for diagnostics or test-release.ps1" >&2
    exit 64
fi

echo "migrate-entrypoint v0.30.0-hotfix4 uid=$(id -u) gid=$(id -g)"

if [ "$(id -u)" = "0" ]; then
    echo "Migration service refuses to run as root" >&2
    exit 1
fi

if [ -n "${DATABASE_URL_FILE:-}" ] && [ ! -r "$DATABASE_URL_FILE" ]; then
    echo "Migration database secret is not readable by uid $(id -u)" >&2
    exit 1
fi

python -m scripts.wait_for_db
alembic upgrade head
python -m app.seed
exit 0
