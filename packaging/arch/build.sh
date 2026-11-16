#!/bin/sh
# Runs inside the Arch Linux container (see scripts/build_package.sh).
set -eu
pacman -Syu --noconfirm --needed base-devel python-build python-installer python-setuptools \
    python-wheel >/dev/null
useradd -m builder
runuser -u builder -- env VERSION="$VERSION" BETA="$BETA" sh /packaging/arch/as-builder.sh
cp /home/builder/pkg/krdpc-*.pkg.tar.zst /out/
chmod a+r /out/krdpc-*
