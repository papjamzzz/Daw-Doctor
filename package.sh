#!/bin/bash
# ──────────────────────────────────────────────────────────────
#  Ableton Live Diagnostic Tool — Build for Distribution
#
#  Creates a standalone macOS binary (no Python required)
#  and wraps it in a .dmg for easy sharing.
#
#  Output:
#    dist/ableton-diagnostics          ← standalone binary
#    Ableton-Diagnostics-v2.0.dmg      ← shareable disk image
#
#  Usage:
#    ./package.sh
#    ./package.sh --no-dmg             ← binary only
# ──────────────────────────────────────────────────────────────

set -e
TOOL_DIR="$(cd "$(dirname "$0")" && pwd)"
VERSION="2.0"
APP_NAME="Ableton-Diagnostics"
NO_DMG=false

for arg in "$@"; do
    [[ "$arg" == "--no-dmg" ]] && NO_DMG=true
done

echo ""
echo "  🎛  Ableton Diagnostics — Building v$VERSION"
echo "  ─────────────────────────────────────────────"
echo ""

cd "$TOOL_DIR"

# ── Check Python ───────────────────────────────────────────────
if ! command -v python3 &>/dev/null; then
    echo "  ✗  python3 not found"; exit 1
fi
echo "  ✓  Python $(python3 --version | cut -d' ' -f2)"

# ── Install PyInstaller ────────────────────────────────────────
echo "  Installing PyInstaller …"
python3 -m pip install pyinstaller psutil rich -q --disable-pip-version-check
echo "  ✓  PyInstaller ready"
echo ""

# ── Build binary ───────────────────────────────────────────────
echo "  Building standalone binary …"
echo "  (This takes ~30 seconds)"
echo ""

python3 -m PyInstaller \
    --onefile \
    --name "ableton-diagnostics" \
    --collect-all psutil \
    --collect-all rich \
    --hidden-import psutil \
    --hidden-import rich \
    --hidden-import rich.console \
    --hidden-import rich.panel \
    --hidden-import rich.table \
    --hidden-import rich.live \
    --hidden-import rich.text \
    --hidden-import rich.rule \
    --hidden-import rich.align \
    --hidden-import rich.columns \
    --hidden-import rich.prompt \
    --hidden-import xml.etree.ElementTree \
    --noconfirm \
    --clean \
    diagnose.py

echo ""
echo "  ✓  Binary built: dist/ableton-diagnostics"

# ── Prepare distribution folder ────────────────────────────────
echo "  Assembling distribution package …"

DIST_STAGE="$TOOL_DIR/dist-package"
rm -rf "$DIST_STAGE"
mkdir -p "$DIST_STAGE"

# Copy the main binary
cp dist/ableton-diagnostics "$DIST_STAGE/"
chmod +x "$DIST_STAGE/ableton-diagnostics"

# Copy Python companion scripts (als_analyzer, monitor use system Python)
cp als_analyzer.py "$DIST_STAGE/"
cp monitor.py      "$DIST_STAGE/"
cp requirements.txt "$DIST_STAGE/"

# Write a self-contained run.sh
cat > "$DIST_STAGE/run.sh" << 'RUNEOF'
#!/bin/bash
# Ableton Live Diagnostic Tool — Launcher
DIR="$(cd "$(dirname "$0")" && pwd)"

case "${1:-}" in
    monitor)
        # monitor.py needs Python (for osascript, psutil)
        python3 "$DIR/monitor.py" "${@:2}"
        ;;
    analyze|als)
        python3 "$DIR/als_analyzer.py" "${@:2}"
        ;;
    *)
        # Main app: use the standalone binary
        "$DIR/ableton-diagnostics"
        ;;
esac
RUNEOF
chmod +x "$DIST_STAGE/run.sh"

# Write a minimal install script for recipients
cat > "$DIST_STAGE/INSTALL.txt" << INSTALLEOF
ABLETON LIVE DIAGNOSTIC TOOL  v${VERSION}
"OBD for your DAW"  ·  macOS Edition
════════════════════════════════════════

HOW TO USE
──────────
Double-click the terminal commands below, or open Terminal and type:

  cd /path/to/this/folder

  ./ableton-diagnostics          ← main diagnostic tool
  ./run.sh monitor               ← background alerts daemon
  ./run.sh analyze               ← .als project file analyzer

QUICK SETUP (optional — adds 'abl' command to your terminal)
─────────────────────────────────────────────────────────────
  echo "alias abl='/path/to/ableton-diagnostics'" >> ~/.zshrc
  source ~/.zshrc
  abl

REQUIREMENTS
────────────
· macOS 11 or later
· For monitor.py and als_analyzer.py: Python 3 (built into macOS)
  Install deps: pip3 install psutil rich

SUPPORT
───────
github.com/YOUR_USERNAME/ableton-diagnostics
INSTALLEOF

echo "  ✓  Distribution package ready: dist-package/"

# ── Build DMG ─────────────────────────────────────────────────
if [ "$NO_DMG" = false ]; then
    echo ""
    echo "  Building DMG disk image …"

    DMG_NAME="${APP_NAME}-v${VERSION}.dmg"

    # Remove old DMG if exists
    rm -f "$TOOL_DIR/$DMG_NAME"

    hdiutil create \
        -volname "$APP_NAME v$VERSION" \
        -srcfolder "$DIST_STAGE" \
        -ov \
        -format UDZO \
        "$TOOL_DIR/$DMG_NAME" \
        > /dev/null

    echo "  ✓  DMG created: $DMG_NAME"
    echo "     Size: $(du -sh "$TOOL_DIR/$DMG_NAME" | cut -f1)"
fi

# ── Cleanup PyInstaller temp files ─────────────────────────────
echo ""
echo "  Cleaning up build artifacts …"
rm -rf build/ ableton-diagnostics.spec
echo "  ✓  Done"

# ── Summary ───────────────────────────────────────────────────
echo ""
echo "  ─────────────────────────────────────────────"
echo "  ✓  Build complete!"
echo ""
echo "  Files created:"
echo "    dist/ableton-diagnostics    ← standalone binary (no Python needed)"
echo "    dist-package/               ← full distribution folder"
if [ "$NO_DMG" = false ]; then
    echo "    ${APP_NAME}-v${VERSION}.dmg   ← shareable disk image"
fi
echo ""
echo "  To share:"
echo "    Send the .dmg to anyone on macOS 11+"
echo "    They double-click to mount, then run ./ableton-diagnostics"
echo ""
echo "  To test the binary:"
echo "    ./dist/ableton-diagnostics"
echo ""
