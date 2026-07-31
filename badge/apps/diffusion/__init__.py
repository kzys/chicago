import binascii
import json

import wifi
import requests
import secrets
import keyboard

# Host-provisioned only (make install-baseten-state FILE=...), no on-device
# entry flow -- see scripts/install_device_file.py.
try:
    with open("/state/baseten.json") as _f:
        BASETEN_IMAGE_API_KEY = json.load(_f).get("BASETEN_IMAGE_API_KEY")
except (OSError, ValueError):
    BASETEN_IMAGE_API_KEY = None

# A separately deployed model, not part of the shared Model APIs catalog
# BASETEN_API_KEY authenticates against - hence the separate key/host.
IMAGE_URL = "https://model-wgl4nj63.api.baseten.co/environments/production/predict"
# 240 outright breaks this model (returns a degenerate 1px-tall image) - it
# needs multiple-of-64 dimensions. 256 is the closest one above the screen's
# height, so there's only a thin crop left to do client-side.
IMAGE_REQUEST_WIDTH = 320
IMAGE_REQUEST_HEIGHT = 256
REQUEST_TIMEOUT = 90  # cold starts and diffusion sampling both take a while
# A response within this long is normal sampling time; past it, a cold start
# is the far more likely explanation, so that's the cutoff for updating the
# status message rather than leaving "Generating..." up for the whole 90s.
COLD_START_TIMEOUT = 30
CALL_ATTEMPTS = 2  # this badge's wifi/TLS stack occasionally drops or mangles a request

MARGIN = 4
LINE_HEIGHT = 13

ERROR_COLOR = color.red

SPINNER = "-/|\\"
SPINNER_FRAME_MS = 150

badge.mode(HIRES)
# Not the same font the keyboard grid uses (winds) -- sins' "g" glyph reads
# better (matches chat), and "Generating..." needs it; the grid keeps its
# own font regardless, since keyboard.draw() sets/restores it independently.
screen.font = rom_font.sins

COMPOSER_Y = keyboard.composer_y(LINE_HEIGHT)

AUTO_INTERVAL_MS = 30000  # regenerate on this cadence, reset by any submit

keyboard.buffer = "pelican riding a bicycle in Chicago"
status_text = None
error_text = None
sprite = None
next_auto_ticks = None  # None means "due immediately" - set once wifi connects
editing = False  # keyboard/composer only shown while editing the prompt


def wrap_line(text, max_width):
    words = text.split(" ")
    lines = []
    cur = ""
    for word in words:
        trial = word if not cur else cur + " " + word
        w, _ = screen.measure_text(trial)
        if w <= max_width or not cur:
            cur = trial
        else:
            lines.append(cur)
            cur = word
    if cur:
        lines.append(cur)
    return lines


def blit_cover(img, dest_x, dest_y, dest_w, dest_h):
    # Scale to cover the destination rect completely (cropping overflow)
    # rather than letterboxing - the model's square output doesn't match
    # the screen's aspect ratio, so something has to give either way.
    scale = max(dest_w / img.width, dest_h / img.height)
    crop_w = dest_w / scale
    crop_h = dest_h / scale
    src_x = (img.width - crop_w) / 2
    src_y = (img.height - crop_h) / 2
    screen.blit(img, rect(src_x, src_y, crop_w, crop_h), rect(dest_x, dest_y, dest_w, dest_h))


def set_status(text):
    global status_text
    status_text = text
    render()
    badge.update()


def _request_image(timeout):
    r = requests.post(
        IMAGE_URL,
        headers={
            "Content-Type": "application/json",
            "Authorization": "Api-Key " + BASETEN_IMAGE_API_KEY,
        },
        json={
            "prompt": keyboard.buffer,
            "width": IMAGE_REQUEST_WIDTH,
            "height": IMAGE_REQUEST_HEIGHT,
        },
        timeout=timeout,
    )
    if r.status_code != 200:
        body = r.text
        r.close()
        raise RuntimeError("HTTP " + str(r.status_code) + ": " + body[:80])
    data = r.json()["data"]
    r.close()
    # image.load() accepts raw bytes directly (undocumented, but confirmed
    # to work) - decoding straight into memory avoids flash wear from
    # writing every auto-refresh to /state.
    return image.load(binascii.a2b_base64(data))


def generate_image():
    last_error = None
    for attempt in range(CALL_ATTEMPTS):
        try:
            try:
                return _request_image(COLD_START_TIMEOUT)
            except OSError:
                # No response within COLD_START_TIMEOUT is far more likely a
                # cold start than a real failure, so this isn't counted as
                # one of the CALL_ATTEMPTS retries -- just keep waiting, with
                # an updated status, for the rest of the normal budget.
                set_status("Probably just a cold start...")
                return _request_image(REQUEST_TIMEOUT - COLD_START_TIMEOUT)
        except (OSError, ValueError, KeyError, RuntimeError) as e:
            last_error = e
            if attempt < CALL_ATTEMPTS - 1:
                set_status("Retrying...")
    raise last_error


def submit_prompt():
    global sprite, error_text, status_text, next_auto_ticks
    prompt = keyboard.buffer.strip()
    if not prompt:
        return
    set_status("Generating...")
    try:
        sprite = generate_image()
        error_text = None
    except (OSError, ValueError, KeyError, RuntimeError) as e:
        error_text = str(e)
    status_text = None
    next_auto_ticks = badge.ticks + AUTO_INTERVAL_MS


def draw_status_overlay():
    if error_text:
        screen.pen = ERROR_COLOR
        y = MARGIN
        for line in wrap_line("Error: " + error_text, screen.width - 2 * MARGIN):
            screen.text(line, MARGIN, y)
            y += LINE_HEIGHT
    elif status_text:
        screen.pen = color.grey
        screen.text(status_text, MARGIN, screen.height - LINE_HEIGHT - MARGIN)


def render():
    screen.pen = color.black
    screen.clear()
    if sprite:
        blit_cover(sprite, 0, 0, screen.width, screen.height)
    if editing:
        keyboard.draw(MARGIN, LINE_HEIGHT)
    else:
        draw_status_overlay()


def update():
    global status_text, editing
    if not wifi.connect():
        wifi.tick()
        spinner = SPINNER[(badge.ticks // SPINNER_FRAME_MS) % len(SPINNER)]
        status_text = "Connecting to " + secrets.WIFI_SSID + " " + spinner
        render()
        return
    status_text = None

    if not editing and (next_auto_ticks is None or badge.ticks >= next_auto_ticks):
        submit_prompt()

    if editing:
        if badge.pressed(BUTTON_UP):
            keyboard.move_row(-1)
        if badge.pressed(BUTTON_DOWN):
            keyboard.move_row(1)
        if badge.pressed(BUTTON_A):
            keyboard.move_col(-1)
        if badge.pressed(BUTTON_C):
            keyboard.move_col(1)
        if badge.pressed(BUTTON_B) and keyboard.type_key() == "enter":
            editing = False
            submit_prompt()
    elif badge.pressed(BUTTON_B):
        editing = True

    render()


run(update)
