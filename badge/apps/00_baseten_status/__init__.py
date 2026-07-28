from datetime import datetime, timezone

import wifi
import requests
import secrets

STATUS_URL = "https://status.baseten.co/api/v2/summary.json"
INCIDENTS_URL = "https://status.baseten.co/api/v2/incidents.json"
STATUS_REFRESH_SECONDS = 60
INCIDENTS_REFRESH_SECONDS = 1800

STATUS_COLORS = {
    "operational": color.green,
    "degraded_performance": color.yellow,
    "partial_outage": color.orange,
    "major_outage": color.red,
    "under_maintenance": color.blue,
}

# Statuspage incident impact levels, worst to best, mapped to a severity rank
# used to pick the loudest color for a history bucket that had more than one.
IMPACT_RANK = {"critical": 3, "major": 2, "minor": 1, "none": 0}
IMPACT_COLORS = {3: color.red, 2: color.red, 1: color.yellow}

# The public Statuspage API has no daily-uptime endpoint (that data is only
# server-rendered into the status page's HTML), so instead of scraping we
# bucket the last 90 days of *incidents* ourselves from /api/v2/incidents.json,
# which is a normal documented, unauthenticated endpoint. One bucket per day,
# rendered at one pixel per day.
HISTORY_DAYS = 90
DAY_WIDTH = 3
DAY_BAR_WIDTH = 2
MARGIN = 4
ROW_HEIGHT = 31

SPINNER = "-/|\\"
SPINNER_FRAME_MS = 150

_CUM_DAYS = (0, 31, 59, 90, 120, 151, 181, 212, 243, 273, 304, 334)


def _is_leap(y):
    return y % 4 == 0 and (y % 100 != 0 or y % 400 == 0)


def _ordinal(y, m, d):
    days = y * 365 + y // 4 - y // 100 + y // 400
    days += _CUM_DAYS[m - 1]
    if m > 2 and _is_leap(y):
        days += 1
    return days + d


def _days_ago(iso_date, today_ordinal):
    # Only the "YYYY-MM-DD" prefix is used — the incident timestamps carry
    # their own UTC offsets, but at day-level bucket width that precision
    # doesn't matter, and skipping it avoids fiddly timezone-offset math.
    y = int(iso_date[0:4])
    m = int(iso_date[5:7])
    d = int(iso_date[8:10])
    return today_ordinal - _ordinal(y, m, d)


badge.mode(HIRES)
screen.font = rom_font.nope

components = []
overall = None
overall_ok = True
status_last_fetch = None
status_error = None

# component id -> list[HISTORY_DAYS] of severity rank, index 0 = most recent day
history = {}
incidents_last_fetch = None
incidents_error = None
time_synced = False


def fetch_status():
    global components, overall, overall_ok, status_error
    try:
        r = requests.get(STATUS_URL)
        j = r.json()
        components = [(c["id"], c["name"], c["status"]) for c in j["components"]]
        overall = j["status"]["description"]
        overall_ok = j["status"]["indicator"] == "none"
        status_error = None
    except (OSError, ValueError) as e:
        status_error = str(e)


def fetch_history():
    global history, incidents_error, time_synced

    if not time_synced:
        try:
            rtc.time_from_ntp()
            rtc.rtc_to_localtime()
            time_synced = True
        except OSError:
            pass

    try:
        today = datetime.now(timezone.utc)
        today_ordinal = _ordinal(today.year, today.month, today.day)

        r = requests.get(INCIDENTS_URL)
        j = r.json()

        buckets = {}
        for incident in j["incidents"]:
            days_ago = _days_ago(incident["started_at"], today_ordinal)
            if days_ago < 0 or days_ago >= HISTORY_DAYS:
                continue
            rank = IMPACT_RANK.get(incident["impact"], 0)

            seen_components = set()
            for update_entry in incident["incident_updates"]:
                for affected in update_entry["affected_components"]:
                    seen_components.add(affected["code"])

            for component_id in seen_components:
                slots = buckets.setdefault(component_id, [0] * HISTORY_DAYS)
                slots[days_ago] = max(slots[days_ago], rank)

        history = buckets
        incidents_error = None
    except (OSError, ValueError, KeyError) as e:
        incidents_error = str(e)


