#!/bin/sh
# Cirax installer.
#
# One-liner (once hosted):
#   curl -fsSL https://raw.githubusercontent.com/cirax/cirax/main/install.sh | sh
#
# What it does:
#   1. ensures `uv` is present (installs it to ~/.local/bin if missing)
#   2. installs the `cirax` CLI via `uv tool install`
#      - from PyPI when the package is published there
#      - otherwise from git (override with CIRAX_REPO=...)
#   3. prints the `cirax doctor` hint
#
# Env overrides:
#   CIRAX_SRC    install from a local checkout directory (no network needed)
#   CIRAX_REPO   git URL to install from   (default: https://github.com/cirax/cirax)
#   CIRAX_REF    git ref to install        (default: main)
#   CIRAX_VERSION install a specific PyPI version
set -eu

SRC="${CIRAX_SRC:-}"
REPO="${CIRAX_REPO:-https://github.com/cirax/cirax}"
REF="${CIRAX_REF:-main}"
VERSION="${CIRAX_VERSION:-}"

have() { command -v "$1" >/dev/null 2>&1; }

echo "==> cirax installer"

# 1. uv — installer needs curl or wget; system Python is NOT required (uv
#    manages its own interpreters).
if ! have uv; then
    if have curl; then
        curl -LsSf https://astral.sh/uv/install.sh | sh
    elif have wget; then
        wget -qO- https://astral.sh/uv/install.sh | sh
    else
        echo "error: need curl or wget to bootstrap uv" >&2
        exit 1
    fi
    export PATH="$HOME/.local/bin:$PATH"
fi

# 2. cirax
if [ -n "$SRC" ]; then
    uv tool install --force --upgrade "$SRC" && INSTALL="local ($SRC)"
elif [ -n "$VERSION" ]; then
    uv tool install --force --upgrade "cirax==$VERSION" && INSTALL="pypi"
elif uv tool install --force --upgrade cirax 2>/dev/null; then
    INSTALL="pypi"
else
    echo "==> not on PyPI yet, installing from git ($REPO@$REF)"
    TMP="$(mktemp -d)"
    trap 'rm -rf "$TMP"' EXIT
    git clone --depth 1 --branch "$REF" "$REPO" "$TMP/cirax"
    uv tool install --force "$TMP/cirax"
    INSTALL="git"
fi

# 3. post-install
echo
echo "==> installed ($INSTALL). Try it:"
echo "      cirax doctor            # what can this machine convert?"
echo "      cirax convert a.png -t webp"
echo
echo "    Engines are system packages; install hints:"
echo "      cirax doctor --show-missing"
