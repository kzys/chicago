badge.mode(HIRES)

MARGIN = 20
GAP = 8

# Every named color/font the firmware exposes, discovered rather than
# hardcoded so these pages don't drift out of sync with the palette/font set.
COLOR_NAMES = sorted(
    name for name in dir(color) if not name.startswith("_") and not callable(getattr(color, name))
)
FONT_NAMES = sorted(name for name in dir(rom_font) if not name.startswith("_"))

page = 0


def utc_now():
    year, month, day, hour, minute, second, _ = rtc.datetime()
    return "{:04d}-{:02d}-{:02d} {:02d}:{:02d}:{:02d} UTC".format(year, month, day, hour, minute, second)


def draw_profile():
    lines = [
        ("Kazuyoshi Kato", rom_font.futile, color.white),
        ("(he/him)", rom_font.nope, color.smoke),
        ("", rom_font.nope, color.smoke),
        ("Infrastructure / Runtime Fabric", rom_font.nope, color.smoke),
        ("Seattle, Washington", rom_font.nope, color.smoke),
        ("Battery: {}%  {}".format(badge.battery_level(), utc_now()), rom_font.winds, color.white),
    ]

    heights = []
    for text, font, _ in lines:
        screen.font = font
        heights.append(screen.measure_text(text)[1])

    y = (screen.height - (sum(heights) + GAP * (len(lines) - 1))) // 2
    for (text, font, pen), h in zip(lines, heights):
        screen.font = font
        screen.pen = pen
        screen.text(text, MARGIN, y)
        y += h + GAP


def draw_colors():
    screen.font = rom_font.smart
    swatch = 16
    row_h = 20
    col_w = screen.width // 2
    rows = -(-len(COLOR_NAMES) // 2)  # ceil division: 2 columns

    for i, name in enumerate(COLOR_NAMES):
        col, row = divmod(i, rows)
        x = col * col_w + MARGIN // 2
        y = row * row_h + MARGIN // 2
        screen.pen = getattr(color, name)
        screen.rectangle(x, y, swatch, swatch)
        screen.pen = color.white
        screen.text(name, x + swatch + 6, y)


def draw_fonts():
    cols = 4
    rows = -(-len(FONT_NAMES) // cols)  # ceil division
    cell_w = screen.width // cols
    cell_h = screen.height // rows

    for i, name in enumerate(FONT_NAMES):
        row, col = divmod(i, cols)
        x = col * cell_w
        y = row * cell_h
        # Fonts vary wildly in glyph size (see badgewaremax vs winds) — clip
        # each cell so a wide/tall face can't bleed into its neighbors.
        screen.clip = rect(x + 1, y + 1, cell_w - 2, cell_h - 2)
        screen.font = getattr(rom_font, name)
        screen.pen = color.white
        screen.text(name, x + 2, y + 2)
    screen.clip = rect(0, 0, screen.width, screen.height)


PAGES = [draw_profile, draw_colors, draw_fonts]


def update():
    global page
    if badge.pressed(BUTTON_DOWN):
        page = (page + 1) % len(PAGES)
    if badge.pressed(BUTTON_UP):
        page = (page - 1) % len(PAGES)

    screen.pen = color.navy
    screen.clear()
    PAGES[page]()


run(update)
