"""Execute a plan: render command templates, run engines in sequence,
stage intermediates in a private workdir, clean up after.

Sandboxing (bubblewrap) lands in Phase 3; every job already runs in its own
temp workspace with no shell involved (argv lists, never a shell string).
"""

from __future__ import annotations

import dataclasses
import re
import shlex
import shutil
import subprocess
import tempfile
import time
from dataclasses import dataclass
from pathlib import Path

from .registry import Registry, TREE_FMT
from .router import Plan, Step
from .sandbox import bwrap_argv, resolve_mode

FLAG_VARS = {"flags", "input_flags", "output_flags"}
_PLACEHOLDER = re.compile(r"\{(\w+)\}")
_FENCE_LINE = re.compile(r"^\s*```[\w-]*\s*$")


def _strip_fences(text: str) -> str:
    """Clean LLM OCR output: drop bare code-fence lines, collapse blanks."""
    lines = [ln for ln in text.splitlines() if not _FENCE_LINE.match(ln)]
    out = "\n".join(lines).strip("\n")
    out = re.sub(r"\n{3,}", "\n\n", out)
    return out + "\n" if out else ""


class ConversionError(RuntimeError):
    pass


@dataclass
class StepResult:
    engine: str
    command: str
    returncode: int
    outputs: list[str] = dataclasses.field(default_factory=list)


def _in_domain(fmt: str, wildcard: str) -> bool:
    if wildcard == "*":
        return True
    return fmt.split("/")[0] + "/*" == wildcard


def _merge_preset_vars(old: dict, spec: dict) -> dict:
    """Merge preset overrides into route vars.

    A wildcard key in the preset (e.g. "video/*") displaces the route's
    exact keys for that domain; exact keys override exactly.
    """
    merged = dict(old)
    for k, v in spec.items():
        if isinstance(v, dict) and isinstance(merged.get(k), dict):
            base = dict(merged[k])
            for pk, pv in v.items():
                if pk.endswith("/*") or pk == "*":
                    base = {rk: rv for rk, rv in base.items()
                            if not _in_domain(rk, pk)}
                base[pk] = pv
            merged[k] = base
        else:
            merged[k] = v
    return merged


def apply_preset(step: Step, preset: str | None) -> Step:
    """Return a Step whose route vars are merged with the engine preset."""
    if not preset or preset not in step.engine.presets:
        return step
    merged = _merge_preset_vars(step.route.vars, step.engine.presets[preset])
    return dataclasses.replace(
        step, route=dataclasses.replace(step.route, vars=merged))


def _builtin(name: str, *, src: Path, dst: Path, outdir: Path, to_fmt: str,
             ext_for, pages: tuple[int, int | None], pattern: Path,
             printf: Path, workdir: Path) -> str | None:
    if name == "input":
        return str(src)
    if name == "output":
        return str(dst)
    if name == "output_stem":
        return str(dst.with_suffix(""))
    if name == "outdir":
        return str(outdir)
    if name == "output_ext":
        return ext_for(to_fmt)
    if name == "output_pattern":
        return str(pattern)  # plain prefix for engines that number files themselves
    if name == "output_printf":
        return str(printf)  # contains %02d, printf-style
    if name == "first_page":
        return str(pages[0])
    if name == "last_page":
        return str(pages[1] if pages[1] else 9999999)
    if name == "workdir":
        return str(workdir)
    return None


