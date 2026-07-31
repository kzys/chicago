"""Shared on-screen QWERTY grid: layout, navigation, and rendering. What a
selected key actually does (SPACE/DEL/ENTER/a regular character) stays
app-specific -- this only owns the grid's state, movement, and drawing.

Installed to /lib/keyboard.py (see `make install-lib`), which is on
sys.path regardless of which app's directory is the current one, so any
app can just `import keyboard`.
"""

ROWS = [
    list("1234567890") + ["DEL"],
    list("qwertyuiop") + ["ENTER"],
    list("asdfghjkl") + [";", "'"],
    list("zxcvbnm") + [",", ".", "/", "SPACE"],
]

# Every row above has exactly 11 columns (an ortholinear grid, not the usual
# staggered QWERTY rows) so UP/DOWN keeps the cursor's column meaning
# consistent instead of landing on a visually unrelated key.
LABELS = {"SPACE": "space", "ENTER": "enter", "DEL": "delete"}

FONT = rom_font.winds
ROW_HEIGHT = 13  # smaller than a nope-sized 14 to match winds' shorter glyphs
KEY_PAD = 1
KEY_BG = color.rgb(30, 40, 55)
KEY_FG = color.white
SELECTED_BG = color.white
SELECTED_FG = color.black

row = 1
col = 0


def top_y(margin):
    return screen.height - margin - len(ROWS) * ROW_HEIGHT


def key_width(row_idx, margin):
    return (screen.width - 2 * margin) // len(ROWS[row_idx])


def row_x_offset(row_idx, margin):
    n = len(ROWS[row_idx])
    w = key_width(row_idx, margin)
    return margin + (screen.width - 2 * margin - n * w) // 2


def clamp_col():
    global col
    col = max(0, min(len(ROWS[row]) - 1, col))


def move_row(delta):
    global row
    row = max(0, min(len(ROWS) - 1, row + delta))
    clamp_col()


def move_col(delta):
    global col
    n = len(ROWS[row])
    col = (col + delta) % n


def selected():
    return ROWS[row][col]


def draw(margin):
    # Own font, restored afterward -- otherwise it'd leak into whatever the
    # calling app draws next frame, since apps set screen.font once at
    # startup rather than before every draw call.
    previous_font = screen.font
    screen.font = FONT

    top = top_y(margin)
    for row_idx, key_row in enumerate(ROWS):
        w = key_width(row_idx, margin)
        x0 = row_x_offset(row_idx, margin)
        y = top + row_idx * ROW_HEIGHT
        # Inset only on the trailing edge (right/bottom) rather than both --
        # an inter-key gap of exactly KEY_PAD instead of KEY_PAD * 2, without
        # needing a fractional KEY_PAD to get there.
        box_w = w - KEY_PAD
        box_h = ROW_HEIGHT - KEY_PAD
        for col_idx, key in enumerate(key_row):
            x = x0 + col_idx * w
            is_selected = row_idx == row and col_idx == col
            bg, fg = (SELECTED_BG, SELECTED_FG) if is_selected else (KEY_BG, KEY_FG)

            screen.pen = bg
            screen.rectangle(x, y, box_w, box_h)
            screen.pen = fg
            label = LABELS.get(key, key)
            label_w, label_h = screen.measure_text(label)
            screen.text(label, x + (box_w - label_w) // 2, y + (box_h - label_h) // 2)

    screen.font = previous_font
