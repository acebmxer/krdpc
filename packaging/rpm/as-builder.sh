#!/bin/sh
set -eu
if [ -n "$BETA" ]; then rpm_version="$VERSION~beta.$BETA"; else rpm_version=$VERSION; fi
mkdir -p "$HOME/rpmbuild/SOURCES"
cp "/work/krdpc-$VERSION.tar.gz" "$HOME/rpmbuild/SOURCES/"
tar -xzOf "/work/krdpc-$VERSION.tar.gz" "krdpc-$VERSION/packaging/rpm/krdpc.spec" >"$HOME/krdpc.spec"
rpmbuild -ba "$HOME/krdpc.spec" \
    --define "dist %{nil}" \
    --define "krdpc_version $rpm_version" \
    --define "krdpc_source_version $VERSION"