def render_args(step: Step, *, src: Path, dst: Path, outdir: Path,
                ext_for, pages: tuple[int, int | None] = (1, None),
                multipage: bool = False, workdir: Path | None = None) -> list[str]:
    """Turn a command template into an argv list.

    Templates are tokenized first, then placeholders are substituted per
    token — so paths with spaces stay single arguments and flag strings
    (e.g. "-c:v libx264 -crf 20") expand into multiple args.
    """
    route = step.route
    to_fmt = step.to_format
    template = route.command_multipage if (multipage and route.command_multipage) \
        else route.command
    if template is None:
        raise ConversionError(f"engine '{step.engine.name}' has no command template")

    stem = dst.with_suffix("").name
    pattern = outdir / stem  # e.g. outdir/page  -> page-1.png, page-2.png
    printf = outdir / f"{stem}-%02d"  # printf-style for gs -sOutputFile
    workdir = workdir if workdir is not None else outdir.parent

    tokens = shlex.split(template or "")
    argv: list[str] = []
    for token in tokens:
        names = _PLACEHOLDER.findall(token)
        # flag-style placeholders expand into many args, but only when the
        # whole token is the placeholder
        if token.startswith("{") and token.endswith("}") and names[0] in FLAG_VARS:
            value = route.var_for(names[0], to_fmt=to_fmt, from_fmt=None)
            if value:
                argv.extend(shlex.split(value))
            continue
        out = token
        for name in names:
            builtin = _builtin(name, src=src, dst=dst, outdir=outdir,
                               to_fmt=to_fmt, ext_for=ext_for, pages=pages,
                               pattern=pattern, printf=printf, workdir=workdir)
            if builtin is None:
                value = route.var_for(name, to_fmt=to_fmt, from_fmt=None)
                if value is not None:
                    builtin = value
                elif name in FLAG_VARS:
                    builtin = ""  # optional flags absent without a preset
                else:
                    raise ConversionError(
                        f"engine '{step.engine.name}': unresolved template "
                        f"variable {{{name}}} (no value for target {to_fmt})")
            out = out.replace("{" + name + "}", builtin or "")
        argv.append(out)
    return argv


def _run(argv: list[str], *, cwd: Path | None = None) -> subprocess.CompletedProcess:
    try:
        proc = subprocess.run(argv, cwd=cwd, capture_output=True, text=True,
                              timeout=1800)
    except FileNotFoundError:
        raise ConversionError(f"engine binary not found: {argv[0]}")
    except subprocess.TimeoutExpired:
        raise ConversionError(f"engine timed out: {argv[0]}")
    return proc


def _fmt_time(sec: float) -> str:
    m, s = divmod(int(sec), 60)
    h, m = divmod(m, 60)
    return f"{h}:{m:02d}:{s:02d}" if h else f"{m}:{s:02d}"


def _step_error(step: Step, proc: subprocess.CompletedProcess) -> str:
    msg = (proc.stderr or proc.stdout or "").strip()[-2000:]
    engine = step.engine
    if engine.setup_hint and engine.version is None:
        msg += f"\nhint: {engine.setup_hint}"
    return (f"{engine.name} failed (exit {proc.returncode}):\n{msg}")


def _run_with_progress(argv: list[str], src: Path) -> subprocess.CompletedProcess:
    """Run a process streaming ffmpeg-style `-progress pipe:1` output."""
    total = None
    ffprobe = shutil.which("ffprobe")
    if ffprobe:
        try:
            out = subprocess.run(
                [ffprobe, "-v", "error", "-show_entries", "format=duration",
                 "-of", "default=nk=1:nw=1", str(src)],
                capture_output=True, text=True, timeout=15).stdout.strip()
            total = float(out)
        except (OSError, ValueError, subprocess.SubprocessError):
            total = None
    try:
        proc = subprocess.Popen(argv, stdout=subprocess.PIPE,
                                stderr=subprocess.PIPE, text=True)
    except FileNotFoundError:
        raise ConversionError(f"engine binary not found: {argv[0]}")
    last = 0.0
    assert proc.stdout is not None
    for line in proc.stdout:
        if line.startswith("out_time_us="):
            try:
                cur = float(line.split("=", 1)[1]) / 1e6
            except ValueError:
                continue
            now = time.monotonic()
            if total and now - last > 0.4 and total > 0:
                pct = min(cur / total * 100.0, 100.0)
                print(f"\r    {pct:3.0f}%  {_fmt_time(cur)} / {_fmt_time(total)}",
                      end="", flush=True)
                last = now
    proc.wait()
    print("\r" + " " * 40 + "\r", end="", flush=True)
    return subprocess.CompletedProcess(argv, proc.returncode,
                                       "", proc.stderr.read() if proc.stderr else "")


def _parse_pages(pages: str) -> tuple[int, int | None]:
    pages = (pages or "first").strip().lower()
    if pages in ("", "first", "1"):
        return 1, 1
    if pages == "all":
        return 1, None
    if "-" in pages:
        a, b = pages.split("-", 1)
        return int(a), int(b)
    n = int(pages)
    return n, n


