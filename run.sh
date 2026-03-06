#!/bin/bash
# ──────────────────────────────────────────────────────────────
#  Ableton Live Diagnostic Tool  v2.0
#  "OBD for your DAW"
#
#  Usage:
#    ./run.sh              — main diagnostic app
#    ./run.sh monitor      — background monitor daemon
#    ./run.sh analyze      — .als project file analyzer
# ──────────────────────────────────────────────────────────────

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"

case "${1:-}" in
    monitor)
        python3 "$SCRIPT_DIR/monitor.py" "${@:2}"
        ;;
    analyze|als)
        python3 "$SCRIPT_DIR/als_analyzer.py" "${@:2}"
        ;;
    *)
        python3 "$SCRIPT_DIR/diagnose.py"
        ;;
esac
