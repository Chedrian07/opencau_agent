#!/usr/bin/env bash
set -euo pipefail

DISPLAY_VALUE="${DISPLAY:-:1}"
export DISPLAY="${DISPLAY_VALUE}"

xdpyinfo -display "${DISPLAY_VALUE}" >/dev/null
xdotool getmouselocation --shell >/dev/null
python3 - <<'PY'
import socket

for port in (5900, 6080):
    with socket.create_connection(("127.0.0.1", port), timeout=2):
        pass
PY