def execute(plan: Plan, reg: Registry, src_path: Path, dst_path: Path,
            workdir: Path | None = None, quiet: bool = False,
            preset: str | None = None, pages: str = "first",
            sandbox: str = "auto") -> list[StepResult]:
    """Run every step of the plan. Intermediates live in workdir; the final
    step writes dst_path directly. Returns per-step results for logging.

    sandbox: "auto" (sandbox when bwrap is present and the engine allows),
    "on" (require sandbox), "off" (never sandbox)."""
    src_path = src_path.resolve()
    dst_path = dst_path.resolve()
    if not plan.steps:
        raise ConversionError("empty plan: nothing to execute")
    cleanup = False
    if workdir is None:
        workdir = Path(tempfile.mkdtemp(prefix="cirax-"))
        cleanup = True
    workdir.mkdir(parents=True, exist_ok=True)
    page_range = _parse_pages(pages)

    results: list[StepResult] = []
    current: Path = src_path
    try:
        for i, step in enumerate(plan.steps):
            step = apply_preset(step, preset)
            last = i == len(plan.steps) - 1
            target_fmt = step.to_format
            do_multipage = (last and step.route.multipage
                            and step.route.command_multipage
                            and pages.lower() not in ("", "first")
                            and target_fmt != TREE_FMT)

            if target_fmt == TREE_FMT:
                out: Path = workdir / f"stage{i:02d}_tree"
                out.mkdir(parents=True, exist_ok=True)
            elif last and not do_multipage:
                out = dst_path
            else:
                out = workdir / f"stage{i:02d}.{reg.ext_for(target_fmt)}"

            outdir = workdir / f"out{i:02d}"
            outdir.mkdir(parents=True, exist_ok=True)
            argv = render_args(step, src=current, dst=out, outdir=outdir,
                               ext_for=reg.ext_for, pages=page_range,
                               multipage=do_multipage, workdir=workdir)
            try:
                sb_mode = resolve_mode(sandbox, step.engine.sandbox)
            except RuntimeError as exc:
                raise ConversionError(str(exc))
            if sb_mode == "on" and not quiet and i == 0:
                print("  sandbox: bwrap (no network, read-only fs)")
            if sb_mode == "on":
                argv = bwrap_argv(argv, src=current, dst=out, workdir=workdir)
            cwd = current if (step.route.cwd == "input" and
                              current.is_dir()) else None
            if not quiet:
                print(f"  [{i + 1}/{len(plan.steps)}] {step.engine.name}: "
                      f"{shlex.join(argv)}")

            if step.route.progress == "ffmpeg" and not do_multipage and \
                    shutil.which("ffprobe") and not quiet:
                proc = _run_with_progress(argv, current)
                if proc.returncode != 0:
                    raise ConversionError(_step_error(step, proc))
            else:
                proc = _run(argv, cwd=cwd)
                if proc.returncode != 0:
                    raise ConversionError(_step_error(step, proc))

            if step.route.output_from == "stdout":
                out.parent.mkdir(parents=True, exist_ok=True)
                text = proc.stdout or ""
                if step.route.post == "strip_fences":
                    text = _strip_fences(text)
                out.write_text(text)

            if step.route.output_mode == "outdir" and not do_multipage:
                produced = sorted(
                    p for p in outdir.iterdir() if p.is_file() and
                    p.name.startswith(out.with_suffix("").name))
                if not produced:
                    raise ConversionError(
                        f"{step.engine.name}: no output produced in {outdir}")
                shutil.move(str(produced[0]), out)

            if do_multipage:
                produced = sorted(outdir.iterdir(), key=lambda p: p.name)
                produced = [p for p in produced if p.is_file()]
                if not produced:
                    raise ConversionError(
                        f"{step.engine.name}: no pages produced in {outdir}")
                final: list[str] = []
                for n, p in enumerate(produced, start=1):
                    if len(produced) == 1:
                        dest = dst_path
                    else:
                        dest = dst_path.with_name(
                            f"{dst_path.stem}-{n:02d}{dst_path.suffix}")
                    shutil.move(str(p), dest)
                    final.append(str(dest))
                if not quiet:
                    print(f"  {len(final)} page(s) written")
                results.append(StepResult(step.engine.name,
                                          shlex.join(argv), proc.returncode,
                                          final))
                current = dst_path
                break
            if not out.exists() and target_fmt != TREE_FMT:
                raise ConversionError(f"{step.engine.name}: {out} was not created")

            results.append(StepResult(step.engine.name, shlex.join(argv),
                                      proc.returncode))
            current = out
        return results
    finally:
        if cleanup:
            shutil.rmtree(workdir, ignore_errors=True)
