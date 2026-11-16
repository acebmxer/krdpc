#!/bin/sh
# Runs inside the Fedora container (see scripts/build_package.sh): installs the build
# tools as root, builds as a normal user, copies the result to /out.
set -eu
dnf install -y -q rpm-build python3-devel pyproject-rpm-macros python3-setuptools \
    python3-wheel desktop-file-utils >/dev/null
useradd -m builder
runuser -u builder -- env VERSION="$VERSION" BETA="$BETA" sh /packaging/rpm/as-builder.sh
for rpm in /home/builder/rpmbuild/RPMS/noarch/krdpc-*.rpm; do
    # "~" is not kept in a GitHub release file name, so the beta is written with "-".
    cp "$rpm" "/out/$(basename "$rpm" | sed 's/~/-/')"
done
chmod a+r /out/krdpc-*
