from datetime import datetime, timezone

import wifi
import requests
import secrets

SERVICES = [
    {
        "name": "Baseten",
        "status_url": "https://status.baseten.co/api/v2/summary.json",
        "incidents_url": "https://status.baseten.co/api/v2/incidents.json",
    },
    {
        "name": "Claude",
        "status_url": "https://status.claude.com/api/v2/summary.json",
        "incidents_url": "https://status.claude.com/api/v2/incidents.json",
    },
]
STATUS_REFRESH_SECONDS = 60
INCIDENTS_REFRESH_SECONDS = 1800

STATUS_COLORS = {
    "operational": color.green,
    "degraded_performance": color.yellow,
    "partial_outage": color.orange,
    "major_outage": color.red,
    "under_maintenance": color.blue,
}

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

# Header is a single small-font line; the component list starts right below
# it. The footer reserves two small-font lines at the bottom of the screen
# for the overall status (and, when present, an error line above it) so
# they don't get pushed around by how many components a service has.
ROWS_START_Y = 24
FOOTER_LINE_H = 14

# Statuspage documents this exact algorithm at
# support.atlassian.com/statuspage/docs/display-historical-uptime-of-components:
# only major_outage/partial_outage minutes count (degraded_performance and
# under_maintenance are explicitly excluded), partial outages are discounted
# to 30% as bad as major ones, and the color follows fixed minute thresholds
# rather than a simple scaled gradient: any downtime at all immediately jumps
# to halfway between green and yellow, then eases to fully yellow by 20min,
# fully orange by 40min, fully red by 60min, and stays red past that.
HUE_GREEN = 85
HUE_YELLOW = 42
HUE_ORANGE = 21
HUE_RED = 0
HUE_HALFWAY = (HUE_GREEN + HUE_YELLOW) // 2

# Badgeware's own dark green reads better against the black background than
# the real site's exact (lighter, teal-leaning) clean-day fill did.
CLEAN_COLOR = color.green

PARTIAL_OUTAGE_WEIGHT = 0.3


def _downtime_color(minutes):
    if minutes <= 0:
        return CLEAN_COLOR
    if minutes <= 20:
        hue = HUE_HALFWAY + (HUE_YELLOW - HUE_HALFWAY) * (minutes / 20)
    elif minutes <= 40:
        hue = HUE_YELLOW + (HUE_ORANGE - HUE_YELLOW) * ((minutes - 20) / 20)
    elif minutes <= 60:
        hue = HUE_ORANGE + (HUE_RED - HUE_ORANGE) * ((minutes - 40) / 20)
    else:
        hue = HUE_RED
    return color.hsv(int(hue), 220, 200)


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


def _total_minutes(iso_datetime):
    # Same simplification as _days_ago: the UTC offset is ignored, which is
    # fine here since a single incident's started_at/resolved_at/updated_at
    # timestamps all carry the same offset, so it cancels out of the
    # subtraction used to compute duration.
    y, m, d = int(iso_datetime[0:4]), int(iso_datetime[5:7]), int(iso_datetime[8:10])
    hh, mm = int(iso_datetime[11:13]), int(iso_datetime[14:16])
    return _ordinal(y, m, d) * 1440 + hh * 60 + mm


def _union_minutes(intervals):
    # Separate incident reports for the same component can overlap in time
    # (e.g. a second report filed before the first is resolved) — summing
    # each incident's duration independently double-counts that overlap, so
    # the actual affected time is the union of the intervals, not their sum.
    if not intervals:
        return 0
    intervals.sort()
    total = 0
    start, end = intervals[0]
    for s, e in intervals[1:]:
        if s <= end:
            end = max(end, e)
        else:
            total += end - start
            start, end = s, e
    total += end - start
    return total


badge.mode(HIRES)
screen.font = rom_font.nope

FOOTER_STATUS_Y = screen.height - MARGIN - FOOTER_LINE_H
FOOTER_ERROR_Y = FOOTER_STATUS_Y - FOOTER_LINE_H


def new_state():
    return {
        "components": [],
        "overall": None,
        "overall_ok": True,
        "status_last_fetch": None,
        "status_error": None,
        # component id -> list[HISTORY_DAYS] of color, index 0 = most recent
        # day. Colors are precomputed once per fetch rather than at draw
        # time, since draw_row() runs this over 90 days x every component,
        # every frame.
        "history": {},
        "incidents_last_fetch": None,
        "incidents_error": None,
        "log_lines": [],
    }


states = [new_state() for _ in SERVICES]
page = 0
time_synced = False


def fetch_status(service, state):
    try:
        r = requests.get(service["status_url"])
        j = r.json()
        state["components"] = [(c["id"], c["name"], c["status"]) for c in j["components"]]
        state["overall"] = j["status"]["description"]
        state["overall_ok"] = j["status"]["indicator"] == "none"
        state["status_error"] = None
    except (OSError, ValueError) as e:
        state["status_error"] = str(e)


