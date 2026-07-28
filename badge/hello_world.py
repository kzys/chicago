def update():
    screen.pen = color.navy
    screen.clear()
    screen.pen = color.white
    screen.font = rom_font.smart
    screen.text("Hello, World!", 10, 50)


run(update)
