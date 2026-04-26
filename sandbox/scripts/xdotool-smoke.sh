#!/usr/bin/env bash
set -euo pipefail

DISPLAY_VALUE="${DISPLAY:-:1}"
export DISPLAY="${DISPLAY_VALUE}"

xdotool mousemove 20 20 click 1
xdotool key ctrl+alt+t
sleep 2
xdotool type --delay 1 "opencau smoke"
xdotool key Return
xdotool getmouselocation --shell
