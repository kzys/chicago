#!/usr/bin/env bash
set -euo pipefail

APP_NAME="${1:?usage: uninstall-app.sh <app-name>}"
PROJECT_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
source "$PROJECT_ROOT/badge/scripts/_msc_common.sh"

msc_enter
msc_wait_for_mount

echo "Removing $APP_NAME..." >&2
rm -rf "${MOUNT_POINT:?}/apps/$APP_NAME"

msc_leave
echo "Uninstalled $APP_NAME." >&2
