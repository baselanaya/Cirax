"""Probe the system: which engines are installed, at what version, with what
hardware acceleration. This is what `cirax doctor` is built on."""

from __future__ import annotations

import re
import shutil
import subprocess
import sys

from .registry import Engine, Registry

FFMPEG_HW_ENCODERS = [
    "h264_nvenc", "hevc_nvenc", "av1_nvenc",
    "h264_qsv", "hevc_qsv", "av1_qsv",
    "h264_vaapi", "hevc_vaapi", "av1_vaapi",
    "h264_vulkan", "hevc_vulkan", "av1_vulkan",
]


def engine_binary(engine: Engine) -> str:
    """The binary name to search for on this platform.

    Windows: engines sometimes ship under a different name (Ghostscript's
    CLI is gswin64c, not gs) — the spec overrides via binaries_windows.
    """
    if sys.platform == "win32" and engine.binaries_windows:
        return engine.binaries_windows
    return engine.binary


def probe_engine(engine: Engine, timeout: int = 15) -> None:
    """Fill in installed/path/version for one engine (in place)."""
    binary = engine_binary(engine)
    path = shutil.which(binary)
    if not path:
        return
    engine.installed = True
    engine.path = path
    if not engine.probe_args:
        return
    try:
        out = subprocess.run(
            [engine.binary, *engine.probe_args],
            capture_output=True, text=True, timeout=timeout,
        )
        text = (out.stdout or "") + (out.stderr or "")
        if engine.version_regex:
            m = re.search(engine.version_regex, text)
            if m:
                # regexes without a capture group report the whole match
                # (used to detect presence, e.g. a pulled ollama model)
                engine.version = m.group(1) if m.groups() else m.group(0)
    except (OSError, subprocess.SubprocessError):
        pass


def probe_all(reg: Registry) -> None:
    for engine in reg.engines:
        probe_engine(engine)


def ffmpeg_hw_accel(reg: Registry) -> list[str]:
    """Report hardware encoder support advertised by the installed ffmpeg."""
    ff = reg.engine("ffmpeg")
    if not ff or not ff.installed:
        return []
    try:
        out = subprocess.run(
            [ff.binary, "-hide_banner", "-encoders"],
            capture_output=True, text=True, timeout=15,
        )
    except (OSError, subprocess.SubprocessError):
        return []
    text = (out.stdout or "") + (out.stderr or "")
    return [name for name in FFMPEG_HW_ENCODERS if name in text]
