# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What this is

Apps for a Pimoroni Tufty 2350 badge (Badgeware firmware, MicroPython). Each app lives in `badge/apps/<name>/` and is deployed to the physical device over USB. There is no emulator/test harness in this repo — "running" an app means installing it to real hardware.

## Commands

```
make install-<app_name>      # e.g. make install-chat - copies badge/apps/<app_name> to the device and resets it
make uninstall-<app_name>    # removes it from the device
make install-secrets FILE=path/to/secrets.py   # copies a local secrets.py onto the device
```

`DEVICE` defaults to `/dev/ttyACM0` and can be overridden: `make install-chat DEVICE=/dev/ttyACM1`.

Before installing, catch syntax errors early (MicroPython tracebacks on-device are painful to debug otherwise):

```
python3 -m py_compile badge/apps/<app_name>/__init__.py
```

There is no linter, formatter, or test suite configured in this project — don't invent one.

### Install mechanics (important gotchas)

- Install/uninstall work by launching the badge's own `mass_storage` app to expose its filesystem as a USB drive (`scripts/_msc_common.py`), copying files, unmounting, then running `mpremote ... reset` — **this reboots the whole badge**, killing whatever app was running.
- Because of that reset, **installing an app does not hot-reload a currently-running instance**. After `make install-X`, you must relaunch the app from the on-device menu (or via `launch()`, see below) to actually run the new code — otherwise you're testing stale behavior.
- The badge's menu has no concept of app order — it just lists `/system/apps` entries alphabetically. `badge/apps/order.txt` is the source of truth for menu order; install/uninstall (`scripts/_order_common.py`) prefix the on-device directory with that 1-based index (e.g. local `badge/apps/chat/` becomes `/system/apps/02_chat` if it's second in `order.txt`). Local directory names under `badge/apps/` stay unprefixed on purpose, so reordering apps is a one-line edit to `order.txt` instead of a directory rename that muddies git history. A new app must be added to `order.txt` or `make install-<app_name>` fails.
- `secrets.py` (WiFi credentials, API keys) is never stored in this repo. It only exists on the device, written via `make install-secrets`. Treat it as a live secret file when reconstructing it locally for updates — read the current one off the device (`mpremote fs cat /system/secrets.py`) rather than guessing its contents.

## Badgeware app architecture

An app is a directory with:
- `__init__.py` — entry point. Runs in a global namespace where the firmware has already injected `screen`, `badge`, `color`, `rom_font`/`pixel_font`, `text`, `image`, `shape`, `rect`, `vec2`, `wifi`, `requests`, `secrets`, button constants (`BUTTON_A/B/C/UP/DOWN/HOME`), display mode constants (`HIRES`/`LORES`/`VSYNC`), and `run()`/`launch()`/`reset()` — these are NOT imports, they're already global. Module-level code runs once at launch; define `update()` (called every frame) and end the file with `run(update)`.
- `icon.png` — 24×24 PNG shown in the badge's menu.

Frame loop shape used by every app here: `update()` reads input (`badge.pressed(BUTTON_X)`, edge-triggered), mutates state, then does one clear+draw+text pass before returning. The framework flips the display and polls buttons automatically after `update()` returns each frame.

Non-obvious platform facts (confirmed empirically, contradicted by or missing from the docs):
- `screen.update()` **does not exist** despite being documented — use `badge.update()` for a mid-frame display flush (e.g. showing a status line before a blocking network call). It also clears the framebuffer and polls buttons as a side effect, so treat it as "advance one frame," not a cheap flush.
- Interrupting a running app from a new `mpremote` connection (to inspect state, grab a screenshot, etc.) resets transient hardware/display state — screen resolution reverts to the default and `badge.caselights()` turns off — even though the app's own variables would otherwise survive. Don't treat readings taken that way as proof a feature is broken; verify by keeping the whole check in one uninterrupted `mpremote run` invocation instead.
- The on-device `requests`/`urequests` HTTP client (they're the same implementation) has no default timeout — pass `timeout=` explicitly or a stalled connection hangs forever with no recovery. Its `Response` only exposes `.json()`/`.text`/`.content`/`.close()`, no streaming/incremental read, so true response streaming isn't achievable through this client.
- That same HTTP client appears to size the outgoing request body by Python character count rather than UTF-8 byte count. Any multi-byte character (emoji, smart quotes/dashes) in a JSON request body silently truncates it, producing a "syntax error in JSON" or "EOF while parsing" on the *next* request that includes that stored text. Keep anything that gets stored and re-sent (e.g. chat history) ASCII-only.
- `badge.mode(HIRES)` gives 320×240 on Tufty; without it, the default is 160×120 (`LORES`).

## Verifying changes without physical interaction

Since there's no emulator, driving an app's logic programmatically (for automated checks, or to grab a screenshot) means executing its `__init__.py` standalone rather than through the menu:

```python
import os
os.chdir("/system/apps/<numbered_app_name>")  # on-device name, e.g. 02_chat — see order.txt, not badge/apps/<app_name>
src = open("__init__.py").read()
src = src.replace("run(update)", "")   # strip the blocking call at the end
exec(src, globals())
# now call update(), or individual functions, directly
```

Run this via `mpremote connect $DEVICE run script.py` as a single invocation — this shares the module's real globals (`screen`, `badge`, etc. are true globals injected by the firmware, not locals of some wrapper), so functions defined in the app's source work as-is. To capture what would be on-screen, dump the raw framebuffer and convert it (RGBA8888, so `width * height * 4` bytes):

```python
with open("/shot.raw", "wb") as f:
    f.write(screen.raw[: screen.width * screen.height * 4])
```

then pull it off with `mpremote fs cp :/shot.raw ./shot.raw` and decode with e.g. `PIL.Image.frombuffer("RGBA", (w, h), data, "raw", "RGBA", 0, 1)`. Clean up `/shot.raw` afterward — the device's flash is small enough that leftover raw screenshots (300KB each) can fill it.
