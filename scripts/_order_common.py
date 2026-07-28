"""Shared helpers for mapping local (unprefixed) app directory names to the
numbered directory names installed on-device. See badge/apps/order.txt for
why this indirection exists.

Imported by install_app.py and uninstall_app.py — not meant to be run
directly.
"""

import shutil
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
ORDER_FILE = PROJECT_ROOT / "badge/apps/order.txt"


def device_name(app_name: str) -> str:
    """Returns the on-device directory name for a local app name, e.g.
    "chat" -> "02_chat", based on its 1-based position in order.txt."""
    idx = 0
    for line in ORDER_FILE.read_text().splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        idx += 1
        if line == app_name:
            return f"{idx:02d}_{app_name}"
    print(f"error: '{app_name}' is not listed in {ORDER_FILE}", file=sys.stderr)
    raise SystemExit(1)


def remove_existing_device_dirs(apps_dir: Path, app_name: str) -> None:
    """Removes any on-device copy of an app, under its unprefixed name or any
    numbered prefix — so a stale prefix from a previous order.txt doesn't
    linger as a duplicate menu entry after reordering."""
    shutil.rmtree(apps_dir / app_name, ignore_errors=True)
    for path in apps_dir.glob(f"*_{app_name}"):
        shutil.rmtree(path, ignore_errors=True)
