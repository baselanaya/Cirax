# Cirax

**Universal local conversion hub for Linux.** Every format to every format,
fully offline, by routing between best-in-class open-source engines
(FFmpeg, libvips, ImageMagick, LibreOffice, Pandoc, Calibre, 7-Zip, qpdf...)
plus modern local AI models (GLM-OCR vision OCR via Ollama).

Cirax doesn't reimplement codecs — it *composes* engines. A declarative YAML
registry describes what each installed engine can read and write; a router
finds the best chain (direct, or through pivot formats like PDF/PNG/WAV/JSON)
and executes it. See [PLAN.md](PLAN.md) for the full architecture and roadmap.

## Install

**PyPI** (once published — `make publish-pypi`):

```sh
uv tool install cirax     # or: pipx install cirax
```

**curl one-liner** (bootstraps `uv`, installs as a `uv tool`):

```sh
CIRAX_SRC=. sh install.sh                 # from this checkout
CIRAX_REPO=https://github.com/baselanaya/Cirax sh <(curl -fsSL \
  https://raw.githubusercontent.com/baselanaya/Cirax/main/install.sh)
```

**Arch/AUR** — PKGBUILD in [`packaging/`](packaging/) (community AUR upload pending).

**npm wrapper** — ships the Python source, bootstraps a private venv on first
run (npm ≥ 12 gates lifecycle scripts, so the bin shim self-installs):

```sh
cd npm && npm run build:python && npm pack   # when publishing
npm install -g ./cirax-0.3.0.tgz && cirax doctor
```

**Development** (uv-managed):

```sh
uv sync                # create .venv, install deps + cirax (editable)
uv run cirax doctor    # or: . .venv/bin/activate
make test              # 31-check smoke suite
```

## Usage

```sh
cirax detect photo.heic              # what is this file?
cirax plan report.docx               # list every reachable target + route
cirax plan report.docx png           # show the exact chain for one target
cirax presets                        # list engine presets

cirax convert report.docx png        # docx -> pdf (libreoffice) -> png (pdftoppm)
cirax convert song.flac -t opus      # via ffmpeg
cirax convert video.mov out.mkv --preset web720     # quality presets
cirax convert doc.pdf page.png --pages all          # all pages -> page-01.png, ...
cirax convert a.png b.png c.png -t webp             # batch
cirax convert photos.zip out.7z      # extract -> recreate (staged)

# AI OCR — GLM-OCR vision model, fully offline after `ollama pull glm-ocr`
cirax convert scan.png text.txt                    # via GLM-OCR (tesseract fallback)
cirax convert scan.png notes --to md               # markdown layout preservation
cirax convert photo.jpg clean.jpg                  # strip EXIF/GPS (exiftool ops route)
cirax convert win.txt unix.txt                     # CRLF -> LF (dos2unix ops route)
cirax convert l1.txt u8.txt --engine iconv --preset latin1-utf8   # charset ops

# 3D, VM disks, geospatial (engines optional; doctor shows availability)
cirax convert model.obj model.glb                  # assimp
cirax convert disk.qcow2 disk.vdi                  # qemu-img
cirax convert area.geojson area.gpkg               # GDAL

# watch a folder: new files are converted as they appear
cirax watch ~/scans -t pdf --out ~/documents

# local web UI — upload in the browser, convert, download
cirax serve                       # http://127.0.0.1:8400

# sandboxing — default is auto: every job runs in bubblewrap with no
# network, read-only filesystem, and writes confined to the job workspace
# and output directory. `--sandbox on` to require it, `off` to disable.
```

## Status — Phase 4 (packaging & publishing)

Working: engine probing, `doctor` capability matrix, multi-engine chain
routing, presets, multi-page PDF raster, batch, ffmpeg progress, staged
archive repacking, office chains (md→docx→pdf via pandoc+LibreOffice),
ebooks (pandoc + Calibre), metadata stripping, line-ending/charset ops,
**GLM-OCR** (zai-org's ~1.3B vision model via Ollama — MIT, one
`ollama pull`, then fully offline; tesseract/ocrmypdf fallback), and:

- **Sandboxed jobs** — when `bwrap` is present (it is, on Arch), every
  conversion runs in a bubblewrap jail: no network, no IPC, read-only
  filesystem, writes confined to the job workspace and the output folder.
  AI engines that talk to the local Ollama daemon opt out explicitly.
- **`cirax watch`** — point it at a folder and every new file is converted
  to the target format automatically (state in `.cirax-watch.json`).
- **3D / VM disks / geospatial** — assimp (obj↔glb↔stl↔ply...),
  qemu-img (qcow2↔vdi↔vmdk↔vhd), GDAL (geojson↔gpkg↔kml).
- 31-check smoke suite, sandboxed by default.

- **`cirax serve`** — local web UI (Python stdlib only): drag-and-drop
  upload, target-format picker, live engine matrix, download the result.
  Loopback by default; uploads run through the same sandboxed pipeline.
- **Packaging**: [`packaging/PKGBUILD`](packaging/) + `.SRCINFO` for
  Arch/AUR; PyPI-ready sdist+wheel (`make publish-pypi`); npm tarball
  (`make publish-npm`).
- Flatpak intentionally skipped: Cirax treats engines as *system*
  dependencies (40+ of them); bundling them per-sandbox would duplicate
  the distro. Native packaging is the right fit.

Remaining: AUR upload (needs an AUR account), `uv publish` to PyPI and
`npm publish` (need account tokens), Blender/Piper adapters.

## Layout

```
src/cirax/
  cli.py         doctor / formats / detect / plan / presets / convert / watch
  registry.py    YAML registry loader (formats + engines + presets)
  probe.py       engine detection, versions, ffmpeg hw-accel
  sandbox.py     bubblewrap per-job jail (no network, read-only fs)
  detect.py      input type detection (ext table + file(1))
  router.py      Dijkstra over the format graph, ranked routes
  executor.py    template rendering, presets, staged execution, progress
  data/
    formats.yaml           format vocabulary + pivots + ext table
    engines/*.yaml         one file per domain, one stanza per engine
install.sh      curl installer (uv tool bootstrap)
npm/            npm wrapper package (bin shim + self-installing core)
tests/smoke.sh  end-to-end suite
```

## Adding an engine

Drop a YAML stanza in `src/cirax/data/engines/` — inputs, outputs, a command
template, optional per-format flags and presets — and the router picks it up.

```yaml
- engine: mycodec
  binary: mycodec
  package: mycodec
  presets:
    web: {flags: {image/myfmt: "-q 70"}}
  routes:
    - from: [image/png]
      to: [image/myfmt]
      lossless: true
      priority: 90
      command: "mycodec encode {input} {flags} {output}"
```
