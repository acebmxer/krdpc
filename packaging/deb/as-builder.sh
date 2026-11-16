#!/bin/sh
set -eu
if [ -n "$BETA" ]; then
    deb_version="$VERSION~beta.$BETA"
    file_version="$VERSION-beta.$BETA"
else
    deb_version=$VERSION
    file_version=$VERSION
fi
tar -xzf "/work/krdpc-$VERSION.tar.gz" -C "$HOME"
src="$HOME/krdpc-$VERSION"
stage="$HOME/stage"

install -d "$stage/DEBIAN" "$stage/usr/bin" "$stage/usr/lib/python3/dist-packages" \
    "$stage/usr/share/applications" "$stage/usr/share/icons/hicolor/scalable/apps" \
    "$stage/usr/share/doc/krdpc"
cp -r "$src/src/krdpc" "$stage/usr/lib/python3/dist-packages/krdpc"
install -m 0755 "$src/packaging/deb/krdpc.launcher" "$stage/usr/bin/krdpc"
install -m 0644 "$src/data/krdpc.desktop" "$stage/usr/share/applications/krdpc.desktop"
install -m 0644 "$src/src/krdpc/krdpc.svg" "$stage/usr/share/icons/hicolor/scalable/apps/krdpc.svg"
install -m 0644 "$src/LICENSE" "$stage/usr/share/doc/krdpc/copyright"
# Not named changelog.gz: Debian reads that name as a Debian-format changelog.
gzip -9n -c "$src/CHANGELOG.md" >"$stage/usr/share/doc/krdpc/CHANGELOG.md.gz"
chmod 0644 "$stage/usr/share/doc/krdpc/CHANGELOG.md.gz"
find "$stage" -type d -exec chmod 0755 {} +
find "$stage/usr/lib" -type f -exec chmod 0644 {} +

(cd "$stage" && find . -type f ! -path './DEBIAN/*' -printf '%P\0' | xargs -0 md5sum >DEBIAN/md5sums)
size=$(du -sk --exclude=DEBIAN "$stage" | cut -f1)
sed -e "s/@VERSION@/$deb_version/" -e "s/@SIZE@/$size/" "$src/packaging/deb/control.in" \
    >"$stage/DEBIAN/control"
install -m 0755 "$src/packaging/deb/postinst" "$src/packaging/deb/prerm" "$stage/DEBIAN/"

dpkg-deb --root-owner-group --build "$stage" "$HOME/krdpc_${file_version}_all.deb"
