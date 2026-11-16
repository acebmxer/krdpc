#!/bin/sh
# Prints the version in src/krdpc/__init__.py, the one place it is kept.
set -eu
sed -n 's/^__version__ = "\(.*\)"$/\1/p' "$(dirname "$0")/../src/krdpc/__init__.py"
