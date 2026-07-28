import json
import time

import wifi
import requests
import secrets

KEY_ROWS = [
    list("1234567890"),
    list("qwertyuiop"),
    list("asdfghjkl") + ["DEL"],
    ["SHIFT"] + list("zxcvbnm") + ["SPACE", "ENTER"],
]

# Every row above has exactly 10 columns (an ortholinear grid, not the usual
# staggered QWERTY rows) so UP/DOWN keeps the cursor's column meaning
# consistent instead of landing on a visually unrelated key.
KEY_LABELS = {"SHIFT": "SHF", "SPACE": "SPC", "ENTER": "ENT"}

BASETEN_URL = "https://inference.baseten.co/v1/chat/completions"
MODEL = "zai-org/GLM-5.2-Fast"
MAX_TOKENS = 1024
MAX_HISTORY = 20  # messages of context kept, oldest dropped first
LOG_BUFFER_MAX = 200  # wrapped display lines kept, oldest dropped first
MAX_TOOL_ROUNDS = 3  # follow-up requests allowed per message before giving up

TOOLS = [
    {
        "type": "function",
        "function": {
            "name": "get_battery_level",
            "description": "Get the badge's current battery level as a percentage (0-100).",
            "parameters": {"type": "object", "properties": {}},
        },
    },
    {
        "type": "function",
        "function": {
            "name": "set_caselights",
            "description": "Set the brightness of the badge's four rear LEDs, all to the same level.",
            "parameters": {
                "type": "object",
                "properties": {
                    "level": {
                        "type": "number",
                        "description": "Brightness from 0 (off) to 1 (full brightness)",
                    }
                },
                "required": ["level"],
            },
        },
    },
]

MARGIN = 4
LOG_LINE_HEIGHT = 9
ROW_HEIGHT = 14
KEY_PAD = 2

KEY_BG = color.rgb(30, 40, 55)
KEY_FG = color.white
SELECTED_BG = color.white
SELECTED_FG = color.black
SHIFT_ON_BG = color.yellow
YOU_COLOR = color.white
BOT_COLOR = color.lime
ERROR_COLOR = color.red

SPINNER = "-/|\\"
SPINNER_FRAME_MS = 150

badge.mode(HIRES)
screen.font = rom_font.nope

