"""Cirax CLI — doctor, formats, detect, plan, presets, convert, watch."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from . import __version__, ui
from .detect import detect
from .executor import ConversionError, execute
from .probe import ffmpeg_hw_accel, probe_all
from .registry import load
from .router import find_plan, reachable

try:
    from rich.console import Console
    from rich.table import Table

    _console = Console()
    _HAS_RICH = True
except ImportError:  # rich is optional at runtime
    _HAS_RICH = False


def _print_table(title: str, columns: list[str], rows: list[list[str]]) -> None:
    if _HAS_RICH:
        table = Table(title=title, show_lines=False)
        for col in columns:
            table.add_column(col)
        for row in rows:
            table.add_row(*row)
        _console.print(table)
    else:
        print(f"\n{title}")
        print(" | ".join(columns))
        for row in rows:
            print(" | ".join(row))


def cmd_doctor(args) -> int:
    reg = load()
    probe_all(reg)
    installed = reg.installed_engines()

    rows = []
    for e in reg.engines:
        status = f"[green]ok[/green]" if _HAS_RICH else "ok"
        if not e.installed:
            status = "[dim]missing[/dim]" if _HAS_RICH else "missing"
        elif not e.executable:
            status = "[yellow]registered (adapter pending)[/yellow]" if _HAS_RICH \
                else "registered (adapter pending)"
        rows.append([
            e.name, e.binary, status, e.version or "-",
            ",".join(e.categories) or "-",
            str(sum(len(r.to_formats) for r in e.routes)),
        ])
    _print_table("Cirax engine registry", ["Engine", "Binary", "Status",
                                           "Version", "Categories", "Targets"],
                 rows)

    hw = ffmpeg_hw_accel(reg)
    print(f"\nEngines: {len(installed)}/{len(reg.engines)} installed · "
          f"formats: {len(reg.formats)}")
    if hw:
        print(f"Hardware video encoders: {', '.join(hw)}")
    from .sandbox import bwrap_available, platform_supported
    if platform_supported():
        print(f"Sandbox: {'bwrap ready' if bwrap_available() else 'bwrap missing'}")
    else:
        print("Sandbox: unavailable on this platform (Linux-only)")

    def platform_hint(e):
        if sys.platform == "win32":
            return e.install_windows
        if sys.platform == "darwin":
            return e.install_macos or e.install_windows
        return e.package or e.install_linux

    missing = [e for e in reg.engines if not e.installed and platform_hint(e)]
    if missing and args.show_missing:
        label = {False: "install hints", True: "Arch package hints"}.get(False)
        print("\nMissing engines:")
        for e in missing:
            print(f"  {platform_hint(e)}   # {e.name} ({e.binary})")

    unsetup = [e for e in reg.engines
               if e.installed and e.setup_hint and not e.version]
    if unsetup:
        print("\nOne-time setup available:")
        for e in unsetup:
            print(f"  {e.name}: {e.setup_hint}")
    return 0


def cmd_formats(args) -> int:
    reg = load()
    probe_all(reg)
    by_domain: dict[str, list] = {}
    for f in reg.formats.values():
        by_domain.setdefault(f.domain, []).append(f)

    for domain in sorted(by_domain):
        pivots = reg.domains.get(domain, [])
        rows = []
        for f in sorted(by_domain[domain], key=lambda x: x.ext):
            ins = sum(1 for e in reg.engines if e.installed and
                      any(r.matches_input(f.mime) for r in e.routes))
            outs = sum(1 for e in reg.engines if e.installed and
                       any(f.mime in r.to_formats for r in e.routes))
            rows.append([f.ext, f.mime, f.name, str(ins), str(outs),
                         "*" if f.mime in pivots else ""])
        _print_table(f"{domain} ({len(by_domain[domain])} formats)",
                     ["Ext", "MIME", "Name", "Readers", "Writers", "Pivot"],
                     rows)
    return 0


def cmd_detect(args) -> int:
    reg = load()
    path = Path(args.file)
    if not path.exists():
        print(f"error: {path} does not exist", file=sys.stderr)
        return 1
    mime, how = detect(path, reg.ext_to_mime)
    fmt = reg.formats.get(mime)
    name = f" ({fmt.name})" if fmt and fmt.name else ""
    print(f"{path.name}: {mime}{name}   [detected via {how}]")
    return 0


def _show_plan(reg, plan, src_path: Path, dst_path: Path) -> None:
    loss = "lossless" if plan.lossless else "lossy"
    chain = " -> ".join(plan.engines) or "(identity)"
    if _HAS_RICH:
        from rich.text import Text
        body = Text()
        for i, step in enumerate(plan.steps):
            tag_style = "green" if step.lossless else "yellow"
            body.append(f"  {i + 1}. ", style="#7d8b99")
            body.append(f"{step.engine.name}", style="bold")
            body.append(f"  ->  {step.to_format}   ")
            body.append("lossless" if step.lossless else "lossy", style=tag_style)
            body.append("\n")
        from rich.console import Group
        from rich.panel import Panel
        _console.print(Panel(
            Group(Text(f"route: {plan.src} → {plan.dst}   [{loss}]"), body),
            title=f"{src_path.name} → {dst_path.name}",
            subtitle=f"via {chain}", border_style="#1668a8"))
    else:
        print(f"route: {plan.src} -> {plan.dst}   [{loss}]")
        for i, step in enumerate(plan.steps):
            tag = "lossless" if step.lossless else "lossy"
            print(f"  {i + 1}. {step.engine.name} -> {step.to_format} [{tag}]")
        print(f"{src_path.name} -> {dst_path} via {chain}")


def cmd_plan(args) -> int:
    reg = load()
    probe_all(reg)
    src_path = Path(args.input)
    if not src_path.exists():
        print(f"error: {src_path} does not exist", file=sys.stderr)
        return 1
    src_mime, how = detect(src_path, reg.ext_to_mime)

    target = args.to
    if not target:
        reach = reachable(reg, src_mime, allow_ai=args.ai)
        print(f"{src_path.name} detected as {src_mime} (via {how}); "
              f"{len(reach)} reachable targets:")
        for mime, plan in sorted(reach.items(), key=lambda kv: kv[1].cost):
            f = reg.formats.get(mime)
            print(f"  .{reg.ext_for(mime):<8} via {' -> '.join(plan.engines):<40} "
                  f"{'lossless' if plan.lossless else 'lossy'}")
        return 0

    dst_mime = target if "/" in target else reg.ext_to_mime.get(target.lstrip("."))
    if not dst_mime:
        print(f"error: unknown target format '{target}'", file=sys.stderr)
        return 1
    plan = find_plan(reg, src_mime, dst_mime, engine_filter=args.engine,
                     allow_ai=args.ai)
    if plan is None:
        print(f"no route from {src_mime} to {dst_mime}"
              + (f" for engine '{args.engine}'" if args.engine else ""),
              file=sys.stderr)
        return 2
    _show_plan(reg, plan, src_path, src_path.with_suffix("." + reg.ext_for(dst_mime)))
    return 0


def cmd_presets(args) -> int:
    reg = load()
    probe_all(reg)
    rows = []
    for e in reg.engines:
        if not e.presets or not e.installed:
            continue
        for name, spec in e.presets.items():
            hint = "; ".join(
                f"{k}={v if not isinstance(v, dict) else '<per-format>'}"
                for k, v in spec.items())
            rows.append([e.name, name, hint])
    _print_table("Presets (use with: cirax convert IN OUT --preset NAME)",
                 ["Engine", "Preset", "Overrides"], rows)
    return 0


def _convert_one(reg, args, src_path: Path, dst_path: Path) -> int:
    src_mime, _ = detect(src_path, reg.ext_to_mime)
    target_ext = dst_path.suffix.lstrip(".")
    dst_mime = reg.ext_to_mime.get(target_ext.lower())
    if not dst_mime:
        print(f"error: unknown target extension '{target_ext}'", file=sys.stderr)
        return 1
    if dst_path.resolve() == src_path.resolve():
        print("error: output is the same file as input", file=sys.stderr)
        return 1

    plan = find_plan(reg, src_mime, dst_mime, engine_filter=args.engine,
                     allow_ai=args.ai)
    if plan is None:
        reach = reachable(reg, src_mime, allow_ai=args.ai)
        print(f"no route from {src_mime} to {dst_mime}", file=sys.stderr)
        if reach:
            print("Reachable targets: " + ", ".join(
                "." + reg.ext_for(m) for m in sorted(reach)), file=sys.stderr)
        return 2
    if args.engine and plan.engines != [args.engine]:
        print(f"error: engine '{args.engine}' cannot run this route "
              f"(router chose {' -> '.join(plan.engines) or 'nothing'})",
              file=sys.stderr)
        return 2

    if not args.quiet:
        ui.status(f"converting [bold]{src_path.name}[/bold]: {plan.src} → "
                  f"{plan.dst}  ({' → '.join(plan.engines)}, "
                  f"{'lossless' if plan.lossless else 'lossy'})"
                  + (f"  [preset: {args.preset}]" if args.preset else ""))
    if args.dry_run:
        return 0
    try:
        execute(plan, reg, src_path, dst_path, quiet=args.quiet,
                preset=args.preset, pages=getattr(args, "pages", "first"),
                sandbox=getattr(args, "sandbox", "auto"))
    except ConversionError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 3
    if not args.quiet:
        ui.status(f"done: [bold]{dst_path}[/bold]")
    return 0


def cmd_convert(args) -> int:
    reg = load()
    probe_all(reg)
    src_paths = [Path(p).expanduser() for p in args.input]

    # `convert in out` vs `convert in1 in2 -t ext`: with no --to and 2+
    # positionals, the last one is the output path
    output = None
    if args.to is None and len(src_paths) >= 2:
        output = src_paths.pop()
    missing = [p for p in src_paths if not p.exists()]
    if missing:
        print(f"error: {' '.join(str(m) for m in missing)} does not exist",
              file=sys.stderr)
        return 1

    if len(src_paths) == 1:
        if output:
            dst = output
            if not dst.suffix:
                print("error: output path needs an extension", file=sys.stderr)
                return 1
        elif args.to:
            dst = src_paths[0].with_suffix("." + args.to.lstrip("."))
        else:
            print("error: give an output path or --to EXT "
                  "(run `cirax plan FILE` to list targets)", file=sys.stderr)
            return 1
        return _convert_one(reg, args, src_paths[0], dst)

    # batch mode: one -t target for many inputs, outputs land next to inputs
    if output:
        print("error: with multiple inputs, use --to EXT instead of an "
              "output path", file=sys.stderr)
        return 1
    if not args.to:
        print("error: batch conversion needs --to EXT", file=sys.stderr)
        return 1
    target_ext = args.to.lstrip(".")
    status = 0
    for src in src_paths:
        code = _convert_one(reg, args, src, src.with_suffix("." + target_ext))
        status = status or code
    return status


def cmd_watch(args) -> int:
    """Watch a folder and convert new files as they appear."""
    import time as _time

    from .executor import ConversionError, execute

    reg = load()
    probe_all(reg)
    watch_dir = Path(args.dir).expanduser().resolve()
    if not watch_dir.is_dir():
        print(f"error: {watch_dir} is not a directory", file=sys.stderr)
        return 1
    out_dir = Path(args.out).expanduser().resolve() if args.out else watch_dir
    out_dir.mkdir(parents=True, exist_ok=True)
    target_ext = args.to.lstrip(".").lower()
    dst_mime = reg.ext_to_mime.get(target_ext)
    if not dst_mime:
        print(f"error: unknown target extension '{target_ext}'", file=sys.stderr)
        return 1
    state_file = watch_dir / ".cirax-watch.json"
    done: dict[str, float] = {}
    if state_file.exists():
        try:
            done = json.loads(state_file.read_text())
        except (OSError, ValueError):
            done = {}

    print(f"watching {watch_dir} -> .{target_ext} in {out_dir} "
          f"(Ctrl-C to stop)")
    try:
        while True:
            for f in sorted(watch_dir.iterdir()):
                if not f.is_file() or f.name.startswith("."):
                    continue
                if f.suffix.lower().lstrip(".") == target_ext:
                    continue
                mtime = f.stat().st_mtime
                if done.get(f.name) == mtime:
                    continue
                if f.name in done:
                    continue  # failed/skipped files aren't retried
                mime, _ = detect(f, reg.ext_to_mime)
                plan = find_plan(reg, mime, dst_mime)
                if plan is None:
                    done[f.name] = mtime  # not convertible; don't nag
                    print(f"skip {f.name} ({mime}: no route to {dst_mime})")
                    continue
                dst = out_dir / (f.stem + "." + target_ext)
                print(f"converting {f.name} -> {dst.name} "
                      f"({' -> '.join(plan.engines)})")
                try:
                    execute(plan, reg, f, dst, quiet=True,
                            sandbox=getattr(args, "sandbox", "auto"))
                    done[f.name] = mtime
                    print(f"done: {dst.name}")
                except ConversionError as exc:
                    done[f.name] = mtime  # don't retry broken files
                    print(f"error converting {f.name}: {exc}", file=sys.stderr)
                state_file.write_text(json.dumps(done, indent=1))
            _time.sleep(max(args.interval, 0.5))
    except KeyboardInterrupt:
        state_file.write_text(json.dumps(done, indent=1))
        print("\nstopped")
    return 0


def cmd_serve(args) -> int:
    from . import webui
    reg = load()
    if args.host not in ("127.0.0.1", "localhost", "::1") and not args.quiet:
        print("note: binding a non-loopback address exposes conversion "
              "execution to your network")
    return webui.serve(reg, args)


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="cirax",
        description="Universal local conversion hub — every format to every "
                    "format, fully offline.")
    p.add_argument("--version", action="version", version=f"cirax {__version__}")
    sub = p.add_subparsers(dest="command", required=True)

    d = sub.add_parser("doctor", help="report engine availability and capability matrix")
    d.add_argument("--show-missing", action="store_true",
                   help="print install hints for missing engines")
    d.set_defaults(func=cmd_doctor)

    f = sub.add_parser("formats", help="list known formats, readers and writers")
    f.set_defaults(func=cmd_formats)

    det = sub.add_parser("detect", help="detect the type of a file")
    det.add_argument("file")
    det.set_defaults(func=cmd_detect)

    pl = sub.add_parser("plan", help="show how a file would be converted (dry run)")
    pl.add_argument("input")
    pl.add_argument("to", nargs="?", help="target extension or MIME "
                                          "(omit to list reachable targets)")
    pl.add_argument("--engine", help="restrict the route to a specific engine")
    pl.add_argument("--ai", action="store_true",
                    help="include generative AI routes")
    pl.set_defaults(func=cmd_plan)

    c = sub.add_parser("convert", help="convert one or many files")
    c.add_argument("input", nargs="+", help="input file(s); with multiple "
                    "inputs and no --to, the last argument is the output path")
    c.add_argument("-t", "--to", help="target extension")
    c.add_argument("-P", "--preset", help="engine preset (see: cirax presets)")
    c.add_argument("--engine", help="force a specific engine (e.g. iconv vs "
                                    "dos2unix, tesseract vs glm-ocr)")
    c.add_argument("--sandbox", choices=["auto", "on", "off"], default="auto",
                   help="bwrap sandbox: auto (default), on, off")
    c.add_argument("--ai", action="store_true",
                   help="allow generative AI routes (OCR, TTS)")
    c.add_argument("--pages", default="first", metavar="N|M-K|all",
                   help="for pdf->image routes: first (default), all, "
                        "a page number, or a range")
    c.add_argument("-n", "--dry-run", action="store_true",
                   help="resolve and print the route, convert nothing")
    c.add_argument("-q", "--quiet", action="store_true")
    c.set_defaults(func=cmd_convert)

    pr = sub.add_parser("presets", help="list available engine presets")
    pr.set_defaults(func=cmd_presets)

    w = sub.add_parser("watch", help="watch a folder, convert new files automatically")
    w.add_argument("dir", help="folder to watch")
    w.add_argument("-t", "--to", required=True, help="target extension")
    w.add_argument("--out", help="output folder (default: same folder)")
    w.add_argument("--interval", type=float, default=2.0,
                   help="poll interval seconds (default 2)")
    w.add_argument("--sandbox", choices=["auto", "on", "off"], default="auto")
    w.add_argument("--ai", action="store_true",
                   help="include generative AI routes")
    w.set_defaults(func=cmd_watch)

    s = sub.add_parser("serve", help="local web UI (upload → convert → download)")
    s.add_argument("--host", default="127.0.0.1",
                   help="bind address (default 127.0.0.1)")
    s.add_argument("--port", type=int, default=8400, help="port (default 8400)")
    s.add_argument("--sandbox", choices=["auto", "on", "off"], default="auto")
    s.add_argument("-q", "--quiet", action="store_true")
    s.set_defaults(func=cmd_serve)
    return p


def main(argv: list[str] | None = None) -> int:
    args_list = list(argv if argv is not None else sys.argv[1:])
    if not args_list:
        ui.banner()
        _console.print(
            "[bold]quickstart[/bold]\n"
            "  [cyan]cirax doctor[/cyan]            what can this machine convert?\n"
            "  [cyan]cirax plan FILE[/cyan]         list every reachable target\n"
            "  [cyan]cirax convert IN OUT[/cyan]    convert (chains engines automatically)\n"
            "  [cyan]cirax watch DIR -t pdf[/cyan]  convert new files as they appear\n"
            "  [cyan]cirax serve[/cyan]             local web UI\n\n"
            "[#7d8b99]add --version · run with -h on any command[/#7d8b99]")
        return 0
    args = build_parser().parse_args(args_list)
    return args.func(args)
