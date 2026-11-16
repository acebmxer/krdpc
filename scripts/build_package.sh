#!/usr/bin/env bash
# Builds one package in a clean distro container, as a normal user.
#
#   scripts/build_package.sh <rpm|deb|arch> <out-dir> [beta-number]
#
# rpm  -> built on Fedora          -> krdpc-<version>-1.noarch.rpm
# deb  -> built on Debian 13       -> krdpc_<version>_all.deb
# arch -> built on Arch Linux      -> krdpc-<version>-1-any.pkg.tar.zst
#
# With a beta number the files are named <version>-beta.<n> (0.1.0-beta.1) and the
# package metadata says 0.1.0~beta.1 (Arch: 0.1.0_beta.1), which sorts before 0.1.0.
# The code is taken from the working tree, so a clean checkout is what CI builds.
# Uses podman, or docker when podman is not installed.
set -euo pipefail

usage() { echo "Usage: $0 <rpm|deb|arch> <out-dir> [beta-number]" >&2; exit 2; }
[[ $# -ge 2 && $# -le 3 ]] || usage
format=$1
beta=${3:-}
[[ -z "$beta" || "$beta" =~ ^[0-9]+$ ]] || usage

root=$(cd "$(dirname "$0")/.." && pwd)
mkdir -p "$2"
out=$(cd "$2" && pwd)
version=$("$root/scripts/package_version.sh")
[[ "$version" =~ ^[0-9]+\.[0-9]+\.[0-9]+$ ]] || { echo "Odd version: '$version'" >&2; exit 1; }

engine=$(command -v podman || command -v docker || true)
[[ -n "$engine" ]] || { echo "Needs podman or docker" >&2; exit 2; }

case "$format" in
    rpm) image=registry.fedoraproject.org/fedora:latest ;;
    deb) image=docker.io/library/debian:trixie ;;
    arch) image=docker.io/library/archlinux:latest ;;
    *) usage ;;
esac

work=$(mktemp -d)
trap 'rm -rf -- "$work"' EXIT
chmod 755 "$work"
tar -C "$root" \
    --exclude-vcs --exclude=./build --exclude=./dist --exclude='*.egg-info' \
    --exclude=__pycache__ --exclude=.pytest_cache --exclude=.ruff_cache --exclude=.venv \
    --transform "s,^\./,krdpc-$version/," \
    -czf "$work/krdpc-$version.tar.gz" .
chmod 644 "$work/krdpc-$version.tar.gz"

"$engine" run --rm --security-opt label=disable \
    -v "$work":/work:rw -v "$root/packaging":/packaging:ro -v "$out":/out:rw \
    -e VERSION="$version" -e BETA="$beta" \
    "$image" sh "/packaging/$format/build.sh"

ls -l "$out"
