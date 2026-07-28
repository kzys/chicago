"""Shared helpers for installing/uninstalling Badgeware apps via disk (MSC) mode.

Imported by install_app.py, uninstall_app.py, and install_secrets.py — not
meant to be run directly.

/system/apps is where the badge's menu actually looks for apps, but it's
mounted read-only over the mpremote/serial connection. The only writable
path into it is disk mode: launching the badge's own mass_storage app
re-exposes the same filesystem as a USB drive, editable like any other disk.
"""

import os
import subprocess
import sys
import time
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
DEVICE = os.environ.get("DEVICE", "/dev/ttyACM0")


def run_mpremote(*args: str) -> subprocess.CompletedProcess:
    return subprocess.run(
        ["uv", "run", "--project", str(PROJECT_ROOT), "mpremote", "connect", DEVICE, *args],
        check=False,
    )


def _lsblk(*columns: str) -> list[list[str]]:
    out = subprocess.run(
        ["lsblk", "-o", ",".join(columns), "-rn"],
        check=True,
        capture_output=True,
        text=True,
    ).stdout
    return [line.split() for line in out.splitlines()]


def _tufty_present() -> bool:
    return any(row and row[-1] == "TUFTY" for row in _lsblk("LABEL"))


def _mpremote_ready() -> bool:
    return (
        subprocess.run(
            ["uv", "run", "--project", str(PROJECT_ROOT), "mpremote", "connect", DEVICE, "exec", "pass"],
            capture_output=True,
        ).returncode
        == 0
    )


def msc_enter() -> None:
    if _tufty_present():
        print("Already in disk mode, skipping launch.", file=sys.stderr)
        return
    print("Entering disk mode...", file=sys.stderr)
    # launch() blocks until the launched app exits (that's how the badge's own
    # main.py uses it to run the menu), so it never returns here on success.
    # Give it a few seconds to trigger USB enumeration, then move on regardless
    # of its exit status — msc_wait_for_mount is the actual success check.
    # -k forces a SIGKILL shortly after SIGTERM: mpremote doesn't reliably
    # respond to SIGTERM while blocked waiting on the launch() call.
    subprocess.run(
        [
            "timeout", "-k", "3", "5",
            "uv", "run", "--project", str(PROJECT_ROOT),
            "mpremote", "connect", DEVICE,
            "exec", "launch('/system/apps/mass_storage')",
        ],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )


def msc_wait_for_mount() -> tuple[str, str]:
    """Returns (block_dev, mount_point) on success, exits the process on failure."""
    block_dev = ""
    for _ in range(20):
        match = next((row for row in _lsblk("NAME", "LABEL") if len(row) == 2 and row[1] == "TUFTY"), None)
        if match:
            block_dev = f"/dev/{match[0]}"
            break
        time.sleep(0.5)
    if not block_dev:
        print("error: TUFTY drive did not appear within 10s", file=sys.stderr)
        raise SystemExit(1)

    # The desktop's own automount daemon (gvfs/udisks) usually mounts new
    # removable media within a second or two on its own. Wait for that instead
    # of racing it with our own `udisksctl mount` call — doing both at once can
    # deadlock against each other.
    mount_point = ""
    for _ in range(10):
        result = subprocess.run(
            ["lsblk", "-no", "MOUNTPOINT", block_dev],
            capture_output=True,
            text=True,
        )
        # A non-zero exit here (rather than just an empty MOUNTPOINT) means
        # block_dev itself is gone — e.g. a previous msc_leave()'s reset only
        # just now took effect. Keep polling instead of raising: it's the
        # same "not mounted yet" state from the caller's point of view.
        mount_point = result.stdout.strip() if result.returncode == 0 else ""
        if mount_point:
            break
        time.sleep(0.5)

    if not mount_point:
        print(f"Not auto-mounted, mounting {block_dev} manually...", file=sys.stderr)
        out = subprocess.run(
            ["udisksctl", "mount", "-b", block_dev, "--no-user-interaction"],
            capture_output=True,
            text=True,
        ).stdout
        marker = " at "
        idx = out.rfind(marker)
        mount_point = out[idx + len(marker):].strip() if idx != -1 else ""

    if not mount_point:
        print(f"error: could not mount {block_dev}", file=sys.stderr)
        raise SystemExit(1)

    print(f"Mounted {block_dev} at {mount_point}", file=sys.stderr)
    return block_dev, mount_point


def msc_leave(block_dev: str) -> None:
    print("Unmounting...", file=sys.stderr)
    subprocess.run(["sync"], check=False)
    for attempt in range(1, 6):
        if subprocess.run(["udisksctl", "unmount", "-b", block_dev]).returncode == 0:
            break
        if attempt == 5:
            print(
                f"error: could not unmount {block_dev} — close any file manager "
                "windows browsing it and try again",
                file=sys.stderr,
            )
            raise SystemExit(1)
        time.sleep(2)
    print("Resetting badge...", file=sys.stderr)
    run_mpremote("reset")

    # reset returns as soon as it's sent the request, well before the badge
    # actually reboots — the TUFTY drive lingers for a moment and the serial
    # port drops out and back during USB re-enumeration. Wait for both to
    # settle so a caller chaining installs (e.g. `make install-all`) doesn't
    # have its next msc_enter() mistake the not-yet-departed drive for still
    # being in disk mode, then race a serial connection that isn't back yet.
    print("Waiting for badge to finish resetting...", file=sys.stderr)
    deadline = time.monotonic() + 10
    while time.monotonic() < deadline and _tufty_present():
        time.sleep(0.5)

    deadline = time.monotonic() + 20
    while time.monotonic() < deadline and not _mpremote_ready():
        time.sleep(1)
