# Shared helpers for installing/uninstalling Badgeware apps via disk (MSC) mode.
# Sourced by install-app.sh and uninstall-app.sh — not meant to be run directly.
#
# /system/apps is where the badge's menu actually looks for apps, but it's
# mounted read-only over the mpremote/serial connection. The only writable
# path into it is disk mode: launching the badge's own mass_storage app
# re-exposes the same filesystem as a USB drive, editable like any other disk.

: "${DEVICE:=/dev/ttyACM0}"

msc_run_mpremote() {
  uv run --project "$PROJECT_ROOT" mpremote connect "$DEVICE" "$@"
}

msc_enter() {
  if lsblk -o LABEL -rn | grep -qx "TUFTY"; then
    echo "Already in disk mode, skipping launch." >&2
    return 0
  fi
  echo "Entering disk mode..." >&2
  # launch() blocks until the launched app exits (that's how the badge's own
  # main.py uses it to run the menu), so it never returns here on success.
  # Give it a few seconds to trigger USB enumeration, then move on regardless
  # of its exit status — msc_wait_for_mount is the actual success check.
  # -k forces a SIGKILL shortly after SIGTERM: mpremote doesn't reliably
  # respond to SIGTERM while blocked waiting on the launch() call.
  timeout -k 3 5 uv run --project "$PROJECT_ROOT" mpremote connect "$DEVICE" exec "launch('/system/apps/mass_storage')" >/dev/null 2>&1 || true
}

# Sets BLOCK_DEV and MOUNT_POINT on success.
msc_wait_for_mount() {
  local block_dev="" mount_point=""
  for _ in $(seq 1 20); do
    block_dev=$(lsblk -o NAME,LABEL -rn | awk '$2=="TUFTY"{print $1; exit}')
    [ -n "$block_dev" ] && break
    sleep 0.5
  done
  if [ -z "$block_dev" ]; then
    echo "error: TUFTY drive did not appear within 10s" >&2
    return 1
  fi
  block_dev="/dev/$block_dev"

  # The desktop's own automount daemon (gvfs/udisks) usually mounts new
  # removable media within a second or two on its own. Wait for that instead
  # of racing it with our own `udisksctl mount` call — doing both at once can
  # deadlock against each other.
  for _ in $(seq 1 10); do
    mount_point=$(lsblk -no MOUNTPOINT "$block_dev")
    [ -n "$mount_point" ] && break
    sleep 0.5
  done
  if [ -z "$mount_point" ]; then
    echo "Not auto-mounted, mounting $block_dev manually..." >&2
    mount_point=$(udisksctl mount -b "$block_dev" --no-user-interaction | sed -n 's/.*at //p')
  fi
  if [ -z "$mount_point" ]; then
    echo "error: could not mount $block_dev" >&2
    return 1
  fi

  BLOCK_DEV="$block_dev"
  MOUNT_POINT="$mount_point"
  echo "Mounted $BLOCK_DEV at $MOUNT_POINT" >&2
}

msc_leave() {
  echo "Unmounting..." >&2
  sync
  local attempt
  for attempt in $(seq 1 5); do
    if udisksctl unmount -b "$BLOCK_DEV" 2>&1; then
      break
    fi
    if [ "$attempt" = 5 ]; then
      echo "error: could not unmount $BLOCK_DEV — close any file manager windows browsing it and try again" >&2
      return 1
    fi
    sleep 2
  done
  echo "Resetting badge..." >&2
  msc_run_mpremote reset
}
