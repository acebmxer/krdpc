#!/bin/sh
set -eu
if [ -n "$BETA" ]; then pkgver="${VERSION}_beta.$BETA"; else pkgver=$VERSION; fi
mkdir -p "$HOME/pkg"
cp "/work/krdpc-$VERSION.tar.gz" "$HOME/pkg/"
tar -xzOf "/work/krdpc-$VERSION.tar.gz" "krdpc-$VERSION/packaging/arch/PKGBUILD" >"$HOME/pkg/PKGBUILD"
cd "$HOME/pkg"
PACKAGER=acebmxer KRDPC_PKGVER="$pkgver" KRDPC_SRCVER="$VERSION" makepkg -f -d --noconfirm