KEYBOARD_TOP = screen.height - MARGIN - len(KEY_ROWS) * ROW_HEIGHT
COMPOSER_Y = KEYBOARD_TOP - MARGIN - LOG_LINE_HEIGHT
LOG_TOP = MARGIN
LOG_BOTTOM = COMPOSER_Y - MARGIN
LOG_MAX_WIDTH = screen.width - 2 * MARGIN
LOG_VISIBLE_LINES = max(1, (LOG_BOTTOM - LOG_TOP) // LOG_LINE_HEIGHT)

chat_history = []
log_lines = []
buffer = ""
cursor_row = 1
cursor_col = 0
shift_active = False
status_text = None


def tool_get_battery_level(args):
    return {"battery_level": badge.battery_level()}


def tool_set_caselights(args):
    level = max(0.0, min(1.0, float(args.get("level", 0))))
    badge.caselights(level)
    return {"ok": True, "level": level}


TOOL_FUNCTIONS = {
    "get_battery_level": tool_get_battery_level,
    "set_caselights": tool_set_caselights,
}


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


def add_log(text, pen):
    for paragraph in text.split("\n"):
        if not paragraph:
            continue
        for line in wrap_line(paragraph, LOG_MAX_WIDTH):
            log_lines.append((line, pen))
    del log_lines[:-LOG_BUFFER_MAX]


REQUEST_TIMEOUT = 45  # without this, a stalled connection hangs forever with no way to recover


def call_model():
    r = requests.post(
        BASETEN_URL,
        headers={
            "Content-Type": "application/json",
            "Authorization": "Api-Key " + secrets.BASETEN_API_KEY,
        },
        json={
            "model": MODEL,
            "messages": chat_history,
            "tools": TOOLS,
            "max_tokens": MAX_TOKENS,
            "temperature": 1,
        },
        timeout=REQUEST_TIMEOUT,
    )
    if r.status_code != 200:
        body = r.text
        r.close()
        raise RuntimeError("HTTP " + str(r.status_code) + ": " + body[:80])
    data = r.json()
    r.close()
    return data["choices"][0]["message"]


CALL_ATTEMPTS = 3  # this badge's wifi/TLS stack occasionally drops or mangles a request


def call_model_with_retry():
    last_error = None
    for attempt in range(CALL_ATTEMPTS):
        try:
            return call_model()
        except (OSError, ValueError, RuntimeError) as e:
            last_error = e
            if attempt < CALL_ATTEMPTS - 1:
                set_status("retrying...")
                time.sleep(1)
    raise last_error


def to_ascii(text):
    # This firmware's HTTP client appears to size the request body by Python
    # character count rather than UTF-8 byte count, so any multi-byte
    # character (emoji, smart punctuation) stored in chat_history silently
    # truncates a later request. The pixel font can't render those glyphs
    # anyway, so strip to plain ASCII once, at the source.
    return "".join(ch for ch in text if ch == "\n" or 32 <= ord(ch) <= 126)


def set_status(text):
    global status_text
    status_text = text
    render()
    badge.update()


def run_tool_call(call):
    name = call["function"]["name"]
    set_status("using: " + name)
    fn = TOOL_FUNCTIONS.get(name)
    try:
        args = json.loads(call["function"].get("arguments") or "{}")
        result = fn(args) if fn else {"error": "unknown tool " + name}
    except (ValueError, TypeError) as e:
        result = {"error": str(e)}
    chat_history.append({"role": "tool", "tool_call_id": call["id"], "content": json.dumps(result)})


def send_message():
    global buffer, status_text
    text = buffer.strip()
    if not text:
        return
    buffer = ""

    add_log("You: " + text, YOU_COLOR)
    chat_history.append({"role": "user", "content": text})
    del chat_history[:-MAX_HISTORY]

    reply = None
    reply_color = BOT_COLOR
    try:
        for _ in range(MAX_TOOL_ROUNDS):
            set_status("...")
            message = call_model_with_retry()
            tool_calls = message.get("tool_calls")
            if not tool_calls:
                # Kimi-K3 can burn the whole token budget on reasoning_content
                # and leave content null if it never got to a final answer.
                reply = to_ascii((message.get("content") or message.get("reasoning_content") or "").strip())
                reply = reply or "(no reply - response cut off, try a shorter question)"
                break

            # Only keep the fields needed to replay tool calls - reasoning_content
            # can be long and re-serializing it on the next round-trip is what
            # produced a malformed request body (HTTP 400 EOF parsing messages[N]).
            content = message.get("content")
            chat_history.append(
                {
                    "role": "assistant",
                    "content": to_ascii(content) if content else content,
                    "tool_calls": tool_calls,
                }
            )
            for call in tool_calls:
                run_tool_call(call)
        if reply is None:
            reply = "(too many tool calls, giving up)"
            reply_color = ERROR_COLOR
    except (OSError, ValueError, KeyError, IndexError, RuntimeError) as e:
        reply = "error: " + str(e)
        reply_color = ERROR_COLOR

    status_text = None
    add_log("Bot: " + reply, reply_color)
    if reply_color is BOT_COLOR:
        chat_history.append({"role": "assistant", "content": reply})
        del chat_history[:-MAX_HISTORY]


def activate_key():
    global buffer, shift_active
    key = KEY_ROWS[cursor_row][cursor_col]
    if key == "SHIFT":
        shift_active = not shift_active
    elif key == "SPACE":
        buffer += " "
    elif key == "DEL":
        buffer = buffer[:-1]
    elif key == "ENTER":
        send_message()
    else:
        buffer += key.upper() if shift_active else key
        shift_active = False


def draw_log():
    status_lines = [(line, color.grey) for line in wrap_line(status_text, LOG_MAX_WIDTH)] if status_text else []
    real_lines = log_lines[-(LOG_VISIBLE_LINES - len(status_lines)):] if len(status_lines) < LOG_VISIBLE_LINES else []
    shown = real_lines + status_lines

    y = LOG_BOTTOM - len(shown) * LOG_LINE_HEIGHT
    for text, pen in shown:
        screen.pen = pen
        screen.text(text, MARGIN, y)
        y += LOG_LINE_HEIGHT


def draw_composer():
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

            if selected:
                bg, fg = SELECTED_BG, SELECTED_FG
            elif key == "SHIFT" and shift_active:
                bg, fg = SHIFT_ON_BG, SELECTED_FG
            else:
                bg, fg = KEY_BG, KEY_FG

            screen.pen = bg
            screen.rectangle(x + KEY_PAD, y + KEY_PAD, w - KEY_PAD * 2, ROW_HEIGHT - KEY_PAD * 2)
            screen.pen = fg
            label = KEY_LABELS.get(key, key) if len(key) > 1 else (key.upper() if shift_active else key)
            label_w, label_h = screen.measure_text(label)
            screen.text(label, x + (w - label_w) // 2, y + (ROW_HEIGHT - label_h) // 2)


def render():
    screen.pen = color.black
    screen.clear()
    draw_log()
    draw_composer()
    draw_keyboard()


def update():
    if not wifi.connect():
        wifi.tick()
        screen.pen = color.black
        screen.clear()
        screen.pen = color.white
        spinner = SPINNER[(badge.ticks // SPINNER_FRAME_MS) % len(SPINNER)]
        screen.text(f"Connecting to {secrets.WIFI_SSID} {spinner}", MARGIN, MARGIN)
        return

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

    render()


run(update)
