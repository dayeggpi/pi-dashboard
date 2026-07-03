#!/usr/bin/env bash
# LED Matrix install script — run as root: sudo bash install.sh
set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
INSTALL_DIR=/opt/led-matrix
SERVICE=led-matrix

echo "=== LED Matrix Installer ==="
echo "Source dir: $SCRIPT_DIR"
echo "Install dir: $INSTALL_DIR"
echo ""

# ── System dependencies ───────────────────────────────────────────────────────
apt-get update -qq
apt-get install -y \
  python3 python3-pip python3-venv \
  python3-pillow python3-numpy python3-rpi.gpio \
  libopenjp2-7 libtiff6 libwebp7 \
  fonts-dejavu-core \
  git build-essential \
  --no-install-recommends

# ── Build rpi-rgb-led-matrix (official C library + Python bindings) ───────────
if [ ! -d /tmp/rpi-rgb-led-matrix ]; then
  echo "Cloning rpi-rgb-led-matrix..."
  git clone https://github.com/hzeller/rpi-rgb-led-matrix.git /tmp/rpi-rgb-led-matrix
fi

cd /tmp/rpi-rgb-led-matrix
make clean
make -j$(nproc)
make install-python PYTHON=$(which python3)
cd -

# ── Copy project files ────────────────────────────────────────────────────────
echo "Copying files to $INSTALL_DIR..."
mkdir -p "$INSTALL_DIR"
cp -r "$SCRIPT_DIR"/* "$INSTALL_DIR/"
find "$INSTALL_DIR" -maxdepth 1 -type f \( -name "*.sh" -o -name "*.service" \) -exec sed -i 's/\r$//' {} +
chmod +x "$INSTALL_DIR/wait-for-network.sh"

# ── Python venv + pip deps ────────────────────────────────────────────────────
echo "Creating Python venv..."
python3 -m venv "$INSTALL_DIR/venv" --system-site-packages
"$INSTALL_DIR/venv/bin/pip" install --upgrade pip -q
"$INSTALL_DIR/venv/bin/pip" install \
  flask \
  Pillow \
  requests \
  spotipy \
  -q

# ── sudoers for shutdown ──────────────────────────────────────────────────────
if ! grep -q 'led-matrix-shutdown' /etc/sudoers.d/led-matrix 2>/dev/null; then
  echo "www-data ALL=(ALL) NOPASSWD: /sbin/shutdown" > /etc/sudoers.d/led-matrix
  chmod 440 /etc/sudoers.d/led-matrix
fi

# ── Disable audio (conflicts with PWM used by matrix) ────────────────────────
if grep -q "dtparam=audio=on" /boot/config.txt 2>/dev/null; then
  sed -i 's/dtparam=audio=on/dtparam=audio=off/' /boot/config.txt
  echo "Audio disabled in /boot/config.txt (required for PWM matrix timing)"
fi

# Also for Pi 5 / newer boot path
BOOT_CFG=/boot/firmware/config.txt
if [ -f "$BOOT_CFG" ] && grep -q "dtparam=audio=on" "$BOOT_CFG"; then
  sed -i 's/dtparam=audio=on/dtparam=audio=off/' "$BOOT_CFG"
fi

# ── systemd service ───────────────────────────────────────────────────────────
install -m 644 "$INSTALL_DIR/led-matrix.service" /etc/systemd/system/led-matrix.service
systemctl daemon-reload
systemctl enable "$SERVICE"
systemctl restart "$SERVICE"

echo ""
echo "=== Done! ==="
echo "Service status:  sudo systemctl status $SERVICE"
echo "Logs:            sudo journalctl -u $SERVICE -f"
echo "Web UI:          http://$(hostname -I | awk '{print $1}'):8080"
echo ""
echo "Next steps:"
echo "  1. Set your Spotify credentials at the web UI → Spotify section"
echo "  2. Reboot to apply audio-off change: sudo reboot"
