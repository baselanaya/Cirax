"""Local web UI for Cirax (`cirax serve`).

Python stdlib only — no web framework. Binds to 127.0.0.1 by default;
uploads run through the exact same sandboxed engine pipeline as the CLI.
The page itself lives in cirax/data/web/index.html (bundled like the rest
of the registry data); this module also doubles as the API surface for
external shells (see docs/TAURI-WINDOWS.md).
"""

from __future__ import annotations

import json
import re
import shutil
import sys
import tempfile
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

from cirax.detect import detect
from cirax.executor import ConversionError, execute
from cirax.probe import probe_all
from cirax.router import find_plan

_MAX_BODY = 1024 * 1024 * 1024  # 1 GiB hard cap

_FALLBACK_PAGE = """<!doctype html><html><head><meta charset="utf-8">
<title>Cirax</title></head><body style="font-family:sans-serif;background:#0d1118;color:#dbe4ec">
<h1>● Cirax</h1><p>serve is running, but the web UI assets failed to load in this
bundle. The CLI and the JSON API still work: POST /api/convert?to=&lt;ext&gt;.</p>
</body></html>"""


def _load_page() -> str:
    """Find the web UI page across dev, frozen onedir, and add-data layouts."""
    me = Path(__file__).resolve().parent / "data" / "web" / "index.html"
    cands = [me]
    if hasattr(sys, "_MEIPASS"):
        base = Path(sys._MEIPASS)  # type: ignore[attr-defined]
        cands += [base / "cirax" / "data" / "web" / "index.html",
                  base / "data" / "web" / "index.html"]
    for cand in cands:
        if cand.exists():
            return cand.read_text()
    return _FALLBACK_PAGE


_PAGE = _load_page()


def parse_multipart(body: bytes, boundary: str) -> dict[str, tuple[str | None, bytes]]:
    """Minimal multipart/form-data parser for our own controlled clients."""
    fields: dict[str, tuple[str | None, bytes]] = {}
    delim = b"--" + boundary.encode("latin1")
    for part in body.split(delim)[1:]:
        if part.startswith(b"--"):
            break
        head, _, payload = part.lstrip(b"\r\n").partition(b"\r\n\r\n")
        payload = payload.rsplit(b"\r\n", 1)[0]
        headers = head.decode("latin1", "replace")
        name_m = re.search(r'name="([^"]*)"', headers)
        file_m = re.search(r'filename="([^"]*)"', headers)
        if name_m:
            fields[name_m.group(1)] = (
                file_m.group(1) if file_m else None, payload)
    return fields




