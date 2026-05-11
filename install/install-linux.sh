#!/usr/bin/env bash
# KimiReader Install Script for Linux/macOS
# Usage: bash install-linux.sh

set -e

PLUGIN_NAME="kimireader"
PLUGIN_VERSION="2.0.0"

RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
CYAN='\033[0;36m'
NC='\033[0m' # No Color

header() {
    echo -e "${CYAN}\n========================================"
    echo -e "$1"
    echo -e "========================================\n${NC}"
}

ok() {
    echo -e "${GREEN}[OK] $1${NC}"
}

warn() {
    echo -e "${YELLOW}[WARN] $1${NC}"
}

err() {
    echo -e "${RED}[ERR] $1${NC}"
}

# ==================== 0. Detect Project Root ====================
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"
cd "$PROJECT_ROOT"

header "KimiReader Installer for Linux/macOS"
echo "Project root: $PROJECT_ROOT"

# ==================== 1. Check Python ====================
header "Step 1: Checking Python"

PYTHON_CMD=""
for cmd in python3 python py3; do
    if command -v "$cmd" &> /dev/null; then
        ver_str=$($cmd --version 2>&1)
        if [[ $ver_str =~ Python\ ([0-9]+)\.([0-9]+) ]]; then
            major="${BASH_REMATCH[1]}"
            minor="${BASH_REMATCH[2]}"
            if [[ $major -ge 3 && $minor -ge 8 ]]; then
                PYTHON_CMD="$cmd"
                ok "Found $ver_str at $(command -v "$cmd")"
                break
            else
                warn "Found $cmd but version too old: $ver_str (need 3.8+)"
            fi
        fi
    fi
done

if [[ -z "$PYTHON_CMD" ]]; then
    err "Python 3.8+ not found. Please install Python."
    echo "  Ubuntu/Debian: sudo apt update && sudo apt install python3 python3-pip"
    echo "  macOS: brew install python3"
    exit 1
fi

# ==================== 2. Install Dependencies ====================
header "Step 2: Installing Python Dependencies"

REQUIREMENTS_FILE="$PROJECT_ROOT/browser_agent/requirements.txt"
if [[ -f "$REQUIREMENTS_FILE" ]]; then
    $PYTHON_CMD -m pip install --user -r "$REQUIREMENTS_FILE"
    ok "Python packages installed"
else
    warn "requirements.txt not found, installing playwright directly"
    $PYTHON_CMD -m pip install --user playwright
fi

# ==================== 3. Install Playwright Browsers ====================
header "Step 3: Installing Playwright Browsers"

$PYTHON_CMD -m playwright install chromium || {
    warn "playwright install chromium failed, trying with system deps..."
    $PYTHON_CMD -m playwright install --with-deps chromium
}
ok "Playwright Chromium browser installed"

# ==================== 4. Install CLI Plugin ====================
header "Step 4: Installing Kimi Code CLI Plugin"

KIMI_PLUGINS_DIR="$HOME/.kimi/plugins"
PLUGIN_TARGET_DIR="$KIMI_PLUGINS_DIR/$PLUGIN_NAME"

mkdir -p "$KIMI_PLUGINS_DIR"

# Remove old version if exists
if [[ -d "$PLUGIN_TARGET_DIR" ]]; then
    warn "Removing old plugin at $PLUGIN_TARGET_DIR"
    rm -rf "$PLUGIN_TARGET_DIR"
fi

# Copy plugin files
cp -r "$PROJECT_ROOT/plugin" "$PLUGIN_TARGET_DIR"
ok "Plugin installed to $PLUGIN_TARGET_DIR"

# ==================== 5. Install User-Level Skill ====================
header "Step 5: Installing Agent Skill"

KIMI_SKILLS_DIR="$HOME/.kimi/skills"
AGENTS_SKILLS_DIR="$HOME/.config/agents/skills"

# Prefer .kimi/skills (brand-specific)
SKILL_TARGET_DIR="$KIMI_SKILLS_DIR"
mkdir -p "$KIMI_SKILLS_DIR"

# Install chat-to-code skill
SKILL_SOURCE="$PROJECT_ROOT/skill/chat-to-code"
SKILL_DEST="$SKILL_TARGET_DIR/chat-to-code"
if [[ -d "$SKILL_DEST" ]]; then rm -rf "$SKILL_DEST"; fi
cp -r "$SKILL_SOURCE" "$SKILL_DEST"
ok "Skill 'chat-to-code' installed to $SKILL_DEST"

