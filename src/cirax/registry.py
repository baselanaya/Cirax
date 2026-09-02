"""Load and model the declarative engine registry.

The registry is the heart of Cirax: formats (the vocabulary) and engines
(capabilities over that vocabulary). Everything else — probing, routing,
execution — reads from here.
"""

from __future__ import annotations

import yaml
from dataclasses import dataclass, field
from importlib import resources

TREE_FMT = "application/x-tree"  # pseudo-format: an extracted directory


@dataclass
class Route:
    """One conversion capability: from a set of formats to a set of formats."""

    from_formats: list[str]
    to_formats: list[str]
    command: str | None = None
    lossless: bool = False
    priority: int = 50
    note: str | None = None
    output_mode: str | None = None  # "outdir": engine writes into a directory
    cwd: str | None = None  # "input": run subprocess with cwd=input path
    vars: dict[str, object] = field(default_factory=dict)
    multipage: bool = False  # can produce one output per page (pdf -> images)
    command_multipage: str | None = None  # alternative template, uses
    # {output_pattern} (plain prefix, e.g. pdftoppm) or {output_printf}
    # (printf-style, e.g. gs -sOutputFile=prefix-%02d)
    progress: str | None = None  # "ffmpeg": parse -progress pipe:1
    output_from: str | None = None  # "stdout": capture engine stdout as output
    ops: bool = False  # same-format operation (strip metadata, line endings)
    post: str | None = None  # post-process captured stdout: "strip_fences"

    def matches_input(self, fmt: str) -> bool:
        if "*" in self.from_formats:
            return True
        if fmt in self.from_formats:
            return True
        domain = fmt.split("/")[0] + "/*"
        return domain in self.from_formats

    def var_for(self, name: str, *, to_fmt: str | None, from_fmt: str | None) -> str | None:
        """Resolve a template variable: static value or dict keyed by format.

        Dict keys are tried in order: exact target format, exact source
        format, "*", then domain wildcards ("video/*").
        """
        value = self.vars.get(name)
        if value is None:
            return None
        if isinstance(value, dict):
            domain = (to_fmt or "").split("/")[0] + "/*"
            for key in (to_fmt, from_fmt, "*", domain):
                if key and key in value:
                    return str(value[key])
            return None
        return str(value)


@dataclass
class Engine:
    name: str
    binary: str
    description: str = ""
    categories: list[str] = field(default_factory=list)
    probe_args: list[str] = field(default_factory=list)
    version_regex: str = ""
    package: str | None = None
    note: str | None = None
    setup_hint: str | None = None  # shown by doctor when binary present but
    # the engine needs one-time setup (e.g. pulling a model)
    routes: list[Route] = field(default_factory=list)
    presets: dict[str, dict[str, object]] = field(default_factory=dict)
    sandbox: str = "default"  # "default" | "none" (needs local daemon/net)
    # filled in by the prober:
    installed: bool = False
    path: str | None = None
    version: str | None = None

    @property
    def executable(self) -> bool:
        """Has at least one runnable route (not a stub / ops-pending engine)."""
        return any(r.command for r in self.routes)


@dataclass
class Format:
    mime: str
    ext: str
    name: str = ""
    domain: str = ""


@dataclass
class Registry:
    formats: dict[str, Format] = field(default_factory=dict)
    domains: dict[str, list[str]] = field(default_factory=dict)  # domain -> pivots
    ext_to_mime: dict[str, str] = field(default_factory=dict)
    engines: list[Engine] = field(default_factory=list)

    def engine(self, name: str) -> Engine | None:
        for e in self.engines:
            if e.name == name:
                return e
        return None

    def ext_for(self, mime: str) -> str:
        f = self.formats.get(mime)
        return f.ext if f else mime.split("/")[-1]

    def installed_engines(self) -> list[Engine]:
        return [e for e in self.engines if e.installed]


def _build_route(d: dict) -> Route:
    return Route(
        from_formats=list(d.get("from", [])),
        to_formats=list(d.get("to", [])),
        command=d.get("command"),
        lossless=bool(d.get("lossless", False)),
        priority=int(d.get("priority", 50)),
        note=d.get("note"),
        output_mode=d.get("output_mode"),
        cwd=d.get("cwd"),
        vars=dict(d.get("vars", {})),
        multipage=bool(d.get("multipage", False)),
        command_multipage=d.get("command_multipage"),
        progress=d.get("progress"),
        output_from=d.get("output_from"),
        ops=bool(d.get("ops", False)),
        post=d.get("post"),
    )


def _build_engine(d: dict) -> Engine:
    probe = d.get("probe", {}) or {}
    return Engine(
        name=d["engine"],
        binary=d["binary"],
        description=d.get("description", ""),
        categories=list(d.get("categories", [])),
        probe_args=list(probe.get("args", [])),
        version_regex=probe.get("version_regex", ""),
        package=d.get("package"),
        note=d.get("note"),
        setup_hint=d.get("setup_hint"),
        routes=[_build_route(r) for r in d.get("routes", [])],
        presets=dict(d.get("presets", {})),
        sandbox=d.get("sandbox", "default"),
    )


def load() -> Registry:
    reg = Registry()
    data_dir = resources.files("cirax") / "data"

    fmts = yaml.safe_load((data_dir / "formats.yaml").read_text())
    reg.domains = {k: list(v.get("pivot", [])) for k, v in fmts.get("domains", {}).items()}
    for mime, f in fmts.get("formats", {}).items():
        domain = mime.split("/")[0]
        reg.formats[mime] = Format(
            mime=mime, ext=f["ext"], name=f.get("name", ""), domain=domain
        )
    reg.ext_to_mime = {k.lower(): v for k, v in fmts.get("ext_to_mime", {}).items()}
    # reverse index: every known format is addressable by its canonical ext too
    for mime, f in reg.formats.items():
        reg.ext_to_mime.setdefault(f.ext, mime)

    engines_dir = data_dir / "engines"
    for path in sorted(engines_dir.glob("*.yaml")):
        doc = yaml.safe_load(path.read_text()) or {}
        items = doc.get("engines", [doc] if "engine" in doc else [])
        for d in items:
            reg.engines.append(_build_engine(d))
    return reg