def make_handler(reg, args):
    class Handler(BaseHTTPRequestHandler):
        def log_message(self, fmt, *a):  # quieter default logging
            if not args.quiet:
                super().log_message(fmt, *a)

        def _json(self, obj, status=200):
            body = json.dumps(obj).encode()
            self.send_response(status)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def do_GET(self):
            if self.path in ("/", "/index.html"):
                body = _PAGE.encode()
                self.send_response(200)
                self.send_header("Content-Type", "text/html; charset=utf-8")
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)
            elif self.path == "/api/formats":
                self._json([
                    {"ext": f.ext, "name": f.name or f.mime, "domain": f.domain}
                    for f in reg.formats.values() if f.mime != "application/x-tree"
                ])
            elif self.path == "/api/engines":
                self._json([
                    {"name": e.name, "installed": e.installed,
                     "version": e.version, "categories": e.categories}
                    for e in reg.engines
                ])
            elif self.path == "/api/domains":
                self._json([
                    {"domain": dom,
                     "formats": sum(1 for f in reg.formats.values()
                                    if f.domain == dom
                                    and f.mime != "application/x-tree")}
                    for dom in sorted({f.domain for f in reg.formats.values()
                                       if f.mime != "application/x-tree"})])
            elif self.path.startswith("/api/plan"):
                import urllib.parse
                qs = urllib.parse.parse_qs(urllib.parse.urlparse(self.path).query)
                src = qs.get("from", [""])[0]
                dst = qs.get("to", [""])[0]
                if not src or not dst:
                    self._json({"error": "pass ?from=<mime>&to=<mime>"}, 400)
                    return
                plan = find_plan(reg, src, dst)
                if plan is None:
                    self._json({"error": f"no route from {src} to {dst}"}, 404)
                    return
                self._json({
                    "from": plan.src, "to": plan.dst,
                    "lossless": plan.lossless,
                    "engines": plan.engines,
                    "steps": [{"engine": s.engine.name,
                               "binary": s.engine.binary,
                               "target": s.to_format,
                               "lossless": s.lossless}
                              for s in plan.steps]})
            else:
                self._json({"error": "not found"}, 404)

        def do_POST(self):
            if self.path.split("?")[0] != "/api/convert":
                self._json({"error": "not found"}, 404)
                return
            import urllib.parse
            qs = urllib.parse.parse_qs(urllib.parse.urlparse(self.path).query)
            target_ext = (qs.get("to", [""])[0] or "").lstrip(".").lower()
            dst_mime = reg.ext_to_mime.get(target_ext)
            if not dst_mime:
                self._json({"error": f"unknown target extension '{target_ext}'"}, 400)
                return
            length = int(self.headers.get("Content-Length") or 0)
            if length <= 0 or length > _MAX_BODY:
                self._json({"error": f"upload size must be 0 < n <= "
                                     f"{_MAX_BODY // 1048576} MB"}, 413)
                return
            ctype = self.headers.get("Content-Type", "")
            m = re.search(r'boundary="?([^";]+)"?', ctype)
            if "multipart/form-data" not in ctype or not m:
                self._json({"error": "expected multipart/form-data"}, 400)
                return
            body = self.rfile.read(length)
            fields = parse_multipart(body, m.group(1))
            payload = fields.get("file")
            if not payload or not payload[1]:
                self._json({"error": "missing 'file' field"}, 400)
                return
            upload_name = Path(payload[0] or "upload").name
            workdir = Path(tempfile.mkdtemp(prefix="cirax-web-"))
            try:
                src = workdir / upload_name
                src.write_bytes(payload[1])
                src_mime, _ = detect(src, reg.ext_to_mime)
                plan = find_plan(reg, src_mime, dst_mime)
                if plan is None:
                    self._json({"error": f"no route from {src_mime} to "
                                         f"{dst_mime}"}, 422)
                    return
                out_name = src.stem + "." + reg.ext_for(dst_mime)
                dst = workdir / "result" / out_name
                dst.parent.mkdir(parents=True, exist_ok=True)
                execute(plan, reg, src, dst, quiet=True,
                        sandbox=getattr(args, "sandbox", "auto"))
                data = dst.read_bytes()
                self.send_response(200)
                self.send_header("Content-Type",
                                 "application/octet-stream")
                self.send_header("X-Cirax-Route", " -> ".join(plan.engines))
                self.send_header("X-Cirax-Loss",
                                 "lossless" if plan.lossless else "lossy")
                self.send_header("Content-Length", str(len(data)))
                self.send_header("Content-Disposition",
                                 f'attachment; filename="{out_name}"')
                self.end_headers()
                self.wfile.write(data)
            except ConversionError as exc:
                self._json({"error": str(exc)}, 422)
            finally:
                shutil.rmtree(workdir, ignore_errors=True)

    return Handler


def serve(reg, args) -> int:
    probe_all(reg)
    server = ThreadingHTTPServer((args.host, args.port),
                                 make_handler(reg, args))
    host = args.host
    where = f"http://{host}:{args.port}"
    if host in ("0.0.0.0", "::"):
        print(f"Cirax web UI on {where}  (LAN-exposed! uploads convert on "
              f"this machine — use --host 127.0.0.1 to restrict)")
    else:
        print(f"Cirax web UI on {where}")
    print("Ctrl-C to stop")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nbye")
    return 0
