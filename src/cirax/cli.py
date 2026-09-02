"""Cirax CLI — doctor, formats, detect, plan, convert."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from . import __version__
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
    print(f"Hardware video encoders: {', '.join(hw) if hw else 'none detected'}")

    missing = [e for e in reg.engines if not e.installed and e.package]
    if missing and args.show_missing:
        print("\nMissing engines (Arch package hints):")
        for e in missing:
            print(f"  sudo pacman -S --needed {e.package}   # {e.name} ({e.binary})")
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
    print(f"route: {plan.src} -> {plan.dst}   [{loss}]")
    for i, step in enumerate(plan.steps):
        tag = "lossless" if step.lossless else "lossy"
        print(f"  {i + 1}. {step.engine.name} ({step.engine.binary}) "
              f"-> {step.to_format} [{tag}]")
    print(f"\n{src_path.name} ({plan.src}) -> {dst_path} ({plan.dst})  via {chain}")


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
        reach = reachable(reg, src_mime)
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
    plan = find_plan(reg, src_mime, dst_mime)
    if plan is None:
        print(f"no route from {src_mime} to {dst_mime}", file=sys.stderr)
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

    plan = find_plan(reg, src_mime, dst_mime)
    if plan is None:
        reach = reachable(reg, src_mime)
        print(f"no route from {src_mime} to {dst_mime}.", file=sys.stderr)
        if reach:
            print("Reachable targets: " + ", ".join(
                "." + reg.ext_for(m) for m in sorted(reach)), file=sys.stderr)
        return 2

    if not args.quiet:
        print(f"converting {src_path.name}: {plan.src} -> {plan.dst} "
              f"({' -> '.join(plan.engines)}, "
              f"{'lossless' if plan.lossless else 'lossy'})"
              + (f" [preset: {args.preset}]" if args.preset else ""))
    if args.dry_run:
        return 0
    try:
        execute(plan, reg, src_path, dst_path, quiet=args.quiet,
                preset=args.preset, pages=getattr(args, "pages", "first"))
    except ConversionError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 3
    if not args.quiet:
        print(f"done: {dst_path}")
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
    pl.set_defaults(func=cmd_plan)

    c = sub.add_parser("convert", help="convert one or many files")
    c.add_argument("input", nargs="+", help="input file(s); with multiple "
                    "inputs and no --to, the last argument is the output path")
    c.add_argument("-t", "--to", help="target extension")
    c.add_argument("-P", "--preset", help="engine preset (see: cirax presets)")
    c.add_argument("--pages", default="first", metavar="N|M-K|all",
                   help="for pdf->image routes: first (default), all, "
                        "a page number, or a range")
    c.add_argument("-n", "--dry-run", action="store_true",
                   help="resolve and print the route, convert nothing")
    c.add_argument("-q", "--quiet", action="store_true")
    c.set_defaults(func=cmd_convert)

    pr = sub.add_parser("presets", help="list available engine presets")
    pr.set_defaults(func=cmd_presets)
    return p


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    return args.func(args)
