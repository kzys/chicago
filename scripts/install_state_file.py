#!/usr/bin/env python3
"""Copies a local file to /state/<remote_name> on the device.

Unlike install_secrets.py, this doesn't go through disk (MSC) mode: /state
is a separate area from /system (which is what MSC mode exposes) and, unlike
/system, is already writable over the regular serial connection.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import _msc_common as msc  # noqa: E402


def main() -> None:
    if len(sys.argv) != 3:
        print("usage: install_state_file.py <local_file> <remote_name>", file=sys.stderr)
        raise SystemExit(1)

    local_file = Path(sys.argv[1])
    remote_name = sys.argv[2]
    if not local_file.is_file():
        print(f"error: {local_file} does not exist", file=sys.stderr)
        raise SystemExit(1)

    print(f"Copying {remote_name}...", file=sys.stderr)
    result = msc.run_mpremote("fs", "cp", str(local_file), f":/state/{remote_name}")
    if result.returncode != 0:
        raise SystemExit(result.returncode)

    print(f"Installed {remote_name}.", file=sys.stderr)


if __name__ == "__main__":
    main()
