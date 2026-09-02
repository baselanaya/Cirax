# Cirax — Universal Local Conversion Hub

**Build plan · Linux-only · 100% local · everything → everything**

> Core idea: you don't build hundreds of converters. You curate ~40 best-in-class open-source
> engines, wrap them behind one declarative registry, and build a **router** that reaches every
> input→output pair via direct mappings plus short conversion chains through "pivot" formats.
> Cirax is that router, plus the queue, UI, and hardening around it.

---

## 1. Vision & design principles

1. **Fully local, forever.** No network calls, no telemetry, no accounts. Enforced by running
   all engine jobs in a network-less sandbox; CI includes an air-gap test.
2. **Engines, not reimplementations.** FFmpeg will always beat anything we write for media.
   Cirax's value is orchestration: discovery, routing, chaining, presets, progress, safety.
3. **Declarative engine registry.** Each engine is a YAML spec (inputs, outputs, command
   template, progress pattern, flags, sandbox profile). Adding a format = adding a stanza, not code.
4. **Chain to reach everything.** `docx → png` = LibreOffice→PDF→pdftoppm→PNG. The router
   composes engines so coverage is the *closure* of the engine graph, not a hand-written matrix.
5. **Honesty about loss.** Every route is tagged lossless / lossy / destructive; the UI shows it
   before running. Dry-run prints the exact pipeline.
6. **Treat input as hostile.** Files from the internet get parsed by 40 different parsers.
   Sandboxing (bubblewrap, hardened policies) is a first-class feature, not an afterthought.
7. **Degrade gracefully.** Missing engine = feature hidden, not broken. `cirax doctor` reports
   what's installed, at what version, with what hardware acceleration.

---

## 2. Curated engine inventory (the best converters out there)

Legend: **Core** = must-have, forms the spine. ☆ = already installed on this machine
(28 of ~90 probed binaries present). Optional = heavy deps or niche; load lazily.

### 2.1 Video & Audio — spine: **FFmpeg**

| Engine | Role | Coverage highlights |
|---|---|---|
| **FFmpeg 8+** ☆ **Core** | Universal A/V transcode | 1000+ formats; x264/x265/SVT-AV1/VP9/VVC; VAAPI·NVENC·QSV·Vulkan hw accel; **built-in Whisper ASR filter (8.0)** for auto-subtitles; ProRes RAW, APV, RealVideo 6 decode |
| **HandBrakeCLI** | Preset-driven video | Curated device presets, subtitle burn-in, quality targets |
| **mkvtoolnix** (`mkvmerge`) | Lossless container surgery | merge/split/extract tracks without re-encode |
| **SoX** ☆ | Audio DSP | resample, dither, channels, effects, noise |
| **codec CLIs**: `opusenc`, `lame`, `flac` ☆, `oggenc`, `shntool` | Specialist encoders | Best-of-codec quality + cue-sheet splitting |
| **gifsicle** | GIF surgery | optimize, loop, frame extract; pair with ffmpeg `→gif` |
| **Whipper** | CD ripping (optical) | AccurateRip-verified, tag-aware |
| **MakeMKV** *(proprietary — optional, never bundled)* | DVD/Blu-ray → MKV | De-css ripping; ship as optional user-installed plugin |
| **yt-dlp** *(network — opt-in, default off)* | URL → file | Off by default to honor "fully local"; explicit `--allow-network` |
| **pysubs2 / alass** | Subtitles | srt↔vtt↔ass↔ssa↔microdvd; sync correction |

Audio/video pivots: **WAV/FLAC** (lossless audio), **MKV/MP4** (container).

### 2.2 Images — spine: **libvips** (batch speed) + **ImageMagick** (format net)

