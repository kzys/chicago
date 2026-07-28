from datetime import datetime, timezone

import wifi
import requests

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
IMPACT_COLORS = {3: color.red, 2: color.orange, 1: color.yellow, 0: color.grey}

# The public Statuspage API has no daily-uptime endpoint (that data is only
# server-rendered into the status page's HTML), so instead of scraping we
# bucket the last 90 days of *incidents* ourselves from /api/v2/incidents.json,
# which is a normal documented, unauthenticated endpoint. One bucket per day,
# rendered at one pixel per day.
HISTORY_DAYS = 90

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
    screen.rectangle(16, y, 20, 16)
    screen.pen = color.white
    screen.text(name, 46, y + 3)

    slots = history.get(component_id)
    for i in range(HISTORY_DAYS):
        rank = slots[HISTORY_DAYS - 1 - i] if slots else 0
        screen.pen = IMPACT_COLORS[rank] if rank else color.navy
        screen.rectangle(214 + i, y + 2, 1, 12)


def update():
    global status_last_fetch, incidents_last_fetch

    screen.pen = color.black
    screen.clear()

    if not wifi.connect():
        wifi.tick()
        screen.pen = color.white
        screen.text("Connecting to WiFi...", 16, 16)
        return

    if status_last_fetch is None or (badge.ticks - status_last_fetch) / 1000 > STATUS_REFRESH_SECONDS:
        fetch_status()
        status_last_fetch = badge.ticks

    if incidents_last_fetch is None or (badge.ticks - incidents_last_fetch) / 1000 > INCIDENTS_REFRESH_SECONDS:
        fetch_history()
        incidents_last_fetch = badge.ticks

    screen.pen = color.white
    screen.text("Baseten Status", 16, 12)

    if overall is not None:
        screen.pen = color.green if overall_ok else color.orange
        screen.text(overall, 16, 34)
    else:
        screen.pen = color.white
        screen.text("Loading...", 16, 34)

    if status_error or incidents_error:
        screen.pen = color.red
        screen.text("Update failed, showing last known", 16, 52)

    y = 68
    for component_id, name, status in components:
        draw_row(y, component_id, name, status)
        y += 26


run(update)
