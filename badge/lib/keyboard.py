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


def col_x(row_idx, col_idx, margin):
    # Each column's edge computed independently (col_idx * available // n)
    # rather than from a single shared width (available // n) * col_idx --
    # the latter loses whatever available isn't evenly divisible by n as an
    # uncovered gap after the last column; this puts that remainder into
    # the last column's width instead, so the row exactly fills [margin,
    # screen.width - margin] with no leftover.
    n = len(ROWS[row_idx])
    return margin + col_idx * (screen.width - 2 * margin) // n


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
    n_rows = len(ROWS)
    for row_idx, key_row in enumerate(ROWS):
        y = top + row_idx * ROW_HEIGHT
        # Inset only on the trailing edge (right/bottom) rather than both --
        # an inter-key gap of exactly KEY_PAD instead of KEY_PAD * 2, without
        # needing a fractional KEY_PAD to get there. Skipped entirely for the
        # last row/column: that inset exists to separate a key from the next
        # one, and there is no next one there -- the full remaining space (the
        # last column also being wider, having absorbed the row's leftover
        # width from col_x's rounding) is free to use instead.
        box_h = ROW_HEIGHT if row_idx == n_rows - 1 else ROW_HEIGHT - KEY_PAD
        n_cols = len(key_row)
        for col_idx, key in enumerate(key_row):
            x = col_x(row_idx, col_idx, margin)
            x_next = col_x(row_idx, col_idx + 1, margin)
            box_w = (x_next - x) if col_idx == n_cols - 1 else (x_next - x - KEY_PAD)
            is_selected = row_idx == row and col_idx == col
            bg, fg = (SELECTED_BG, SELECTED_FG) if is_selected else (KEY_BG, KEY_FG)

            screen.pen = bg
            screen.rectangle(x, y, box_w, box_h)
            screen.pen = fg
            # Uppercase only the plain character keys, not the LABELS words
            # (delete/enter/space) -- descenders (g/j/p/q/y) sit right at the
            # bottom edge of a key this short, but the words are too wide for
            # their column already without also widening for all-caps.
            label = LABELS.get(key, key.upper())
            label_w, label_h = screen.measure_text(label)
            screen.text(label, x + (box_w - label_w) // 2, y + (box_h - label_h) // 2)

    screen.font = previous_font
