"""Input type detection: extension overrides first (deterministic for our
vocabulary), then file(1) content sniffing, then stdlib guessing."""

from __future__ import annotations

import mimetypes
import subprocess
from pathlib import Path

# file(1) outputs that need mapping into our canonical vocabulary
_NORMALIZE = {
    "application/x-matroska": "video/x-matroska",
    "application/ogg": "audio/ogg",
    "application/x-extension-mp4": "video/mp4",
    "image/jpeg": "image/jpeg",
    "text/x-markdown": "text/markdown",
    "image/x-ms-bmp": "image/bmp",
    "application/vnd.rar": "application/vnd.rar",
    "audio/x-opus+ogg": "audio/opus",
}


def detect(path: Path, ext_to_mime: dict[str, str]) -> tuple[str, str]:
    """Return (mime, how) where how is 'extension' | 'content' | 'guess'."""
    ext = path.suffix.lower().lstrip(".")
    if ext and ext in ext_to_mime:
        return ext_to_mime[ext], "extension"
    try:
        out = subprocess.run(
            ["file", "-b", "--mime-type", str(path)],
            capture_output=True, text=True, timeout=5,
        ).stdout.strip()
        if out:
            return _NORMALIZE.get(out, out), "content"
    except (OSError, subprocess.SubprocessError):
        pass
    guess, _ = mimetypes.guess_type(path.name)
    return (guess or "application/octet-stream"), "guess"
