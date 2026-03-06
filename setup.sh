#!/bin/bash
# ──────────────────────────────────────────────────────────────
#  Ableton Live Diagnostic Tool — Personal Setup
#
#  Installs:
#    1. Terminal alias  →  type  abl  anywhere to launch
#    2. Clickable .app  →  drag to your Dock (optional)
# ──────────────────────────────────────────────────────────────

set -e
TOOL_DIR="$(cd "$(dirname "$0")" && pwd)"

# Detect shell config
if [[ "$SHELL" == *"zsh"* ]]; then
    SHELL_RC="$HOME/.zshrc"
else
    SHELL_RC="$HOME/.bash_profile"
fi

echo ""
echo "  ⚕  DAW Doctor — Setup"
echo "  ─────────────────────────────────────────"
echo ""

# ── Step 1: Install Python deps ────────────────────────────────
echo "  [1/3]  Installing Python dependencies …"
python3 -m pip install psutil rich -q --disable-pip-version-check
echo "         ✓  psutil + rich installed"
echo ""

# ── Step 2: Shell alias ────────────────────────────────────────
echo "  [2/3]  Setting up terminal alias …"
ALIAS_LINE="alias abl='$TOOL_DIR/run.sh'"

if grep -qF "alias abl=" "$SHELL_RC" 2>/dev/null; then
    echo "         ✓  'abl' alias already exists in $SHELL_RC"
else
    echo "" >> "$SHELL_RC"
    echo "# Ableton Live Diagnostic Tool" >> "$SHELL_RC"
    echo "$ALIAS_LINE" >> "$SHELL_RC"
    echo "         ✓  Added 'abl' alias to $SHELL_RC"
fi
echo ""

# ── Step 3: Clickable .app (optional) ─────────────────────────
echo "  [3/3]  Create a clickable .app for your Dock?"
echo "         (Opens a Terminal window and launches the tool)"
echo ""
read -rp "         Create Ableton Diagnostics.app? [y/N]: " CREATE_APP

if [[ "$CREATE_APP" =~ ^[Yy]$ ]]; then
    APP_DIR="$HOME/Applications"
    APP_PATH="$APP_DIR/DAW Doctor.app"
    mkdir -p "$APP_DIR"

    # Build an AppleScript .app that opens Terminal and runs the tool
    # Write to a temp file to avoid shell escaping issues with osacompile -e
    cat > /tmp/abl_launcher.applescript << APPLEEOF
tell application "Terminal"
    if not (exists window 1) then reopen
    activate
    do script "cd '$TOOL_DIR' && python3 diagnose.py; exec \$SHELL"
end tell
APPLEEOF
    osacompile -o "$APP_PATH" /tmp/abl_launcher.applescript 2>/dev/null
    rm -f /tmp/abl_launcher.applescript

    if [ -d "$APP_PATH" ]; then
        echo ""
        echo "         ✓  Created: $APP_PATH"
        echo "         → Open Finder → Applications → drag it to your Dock"
        echo "         → Or: open '$APP_PATH'"

        # Offer to open it now to reveal in Finder
        read -rp "         Reveal in Finder now? [y/N]: " REVEAL
        if [[ "$REVEAL" =~ ^[Yy]$ ]]; then
            open -R "$APP_PATH"
        fi
    else
        echo "         ✗  Could not create .app (osacompile failed)"
    fi
else
    echo "         Skipped."
fi

# ── Done ──────────────────────────────────────────────────────
echo ""
echo "  ─────────────────────────────────────────"
echo "  ✓  Setup complete!"
echo ""
echo "  To launch from any terminal:"
echo "    source $SHELL_RC   (one time, to load the alias)"
echo "    abl                (then type this anytime)"
echo ""
echo "  Direct commands:"
echo "    $TOOL_DIR/run.sh"
echo "    $TOOL_DIR/run.sh monitor   ← background alerts"
echo "    $TOOL_DIR/run.sh analyze   ← .als file analyzer"
echo ""
