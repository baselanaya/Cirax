"""Local web UI for Cirax (`cirax serve`).

Python stdlib only — no web framework. Binds to 127.0.0.1 by default;
uploads run through the exact same sandboxed engine pipeline as the CLI.
"""

from __future__ import annotations

import json
import re
import shutil
import tempfile
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

from .detect import detect
from .executor import ConversionError, execute
from .probe import probe_all
from .router import find_plan

_MAX_BODY = 1024 * 1024 * 1024  # 1 GiB hard cap


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


_PAGE = """<!doctype html>
<html lang="en"><head>
<meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">
<title>Cirax — local conversion hub</title>
<style>
:root { color-scheme: dark; }
* { box-sizing: border-box; }
body { font-family: system-ui, sans-serif; margin: 0 auto; padding: 2rem;
       max-width: 46rem; background: #101418; color: #dbe4ec; }
h1 { font-size: 1.4rem; margin: 0 0 .2rem; }
h1 span { color: #5ac8fa; }
p.sub { color: #7d8b99; margin-top: 0; }
#drop { border: 2px dashed #33424f; border-radius: 12px; padding: 2.2rem 1rem;
        text-align: center; cursor: pointer; transition: border-color .15s; }
#drop.over { border-color: #5ac8fa; }
.row { display: flex; gap: .6rem; margin: 1rem 0; }
select, button { font: inherit; padding: .55rem .8rem; border-radius: 8px;
                 border: 1px solid #33424f; background: #1a2129; color: inherit; }
button { background: #1668a8; border-color: #1668a8; cursor: pointer; }
button:disabled { opacity: .5; cursor: wait; }
#status { min-height: 1.4rem; color: #9fb0bf; }
#status.err { color: #ff8484; }
a.dl { display: none; margin-top: .4rem; }
table { border-collapse: collapse; width: 100%; font-size: .86rem; margin-top: .6rem; }
td, th { padding: .3rem .5rem; border-bottom: 1px solid #202b34; text-align: left; }
th { color: #7d8b99; font-weight: 500; }
.ok { color: #7fd18b; } .miss { color: #5c6b78; }
footer { margin-top: 2rem; color: #5c6b78; font-size: .8rem; }
</style></head><body>
<h1><span>●</span> Cirax</h1>
<p class="sub">every format → every format · 100% local · nothing leaves this machine</p>

<div id="drop">drop a file here, or click to choose</div>
<input id="file" type="file" hidden>
<div class="row">
  <select id="target"></select>
  <button id="go" disabled>Convert</button>
</div>
<div id="status"></div>
<a id="dl" class="dl button" download>Download result</a>

<h2 style="font-size:1rem;margin-top:2.4rem">Engine matrix</h2>
<table id="engines"><tr><th>Engine</th><th>Status</th><th>Version</th><th>Domains</th></tr></table>
<footer>CLI: <code>cirax doctor · plan · convert · watch</code> — sandboxed with bwrap, offline.</footer>

<script>
const $ = id => document.getElementById(id);
let f = null;
const drop = $("drop");
drop.onclick = () => $("file").click();
drop.ondragover = e => { e.preventDefault(); drop.classList.add("over"); };
drop.ondragleave = () => drop.classList.remove("over");
drop.ondrop = e => { e.preventDefault(); drop.classList.remove("over"); pick(e.dataTransfer.files[0]); };
$("file").onchange = e => pick(e.target.files[0]);
function pick(x) {
  if (!x) return;
  f = x; drop.textContent = f.name + "  (" + (f.size/1048576).toFixed(1) + " MB)";
  $("go").disabled = false; $("dl").style.display = "none"; $("status").textContent = "";
}
fetch("/api/formats").then(r => r.json()).then(fmts => {
  const by = {};
  for (const x of fmts) (by[x.domain] = by[x.domain] || []).push(x);
  for (const [dom, list] of Object.entries(by)) {
    const g = document.createElement("optgroup"); g.label = dom;
    for (const x of list.sort((a,b) => a.ext.localeCompare(b.ext))) {
      const o = document.createElement("option"); o.value = x.ext;
      o.textContent = "." + x.ext + " — " + x.name; g.append(o);
    }
    $("target").append(g);
  }
});
$("go").onclick = async () => {
  if (!f) return;
  $("go").disabled = true; $("status").textContent = "converting…"; $("dl").style.display = "none";
  const fd = new FormData(); fd.append("file", f);
  try {
    const r = await fetch("/api/convert?to=" + encodeURIComponent($("target").value),
                          { method: "POST", body: fd });
    if (!r.ok) { const e = await r.json().catch(() => ({error: r.statusText}));
                 throw new Error(e.error || r.statusText); }
    const blob = await r.blob();
    const cd = r.headers.get("Content-Disposition") || "";
    const name = (cd.match(/filename="(.*)"/) || [])[1] || "result";
    const url = URL.createObjectURL(blob);
    const a = $("dl"); a.href = url; a.download = name; a.style.display = "inline-block";
    a.textContent = "Download " + name + " (" + (blob.size/1048576).toFixed(1) + " MB)";
    $("status").textContent = "done.";
  } catch (err) { $("status").textContent = "error: " + err.message;
                  $("status").className = "err"; }
  $("go").disabled = false;
};
fetch("/api/engines").then(r => r.json()).then(rows => {
  const t = $("engines");
  for (const e of rows) {
    const tr = document.createElement("tr");
    tr.innerHTML = `<td>${e.name}</td>` +
      `<td class="${e.installed ? "ok" : "miss"}">${e.installed ? "installed" : "—"}</td>` +
      `<td>${e.version || ""}</td><td>${e.categories.join(", ")}</td>`;
    t.append(tr);
  }
});
</script></body></html>"""


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
