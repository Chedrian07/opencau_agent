#!/usr/bin/env bash
set -euo pipefail

DISPLAY_VALUE="${DISPLAY:-:1}"
DISPLAY_WIDTH="${DISPLAY_WIDTH:-1920}"
DISPLAY_HEIGHT="${DISPLAY_HEIGHT:-1080}"
DISPLAY_DEPTH="${DISPLAY_DEPTH:-24}"

export DISPLAY="${DISPLAY_VALUE}"
export HOME=/home/agent
export XDG_RUNTIME_DIR=/run/user/1200

mkdir -p /tmp/.X11-unix /run/user/1200 /home/agent/.cache /home/agent/.config /home/agent/Desktop /home/agent/Downloads
chmod 1777 /tmp/.X11-unix
chown -R agent:agent /home/agent

rm -f /tmp/.X1-lock /tmp/opencau-ready

configure_firefox_profile() {
  local profile_dir="/home/agent/.mozilla/firefox/opencau.default-release"
  mkdir -p "${profile_dir}"
  cat > /home/agent/.mozilla/firefox/profiles.ini <<'EOF'
[Profile0]
Name=opencau
IsRelative=1
Path=opencau.default-release
Default=1

[General]
StartWithLastProfile=1
Version=2
EOF
  cat > "${profile_dir}/user.js" <<'EOF'
user_pref("browser.aboutwelcome.enabled", false);
user_pref("browser.newtabpage.enabled", false);
user_pref("browser.shell.checkDefaultBrowser", false);
user_pref("browser.startup.homepage", "about:blank");
user_pref("browser.startup.homepage_override.buildID", "ignore");
user_pref("browser.startup.homepage_override.mstone", "ignore");
user_pref("browser.startup.page", 0);
user_pref("datareporting.policy.dataSubmissionPolicyBypassNotification", true);
user_pref("startup.homepage_welcome_url", "");
user_pref("startup.homepage_welcome_url.additional", "");
user_pref("toolkit.telemetry.reportingpolicy.firstRun", false);
EOF
}

configure_firefox_profile

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

eval "$(dbus-launch --sh-syntax)"
export DBUS_SESSION_BUS_ADDRESS

if command -v xfconf-query >/dev/null 2>&1; then
  {
    xfconf-query -c xfce4-desktop -p /desktop-icons/file-icons/show-home -n -t bool -s false
    xfconf-query -c xfce4-desktop -p /desktop-icons/file-icons/show-filesystem -n -t bool -s false
    xfconf-query -c xfce4-desktop -p /desktop-icons/file-icons/show-removable -n -t bool -s false
    xfconf-query -c xfce4-desktop -p /desktop-icons/file-icons/show-trash -n -t bool -s false
  } >/tmp/xfce-desktop-config.log 2>&1 || true
fi

startxfce4 >/tmp/xfce.log 2>&1 &
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
  if [ -n "${DBUS_SESSION_BUS_PID:-}" ]; then
    kill "${DBUS_SESSION_BUS_PID}" >/dev/null 2>&1 || true
  fi
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
