# chicago

Apps for a [Pimoroni Tufty 2350](https://shop.pimoroni.com/en-us/products/tufty-2350) badge running [Badgeware](https://badgewa.re/) firmware (MicroPython). Built at [Baseten](https://www.baseten.co/)'s Chicago offsite.

Each app lives in `badge/apps/<name>/` and is installed onto the badge over USB — there's no emulator, so "running" an app means putting it on real hardware.

## Apps

- **hello** — font/color preview grid, for browsing what the firmware ships.
- **chat** — LLM chat client (Baseten Model APIs) with an on-device keyboard.
- **diffusion** — text-to-image via a Baseten-hosted diffusion model.
- **isitdown** — status page dashboard (Baseten, Claude).
- **config** — WiFi network picker, backed by saved credentials.

## Setup

Requires Python 3.12+ and [uv](https://docs.astral.sh/uv/):

```
uv sync
```

Connect the badge over USB, then install an app:

```
make install-chat            # copies badge/apps/chat to the device and resets it
make uninstall-chat          # removes it
```

`DEVICE` defaults to `/dev/ttyACM0`:

```
make install-chat DEVICE=/dev/ttyACM1
```

Catch syntax errors before installing (on-device tracebacks are painful to debug):

```
python3 -m py_compile badge/apps/chat/__init__.py
```

## WiFi and API keys

Nothing here is committed with real credentials — `secrets.py` only carries non-sensitive config (region/timezone) plus logic to load WiFi credentials at import time. Everything else is provisioned onto the device separately and gitignored locally:

```
make install-secrets                                  # secrets.py -> device
make provision-wifi                                    # pull saved WiFi from NetworkManager -> device
make add-wifi-network SSID="some network"              # prompt for one network's password -> device
make install-baseten-state FILE=baseten.json           # Baseten API keys -> device
```

`chat` and `diffusion` each read their own key out of `/state/baseten.json` (`BASETEN_API_KEY`, `BASETEN_IMAGE_API_KEY`).

See `CLAUDE.md` for more on the app architecture, install mechanics, and platform gotchas.