def fetch_history(service, state):
    global time_synced

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

        r = requests.get(service["incidents_url"])
        j = r.json()

        # major_outage beats partial_outage as the "worst state reached" for a
        # given component during a single incident — the whole incident span
        # is then attributed to whichever of the two it is (there's no
        # per-update timestamp granularity fine enough to split a single
        # incident's duration between the two states it passed through).
        OUTAGE_RANK = {"major_outage": 2, "partial_outage": 1}

        major_by_component = {}
        partial_by_component = {}
        for incident in j["incidents"]:
            days_ago = _days_ago(incident["started_at"], today_ordinal)
            if days_ago < 0 or days_ago >= HISTORY_DAYS:
                continue

            start_min = _total_minutes(incident["started_at"])
            end_at = incident["resolved_at"] or incident["updated_at"]
            end_min = _total_minutes(end_at)
            if end_min < start_min:
                end_min = start_min

            worst = {}
            for update_entry in incident["incident_updates"]:
                for affected in update_entry["affected_components"] or []:
                    cid = affected["code"]
                    rank = OUTAGE_RANK.get(affected["new_status"], 0)
                    if rank > worst.get(cid, 0):
                        worst[cid] = rank

            for component_id, rank in worst.items():
                if rank == 2:
                    target = major_by_component
                elif rank == 1:
                    target = partial_by_component
                else:
                    continue
                days = target.setdefault(component_id, [None] * HISTORY_DAYS)
                if days[days_ago] is None:
                    days[days_ago] = []
                days[days_ago].append((start_min, end_min))

        all_components = set(major_by_component) | set(partial_by_component)
        history = {}
        for component_id in all_components:
            major_days = major_by_component.get(component_id, [None] * HISTORY_DAYS)
            partial_days = partial_by_component.get(component_id, [None] * HISTORY_DAYS)
            colors = []
            for day in range(HISTORY_DAYS):
                major_minutes = _union_minutes(major_days[day]) if major_days[day] else 0
                partial_minutes = _union_minutes(partial_days[day]) if partial_days[day] else 0
                total = major_minutes + partial_minutes * PARTIAL_OUTAGE_WEIGHT
                colors.append(_downtime_color(total))
            history[component_id] = colors
        state["history"] = history
        state["incidents_error"] = None
    except (OSError, ValueError, KeyError) as e:
        state["incidents_error"] = str(e)


def draw_row(y, state, component_id, name, status):
    screen.font = rom_font.nope
    screen.pen = STATUS_COLORS.get(status, color.grey)
    screen.text(name, MARGIN, y)

    slots = state["history"].get(component_id)
    bar_y = y + 15
    for i in range(HISTORY_DAYS):
        screen.pen = slots[HISTORY_DAYS - 1 - i] if slots else CLEAN_COLOR
        screen.rectangle(MARGIN + i * DAY_WIDTH, bar_y, DAY_BAR_WIDTH, 10)


def draw_log(state):
    # badge.update() (the only mid-frame display flush that actually exists —
    # despite the docs, screen.update() is not a real attribute on this
    # firmware) clears the framebuffer as a side effect of flushing it, so
    # log lines are redrawn from scratch every time rather than assumed to
    # persist across flushes.
    screen.pen = color.black
    screen.clear()
    y = MARGIN
    for text, pen in state["log_lines"]:
        screen.pen = pen
        screen.text(text, MARGIN, y)
        y += 16


def update():
    global page

    if badge.pressed(BUTTON_A):
        page = (page - 1) % len(SERVICES)
    if badge.pressed(BUTTON_C):
        page = (page + 1) % len(SERVICES)

    service = SERVICES[page]
    state = states[page]

    if not wifi.connect():
        wifi.tick()
        screen.pen = color.black
        screen.clear()
        screen.pen = color.white
        spinner = SPINNER[(badge.ticks // SPINNER_FRAME_MS) % len(SPINNER)]
        screen.text(f"Connecting to {secrets.WIFI_SSID} {spinner}", MARGIN, MARGIN)
        return

    # Only show the boot log on a service's very first load — background
    # refreshes (every 60s for status, every 30 min for incidents) happen
    # silently so they don't keep interrupting the dashboard view.
    # requests.get() has no progress reporting of its own, so this is just
    # "which request is currently in flight", flushed to the screen before
    # each blocking call.
    booting = state["overall"] is None
    if booting:
        state["log_lines"].clear()
        state["log_lines"].append((f"Connected to {secrets.WIFI_SSID}", color.white))
        draw_log(state)

    if (
        state["status_last_fetch"] is None
        or (badge.ticks - state["status_last_fetch"]) / 1000 > STATUS_REFRESH_SECONDS
    ):
        if booting:
            state["log_lines"].append((f"GET {service['name']} summary", color.grey))
            draw_log(state)
            badge.update()
        fetch_status(service, state)
        state["status_last_fetch"] = badge.ticks
        if booting and state["status_error"]:
            state["log_lines"].append((f"failed: {state['status_error']}", color.red))
            draw_log(state)

    if (
        state["incidents_last_fetch"] is None
        or (badge.ticks - state["incidents_last_fetch"]) / 1000 > INCIDENTS_REFRESH_SECONDS
    ):
        if booting:
            state["log_lines"].append((f"GET {service['name']} incidents", color.grey))
            draw_log(state)
            badge.update()
        fetch_history(service, state)
        state["incidents_last_fetch"] = badge.ticks
        if booting and state["incidents_error"]:
            state["log_lines"].append((f"failed: {state['incidents_error']}", color.red))
            draw_log(state)

    if booting and state["overall"] is None:
        # first status fetch failed; stay on the boot log until the next retry
        return

    screen.pen = color.black
    screen.clear()

    screen.font = rom_font.sins
    screen.pen = color.white
    screen.text("{} Status".format(service["name"]), MARGIN, MARGIN)

    y = ROWS_START_Y
    for component_id, name, status in state["components"]:
        draw_row(y, state, component_id, name, status)
        y += ROW_HEIGHT

    screen.font = rom_font.sins
    if state["status_error"] or state["incidents_error"]:
        screen.pen = color.red
        screen.text("Update failed, showing last known", MARGIN, FOOTER_ERROR_Y)

    if state["overall"] is not None:
        screen.pen = color.green if state["overall_ok"] else color.orange
        screen.text(state["overall"], MARGIN, FOOTER_STATUS_Y)
    else:
        screen.pen = color.white
        screen.text("Loading...", MARGIN, FOOTER_STATUS_Y)


run(update)
