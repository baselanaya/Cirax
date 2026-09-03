#!/usr/bin/env python3
"""Generate docs/FORMATS.md — the complete map of every file type Cirax knows.

Run from the repo root:  uv run python scripts/generate_format_map.py
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from cirax.registry import load  # noqa: E402
from cirax.router import reachable  # noqa: E402
from cirax.probe import probe_all  # noqa: E402

DOMAIN_TITLES = {
    "image": "Images",
    "video": "Video",
    "audio": "Audio",
    "document": "Documents",
    "spreadsheet": "Spreadsheets",
    "presentation": "Presentations",
    "ebook": "Ebooks",
    "archive": "Archives",
    "data": "Data & serialization",
    "font": "Fonts",
    "model3d": "3D models",
    "subtitle": "Subtitles",
    "gis": "Geospatial",
    "disk": "Disk images",
    "compression": "Single-file compression",
}


def main() -> None:
    reg = load()
    probe_all(reg)
    installed = {e.name for e in reg.installed_engines()}

    by_domain: dict[str, list] = {}
    for f in reg.formats.values():
        if f.mime == "application/x-tree":
            continue
        by_domain.setdefault(f.domain, []).append(f)

    lines: list[str] = []
    lines.append("# Cirax format map")
    lines.append("")
    lines.append(f"**{len(reg.formats) - 1} formats across {len(by_domain)} domains, "
                 f"served by {len(reg.engines)} registered engines "
                 f"({len(installed)} installed on this machine).**")
    lines.append("")
    lines.append("Every row lists the engines that *read* and *write* the format on "
                 "this machine. Missing engines simply gray the routes out — "
                 "`cirax doctor --show-missing` tells you what to install.")
    lines.append("")

    for domain in sorted(by_domain):
        title = DOMAIN_TITLES.get(domain, domain.capitalize())
        pivots = reg.domains.get(domain, [])
        lines.append(f"## {title}")
        lines.append("")
        if pivots:
            pivot_exts = ", ".join(f"`. {reg.ext_for(p)}`" if False else
                                   f"`.{reg.ext_for(p)}`" for p in pivots)
            lines.append(f"Pivot formats (the router's interchanges): {pivot_exts}")
            lines.append("")
        lines.append("| Format | Ext | Reads (engines) | Writes (engines) |")
        lines.append("|---|---|---|---|")
        for f in sorted(by_domain[domain], key=lambda x: (x.domain, x.ext)):
            if f.mime == "application/x-tree":
                continue
            readers, writers = [], []
            for e in reg.engines:
                if not e.installed:
                    continue
                # wildcard-from engines (zstd "compresses anything") are
                # packagers, not readers — keep them out of the columns
                wild = any(len(r.from_formats) == 1 and "*" in r.from_formats
                           for r in e.routes)
                if wild and f.domain != "compression":
                    continue
                if any(r.matches_input(f.mime) and f.mime in r.to_formats
                       and not r.ops for r in e.routes):
                    writers.append(e.name)
                if any(r.matches_input(f.mime) for r in e.routes):
                    readers.append(e.name)
            fmt_name = f" {f.name}" if f.name else ""
            lines.append(f"| {f.mime} — {fmt_name.strip()} | `.{f.ext}` | "
                         f"{', '.join(readers) or '—'} | "
                         f"{', '.join(writers) or '—'} |")
        lines.append("")

    # cross-domain highlights: the pivot chains make cross-domain routes real
    lines.append("## Cross-domain routes (examples)")
    lines.append("")
    lines.append("| From | To | Chain |")
    lines.append("|---|---|---|")
    samples = [
        ("report.docx", "docx"), ("photo.heic", "heic"), ("clip.mp4", "mp4"),
        ("song.flac", "flac"), ("scan.png", "png"), ("book.epub", "epub"),
        ("table.xlsx", "xlsx"), ("model.obj", "obj"), ("disk.qcow2", "qcow2"),
        ("area.geojson", "geojson"), ("talk.mp3", "mp3"), ("sub.ass", "ass"),
        ("font.ttf", "ttf"), ("data.json", "json"),
    ]
    seen = set()
    for fname, ext in samples:
        mime = reg.ext_to_mime.get(ext)
        if not mime:
            continue
        for target_ext, target_mime in [
            ("png", "image/png"), ("pdf", "application/pdf"),
            ("txt", "text/plain"), ("md", "text/markdown"),
            ("srt", "application/x-subrip"), ("webp", "image/webp"),
            ("jpg", "image/jpeg"), ("mp3", "audio/mpeg"),
            ("md", "text/markdown"), ("csv", "text/csv"),
            ("parquet", "application/x-parquet"), ("glb", "model/gltf-binary"),
            ("vdi", "application/x-vdi"), ("gpkg", "application/geopackage+sqlite3"),
        ]:
            if target_mime == mime:
                continue
            plan = __import__("cirax.router", fromlist=["find_plan"]) \
                .find_plan(reg, mime, target_mime)
            if plan and plan.steps:
                key = (ext, target_ext, tuple(plan.engines))
                if key in seen:
                    continue
                seen.add(key)
                lines.append(f"| `.{ext}` | `.{reg.ext_for(target_mime)}` | "
                             f"{' → '.join(plan.engines)} "
                             f"({'lossless' if plan.lossless else 'lossy'}) |")
                break
    lines.append("")
    lines.append("---")
    lines.append("")
    lines.append("_Auto-generated by `scripts/generate_format_map.py`. "
                 "Regenerate after registry changes._")

    out = Path(__file__).resolve().parent.parent / "docs" / "FORMATS.md"
    out.parent.mkdir(exist_ok=True)
    out.write_text("\n".join(lines) + "\n")
    print(f"wrote {out} ({len(lines)} lines)")


if __name__ == "__main__":
    main()
