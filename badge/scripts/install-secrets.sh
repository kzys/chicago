#!/usr/bin/env bash
set -euo pipefail

LOCAL_FILE="${1:?usage: install-secrets.sh <path-to-secrets.py>}"
PROJECT_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
source "$PROJECT_ROOT/badge/scripts/_msc_common.sh"

if [ ! -f "$LOCAL_FILE" ]; then
  echo "error: $LOCAL_FILE does not exist" >&2
  exit 1
fi

msc_enter
msc_wait_for_mount

echo "Copying secrets.py..." >&2
cp "$LOCAL_FILE" "$MOUNT_POINT/secrets.py"

msc_leave
echo "Installed secrets.py." >&2
