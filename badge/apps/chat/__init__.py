import json
import time

import wifi
import requests
import secrets
import keyboard

# Host-provisioned only (make install-baseten-state FILE=...), no on-device
# entry flow -- see scripts/install_state_file.py.
try:
    with open("/state/baseten.json") as _f:
        BASETEN_API_KEY = json.load(_f).get("BASETEN_API_KEY")
except (OSError, ValueError):
    BASETEN_API_KEY = None

BASETEN_URL = "https://inference.baseten.co/v1/chat/completions"
MODELS_URL = "https://inference.baseten.co/v1/models"
MODEL = "zai-org/GLM-5.2-Fast"
MAX_TOKENS = 300
MAX_HISTORY = 20  # messages of context kept, oldest dropped first
LOG_BUFFER_MAX = 200  # wrapped display lines kept, oldest dropped first
MAX_TOOL_ROUNDS = 3  # follow-up requests allowed per message before giving up

STATIC_TOOLS = [
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
            "description": (
                "Set the brightness of the badge's four rear LEDs. 'level' sets all four at "
                "once; level1-level4 address individual LEDs and override 'level' for that one. "
                "Any LED with no value at all (neither 'level' nor its own levelN) is set to 0."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "level": {
                        "type": "number",
                        "description": "Brightness from 0 (off) to 1 (full brightness) applied to all four LEDs",
                    },
                    "level1": {"type": "number", "description": "Brightness for LED 1 alone (0-1)"},
                    "level2": {"type": "number", "description": "Brightness for LED 2 alone (0-1)"},
                    "level3": {"type": "number", "description": "Brightness for LED 3 alone (0-1)"},
                    "level4": {"type": "number", "description": "Brightness for LED 4 alone (0-1)"},
                },
                "required": [],
            },
        },
    },
]


def build_tools():
    # available_models is fetched once after wifi connects (see fetch_available_models),
    # so the switch_model schema is only built with a real enum once that's known -
    # before that it just accepts any string, best-effort.
    switch_model_tool = {
        "type": "function",
        "function": {
            "name": "switch_model",
            "description": "Switch the underlying LLM used for future replies.",
            "parameters": {
                "type": "object",
                "properties": {"model": {"type": "string", "description": "Model id to switch to"}},
                "required": ["model"],
            },
        },
    }
    if available_models:
        switch_model_tool["function"]["parameters"]["properties"]["model"]["enum"] = available_models
    return STATIC_TOOLS + [switch_model_tool]


MARGIN = 4
LOG_LINE_HEIGHT = 13  # 8px glyph height + 5px line spacing

YOU_COLOR = color.white
BOT_COLOR = color.lime
ERROR_COLOR = color.red

SPINNER = "-/|\\"
SPINNER_FRAME_MS = 150

badge.mode(HIRES)
screen.font = rom_font.nope

