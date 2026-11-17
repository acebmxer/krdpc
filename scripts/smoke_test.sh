#!/usr/bin/env bash
# Installs a built package in a clean distro container and checks krdpc works.
#
#   scripts/smoke_test.sh <fedora|debian|ubuntu|arch> <package-dir>
#
# <package-dir> holds the release files (one .rpm, .deb and .pkg.tar.zst). Fedora
# installs the .rpm, Debian and Ubuntu the .deb, Arch the .pkg.tar.zst. Each run:
# install with the distro's own package manager (which also fetches FreeRDP,
# PySide6 and keyring), check the command, menu entry, icon and Python imports,
# check the package knows its release and format (for updating itself), check the
# real xfreerdp accepts the arguments krdpc builds, then start the app as a normal
# user on a virtual X display and fail if it exits within LAUNCH_SECONDS or does
# not quit on Ctrl+C.
# Uses podman, or docker when podman is not installed.
set -euo pipefail

usage() { echo "Usage: $0 <fedora|debian|ubuntu|arch> <package-dir>" >&2; exit 2; }
[[ $# -eq 2 ]] || usage
distro=$1
packages=$(cd "$2" && pwd) || { echo "No such directory: $2" >&2; exit 2; }
launch_seconds=${LAUNCH_SECONDS:-15}

engine=$(command -v podman || command -v docker || true)
[[ -n "$engine" ]] || { echo "Needs podman or docker" >&2; exit 2; }

find_one() {
    # shellcheck disable=SC2206 # $1 is a glob pattern
    local found=("$packages"/$1)
    [[ ${#found[@]} -eq 1 && -f "${found[0]}" ]] \
        || { echo "Expected exactly one $1 in $packages" >&2; exit 1; }
    basename "${found[0]}"
}

case "$distro" in
    fedora)
        image=registry.fedoraproject.org/fedora:latest
        pkg=$(find_one 'krdpc-*.rpm')
        format=rpm
        install="dnf install -y -q \"/b/$pkg\" xorg-x11-server-Xvfb"
        ;;
    debian | ubuntu)
        if [[ "$distro" == debian ]]; then image=docker.io/library/debian:trixie; else image=docker.io/library/ubuntu:26.04; fi
        pkg=$(find_one 'krdpc_*.deb')
        format=deb
        install="export DEBIAN_FRONTEND=noninteractive; apt-get update -qq \
            && apt-get install -y -qq \"/b/$pkg\" xvfb >/dev/null"
        ;;
    arch)
        image=docker.io/library/archlinux:latest
        pkg=$(find_one 'krdpc-*.pkg.tar.zst')
        format=arch
        install="pacman -Syu --noconfirm --needed -q xorg-server-xvfb >/dev/null \
            && pacman -U --noconfirm \"/b/$pkg\" >/dev/null"
        ;;
    *) usage ;;
esac

# Runs inside the container as root. $1 = launch seconds, $2 = package format.
read -r -d '' check <<'INNER' || true
set -euo pipefail
launch_seconds=$1
export KRDPC_FORMAT=$2

command -v krdpc >/dev/null || { echo "FAIL: no krdpc command"; exit 1; }
grep -q '^Exec=krdpc' /usr/share/applications/krdpc.desktop \
    || { echo "FAIL: bad or missing menu entry"; exit 1; }
[[ -f /usr/share/icons/hicolor/scalable/apps/krdpc.svg ]] || { echo "FAIL: no icon"; exit 1; }
# FreeRDP 3's program is xfreerdp3 on Debian and Ubuntu, xfreerdp on Fedora and Arch.
xfreerdp=$(command -v xfreerdp3 || command -v xfreerdp || true)
[[ -n "$xfreerdp" ]] || { echo "FAIL: no xfreerdp program was installed"; exit 1; }
"$xfreerdp" --version 2>&1 | grep -q 'version 3' || { echo "FAIL: $xfreerdp is not FreeRDP 3"; exit 1; }
echo "ok: command, menu entry, icon, $("$xfreerdp" --version 2>&1 | head -1)"

# The packaged code, imported the way the installed command imports it.
QT_QPA_PLATFORM=offscreen python3 - <<'PY'
from pathlib import Path

import keyring
import krdpc
from PySide6.QtGui import QIcon
from PySide6.QtWidgets import QApplication

app = QApplication([])
icon = QIcon(str(Path(krdpc.__file__).with_name("krdpc.svg")))
assert not icon.pixmap(32, 32).isNull(), "the SVG icon does not draw (Qt SVG support missing)"
print("ok: krdpc", krdpc.__version__, "imports, icon draws, keyring", keyring.__name__)
PY

# The package knows which release and format it is, so it can update itself.
python3 - <<'PY'
import os

from krdpc import updates

current = updates.installed()
assert current.package_format == os.environ["KRDPC_FORMAT"], current
assert current.can_update_itself and updates.version_key(current.release), current
print("ok: package says it is krdpc", current.release, current.package_format)
PY

# The real xfreerdp must accept every option krdpc can build (an unknown option gives
# exit code 128). It is pointed at a closed local port, so it only fails to connect.
python3 - >/tmp/args <<'PY'
from krdpc.command import build_command
from krdpc.profile import Profile

profile = Profile(
    name="smoke", server="127.0.0.1:1", username="u", domain="D",
    resolution_mode="fixed", resolution_width=1280, resolution_height=720,
    color_depth="16", quality="poor", maximize=True, multimon=True, clipboard=False,
    sound="local", microphone=True, drive="/tmp", share_printers=True, share_usb=True,
    security="nla", trusted_certificate="ab" * 32, network="lan", reconnect_attempts=2,
    timeout=5, console=True, client_name="cl", keyboard_layout="0x409", program="notepad",
)
print("\n".join(build_command(profile, "xfreerdp", "a password")[1:]))
PY
set +e
timeout 30 "$xfreerdp" /args-from:stdin </tmp/args >/tmp/xfreerdp.log 2>&1
code=$?
set -e
if [[ $code -eq 128 || $code -eq 124 || $code -eq 139 ]]; then
    echo "FAIL: xfreerdp did not accept krdpc's options (exit $code)"; tail -5 /tmp/xfreerdp.log; exit 1
fi
echo "ok: xfreerdp accepted krdpc's options (exit $code is the refused connection)"

id tester >/dev/null 2>&1 || useradd -m tester
Xvfb :99 -screen 0 1280x800x24 >/dev/null 2>&1 &
sleep 2
log=/tmp/app.log
# setpriv runs krdpc itself (no su/sh in between), so $pid is the app and Ctrl+C reaches it.
setpriv --reuid=tester --regid=tester --init-groups \
    env HOME=/home/tester DISPLAY=:99 krdpc >"$log" 2>&1 &
pid=$!
for _ in $(seq "$launch_seconds"); do
    if ! kill -0 "$pid" 2>/dev/null; then
        echo "FAIL: krdpc exited early"; cat "$log"; exit 1
    fi
    sleep 1
done
echo "ok: krdpc stayed up for ${launch_seconds}s on a virtual display"
kill -INT "$pid"
for _ in $(seq 10); do
    kill -0 "$pid" 2>/dev/null || break
    sleep 1
done
if kill -0 "$pid" 2>/dev/null; then echo "FAIL: krdpc did not quit on Ctrl+C"; exit 1; fi
echo "ok: krdpc quit on Ctrl+C"
INNER

"$engine" run --rm --security-opt label=disable -v "$packages":/b:ro -e CHECK="$check" \
    "$image" sh -c "$install && bash -c \"\$CHECK\" _ $launch_seconds $format"
