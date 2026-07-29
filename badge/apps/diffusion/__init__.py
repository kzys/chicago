import binascii

import wifi
import requests
import secrets

KEY_ROWS = [
    list("1234567890") + ["DEL"],
    list("qwertyuiop") + ["ENTER"],
    list("asdfghjkl") + [";", "'"],
    list("zxcvbnm") + [",", ".", "/", "SPACE"],
]

# Every row above has exactly 11 columns (an ortholinear grid, not the usual
# staggered QWERTY rows) so UP/DOWN keeps the cursor's column meaning
# consistent instead of landing on a visually unrelated key.
KEY_LABELS = {"SPACE": "SPC", "ENTER": "ENT"}

# A separately deployed model, not part of the shared Model APIs catalog
# BASETEN_API_KEY authenticates against - hence the separate key/host.
IMAGE_URL = "https://model-wgl4nj63.api.baseten.co/environments/production/predict"
IMAGE_PATH = "/state/diffusion.png"
# 240 outright breaks this model (returns a degenerate 1px-tall image) - it
# needs multiple-of-64 dimensions. 256 is the closest one above the screen's
# height, so there's only a thin crop left to do client-side.
IMAGE_REQUEST_WIDTH = 320
IMAGE_REQUEST_HEIGHT = 256
REQUEST_TIMEOUT = 90  # cold starts and diffusion sampling both take a while
CALL_ATTEMPTS = 2  # this badge's wifi/TLS stack occasionally drops or mangles a request

MARGIN = 4
LINE_HEIGHT = 13
ROW_HEIGHT = 14
KEY_PAD = 2

KEY_BG = color.rgb(30, 40, 55)
KEY_FG = color.white
SELECTED_BG = color.white
SELECTED_FG = color.black
ERROR_COLOR = color.red

SPINNER = "-/|\\"
SPINNER_FRAME_MS = 150

badge.mode(HIRES)
screen.font = rom_font.nope

KEYBOARD_TOP = screen.height - MARGIN - len(KEY_ROWS) * ROW_HEIGHT
COMPOSER_Y = KEYBOARD_TOP - MARGIN - LINE_HEIGHT

AUTO_INTERVAL_MS = 30000  # regenerate on this cadence, reset by any submit

buffer = "pelican riding a bicycle in front of a famous Chicago landmark"
cursor_row = 1
cursor_col = 0
status_text = None
error_text = None
sprite = None
next_auto_ticks = None  # None means "due immediately" - set once wifi connects
editing = False  # keyboard/composer only shown while editing the prompt


def key_width(row_idx):
    return (screen.width - 2 * MARGIN) // len(KEY_ROWS[row_idx])


def row_x_offset(row_idx):
    n = len(KEY_ROWS[row_idx])
    w = key_width(row_idx)
    return MARGIN + (screen.width - 2 * MARGIN - n * w) // 2


def clamp_col():
    global cursor_col
    n = len(KEY_ROWS[cursor_row])
    cursor_col = max(0, min(n - 1, cursor_col))


def move_row(delta):
    global cursor_row
    cursor_row = max(0, min(len(KEY_ROWS) - 1, cursor_row + delta))
    clamp_col()


def move_col(delta):
    global cursor_col
    n = len(KEY_ROWS[cursor_row])
    cursor_col = (cursor_col + delta) % n


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


def generate_image():
    last_error = None
    for attempt in range(CALL_ATTEMPTS):
        try:
            r = requests.post(
                IMAGE_URL,
                headers={
                    "Content-Type": "application/json",
                    "Authorization": "Api-Key " + secrets.BASETEN_IMAGE_API_KEY,
                },
                json={
                    "prompt": buffer,
                    "width": IMAGE_REQUEST_WIDTH,
                    "height": IMAGE_REQUEST_HEIGHT,
                },
                timeout=REQUEST_TIMEOUT,
            )
            if r.status_code != 200:
                body = r.text
                r.close()
                raise RuntimeError("HTTP " + str(r.status_code) + ": " + body[:80])
            data = r.json()["data"]
            r.close()
            with open(IMAGE_PATH, "wb") as f:
                f.write(binascii.a2b_base64(data))
            return image.load(IMAGE_PATH)
        except (OSError, ValueError, KeyError, RuntimeError) as e:
            last_error = e
            if attempt < CALL_ATTEMPTS - 1:
                set_status("Retrying...")
    raise last_error


def submit_prompt():
    global sprite, error_text, status_text, next_auto_ticks
    prompt = buffer.strip()
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


def activate_key():
    global buffer, editing
    key = KEY_ROWS[cursor_row][cursor_col]
    if key == "SPACE":
        buffer += " "
    elif key == "DEL":
        buffer = buffer[:-1]
    elif key == "ENTER":
        editing = False
        submit_prompt()
    else:
        buffer += key


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


def draw_composer():
    # Solid backing bar, same as the keyboard's key backgrounds, so the
    # prompt text stays legible over whatever's underneath in the image.
    screen.pen = KEY_BG
    screen.rectangle(0, COMPOSER_Y - 2, screen.width, LINE_HEIGHT + 4)
    screen.pen = color.white
    cursor_char = "_" if (badge.ticks // 400) % 2 == 0 else " "
    screen.text(buffer + cursor_char, MARGIN, COMPOSER_Y)


def draw_keyboard():
    for row_idx, row in enumerate(KEY_ROWS):
        w = key_width(row_idx)
        x0 = row_x_offset(row_idx)
        y = KEYBOARD_TOP + row_idx * ROW_HEIGHT
        for col_idx, key in enumerate(row):
            x = x0 + col_idx * w
            selected = row_idx == cursor_row and col_idx == cursor_col

            bg, fg = (SELECTED_BG, SELECTED_FG) if selected else (KEY_BG, KEY_FG)

            screen.pen = bg
            screen.rectangle(x + KEY_PAD, y + KEY_PAD, w - KEY_PAD * 2, ROW_HEIGHT - KEY_PAD * 2)
            screen.pen = fg
            label = KEY_LABELS.get(key, key)
            label_w, label_h = screen.measure_text(label)
            screen.text(label, x + (w - label_w) // 2, y + (ROW_HEIGHT - label_h) // 2)


def render():
    screen.pen = color.black
    screen.clear()
    if sprite:
        blit_cover(sprite, 0, 0, screen.width, screen.height)
    if editing:
        draw_composer()
        draw_keyboard()
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
            move_row(-1)
        if badge.pressed(BUTTON_DOWN):
            move_row(1)
        if badge.pressed(BUTTON_A):
            move_col(-1)
        if badge.pressed(BUTTON_C):
            move_col(1)
        if badge.pressed(BUTTON_B):
            activate_key()
    elif badge.pressed(BUTTON_B):
        editing = True

    render()


run(update)
