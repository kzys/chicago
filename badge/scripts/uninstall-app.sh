#!/usr/bin/env bash
set -euo pipefail

APP_NAME="${1:?usage: uninstall-app.sh <app-name>}"
PROJECT_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
source "$PROJECT_ROOT/badge/scripts/_msc_common.sh"
source "$PROJECT_ROOT/badge/scripts/_order_common.sh"

msc_enter
msc_wait_for_mount

echo "Removing $APP_NAME..." >&2
remove_existing_device_dirs "$APP_NAME"

msc_leave
echo "Uninstalled $APP_NAME." >&2