| Engine | Role | Coverage highlights |
|---|---|---|
| **libvips** (`vips` CLI) ☆ **Core** | Fast batch raster convert | jpeg/png/tiff/webp/avif/jxl/heif/gif/pdf-out; tiny memory footprint, ideal for queues |
| **ImageMagick 7** (`magick`) ☆ **Core** | Widest format net | 300+ formats incl. PSD, DCM (DICOM), XCF (partial), MIFF, PCL… |
| **GraphicsMagick** | High-throughput batch | Faster IM fork for bulk jobs |
| **cwebp / dwebp** | WebP | Reference encoder |
| **avifenc / avifdec** (libavif) | AVIF | Royalty-free modern codec |
| **cjxl / djxl** (libjxl) | JPEG XL | Best modern lossless + JPEG recompress |
| **heif-convert** (libheif) ☆ | HEIC/HEIF read | iPhone photos → anything |
| **oxipng** ☆ · **pngquant** ☆ · **mozjpeg** (`cjpeg`) | Optimizers | Lossless / palette / mozjpeg recompress |
| **darktable-cli / rawtherapee-cli** | RAW development | Best-quality RAW→JPEG/TIFF; dcraw/LibRaw as fast fallback |
| **GIMP** (`gimp -i -b` script-fu) | XCF and layer magic | xcf→png/psd, layered exports |
| **Inkscape** (`inkscape --export-type=`) | Vector hub | svg↔pdf/png/ps/eps/emf/wmf/dxf |
| **resvg / rsvg-convert** | SVG rasterize | Fastest correct SVG→PNG |
| **potrace** · **vtracer** | Vectorization | bitmap→SVG trace (vtracer: full-color) |
| **exiftool** ☆ | Metadata | Read/write/strip metadata across 100s of formats |
| **libicns** (`png2icns`) · `magick` | Icon formats | ICO/ICNS/favicon |

Image pivots: **PNG** (lossless), **JPEG** (photographic), **PDF** (multipage), **SVG** (vector).

### 2.3 Documents & Office — spine: **LibreOffice headless** + **Pandoc**

| Engine | Role | Coverage highlights |
|---|---|---|
| **LibreOffice** (`soffice --headless --convert-to`, via **unoserver** for concurrency) ☆ **Core** | Office hub | doc/docx/odt/rtf/xls/xlsx/ods/ppt/pptx/odp/csv ↔ pdf/html/txt/epub/png |
| **Pandoc** ☆ **Core** | Universal markup | md/html/latex/typst/rtf/docx/odt/epub/org/rst/mediawiki/pptx + citeproc |
| **Tectonic** (or texlive `xelatex`) | LaTeX | self-contained tex→pdf |
| **Typst** | Modern typesetting | typ→pdf/png |
| **Calibre** (`ebook-convert`) **Core** | Ebook king | epub/mobi/azw3/kfx/fb2/lit/cbz/cbr ↔ epub/pdf/mobi/azw3/txt/docx |
| **WeasyPrint** | HTML→PDF print-grade | CSS paged media; replaces deprecated wkhtmltopdf |
| **Chromium headless** (`--print-to-pdf`, `--screenshot`) | Pixel-perfect web | html→pdf/png exactly as browsers render |
| **Marp CLI / pandoc+beamer** | Slides | md→pptx/pdf/beamer |
| **ssconvert** (Gnumeric) | Spreadsheet light | xlsx↔csv without LibreOffice startup cost |

Document pivots: **PDF** (visual), **HTML** (semantic), **DOCX/ODT** (editable), **UTF-8 TXT** (raw text).

### 2.4 PDF — spine: **qpdf + Ghostscript + Poppler + MuPDF**

| Engine | Role | Coverage highlights |
|---|---|---|
| **qpdf** ☆ | Lossless surgery | merge/split/encrypt/decrypt/linearize/repair, forms |
| **Ghostscript** (`gs`) ☆ | Rasterize/compress | ps↔pdf, downsample/compress, page→image |
| **Poppler-utils** | Extract & rasterize | pdftotext/pdftohtml/pdftoppm/pdftocairo/pdfinfo |
| **mutool** (MuPDF) | Clean/draw/convert | fast renderer, pdf↔svg/xhtml, garbage-collect |
| **img2pdf** | Lossless image→PDF | embeds JPEG/JP2 without recompression |
| **OCRmyPDF + Tesseract** ☆ | OCR | image/raster-PDF → searchable PDF, 100+ languages |
| **pdftk-java** *(optional)* | Legacy compat | forms/stamps when qpdf insufficient |

### 2.5 Archives & compression — spine: **7-Zip**

| Engine | Role | Coverage highlights |
|---|---|---|
| **7-Zip** (`7zz`/`7z`) ☆ **Core** | Archive hub | create: 7z/zip/gz/xz/bz2/tar; extract also: rar, cab, iso, wim, cpio, rpm, deb, dmg(partial), msi |
| **zstd** ☆ · **xz** ☆ · **lz4** · **brotli** | Modern compressors | per-format best-in-class ratios/speed |
| **zpaq** / **lrzip** *(optional)* | Max-ratio cold storage | |
| **unar/lsar** | Extraction excellence | filename encoding hell handled (zip from Windows/macOS) |
| **xorriso / genisoimage** | ISO authoring | iso/UDF creation, bootable images |
| **squashfs-tools** | System images | squashfs↔directory (live ISOs, containers) |

