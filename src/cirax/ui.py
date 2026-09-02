"""Decorated CLI output: banner, panels, status lines (rich with fallback)."""

from __future__ import annotations

BANNER = r"""
  ██████╗██╗██████╗  █████╗ ██╗  ██╗
 ██╔════╝██║██╔══██╗██╔══██╗╚██╗██╔╝
 ██║     ██║██████╔╝███████║ ╚███╔╝
 ██║     ██║██╔══██╗██╔══██║ ██╔██╗
 ╚██████╗██║██║  ██║██║  ██║██╔╝ ██╗
  ╚═════╝╚═╝╚═╝  ╚═╝╚═╝  ╚═╝╚═╝  ╚═╝
"""

TAGLINE = "every format → every format · 100% local · sandboxed"

try:
    from rich.console import Console
    from rich.panel import Panel
    from rich.text import Text

    _c = Console()

    def banner() -> None:
        text = Text(BANNER, style="bold #5ac8fa")
        text.append(TAGLINE, style="#7d8b99")
        _c.print(Panel(text, border_style="#1668a8", padding=(0, 2)))

    def status(msg: str) -> None:
        _c.print(f"[green]●[/green] {msg}")

    def err(msg: str) -> None:
        _c.print(f"[red]✗[/red] {msg}")

    def info(msg: str) -> None:
        _c.print(f"[#7d8b99]·[/#7d8b99] {msg}")

    def panel(title: str, lines: list[tuple[str, str]]) -> None:
        body = Text()
        for i, (style, line) in enumerate(lines):
            body.append(line, style=style)
            if i < len(lines) - 1:
                body.append("\n")
        _c.print(Panel(body, title=title, border_style="#1668a8"))

except ImportError:  # pragma: no cover - rich is a hard dep, belt and braces
    def banner() -> None:
        print(BANNER + TAGLINE)

    def status(msg: str) -> None:
        print(f"● {msg}")

    def err(msg: str) -> None:
        print(f"✗ {msg}")

    def info(msg: str) -> None:
        print(f"· {msg}")

    def panel(title: str, lines: list[tuple[str, str]]) -> None:
        print(f"── {title} " + "─" * max(0, 40 - len(title)))
        for _, line in lines:
            print(line)
