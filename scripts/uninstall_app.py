#!/usr/bin/env python3
import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import _msc_common as msc  # noqa: E402
import _order_common as order  # noqa: E402


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("app_name")
    args = parser.parse_args()

    msc.msc_enter()
    block_dev, mount_point = msc.msc_wait_for_mount()

    print(f"Removing {args.app_name}...", file=sys.stderr)
    order.remove_existing_device_dirs(Path(mount_point) / "apps", args.app_name)

    msc.msc_leave(block_dev)
    print(f"Uninstalled {args.app_name}.", file=sys.stderr)


if __name__ == "__main__":
    main()
