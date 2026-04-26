#!/usr/bin/env bash
set -euo pipefail

DISPLAY_VALUE="${DISPLAY:-:1}"
OUT="${1:-/tmp/screenshot.png}"
export DISPLAY="${DISPLAY_VALUE}"

mkdir -p "$(dirname "${OUT}")"
scrot "${OUT}"
test -s "${OUT}"
sha256sum "${OUT}"
