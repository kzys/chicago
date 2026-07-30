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

wlan = network.WLAN(network.STA_IF)
networks = []
scroll = 0
error = None


def _strength_color(rssi):
    if rssi >= -60:
        return color.green
    if rssi >= -75:
        return color.yellow
    return color.red


def scan():
    global networks, error
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
    for name, rssi, channel, security in networks[scroll:]:
        if y + ROW_H > screen.height - ROW_H:
            break

        screen.font = rom_font.smart
        screen.pen = _strength_color(rssi)
        screen.text(name, MARGIN, y)

        screen.font = rom_font.sins
        screen.pen = color.smoke
        meta = "{}dBm  ch{}  {}".format(rssi, channel, SECURITY_NAMES.get(security, "secured"))
        screen.text(meta, MARGIN, y + 15)

        y += ROW_H

    screen.font = rom_font.sins
    screen.pen = color.smoke
    screen.text("A: rescan  UP/DOWN: scroll", MARGIN, screen.height - MARGIN - 10)


def update():
    global scroll

    if badge.pressed(BUTTON_A):
        scroll = 0
        scan()
    if badge.pressed(BUTTON_DOWN):
        scroll = min(max(0, len(networks) - 1), scroll + 1)
    if badge.pressed(BUTTON_UP):
        scroll = max(0, scroll - 1)

    draw()


run(update)
