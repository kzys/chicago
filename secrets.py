"""Installed onto the device as /system/secrets.py (see `make install-secrets`
in the README/CLAUDE.md). Unlike most secrets.py files, this one is meant to
be committed: it holds no actual credentials, just non-sensitive config plus
the logic to load WiFi credentials from /state at import time (needed here
specifically because the firmware's own wifi.connect() reads
secrets.WIFI_SSID/WIFI_PASSWORD directly). Other API keys (see badge/apps/chat
and badge/apps/diffusion) are loaded by the apps that use them instead, since
nothing forces them through this file.
"""
import json

# Options are us, cuba, eu, moldova, lebanon, egypt, chile, australia, nz
REGION = "us"

# Offset from GMT as number of hours, i.e. 0, 1, -7 etc.
# PDT is -7, CDT is -5.
TIMEZONE = -7

# WiFi credentials come from whichever network badge/apps/config's picker
# last connected to, not a hardcoded value -- see badge/apps/config and
# scripts/provision_wifi_json.py for how /state/config.json gets written.
WIFI_SSID = None
WIFI_PASSWORD = None
try:
    with open("/state/config.json") as _f:
        _config = json.load(_f)
    _selected = _config.get("selected")
    _networks = _config.get("networks", {})
    if _selected and _selected in _networks:
        WIFI_SSID = _selected
        WIFI_PASSWORD = _networks[_selected]
except (OSError, ValueError):
    pass
