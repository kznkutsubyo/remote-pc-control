#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
APP_DIR="$SCRIPT_DIR/pc-phone-remote"

if [ ! -d "$APP_DIR" ]; then
    echo "Error: pc-phone-remote directory not found next to install-linux.sh" >&2
    exit 1
fi

echo "=== PC Phone Remote Pro — Linux Installer ==="

install_system_packages() {
    if command -v apt-get >/dev/null 2>&1; then
        echo "[1/5] Installing system tools via apt (python3, pip, tk, xdotool, playerctl, wmctrl)..."
        sudo apt-get update -y
        sudo apt-get install -y python3 python3-pip python3-tk xdotool playerctl wmctrl pulseaudio-utils || true
    elif command -v dnf >/dev/null 2>&1; then
        echo "[1/5] Installing system tools via dnf..."
        sudo dnf install -y python3 python3-pip python3-tkinter xdotool playerctl wmctrl pulseaudio-utils || true
    elif command -v pacman >/dev/null 2>&1; then
        echo "[1/5] Installing system tools via pacman..."
        sudo pacman -S --needed --noconfirm python python-pip tk xdotool playerctl wmctrl libpulse || true
    elif command -v zypper >/dev/null 2>&1; then
        echo "[1/5] Installing system tools via zypper..."
        sudo zypper --non-interactive install python3 python3-pip python3-tk xdotool playerctl wmctrl pulseaudio-utils || true
    else
        echo "[1/5] Unknown package manager — make sure python3, xdotool, playerctl, and wmctrl are installed."
    fi
}

install_system_packages

echo "[2/5] Installing Python dependencies..."
if python3 -m pip install --user --quiet -r "$APP_DIR/requirements.txt" 2>/dev/null; then
    true
elif python3 -m pip install --user --break-system-packages --quiet -r "$APP_DIR/requirements.txt" 2>/dev/null; then
    true
else
    python3 -m pip install -r "$APP_DIR/requirements.txt"
fi

echo "[3/5] Generating brand icon & desktop entries..."
python3 "$APP_DIR/brand_icon.py"

ICON_DIR="$HOME/.local/share/icons/hicolor/512x512/apps"
APPS_DIR="$HOME/.local/share/applications"
mkdir -p "$ICON_DIR" "$APPS_DIR"
cp "$APP_DIR/assets/app_icon_512.png" "$ICON_DIR/pc-phone-remote.png"

cat > "$APPS_DIR/pc-phone-remote.desktop" <<EOF
[Desktop Entry]
Type=Application
Name=PC Phone Remote Pro
Comment=Control this Linux PC from Android or iPhone
Exec=python3 "$APP_DIR/configure.py"
Path=$APP_DIR
Icon=$ICON_DIR/pc-phone-remote.png
Terminal=false
Categories=Utility;Network;
EOF
chmod +x "$APPS_DIR/pc-phone-remote.desktop"

echo "[4/5] Configuring firewall ports (TCP 8765, UDP 8766) if active..."
if command -v ufw >/dev/null 2>&1 && sudo ufw status 2>/dev/null | grep -qi "Status: active"; then
    sudo ufw allow 8765/tcp || true
    sudo ufw allow 8766/udp || true
elif command -v firewall-cmd >/dev/null 2>&1 && firewall-cmd --state >/dev/null 2>&1; then
    sudo firewall-cmd --permanent --add-port=8765/tcp || true
    sudo firewall-cmd --permanent --add-port=8766/udp || true
    sudo firewall-cmd --reload || true
fi

echo "[5/5] Configuring unified PIN, autostart, and starting background server..."
PIN_ARG="${1:-}"
if [ -n "$PIN_ARG" ]; then
    python3 "$APP_DIR/installer.py" --silent --pin "$PIN_ARG" --no-firewall --no-shortcuts
else
    python3 "$APP_DIR/installer.py" --silent --no-firewall --no-shortcuts
fi

echo ""
echo "✓ PC Phone Remote Pro is installed and running!"
echo "Open the printed /app URL in iPhone Safari or tap 'Auto-Find PC on Wi-Fi' in Android."
