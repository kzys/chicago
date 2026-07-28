# Shared helpers for mapping local (unprefixed) app directory names to the
# numbered directory names installed on-device. See badge/apps/order.txt for
# why this indirection exists.
#
# Sourced by install-app.sh and uninstall-app.sh — not meant to be run
# directly. Requires PROJECT_ROOT to already be set by the caller.

ORDER_FILE="$PROJECT_ROOT/badge/apps/order.txt"

# Prints the on-device directory name for a local app name, e.g.
# "chat" -> "02_chat", based on its 1-based position in order.txt.
order_device_name() {
  local app_name="$1" idx=0 line
  while IFS= read -r line || [ -n "$line" ]; do
    [ -z "$line" ] && continue
    case "$line" in
      \#*) continue ;;
    esac
    idx=$((idx + 1))
    if [ "$line" = "$app_name" ]; then
      printf "%02d_%s\n" "$idx" "$app_name"
      return 0
    fi
  done < "$ORDER_FILE"
  echo "error: '$app_name' is not listed in $ORDER_FILE" >&2
  return 1
}

# Removes any on-device copy of an app, under its unprefixed name or any
# numbered prefix — so a stale prefix from a previous order.txt doesn't
# linger as a duplicate menu entry after reordering.
remove_existing_device_dirs() {
  local app_name="$1" d
  rm -rf "${MOUNT_POINT:?}/apps/$app_name"
  for d in "$MOUNT_POINT"/apps/*_"$app_name"; do
    [ -e "$d" ] && rm -rf "$d"
  done
}