Archive pivot: **tar** (unified intermediate), extracted-directory staging.

### 2.6 Disk images & VM disks — spine: **qemu-img**

| Engine | Role | Coverage highlights |
|---|---|---|
| **qemu-img** ☆-able **Core** | VM disk convert | qcow2 ↔ vdi ↔ vmdk ↔ vpc/vhd ↔ vhdx ↔ raw |
| **VBoxManage clonemedium** *(optional)* | VirtualBox variants | vdi↔vmdk with extra fidelity |
| **7z / xorriso / isoinfo** | ISO inspect/extract | |
| **dd / ddrescue / partclone** *(optional)* | Raw device images | rescue-grade imaging |

### 2.7 Data & serialization — spine: **jq + yq + Miller + DuckDB**

| Engine | Role | Coverage highlights |
|---|---|---|
| **jq** ☆ | JSON | query/transform |
| **yq** (mikefarah) | Polyglot | yaml ↔ json ↔ xml ↔ csv ↔ tsv ↔ properties |
| **xmlstarlet** | XML | xpath edit/convert |
| **Miller** (`mlr`) | Records | csv/tsv/json/jsonl ↔ each other, stats |
| **DuckDB** | Tabular Swiss knife | csv/parquet/json/xlsx(read) interconvert via SQL; huge files, streaming |
| **csvkit** | CSV suite | in2csv/csvsql/csvlook |
| **htmlq / pup** | HTML→data | html → text/json via selectors |
| **iconv / uconv** ☆-able | Text encodings | utf-8 ↔ latin1 ↔ shift-jis ↔ … |
| **dos2unix** | Line endings | |
| **sqlite3** | DB files | .import/.dump/csv mode |

Data pivot: **JSON** (and CSV for tabular).

### 2.8 Geospatial *(optional tier, heavy deps — Phase 3)*

| Engine | Role | Coverage highlights |
|---|---|---|
| **GDAL** (`gdal_translate`, `gdalwarp`) | Raster GIS | geotiff/COG/png/jp2/hgt/netcdf |
| **OGR** (`ogr2ogr`) | Vector GIS | shapefile/geojson/gpkg/kml/gml/csv-wkt/osm-pbf |
| **PDAL** | Point clouds | las/laz/e57/ply |

### 2.9 3D & CAD — spine: **assimp + Blender headless**

| Engine | Role | Coverage highlights |
|---|---|---|
| **assimp** | Format net | obj/fbx/gltf/collada/stl/ply/3ds/x3d/… (50+ formats) |
| **Blender** (`blender -b -P script.py`) **Core** | High-fidelity hub | blend↔gltf/fbx/obj/stl/dae/abc/usd; best FBX handling |
| **FreeCAD CLI** | CAD meshes | step/iges/brep → stl/obj |
| **OpenSCAD** | Programmatic CAD | scad → stl/3mf/off |
| **admesh** | STL repair | fix/check meshes before printing |
| **MeshLab** (`meshlabserver`) | Mesh processing | filter-script driven conversions |

3D pivot: **glTF 2.0** (modern) / **OBJ** (legacy).

### 2.10 Fonts — spine: **fonttools**

| Engine | Role | Coverage highlights |
|---|---|---|
| **fonttools** (`ttx`, `pyftsubset`) | Font hub | ttf/otf/woff/woff2 ↔ ttx; subsetting |
| **woff2_compress / _decompress** | WOFF2 | reference codec |
| **FontForge** (`fontforge -lang=ff -c`) | Exotic formats | bdf/pcf bitmap fonts, svg glyphs, ttf↔otf hints |

### 2.11 Local AI extras *(all offline — differentiators)*

