#!/bin/sh
set -eu
ROOT_DIR=$(CDPATH= cd -- "$(dirname -- "$0")/../.." && pwd)
# Destructive privilege/ownership fixtures must NEVER run on a live database.
# This alias checks fresh and upgraded DISPOSABLE PostgreSQL 16 instances.
exec python3 "$ROOT_DIR/scripts/release_tests.py" --suite pg "$@"
