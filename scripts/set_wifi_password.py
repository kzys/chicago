#!/usr/bin/env python3
"""Sets (or updates) a single network's password in a local config.json, in
the format the badge's config app reads from /state/config.json (see
badge/apps/config). Complements provision_wifi_json.py's bulk extraction
from NetworkManager -- for networks that aren't saved there at all (guest
wifi, hotel networks, anything you just want to type in once).

    python3 scripts/set_wifi_password.py "Some SSID"
    make install-config-state FILE=config.json

Prompts for the password rather than taking it as an argument, so it
doesn't end up in shell history or a process listing. Any other keys
already in the file (e.g. "selected", or other networks) are left alone.
"""
import argparse
import getpass
import json
import sys
from pathlib import Path


def main() -> None:
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument("ssid")
    parser.add_argument("-f", "--file", default="config.json", help="local config.json path")
    args = parser.parse_args()

    path = Path(args.file)
    data = json.loads(path.read_text()) if path.is_file() else {}
    data.setdefault("networks", {})

    password = getpass.getpass(f"Password for {args.ssid!r}: ")
    data["networks"][args.ssid] = password

    path.write_text(json.dumps(data, indent=2))
    print(f"Set password for {args.ssid!r} in {path}", file=sys.stderr)


if __name__ == "__main__":
    main()