| Engine | Role | Coverage highlights |
|---|---|---|
| **whisper.cpp** (or FFmpeg 8's whisper filter) ☆-able | Speech→text | audio/video → txt/srt/vtt, 99 languages, CPU/Vulkan |
| **Tesseract** ☆ | Image→text | OCR → txt/pdf/hocr |
| **Piper** | Text→speech | txt → wav, fast CPU voices |
| **realesrgan-ncnn-vulkan** *(optional)* | Upscale | image/video super-resolution |

### 2.12 Existing projects to study (do not fork; steal ideas)

- **[ConvertX](https://github.com/C4illin/ConvertX)** — self-hosted web converter, 1000+ formats by wrapping ffmpeg/imagemagick/libreoffice/pandoc/latex/calibre. Closest cousin; validates the engine-wrapping approach. Cirax differs: desktop-first, fully local/offline, sandboxed, chain router.
- **[Stirling-PDF](https://github.com/Stirling-Tools/stirling-pdf)** — 55+ PDF tools, desktop client + self-host; model for the PDF toolbox UX and air-gapped packaging.
- **Gotenberg** — clean conversion-API design (engine → uniform HTTP API).
- **HandBrake GUI** — preset UX done right.
- **Videomass / SoundConverter** — Linux ffmpeg/audio GUI conventions.
- **Paperless-ngx** — OCRmyPDF pipeline patterns (deskew, rotate, language detection).

---

## 3. Coverage: how "everything → everything" is reached

Direct edges cover common pairs; **chains through pivots** cover the rest. Route ranking:
prefer lossless → fewest hops → engine quality → hw-accelerated.

```
Domain pivots:
  documents : PDF (visual) · HTML/DOCX (semantic) · UTF-8 TXT (raw)
  images    : PNG (lossless) · JPEG (photo) · SVG/PDF (vector)
  audio     : WAV / FLAC
  video     : MKV / MP4
  data      : JSON · CSV
  3D        : glTF / OBJ
  archives  : tar + extracted dir
```

Example chains the router composes automatically:

| Request | Pipeline |
|---|---|
| `docx → png` | soffice→pdf → pdftoppm→png |
| `mp4 → srt` | ffmpeg (whisper filter / whisper.cpp) |
| `webm → mp3` | ffmpeg → lame |
| `heic → jpg` | libheif/vips |
| `epub → pdf` | ebook-convert |
| `xlsx → parquet` | duckdb |
| `png → svg` | vtracer/potrace |
| `pdf → wav` | pdftotext → piper |
| `stl → step` | FreeCAD CLI |
| `qcow2 → vmdk` | qemu-img |
| `rar → 7z` | unar → 7zz |
| `raw → webp` | darktable-cli → cwebp |
| `video → gif` | ffmpeg + gifsicle optimize |

Cross-domain conversions (video→audio→ringtone, doc→image, image→text→speech) all fall out
of pivot composition — that is what makes "every converter possible" tractable.

---

## 4. Architecture

```
┌────────────────────────────────────────────────────────────┐
│ Interfaces:  CLI · GUI (Tauri) · local Web (opt) ·         │
│              file-manager actions · watch folders          │
├────────────────────────────────────────────────────────────┤
│ Job Engine:  queue · per-engine concurrency · progress ·   │
│              cancel/resume · temp workspace · cleanup      │
├────────────────────────────────────────────────────────────┤
│ Router:      input detect (magic/ext/ffprobe/identify) →   │
│              capability lookup → path search (BFS over     │
│              engine graph) → ranking → plan (dry-runnable) │
├────────────────────────────────────────────────────────────┤
│ Engine Registry (YAML): capabilities · command templates · │
│              flag maps · progress patterns · sandbox profi.│
├────────────────────────────────────────────────────────────┤
│ Engines:     ffmpeg · vips/magick · soffice · pandoc · gs… │
├────────────────────────────────────────────────────────────┤
│ Sandbox:     bubblewrap per job (no net, ro input,         │
│              wo output, tmpfs), hardened policies          │
└────────────────────────────────────────────────────────────┘
```

**Engine spec sketch** (one stanza = one capability):

```yaml
engine: vips
probes: ["vips --version"]
route:
  from: [image/jpeg, image/png, image/tiff, image/webp, image/heic, image/avif]
  to:   [image/webp, image/avif, image/jxl, image/png, image/jpeg, image/tiff]
  lossless: optional
  cost: fast
command: >
  vips copy {{input}} {{output}}{{flag_ext}}
progress: none
sandbox: bwrap-no-net
```

- **Input detection**: `libmagic` + extension + domain probes (`ffprobe`, `magick identify`,
  `pdfinfo`) when magic is ambiguous.
- **Router**: BFS over the capability graph, ranked; max 3 hops; refuses destructive routes
  unless confirmed. `cirax plan a.docx b.png` prints the pipeline without running.
- **Job engine**: async queue; known single-instance engines (soffice) get a persistent
  `unoserver` worker; progress adapters per engine (`ffmpeg -progress pipe:` → %; gs → page i/n).
- **Temp discipline**: every job runs in its own `TMPDIR`; crumb cleanup guaranteed; optional
  `--keep-workdir` for debugging.

**Stack recommendation**: core daemon + CLI in **Python** (fastest to iterate, subprocess
orchestration is its home turf; `asyncio`, `pydantic` for the registry), GUI in **Tauri**
(Rust shell + web UI) talking to the daemon over a local Unix socket; engine specs stay YAML so
the community can contribute formats without touching code. (Go single-binary is the fallback
if you want zero runtime deps; it trades away iteration speed.)

---

## 5. Security & hardening (a real differentiator)

- **bubblewrap per job**: `--unshare-net --unshare-ipc`, read-only bind of input, write-only
  output, fresh tmpfs. Engine processes never see the network or $HOME.
- **Hardened defaults**: ImageMagick `policy.xml` (disable coders with CVE history: MVG, MSL,
  EPS-emit), Ghostscript `-dSAFER`, tar/7z path-traversal ("zip-slip") guards, LibreOffice
  macro-disabled profile.
- **Resource limits**: per-job CPU/mem caps, output size sanity checks, timeouts.
- **Patent honesty**: AV1/Opus/WebP/JPEG XL = royalty-free defaults. HEVC/VVC/AAC *encoding*
  kept optional and documented; decoding everywhere.

## 6. Interfaces

1. **CLI** — `cirax convert in.mov out.webm --preset web-1080p`, `cirax batch dir/ --to pdf`,
   `cirax plan`, `cirax doctor`, `cirax watch ~/incoming --rule '*.heic→jpg'`.
2. **GUI (Tauri)** — drag-and-drop, queue with live progress, preset picker, pipeline
   visualization (shows the chain + loss tags), per-job logs.
3. **Desktop integration** — Nautilus/Dolphin "Convert with Cirax" actions; xdg "Open with".
4. **Local web UI** (optional, loopback/LAN) — ConvertX-style, for headless servers.

## 7. Packaging & dependencies (CachyOS/Arch first)

- Engines are **system deps**, not vendored: declare pacman/AUR packages per engine; `cirax
  doctor` maps installed→available features; GUI hides what's absent; one-shot `cirax setup`
  prints (or runs, with consent) the install commands.
- Ship official `cirax` PKGBUILD + AUR; Flatpak later (sandbox story is strong there, bundling
  is the cost); Nix flake for declarative fans.
- Never bundle: MakeMKV (proprietary), codecs with patent exposure stay optional system deps.

## 8. Roadmap

| Phase | Scope | Exit criteria |
|---|---|---|
| **0 — Scaffold** (1–2 wk) | Repo, registry schema + probe, router skeleton, `cirax doctor`, CLI stub | doctor reports real capability matrix on this machine |
| **1 — MVP** (3–4 wk) | Images (vips/magick + webp/avif/jxl/heic), A/V (ffmpeg + hw accel probe), archives (7z/zstd), docs (pandoc, soffice→pdf), PDF (qpdf/gs/poppler/img2pdf), chaining router, full CLI | the chains table in §3 works end-to-end |
| **2 — Breadth** (3–4 wk) | Ebooks (calibre), OCR (tesseract/ocrmypdf), RAW (darktable), vector (inkscape/potrace/vtracer), fonts (fonttools), data (jq/yq/mlr/duckdb), exiftool, subtitles, GUI alpha | 90% of everyday consumer conversions |
| **3 — Depth** (4+ wk) | 3D (assimp/blender/freecad), VM disks (qemu-img), GIS (gdal, optional), bwrap sandboxing, watch folders, local web UI, whisper/piper AI extras | untrusted-file hardening audit passes |
| **4 — Polish** | PKGBUILD/AUR, Flatpak, pipeline editor UI, preset library, docs site | v1.0 release |

MVP alone (Phase 1) already covers the overwhelming majority of real-world asks: images, video,
audio, archives, office→PDF, PDF→anything, plus the chains between them.

## 9. Risks & mitigations

- **Engine sprawl** → registry is YAML; optional tier installs lazily; every feature degrades.
- **soffice single-instance** → unoserver worker pool.
- **Malformed-input CVEs** → sandbox profile per engine is mandatory for "untrusted" mode.
- **Calibre/LibreOffice heaviness** → optional tier; ssconvert/duckdb as lightweight paths.
- **Format-pair matrix explosion** → pivots + BFS keep it O(domains), not O(pairs).
