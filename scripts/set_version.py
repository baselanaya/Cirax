#!/usr/bin/env python3
"""Set the Cirax version everywhere it lives (no pattern guessing).

Usage:  uv run python scripts/set_version.py 1.2.3
"""

import json
import pathlib
import re
import sys

ROOT = pathlib.Path(__file__).resolve().parent.parent


def fail(msg: str) -> None:
    print(f"error: {msg}", file=sys.stderr)
    sys.exit(1)


def main() -> None:
    if len(sys.argv) != 2:
        fail("usage: set_version.py X.Y.Z")
    ver = sys.argv[1]
    if not re.fullmatch(r"\d+\.\d+\.\d+", ver):
        fail(f"not a plain X.Y.Z version: {ver}")

    pyproject = ROOT / "pyproject.toml"
    text = pyproject.read_text()
    new = re.sub(r'(?m)^version = ".*"$', f'version = "{ver}"', text)
    if new == text:
        fail("pyproject.toml: version line not found or unchanged")
    pyproject.write_text(new)

    init = ROOT / "src" / "cirax" / "__init__.py"
    text = init.read_text()
    new = re.sub(r'(?m)^__version__ = ".*"$', f'__version__ = "{ver}"', text)
    if new == text:
        fail("__init__.py: version line not found or unchanged")
    init.write_text(new)

    npm = ROOT / "npm" / "package.json"
    data = json.loads(npm.read_text())
    data["version"] = ver
    npm.write_text(json.dumps(data, indent=2) + "\n")

    print(f"version set to {ver} (pyproject, __init__, package.json)")


if __name__ == "__main__":
    main()
