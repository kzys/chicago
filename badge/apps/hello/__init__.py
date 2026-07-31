badge.mode(HIRES)

MARGIN = 20
GAP = 8

# Every named color/font the firmware exposes, discovered rather than
# hardcoded so these pages don't drift out of sync with the palette/font set.
COLOR_NAMES = sorted(
    name for name in dir(color) if not name.startswith("_") and not callable(getattr(color, name))
)
FONT_NAMES = sorted(name for name in dir(rom_font) if not name.startswith("_"))

ALNUM = "ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789"
PANGRAM = "the quick brown fox jumps over the lazy dog"
FONT_PREVIEW_W = 320 - MARGIN * 2  # wrap width for the preview lines


def _is_monospace(font):
    screen.font = font
    widths = set(screen.measure_text(c)[0] for c in ALNUM)
    return len(widths) == 1


def _wrap_text(font, text, max_width):
    screen.font = font
    lines = []
    current = ""
    for word in text.split(" "):
        candidate = word if not current else current + " " + word
        w, _ = screen.measure_text(candidate)
        if w <= max_width or not current:
            current = candidate
        else:
            lines.append(current)
            current = word
    if current:
        lines.append(current)
    return lines


def _build_font_row(name):
    font = getattr(rom_font, name)
    mono = _is_monospace(font)

    screen.font = rom_font.sins
    meta = "{} {}px {}".format(name, font.height, "monospace" if mono else "")
    _, meta_h = screen.measure_text(meta)

    return {
        "font": font,
        "meta": meta,
        "meta_h": meta_h,
        # Both cases, not the previous single Title-cased line, so a font's
        # lowercase and uppercase glyphs are both actually visible.
        "lines": _wrap_text(font, PANGRAM, FONT_PREVIEW_W) + _wrap_text(font, PANGRAM.upper(), FONT_PREVIEW_W),
        "line_h": font.height,
    }


# Per-font state, computed once at startup rather than on every redraw of
# the font page. Same idea as draw_profile's per-line (text, font, color)
# tuples, just with a pre-wrapped list of preview lines per font.
FONT_ROWS = [_build_font_row(name) for name in FONT_NAMES]

page = 0
font_scroll = 0


def utc_now():
    year, month, day, hour, minute, second, _ = rtc.datetime()
    return "{:04d}-{:02d}-{:02d} {:02d}:{:02d}:{:02d} UTC".format(year, month, day, hour, minute, second)


def draw_profile():
    lines = [
        ("Kazuyoshi Kato", rom_font.ignore, color.white),
        ("(he/him)", rom_font.nope, color.smoke),
        ("", rom_font.nope, color.smoke),
        ("Infrastructure / Runtime Fabric", rom_font.nope, color.smoke),
        ("Seattle, Washington", rom_font.nope, color.smoke),
        ("", rom_font.nope, color.smoke),
        (
            "  ".join(
                [
                    "Battery: {}".format(
                        "Charging" if badge.is_charging() else "{}%".format(badge.battery_level())
                    ),
                    "{:.2f}V".format(badge.battery_voltage()),
                ]
                + (["USB"] if badge.usb_connected() else [])
            ),
            rom_font.teatime,
            color.white,
        ),
        (utc_now(), rom_font.teatime, color.white),
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
    for row in FONT_ROWS[font_scroll:]:
        block_h = row["meta_h"] + len(row["lines"]) * row["line_h"]
        if y + block_h > screen.height:
            break

        screen.font = rom_font.sins
        screen.pen = color.smoke
        screen.text(row["meta"], MARGIN, y)
        y += row["meta_h"]

        screen.font = row["font"]
        screen.pen = color.white
        for line in row["lines"]:
            screen.text(line, MARGIN, y)
            y += row["line_h"]

        y += GAP


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
            font_scroll = min(len(FONT_ROWS) - 1, font_scroll + 1)

    screen.pen = color.navy
    screen.clear()
    PAGES[page]()


run(update)
