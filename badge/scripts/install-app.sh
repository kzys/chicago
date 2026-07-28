#!/usr/bin/env bash
set -euo pipefail

APP_NAME="${1:?usage: install-app.sh <app-name>}"
PROJECT_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
LOCAL_APP_DIR="$PROJECT_ROOT/badge/apps/$APP_NAME"
source "$PROJECT_ROOT/badge/scripts/_msc_common.sh"
source "$PROJECT_ROOT/badge/scripts/_order_common.sh"

if [ ! -d "$LOCAL_APP_DIR" ]; then
  echo "error: $LOCAL_APP_DIR does not exist" >&2
  exit 1
fi

DEVICE_APP_NAME="$(order_device_name "$APP_NAME")"

msc_enter
msc_wait_for_mount

echo "Copying $APP_NAME as $DEVICE_APP_NAME..." >&2
mkdir -p "$MOUNT_POINT/apps"
remove_existing_device_dirs "$APP_NAME"
cp -r "$LOCAL_APP_DIR" "$MOUNT_POINT/apps/$DEVICE_APP_NAME"

msc_leave
echo "Installed $APP_NAME." >&2
