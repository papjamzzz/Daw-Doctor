#!/bin/bash
# ──────────────────────────────────────────────────────────────
#  Ableton Live Diagnostic Tool — One-Line Installer
#
#  For sharing via GitHub. Recipients run:
#
#    curl -fsSL https://raw.githubusercontent.com/YOUR_USERNAME/\
#    ableton-diagnostics/main/install.sh | bash
#
#  Or clone and run:
#    git clone https://github.com/YOUR_USERNAME/ableton-diagnostics
#    cd ableton-diagnostics && ./install.sh
# ──────────────────────────────────────────────────────────────

set -e

# ── Config — UPDATE THESE before sharing ──────────────────────
GITHUB_USER="YOUR_USERNAME"
REPO_NAME="ableton-diagnostics"
BRANCH="main"
INSTALL_DIR="$HOME/$REPO_NAME"
# ──────────────────────────────────────────────────────────────

REPO_URL="https://github.com/$GITHUB_USER/$REPO_NAME"
RAW_URL="https://raw.githubusercontent.com/$GITHUB_USER/$REPO_NAME/$BRANCH"

echo ""
echo "  🎛  Ableton Live Diagnostic Tool — Installer"
echo "  ─────────────────────────────────────────────"
echo ""

# ── Check macOS ────────────────────────────────────────────────
if [[ "$(uname)" != "Darwin" ]]; then
    echo "  ✗  This tool is macOS only."; exit 1
fi
echo "  ✓  macOS $(sw_vers -productVersion)"

# ── Check Python 3 ────────────────────────────────────────────
if ! command -v python3 &>/dev/null; then
    echo ""
    echo "  ✗  Python 3 not found."
    echo "     Install it with:  brew install python3"
    echo "     Or download from: https://python.org"
    exit 1
fi
echo "  ✓  Python $(python3 --version | cut -d' ' -f2)"

# ── Download files ────────────────────────────────────────────
echo ""
echo "  Downloading …"

FILES=(diagnose.py als_analyzer.py monitor.py requirements.txt run.sh)

if command -v git &>/dev/null && [[ "${GITHUB_USER}" != "YOUR_USERNAME" ]]; then
    # Full git clone if configured
    if [ -d "$INSTALL_DIR/.git" ]; then
        echo "  Updating existing install …"
        git -C "$INSTALL_DIR" pull --quiet
    else
        git clone --quiet "$REPO_URL" "$INSTALL_DIR"
    fi
    echo "  ✓  Downloaded via git"
else
    # Fallback: download individual files
    mkdir -p "$INSTALL_DIR"
    if [[ "${GITHUB_USER}" == "YOUR_USERNAME" ]]; then
        # Running locally (setup.sh delegates here, or user cloned manually)
        # Just use the directory the script is in
        INSTALL_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
        echo "  ✓  Using local directory: $INSTALL_DIR"
    else
        for f in "${FILES[@]}"; do
            curl -fsSL "$RAW_URL/$f" -o "$INSTALL_DIR/$f"
        done
        echo "  ✓  Downloaded from GitHub"
    fi
fi

chmod +x "$INSTALL_DIR/run.sh"

# ── Install Python deps ────────────────────────────────────────
echo ""
echo "  Installing Python dependencies …"
python3 -m pip install psutil rich -q --disable-pip-version-check
echo "  ✓  psutil + rich installed"

# ── Shell alias ────────────────────────────────────────────────
echo ""
if [[ "$SHELL" == *"zsh"* ]]; then
    SHELL_RC="$HOME/.zshrc"
else
    SHELL_RC="$HOME/.bash_profile"
fi

ALIAS_LINE="alias abl='$INSTALL_DIR/run.sh'"

if grep -qF "alias abl=" "$SHELL_RC" 2>/dev/null; then
    echo "  ✓  'abl' command already configured"
else
    echo "" >> "$SHELL_RC"
    echo "# Ableton Live Diagnostic Tool" >> "$SHELL_RC"
    echo "$ALIAS_LINE" >> "$SHELL_RC"
    echo "  ✓  Added 'abl' command to $SHELL_RC"
fi

# ── Done ──────────────────────────────────────────────────────
echo ""
echo "  ─────────────────────────────────────────────"
echo "  ✓  Installation complete!"
echo ""
echo "  Installed to: $INSTALL_DIR"
echo ""
echo "  Run now:"
echo "    python3 $INSTALL_DIR/diagnose.py"
echo ""
echo "  After opening a new terminal (alias will be active):"
echo "    abl              ← main tool"
echo "    abl monitor      ← background monitor daemon"
echo "    abl analyze      ← .als project analyzer"
echo ""
echo "  Or run the setup for a Dock .app:"
echo "    $INSTALL_DIR/setup.sh"
echo ""
