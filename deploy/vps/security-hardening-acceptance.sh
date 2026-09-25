#!/bin/sh
set -eu
ROOT_DIR=$(CDPATH= cd -- "$(dirname -- "$0")/../.." && pwd)
# Historical entry point now launches only isolated tests. It NEVER reads
# .env.production, runs a live migration, or invokes a destructive restore.
# A test PASS is not SECURITY/PRODUCTION GO. Other security gates remain open.
exec python3 "$ROOT_DIR/scripts/release_tests.py" --suite all "$@"
