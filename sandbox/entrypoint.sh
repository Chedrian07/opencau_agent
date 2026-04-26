#!/usr/bin/env bash
set -euo pipefail

DISPLAY_VALUE="${DISPLAY:-:1}"
DISPLAY_WIDTH="${DISPLAY_WIDTH:-1920}"
DISPLAY_HEIGHT="${DISPLAY_HEIGHT:-1080}"
DISPLAY_DEPTH="${DISPLAY_DEPTH:-24}"

export DISPLAY="${DISPLAY_VALUE}"
export HOME=/home/agent
export XDG_RUNTIME_DIR=/run/user/1200

mkdir -p /tmp/.X11-unix /run/user/1200 /home/agent/.cache /home/agent/.config /home/agent/Downloads
chmod 1777 /tmp/.X11-unix

rm -f /tmp/.X1-lock /tmp/opencau-ready

Xvfb "${DISPLAY_VALUE}" \
  -screen 0 "${DISPLAY_WIDTH}x${DISPLAY_HEIGHT}x${DISPLAY_DEPTH}" \
  -ac \
  +extension RANDR &
xvfb_pid=$!

for _ in $(seq 1 50); do
  if xdpyinfo -display "${DISPLAY_VALUE}" >/dev/null 2>&1; then
    break
  fi
  sleep 0.1
done

dbus-launch --exit-with-session startxfce4 >/tmp/xfce.log 2>&1 &
xfce_pid=$!

x11vnc \
  -display "${DISPLAY_VALUE}" \
  -localhost \
  -forever \
  -shared \
  -nopw \
  -rfbport 5900 \
  -quiet >/tmp/x11vnc.log 2>&1 &
x11vnc_pid=$!

websockify \
  --web=/usr/share/novnc/ \
  0.0.0.0:6080 \
  localhost:5900 >/tmp/websockify.log 2>&1 &
websockify_pid=$!

cleanup() {
  kill "${websockify_pid}" "${x11vnc_pid}" "${xfce_pid}" "${xvfb_pid}" >/dev/null 2>&1 || true
}
trap cleanup EXIT INT TERM

for _ in $(seq 1 100); do
  if /usr/local/bin/healthcheck.sh >/dev/null 2>&1; then
    touch /tmp/opencau-ready
    break
  fi
  sleep 0.2
done

if [ ! -f /tmp/opencau-ready ]; then
  echo "sandbox failed readiness checks" >&2
  exit 1
fi

wait -n "${xvfb_pid}" "${xfce_pid}" "${x11vnc_pid}" "${websockify_pid}"