def draw_row(y, component_id, name, status):
    screen.pen = STATUS_COLORS.get(status, color.grey)
    screen.text(name, MARGIN, y)

    slots = history.get(component_id)
    bar_y = y + 15
    for i in range(HISTORY_DAYS):
        rank = slots[HISTORY_DAYS - 1 - i] if slots else 0
        screen.pen = IMPACT_COLORS.get(rank, color.green)
        screen.rectangle(MARGIN + i * DAY_WIDTH, bar_y, DAY_BAR_WIDTH, 10)


log_lines = []


def draw_log():
    # badge.update() (the only mid-frame display flush that actually exists —
    # despite the docs, screen.update() is not a real attribute on this
    # firmware) clears the framebuffer as a side effect of flushing it, so
    # log lines are redrawn from scratch every time rather than assumed to
    # persist across flushes.
    screen.pen = color.black
    screen.clear()
    y = MARGIN
    for text, pen in log_lines:
        screen.pen = pen
        screen.text(text, MARGIN, y)
        y += 16


def update():
    global status_last_fetch, incidents_last_fetch

    if not wifi.connect():
        wifi.tick()
        screen.pen = color.black
        screen.clear()
        screen.pen = color.white
        spinner = SPINNER[(badge.ticks // SPINNER_FRAME_MS) % len(SPINNER)]
        screen.text(f"Connecting to {secrets.WIFI_SSID} {spinner}", MARGIN, MARGIN)
        return

    # Only show the boot log on the very first load — background refreshes
    # (every 60s for status, every 30 min for incidents) happen silently so
    # they don't keep interrupting the dashboard view. requests.get() has no
    # progress reporting of its own, so this is just "which request is
    # currently in flight", flushed to the screen before each blocking call.
    booting = overall is None
    if booting:
        log_lines.clear()
        log_lines.append((f"Connected to {secrets.WIFI_SSID}", color.white))
        draw_log()

    if status_last_fetch is None or (badge.ticks - status_last_fetch) / 1000 > STATUS_REFRESH_SECONDS:
        if booting:
            log_lines.append(("GET /api/v2/summary.json", color.grey))
            draw_log()
            badge.update()
        fetch_status()
        status_last_fetch = badge.ticks
        if booting and status_error:
            log_lines.append((f"failed: {status_error}", color.red))
            draw_log()

    if incidents_last_fetch is None or (badge.ticks - incidents_last_fetch) / 1000 > INCIDENTS_REFRESH_SECONDS:
        if booting:
            log_lines.append(("GET /api/v2/incidents.json", color.grey))
            draw_log()
            badge.update()
        fetch_history()
        incidents_last_fetch = badge.ticks
        if booting and incidents_error:
            log_lines.append((f"failed: {incidents_error}", color.red))
            draw_log()

    if booting and overall is None:
        # first status fetch failed; stay on the boot log until the next retry
        return

    screen.pen = color.black
    screen.clear()

    screen.pen = color.white
    screen.text("Baseten Status", MARGIN, MARGIN)

    if overall is not None:
        screen.pen = color.green if overall_ok else color.orange
        screen.text(overall, MARGIN, MARGIN + 16)
    else:
        screen.pen = color.white
        screen.text("Loading...", MARGIN, MARGIN + 16)

    if status_error or incidents_error:
        screen.pen = color.red
        screen.text("Update failed, showing last known", MARGIN, MARGIN + 32)

    y = MARGIN + 44
    for component_id, name, status in components:
        draw_row(y, component_id, name, status)
        y += ROW_HEIGHT


run(update)
