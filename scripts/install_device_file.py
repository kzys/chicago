#!/usr/bin/env python3
"""Copies a local file to an absolute path on the device.

Doesn't go through disk (MSC) mode: unlike /system, both /state and /lib
are writable over the regular serial connection. /lib doesn't exist on a
fresh device (unlike /state), so this creates the target's parent
directory first if needed.
"""
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import _msc_common as msc  # noqa: E402


def main() -> None:
    if len(sys.argv) != 3:
        print("usage: install_device_file.py <local_file> <remote_path>", file=sys.stderr)
        raise SystemExit(1)

    local_file = Path(sys.argv[1])
    remote_path = sys.argv[2]
    if not local_file.is_file():
        print(f"error: {local_file} does not exist", file=sys.stderr)
        raise SystemExit(1)
    if not remote_path.startswith("/"):
        print(f"error: remote path must be absolute, got {remote_path!r}", file=sys.stderr)
        raise SystemExit(1)

    remote_dir = remote_path.rsplit("/", 1)[0] or "/"
    subprocess.run(
        ["uv", "run", "--project", str(msc.PROJECT_ROOT), "mpremote", "connect", msc.DEVICE, "fs", "mkdir", f":{remote_dir}"],
        capture_output=True,  # silence "File exists" -- expected on every run after the first
    )

    print(f"Copying {remote_path}...", file=sys.stderr)
    result = msc.run_mpremote("fs", "cp", str(local_file), f":{remote_path}")
    if result.returncode != 0:
        raise SystemExit(result.returncode)

    print(f"Installed {remote_path}.", file=sys.stderr)


if __name__ == "__main__":
    main()
