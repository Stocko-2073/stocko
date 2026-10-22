#!/usr/bin/env bash
# Open the U-BOT console: ESP-IDF's serial monitor, which is a full terminal so
# linenoise line editing, history and tab completion all work.
#
#   ./monitor.sh                    default port
#   ./monitor.sh /dev/cu.usbmodem101
#
# Ctrl-] leaves. The board resets when the monitor attaches, so the boot log
# comes first and the `ubot> ` prompt after it.
set -euo pipefail

PORT="${1:-/dev/cu.usbmodem2101}"
IDF="${IDF_PATH:-$HOME/esp/esp-idf}"

cd "$(dirname "$0")"
# shellcheck disable=SC1091
. "$IDF/export.sh" >/dev/null
exec idf.py -p "$PORT" monitor
