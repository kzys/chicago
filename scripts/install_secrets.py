#!/usr/bin/env python3
import argparse
import shutil
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import _msc_common as msc  # noqa: E402


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("local_file")
    args = parser.parse_args()

    local_file = Path(args.local_file)
    if not local_file.is_file():
        print(f"error: {local_file} does not exist", file=sys.stderr)
        raise SystemExit(1)

    msc.msc_enter()
    block_dev, mount_point = msc.msc_wait_for_mount()

    print("Copying secrets.py...", file=sys.stderr)
    shutil.copy(local_file, Path(mount_point) / "secrets.py")

    msc.msc_leave(block_dev)
    print("Installed secrets.py.", file=sys.stderr)


if __name__ == "__main__":
    main()
