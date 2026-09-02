#!/usr/bin/env bash
# Copy the Python source into npm/python/ so `npm publish` ships it.
# Run before publishing:  cd npm && npm run build:python && npm publish
set -euo pipefail
cd "$(dirname "$0")/../.."

rm -rf npm/python
mkdir -p npm/python/src
cp pyproject.toml README.md LICENSE npm/python/ 2>/dev/null || cp pyproject.toml README.md npm/python/
cp -r src/cirax npm/python/src/
find npm/python -name '__pycache__' -type d -exec rm -rf {} +
echo "bundled python source into npm/python/ (version: $(grep -m1 version npm/python/pyproject.toml))"