COMPOSER_Y = keyboard.top_y(0) - MARGIN - LOG_LINE_HEIGHT
HEADER_Y = MARGIN
LOG_TOP = HEADER_Y + LOG_LINE_HEIGHT + MARGIN
LOG_BOTTOM = COMPOSER_Y - MARGIN
LOG_MAX_WIDTH = screen.width - 2 * MARGIN
LOG_VISIBLE_LINES = max(1, (LOG_BOTTOM - LOG_TOP) // LOG_LINE_HEIGHT)

chat_history = []
log_lines = []
buffer = ""
status_text = None
log_scroll = 0  # lines scrolled back from the bottom (0 = latest)
available_models = []  # populated once by fetch_available_models(), after wifi connects
models_loaded = False  # tried once, whether or not it succeeded


def tool_get_battery_level(args):
    return {"battery_level": badge.battery_level()}


def tool_set_caselights(args):
    default = args.get("level", 0)
    levels = [max(0.0, min(1.0, float(args.get("level" + str(i), default)))) for i in range(1, 5)]
    badge.caselights(*levels)
    return {"ok": True, "levels": levels}


def tool_switch_model(args):
    global MODEL
    requested = args.get("model", "")
    if not requested:
        return {"error": "no model specified"}
    if available_models and requested not in available_models:
        return {"error": "unknown model", "available": available_models}
    MODEL = requested
    return {"ok": True, "model": MODEL}


TOOL_FUNCTIONS = {
    "get_battery_level": tool_get_battery_level,
    "set_caselights": tool_set_caselights,
    "switch_model": tool_switch_model,
}


def fetch_available_models():
    global available_models, models_loaded
    models_loaded = True
    try:
        r = requests.get(
            MODELS_URL,
            headers={"Authorization": "Api-Key " + BASETEN_API_KEY},
            timeout=REQUEST_TIMEOUT,
        )
        if r.status_code == 200:
            available_models = [m["id"] for m in r.json().get("data", [])]
        r.close()
    except (OSError, ValueError):
        pass  # not fatal - switch_model just won't have an enum to constrain choices to


def scroll_log(delta):
    global log_scroll
    log_scroll = max(0, log_scroll + delta)


def handle_up():
    if keyboard.row == 0:
        scroll_log(1)
    else:
        keyboard.move_row(-1)


def handle_down():
    if keyboard.row == len(keyboard.ROWS) - 1:
        scroll_log(-1)
    else:
        keyboard.move_row(1)


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
    global log_scroll
    for paragraph in text.split("\n"):
        if not paragraph:
            continue
        for line in wrap_line(paragraph, LOG_MAX_WIDTH):
            log_lines.append((line, pen))
    del log_lines[:-LOG_BUFFER_MAX]
    log_scroll = 0  # snap back to the latest message whenever new content arrives


REQUEST_TIMEOUT = 45  # without this, a stalled connection hangs forever with no way to recover

SYSTEM_PROMPT = (
    "You are a helpful assistant running on a tiny badge with a small pixel "
    "screen. Keep replies short - a sentence or two, no long code blocks or "
    "lists unless specifically asked. If asked to switch to a different "
    "model, use the switch_model tool - its schema lists what's available."
)


def call_model():
    r = requests.post(
        BASETEN_URL,
        headers={
            "Content-Type": "application/json",
            "Authorization": "Api-Key " + BASETEN_API_KEY,
        },
        json={
            "model": MODEL,
            "messages": [{"role": "system", "content": SYSTEM_PROMPT}] + chat_history,
            "tools": build_tools(),
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
    return data["choices"][0]  # message + finish_reason


CALL_ATTEMPTS = 3  # this badge's wifi/TLS stack occasionally drops or mangles a request


def call_model_with_retry():
    last_error = None
    for attempt in range(CALL_ATTEMPTS):
        try:
            return call_model()
        except (OSError, ValueError, RuntimeError) as e:
            last_error = e
            if attempt < CALL_ATTEMPTS - 1:
                set_status("Retrying...")
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
    set_status("Using: " + name)
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

    add_log(text, YOU_COLOR)
    chat_history.append({"role": "user", "content": text})
    del chat_history[:-MAX_HISTORY]

    reply = None
    reply_color = BOT_COLOR
    try:
        for _ in range(MAX_TOOL_ROUNDS):
            set_status("...")
            choice = call_model_with_retry()
            message = choice["message"]
            tool_calls = message.get("tool_calls")
            if not tool_calls:
                # Kimi-K3 can burn the whole token budget on reasoning_content
                # and leave content null if it never got to a final answer.
                reply = to_ascii((message.get("content") or message.get("reasoning_content") or "").strip())
                if reply and choice.get("finish_reason") == "length":
                    reply += " [cut off]"
                reply = reply or "(No reply - response cut off, try a shorter question)"
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
            reply = "(Too many tool calls, giving up)"
            reply_color = ERROR_COLOR
    except (OSError, ValueError, KeyError, IndexError, RuntimeError) as e:
        reply = "Error: " + str(e)
        reply_color = ERROR_COLOR

    status_text = None
    add_log(reply, reply_color)
    if reply_color is BOT_COLOR:
        chat_history.append({"role": "assistant", "content": reply})
        del chat_history[:-MAX_HISTORY]


def activate_key():
    global buffer
    key = keyboard.selected()
    if key == "SPACE":
        buffer += " "
    elif key == "DEL":
        buffer = buffer[:-1]
    elif key == "ENTER":
        send_message()
    else:
        buffer += key


def draw_log():
    global log_scroll
    status_lines = [(line, color.grey) for line in wrap_line(status_text, LOG_MAX_WIDTH)] if status_text else []
    n_visible = LOG_VISIBLE_LINES - len(status_lines)

    if n_visible <= 0:
        real_lines = []
    else:
        total = len(log_lines)
        max_scroll = max(0, total - n_visible)
        log_scroll = max(0, min(log_scroll, max_scroll))
        end = total - log_scroll
        real_lines = log_lines[max(0, end - n_visible) : end]

    shown = real_lines + status_lines

    y = LOG_BOTTOM - len(shown) * LOG_LINE_HEIGHT
    for text, pen in shown:
        screen.pen = pen
        screen.text(text, MARGIN, y)
        y += LOG_LINE_HEIGHT


def draw_header():
    screen.pen = color.grey
    screen.text(MODEL, MARGIN, HEADER_Y)


def draw_composer():
    screen.pen = color.white
    cursor_char = "_" if (badge.ticks // 400) % 2 == 0 else " "
    screen.text(buffer + cursor_char, MARGIN, COMPOSER_Y)


def render():
    screen.pen = color.black
    screen.clear()
    draw_header()
    draw_log()
    draw_composer()
    keyboard.draw(0)


def update():
    global status_text
    if not wifi.connect():
        wifi.tick()
        spinner = SPINNER[(badge.ticks // SPINNER_FRAME_MS) % len(SPINNER)]
        status_text = f"Connecting to {secrets.WIFI_SSID} {spinner}"
        render()
        return
    status_text = None  # clear the "connecting..." message left over from just before this

    if not models_loaded:
        status_text = "Listing models..."
        render()
        badge.update()
        fetch_available_models()
        status_text = None

    if badge.pressed(BUTTON_UP):
        handle_up()
    if badge.pressed(BUTTON_DOWN):
        handle_down()
    if badge.pressed(BUTTON_A):
        keyboard.move_col(-1)
    if badge.pressed(BUTTON_C):
        keyboard.move_col(1)
    if badge.pressed(BUTTON_B):
        activate_key()

    render()


run(update)
