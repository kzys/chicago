#!/usr/bin/env python3
"""Reads saved WiFi credentials from NetworkManager (via nmcli, which pulls
secrets out of the GNOME keyring) and writes them as {"networks": {ssid:
password, ...}} to a local JSON file, in the format the badge's config app
reads from /state/config.json (see badge/apps/config).

This reads your saved WiFi passwords, so run it yourself rather than having
an agent run it on your behalf -- e.g.:

    python3 scripts/provision_wifi_json.py -o config.json
    make install-config-state FILE=config.json

Networks with no simple pre-shared key (open networks, 802.1X/enterprise
auth) are skipped rather than written with an empty password.

Note this overwrites /state/config.json wholesale, including whichever
network the config app had "selected" -- you'll need to reselect one after
installing.
"""
import argparse
import json
import subprocess
import sys

WIFI_TYPES = ("802-11-wireless", "wifi")


def nmcli(*args: str) -> str:
    result = subprocess.run(["nmcli", *args], capture_output=True, text=True)
    return result.stdout.strip()


def main() -> None:
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument("-o", "--output", default="config.json", help="local output path")
    args = parser.parse_args()

    # Connection *names* aren't unique -- nmcli happily lets you have two
    # profiles both named "manchego" -- so looking a connection up by name
    # is ambiguous and nmcli concatenates the field from every match (which
    # is what produced doubled-up values here). UUIDs are always unique.
    connection_uuids = []
    for line in nmcli("-t", "-f", "UUID,TYPE", "connection", "show").splitlines():
        uuid, _, conn_type = line.rpartition(":")
        if conn_type in WIFI_TYPES:
            connection_uuids.append(uuid)

    networks = {}
    skipped = []
    for uuid in connection_uuids:
        ssid = nmcli("-g", "802-11-wireless.ssid", "connection", "show", uuid) or uuid
        psk = nmcli("-s", "-g", "802-11-wireless-security.psk", "connection", "show", uuid)
        if psk:
            networks[ssid] = psk
        else:
            skipped.append(ssid)

    with open(args.output, "w") as f:
        json.dump({"networks": networks}, f, indent=2)

    print(f"Wrote {len(networks)} network(s) to {args.output}", file=sys.stderr)
    if skipped:
        print(
            f"Skipped {len(skipped)} network(s) with no simple PSK (open/enterprise auth): "
            + ", ".join(skipped),
            file=sys.stderr,
        )


if __name__ == "__main__":
    main()
