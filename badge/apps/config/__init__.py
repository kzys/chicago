import json
import network

badge.mode(HIRES)

MARGIN = 12
ROW_H = 30

SECURITY_NAMES = {
    0: "open",
    1: "WEP",
    2: "WPA",
    3: "WPA2",
    4: "WPA/WPA2",
}

# /state/config.json shape: {"networks": {ssid: password, ...}, "selected":
# ssid}. "networks" is managed externally (like secrets.py) rather than
# entered on the badge; "selected" is written by this app -- the SSID last
# connected to here. secrets.py itself reads "selected" back out on import
# to point every other app's wifi.connect() at the same network, so keeping
# it a sibling of "networks" rather than mixed into the same dict means a
# real network can never collide with the reserved key.
KNOWN_NETWORKS_PATH = "/state/config.json"
CONNECT_TIMEOUT_MS = 15000

wlan = network.WLAN(network.STA_IF)
networks = []
known_networks = {}
scroll = 0
error = None

# Connecting is its own little state machine: wlan.connect() just kicks off
# the join, so progress is polled via wlan.isconnected() each frame rather
# than blocking here.
connect_state = None  # None | "connecting" | "connected" | "failed"
connect_ssid = None
connect_started = 0
connect_error = None


def load_known_networks():
    global known_networks
    try:
        with open(KNOWN_NETWORKS_PATH) as f:
            known_networks = json.load(f).get("networks", {})
    except (OSError, ValueError):
        known_networks = {}


def select_network(ssid):
    # MicroPython's json.dump() has no indent= support, so this hand-builds
    # the (fixed, shallow) layout instead -- but still delegates every actual
    # string value to json.dumps() rather than hand-escaping it, so SSIDs or
    # passwords with quotes/backslashes/unicode still come out correct.
    lines = ["{", '  "networks": {']
    items = list(known_networks.items())
    for i, (net_ssid, password) in enumerate(items):
        comma = "," if i < len(items) - 1 else ""
        lines.append("    {}: {}{}".format(json.dumps(net_ssid), json.dumps(password), comma))
    lines.append("  },")
    lines.append('  "selected": {}'.format(json.dumps(ssid)))
    lines.append("}")
    with open(KNOWN_NETWORKS_PATH, "w") as f:
        f.write("\n".join(lines))


def start_connect(ssid):
    global connect_state, connect_ssid, connect_started, connect_error
    password = known_networks.get(ssid)
    connect_ssid = ssid
    try:
        wlan.disconnect()
    except OSError:
        pass
    try:
        wlan.connect(ssid, password)
        connect_state = "connecting"
        connect_started = badge.ticks
        connect_error = None
    except OSError as e:
        connect_state = "failed"
        connect_error = str(e)


def _strength_color(rssi):
    if rssi >= -60:
        return color.green
    if rssi >= -75:
        return color.yellow
    return color.red


def scan():
    global networks, error
    load_known_networks()

    screen.pen = color.navy
    screen.clear()
    screen.font = rom_font.smart
    screen.pen = color.white
    screen.text("Scanning...", MARGIN, MARGIN)
    badge.update()

    try:
        wlan.active(True)
        results = wlan.scan()
        error = None
    except OSError as e:
        results = []
        error = str(e)

    seen = {}
    for ssid, _bssid, channel, rssi, security, _hidden in results:
        name = ssid.decode("utf-8", "replace") or "(hidden)"
        # The same AP's multiple radios/bands show up as separate scan
        # entries sharing an SSID; keep only the strongest one per name.
        if name not in seen or rssi > seen[name][1]:
            seen[name] = (name, rssi, channel, security)
    networks = sorted(seen.values(), key=lambda n: -n[1])


scan()


FOOTER_H = 40


def draw():
    screen.pen = color.navy
    screen.clear()

    screen.font = rom_font.smart
    screen.pen = color.white
    screen.text("WiFi Networks ({})".format(len(networks)), MARGIN, MARGIN)

    if error:
        screen.pen = color.red
        screen.text("Scan failed: {}".format(error), MARGIN, MARGIN + ROW_H)
        return

    y = MARGIN + ROW_H
    for i, (name, rssi, channel, security) in enumerate(networks[scroll:]):
        if y + ROW_H > screen.height - FOOTER_H:
            break

        screen.font = rom_font.smart
        screen.pen = _strength_color(rssi)
        screen.text(("> " if i == 0 else "  ") + name, MARGIN, y)

        screen.font = rom_font.sins
        screen.pen = color.smoke
        meta = "{}dBm  ch{}  {}".format(rssi, channel, SECURITY_NAMES.get(security, "secured"))
        if name in known_networks:
            meta += "  known"
        screen.text(meta, MARGIN, y + 15)

        y += ROW_H

    screen.font = rom_font.sins
    if connect_state == "connecting":
        screen.pen = color.yellow
        screen.text("Connecting to {}...".format(connect_ssid), MARGIN, screen.height - MARGIN - 24)
    elif connect_state == "connected":
        ip = wlan.ifconfig()[0]
        screen.pen = color.green
        screen.text("Connected to {} ({})".format(connect_ssid, ip), MARGIN, screen.height - MARGIN - 24)
    elif connect_state == "failed":
        screen.pen = color.red
        screen.text(
            "Failed to connect to {}: {}".format(connect_ssid, connect_error or "?"),
            MARGIN,
            screen.height - MARGIN - 24,
        )

    screen.pen = color.smoke
    screen.text("A: rescan  C: connect  UP/DOWN: scroll", MARGIN, screen.height - MARGIN - 10)


def update():
    global scroll, connect_state, connect_ssid, connect_error

    if badge.pressed(BUTTON_A):
        scroll = 0
        scan()
    if badge.pressed(BUTTON_DOWN):
        scroll = min(max(0, len(networks) - 1), scroll + 1)
    if badge.pressed(BUTTON_UP):
        scroll = max(0, scroll - 1)
    if badge.pressed(BUTTON_C) and networks:
        selected = networks[scroll][0]
        if selected in known_networks:
            start_connect(selected)
        else:
            connect_state = "failed"
            connect_ssid = selected
            connect_error = "no saved password"

    if connect_state == "connecting":
        if wlan.isconnected():
            connect_state = "connected"
            select_network(connect_ssid)
        elif badge.ticks - connect_started > CONNECT_TIMEOUT_MS:
            connect_state = "failed"
            connect_error = "timed out"

    draw()


run(update)
