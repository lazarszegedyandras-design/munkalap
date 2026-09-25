#!/bin/sh
set -eu
ROOT_DIR=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
exec python3 "$ROOT_DIR/scripts/release_tests.py" "$@"
