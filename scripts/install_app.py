#!/usr/bin/env python3
import argparse
import shutil
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import _msc_common as msc  # noqa: E402
import _order_common as order  # noqa: E402


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("app_name")
    args = parser.parse_args()

    local_app_dir = msc.PROJECT_ROOT / "badge" / "apps" / args.app_name
    if not local_app_dir.is_dir():
        print(f"error: {local_app_dir} does not exist", file=sys.stderr)
        raise SystemExit(1)

    device_app_name = order.device_name(args.app_name)

    msc.msc_enter()
    block_dev, mount_point = msc.msc_wait_for_mount()

    print(f"Copying {args.app_name} as {device_app_name}...", file=sys.stderr)
    apps_dir = Path(mount_point) / "apps"
    apps_dir.mkdir(parents=True, exist_ok=True)
    order.remove_existing_device_dirs(apps_dir, args.app_name)
    shutil.copytree(local_app_dir, apps_dir / device_app_name)

    msc.msc_leave(block_dev)
    print(f"Installed {args.app_name}.", file=sys.stderr)


if __name__ == "__main__":
    main()
