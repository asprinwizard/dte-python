#!/bin/bash
# Sets up a Raspberry Pi OS Bookworm Lite (64-bit) CM4 as a DTE recorder.
# Run from the project directory as root:  sudo ./deploy/setup.sh
# Safe to run more than once.
#
# It does NOT install the custom FireWire kernel; see README.md for that.
set -euo pipefail

APP_USER=dte
PROJECT_DIR="$(cd "$(dirname "$0")/.." && pwd)"
BOOT_CONFIG=/boot/firmware/config.txt

if [[ $EUID -ne 0 ]]; then
    echo "Run as root: sudo $0" >&2
    exit 1
fi

echo "== Packages"
apt-get update
apt-get install -y \
    python3-venv python3-gpiozero python3-lgpio python3-rpi.gpio \
    exfatprogs dosfstools \
    libraw1394-11 libavc1394-0 librom1394-0 libiec61883-0 libdv4

echo "== User groups"
for group in gpio video plugdev; do
    getent group "$group" >/dev/null && usermod -aG "$group" "$APP_USER"
done

echo "== Python environment"
sudo -u "$APP_USER" python3 -m venv --system-site-packages "$PROJECT_DIR/.venv"
sudo -u "$APP_USER" "$PROJECT_DIR/.venv/bin/pip" install -r "$PROJECT_DIR/requirements.txt"

echo "== System files"
install -m 0440 "$PROJECT_DIR/deploy/99-dte-sudoers" /etc/sudoers.d/99-dte
visudo -cf /etc/sudoers.d/99-dte
install -m 0644 "$PROJECT_DIR/deploy/99-dte-firewire.rules" /etc/udev/rules.d/99-dte-firewire.rules
install -m 0644 "$PROJECT_DIR/deploy/99-dte-sysctl.conf" /etc/sysctl.d/99-dte.conf
udevadm control --reload-rules && udevadm trigger --subsystem-match=firewire || true
sysctl --system >/dev/null

install -d -o "$APP_USER" -g "$APP_USER" /media/dte /media/dte/usb
install -d -o "$APP_USER" -g "$APP_USER" "/home/$APP_USER/Videos"

echo "== Boot config ($BOOT_CONFIG)"
add_line() {
    grep -qxF "$1" "$BOOT_CONFIG" || { echo "$1" >> "$BOOT_CONFIG"; echo "  added: $1"; }
}
add_line "dtoverlay=pcie-32bit-dma"
add_line "dtoverlay=pwm-2chan,pin=12,func=4,pin2=13,func2=4"
if ! grep -q "^kernel=kernel-firewire.img" "$BOOT_CONFIG"; then
    echo "  WARNING: kernel=kernel-firewire.img is not set; see README.md"
fi

echo "== Checks"
if [[ ! -x "$PROJECT_DIR/dvgrab" ]]; then
    echo "  WARNING: $PROJECT_DIR/dvgrab is missing or not executable"
elif ! "$PROJECT_DIR/dvgrab" --version 2>&1 | grep -q -- "-dte"; then
    echo "  WARNING: ./dvgrab is not a dvgrab-dte build with --json; build feature/json-status"
fi
if [[ -r /proc/config.gz ]]; then
    for opt in CONFIG_EXFAT_FS CONFIG_VFAT_FS CONFIG_USB_STORAGE CONFIG_FIREWIRE_OHCI; do
        zgrep -qE "^$opt=(y|m)" /proc/config.gz || echo "  WARNING: $opt is not enabled in the running kernel"
    done
fi

echo "== Service"
install -m 0644 "$PROJECT_DIR/deploy/dte.service" /etc/systemd/system/dte.service
systemctl daemon-reload
systemctl enable dte.service

echo "Done. Reboot to apply the boot config, then check: systemctl status dte"
