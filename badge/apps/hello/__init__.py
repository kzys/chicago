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
font_scroll = 0


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
        ("Battery: {}%  {}".format(badge.battery_level(), utc_now()), rom_font.teatime, color.white),
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
    border = 1
    row_h = 20
    col_w = screen.width // 2
    rows = -(-len(COLOR_NAMES) // 2)  # ceil division: 2 columns

    for i, name in enumerate(COLOR_NAMES):
        col, row = divmod(i, rows)
        x = col * col_w + MARGIN // 2
        y = row * row_h + MARGIN // 2
        # Draw a black rect a shade bigger underneath, then the swatch on
        # top of it, so the border shows as a ring rather than needing a
        # separate outline-only draw call.
        screen.pen = color.black
        screen.rectangle(x - border, y - border, swatch + 2 * border, swatch + 2 * border)
        screen.pen = getattr(color, name)
        screen.rectangle(x, y, swatch, swatch)
        screen.pen = color.white
        screen.text(name, x + swatch + 6, y)


def draw_fonts():
    y = MARGIN
    for name in FONT_NAMES[font_scroll:]:
        screen.font = getattr(rom_font, name)
        _, h = screen.measure_text(name)
        if y + h > screen.height:
            break
        screen.pen = color.white
        screen.text(name, MARGIN, y)
        y += h + GAP


PAGES = [draw_profile, draw_colors, draw_fonts]
FONTS_PAGE = PAGES.index(draw_fonts)


def update():
    global page, font_scroll
    if badge.pressed(BUTTON_A):
        page = (page - 1) % len(PAGES)
    if badge.pressed(BUTTON_C):
        page = (page + 1) % len(PAGES)

    if page == FONTS_PAGE:
        if badge.pressed(BUTTON_UP):
            font_scroll = max(0, font_scroll - 1)
        if badge.pressed(BUTTON_DOWN):
            font_scroll = min(len(FONT_NAMES) - 1, font_scroll + 1)

    screen.pen = color.navy
    screen.clear()
    PAGES[page]()


run(update)