# Install 导入聊天记录 skill
IMPORT_SKILL_SOURCE="$PROJECT_ROOT/skill/import-chat"
IMPORT_SKILL_DEST="$SKILL_TARGET_DIR/import-chat"
if [[ -d "$IMPORT_SKILL_DEST" ]]; then rm -rf "$IMPORT_SKILL_DEST"; fi
cp -r "$IMPORT_SKILL_SOURCE" "$IMPORT_SKILL_DEST"
ok "Skill '导入聊天记录' installed to $IMPORT_SKILL_DEST"

# ==================== 6. VSCode Extension Check ====================
header "Step 6: VSCode Extension Check"

VSCODE_EXT_DIR="$HOME/.vscode/extensions"
KIMI_VSCODE_EXT=$(find "$VSCODE_EXT_DIR" -maxdepth 1 -name "moonshot-ai.kimi-code-*" 2>/dev/null | head -n 1)

if [[ -n "$KIMI_VSCODE_EXT" ]]; then
    ok "Found VSCode Kimi Code extension: $(basename "$KIMI_VSCODE_EXT")"
    echo "Note: VSCode Kimi Code uses the same CLI underneath, so the plugin should work in VSCode too."
    echo "To use in VSCode: open Kimi Code chat panel, then type '/flow:chat-to-code' or '/skill:chat-to-code-plan'"
else
    warn "VSCode Kimi Code extension not found. You can install it from VSCode marketplace."
fi

# ==================== 7. Project-Level Skill (Optional) ====================
header "Step 7: Project-Level Skill (Optional)"

GIT_ROOT=""
if command -v git &> /dev/null; then
    GIT_ROOT=$(git rev-parse --show-toplevel 2>/dev/null || true)
fi

if [[ -n "$GIT_ROOT" ]]; then
    PROJECT_SKILL_DIR="$GIT_ROOT/.kimi/skills/chat-to-code"
    PROJECT_IMPORT_SKILL_DIR="$GIT_ROOT/.kimi/skills/import-chat"
    if [[ ! -d "$PROJECT_SKILL_DIR" ]]; then
        read -p "Install Skills to current project ($GIT_ROOT)? [Y/n] " response
        if [[ -z "$response" || "$response" =~ ^[Yy]$ ]]; then
            mkdir -p "$(dirname "$PROJECT_SKILL_DIR")"
            cp -r "$SKILL_SOURCE" "$PROJECT_SKILL_DIR"
            cp -r "$IMPORT_SKILL_SOURCE" "$PROJECT_IMPORT_SKILL_DIR"
            ok "Project-level skills installed"
        fi
    fi
else
    warn "Not in a git repository. Project-level skill not installed."
    echo "You can manually copy 'skill/chat-to-code' to your project's '.kimi/skills/' directory."
fi

# ==================== 8. Create python3 symlink if needed ====================
header "Step 8: Adapting Plugin for Python"

PYTHON_EXE=$(command -v "$PYTHON_CMD")
echo "Detected Python executable: $PYTHON_EXE"

# On some systems, 'python3' is available but plugin.json uses it.
# Check if python3 is actually available.
if ! command -v python3 &> /dev/null; then
    # Create a symlink or wrapper
    WRAPPER_DIR="$HOME/.local/bin"
    mkdir -p "$WRAPPER_DIR"
    ln -sf "$PYTHON_EXE" "$WRAPPER_DIR/python3"
    ok "Created python3 symlink at $WRAPPER_DIR/python3"
    echo "Please ensure $WRAPPER_DIR is in your PATH."
fi

# ==================== 9. Final Instructions ====================
header "Installation Complete!"

echo -e "\nNext steps:"
echo "1. Restart Kimi Code CLI (or VSCode if using the extension)"
echo "2. Run the following command in Kimi Code chat:"
echo "   /flow:chat-to-code"
echo "   or"
echo "   /skill:chat-to-code-plan"
echo -e "\n3. First time only: you may need to login:"
echo "   The Flow will prompt you to login if not already logged in."
echo "   Or manually run:"
echo "   -> kimi_login (opens browser for manual login)"
echo -e "\n4. Your login state is saved at:"
echo "   ~/.kimireader"
echo -e "\nFor help, see README.md in $PROJECT_ROOT"
