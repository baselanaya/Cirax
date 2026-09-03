"""Platform-aware filesystem locations (Linux / Windows / macOS)."""

from __future__ import annotations

import os
import sys
from pathlib import Path


def state_dir() -> Path:
    """Per-user writable state (crash logs, caches)."""
    if sys.platform == "win32":
        base = os.environ.get("LOCALAPPDATA") or \
            Path.home() / "AppData" / "Local"
        return Path(base) / "Cirax"
    if sys.platform == "darwin":
        return Path.home() / "Library" / "Application Support" / "Cirax"
    return Path.home() / ".local" / "state" / "cirax"


def is_windows() -> bool:
    return sys.platform == "win32"
