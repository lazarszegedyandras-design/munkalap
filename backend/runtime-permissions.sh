#!/bin/sh
set -eu

TARGET=${RUNTIME_DIR:-/app/runtime}
APP_UID=${APP_RUNTIME_UID:-10001}
APP_GID=${APP_RUNTIME_GID:-10001}

case "$APP_UID:$APP_GID" in
    *[!0-9:]*|:|:*|*:)
        echo "Invalid APP_RUNTIME_UID/APP_RUNTIME_GID" >&2
        exit 1
        ;;
esac

if [ "$(id -u)" != "0" ]; then
    echo "runtime-permissions must run as root inside its isolated one-shot container" >&2
    exit 1
fi

if [ ! -d "$TARGET" ]; then
    echo "Runtime volume mount is missing: $TARGET" >&2
    exit 1
fi

echo "runtime-permissions v0.30.0-hotfix5 target=$TARGET owner=$APP_UID:$APP_GID"
chown -R "$APP_UID:$APP_GID" "$TARGET"
chmod -R u+rwX "$TARGET"
chmod u+rwx "$TARGET"

ACTUAL_UID=$(stat -c '%u' "$TARGET")
ACTUAL_GID=$(stat -c '%g' "$TARGET")
if [ "$ACTUAL_UID" != "$APP_UID" ] || [ "$ACTUAL_GID" != "$APP_GID" ]; then
    echo "Runtime volume ownership repair failed: got $ACTUAL_UID:$ACTUAL_GID" >&2
    exit 1
fi

echo "Runtime volume permissions ready for uid=$APP_UID gid=$APP_GID"
