#!/usr/bin/env bash
set -euo pipefail

APP_NAME="${1:?usage: install-app.sh <app-name>}"
PROJECT_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
LOCAL_APP_DIR="$PROJECT_ROOT/badge/apps/$APP_NAME"
source "$PROJECT_ROOT/badge/scripts/_msc_common.sh"

if [ ! -d "$LOCAL_APP_DIR" ]; then
  echo "error: $LOCAL_APP_DIR does not exist" >&2
  exit 1
fi

msc_enter
msc_wait_for_mount

echo "Copying $APP_NAME..." >&2
rm -rf "${MOUNT_POINT:?}/apps/$APP_NAME"
mkdir -p "$MOUNT_POINT/apps"
cp -r "$LOCAL_APP_DIR" "$MOUNT_POINT/apps/$APP_NAME"

msc_leave
echo "Installed $APP_NAME." >&2
