"""Per-job sandboxing via bubblewrap.

Untrusted input gets parsed by dozens of engines; each parser is attack
surface. When bwrap is available and the engine permits it, every job runs
with:

  - no network, no IPC (unshared namespaces)
  - the whole filesystem read-only (inputs anywhere stay readable)
  - write access limited to the job workdir and the output directory
  - HOME caches replaced by a throwaway tmpfs

Engines that need the local AI daemon (Ollama listens on localhost TCP)
opt out via `sandbox: none` in their spec — the daemon itself is trusted,
local-only infrastructure.
"""

from __future__ import annotations

import shutil
import sys
from pathlib import Path

# sandbox values for engine specs: "default" (sandboxed) | "none" (opt out)


def bwrap_available() -> bool:
    return shutil.which("bwrap") is not None


def platform_supported() -> bool:
    """Sandboxing needs bubblewrap — a Linux technology."""
    return sys.platform.startswith("linux")


def resolve_mode(mode: str, engine_sandbox: str | None) -> str:
    """Resolve CLI --sandbox (auto|on|off) against the engine's preference."""
    if mode == "off":
        return "off"
    if not platform_supported():
        if mode == "on":
            raise RuntimeError(
                "sandboxing requires bubblewrap, which is Linux-only; "
                "use --sandbox off (Windows runs engines unsandboxed)")
        return "off"
    if engine_sandbox == "none":
        if mode == "on":
            raise RuntimeError(
                "engine opted out of sandboxing (needs the local AI daemon); "
                "use --sandbox off to proceed unsandboxed")
        return "off"
    if mode == "on" and not bwrap_available():
        raise RuntimeError("bubblewrap (bwrap) not found; cannot force sandbox")
    if mode == "auto" and not bwrap_available():
        return "off"
    return "on"


def bwrap_argv(argv: list[str], *, src: Path, dst: Path,
               workdir: Path) -> list[str]:
    """Wrap argv in a bubblewrap invocation.

    /tmp is a private tmpfs because several engines (ghostscript, ...) need
    writable temp space; if the input file lives under /tmp it is re-bound
    read-only on top so it stays visible.
    """
    dst_dir = dst.parent if str(dst.parent) != str(dst) else dst
    home = Path.home()
    bwrap: list[str] = [
        "bwrap",
        "--ro-bind", "/", "/",
        "--dev", "/dev",
        "--proc", "/proc",
        "--tmpfs", "/tmp",
        "--bind", str(workdir), str(workdir),
        "--bind", str(dst_dir), str(dst_dir),
    ]
    try:
        outside = not (src.is_relative_to(workdir)
                       or src.is_relative_to(dst_dir))
    except (OSError, ValueError):
        outside = True
    if outside:
        bwrap += ["--ro-bind", str(src), str(src)]
    if home.exists():
        # engines that insist on writing caches get a throwaway one
        bwrap += ["--tmpfs", str(home / ".cache")]
    bwrap += [
        "--unshare-net",
        "--unshare-ipc",
        "--die-with-parent",
        "--new-session",
    ]
    return bwrap + argv
