#!/bin/sh
# Runs inside the Debian container (see scripts/build_package.sh).
set -eu
export DEBIAN_FRONTEND=noninteractive
apt-get update -qq
apt-get install -y -qq dpkg-dev >/dev/null
useradd -m builder
runuser -u builder -- env VERSION="$VERSION" BETA="$BETA" sh /packaging/deb/as-builder.sh
cp /home/builder/krdpc_*.deb /out/
chmod a+r /out/krdpc_*
