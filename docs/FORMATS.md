# Cirax format map

**108 formats across 15 domains, served by 58 registered engines (45 installed on this machine).**

Every row lists the engines that *read* and *write* the format on this machine. Missing engines simply gray the routes out — `cirax doctor --show-missing` tells you what to install.

## Archives

Pivot formats (the router's interchanges): `.tar`, `.tree`

| Format | Ext | Reads (engines) | Writes (engines) |
|---|---|---|---|
| application/x-7z-compressed — 7-Zip | `.7z` | sevenzip | — |
| application/x-iso9660-image — ISO 9660 | `.iso` | sevenzip, xorriso | — |
| application/vnd.rar — RAR | `.rar` | sevenzip | — |
| application/x-tar — tar | `.tar` | sevenzip | — |
| application/zip — ZIP | `.zip` | sevenzip | — |

## Audio

Pivot formats (the router's interchanges): `.flac`, `.wav`

| Format | Ext | Reads (engines) | Writes (engines) |
|---|---|---|---|
| audio/aac — raw AAC | `.aac` | whisper, ffmpeg | ffmpeg |
| audio/aiff — AIFF | `.aiff` | whisper, ffmpeg, sox, flac | ffmpeg, sox |
| audio/amr — AMR narrowband | `.amr` | whisper, ffmpeg | ffmpeg |
| audio/flac — FLAC | `.flac` | whisper, ffmpeg, sox, flac, opusenc | ffmpeg, sox |
| audio/mp4 — AAC in MP4 | `.m4a` | whisper, ffmpeg, sox | ffmpeg |
| audio/mpeg — MP3 | `.mp3` | whisper, ffmpeg, sox | ffmpeg, sox |
| audio/ogg — Ogg Vorbis | `.ogg` | whisper, ffmpeg, sox | ffmpeg, sox |
| audio/opus — Opus | `.opus` | whisper, ffmpeg | ffmpeg |
| audio/x-wav — WAV PCM | `.wav` | whisper, ffmpeg, sox, lame, flac, opusenc | ffmpeg, sox |
| audio/x-ms-wma — Windows Media Audio | `.wma` | whisper, ffmpeg | ffmpeg |

## Single-file compression

Pivot formats (the router's interchanges): `.zst`

| Format | Ext | Reads (engines) | Writes (engines) |
|---|---|---|---|
| application/gzip — gzip | `.gz` | sevenzip, zstd | — |
| application/x-xz — xz | `.xz` | sevenzip, zstd | — |
| application/zstd — Zstandard | `.zst` | sevenzip, zstd | zstd |

## Data & serialization

Pivot formats (the router's interchanges): `.json`, `.csv`

| Format | Ext | Reads (engines) | Writes (engines) |
|---|---|---|---|
| application/json — JSON | `.json` | yq, miller, jq | yq, miller, jq |
| application/x-ndjson — newline-delimited JSON | `.jsonl` | miller, duckdb | miller |
| application/xml — XML | `.xml` | yq, iconv | yq |
| application/yaml — YAML | `.yaml` | yq | yq |

## Disk images

Pivot formats (the router's interchanges): `.qcow2`

| Format | Ext | Reads (engines) | Writes (engines) |
|---|---|---|---|
| application/x-raw-disk — Raw disk image | `.img` | qemu-img | qemu-img |
| application/x-qemu-disk — QEMU copy-on-write | `.qcow2` | qemu-img | qemu-img |
| application/x-vdi — VirtualBox disk | `.vdi` | qemu-img | qemu-img |
| application/x-vhd — Hyper-V disk | `.vhd` | qemu-img | qemu-img |
| application/x-vhdx — Hyper-V disk (v2) | `.vhdx` | qemu-img | qemu-img |
| application/x-vmdk — VMware disk | `.vmdk` | qemu-img | qemu-img |

## Documents

Pivot formats (the router's interchanges): `.pdf`, `.txt`, `.html`

| Format | Ext | Reads (engines) | Writes (engines) |
|---|---|---|---|
| application/msword — Word (legacy) | `.doc` | libreoffice | — |
| application/vnd.openxmlformats-officedocument.wordprocessingml.document — Word (OOXML) | `.docx` | libreoffice, pandoc, calibre | libreoffice, pandoc, calibre |
| text/html — HTML | `.html` | iconv, libreoffice, pandoc, calibre | libreoffice, pandoc, calibre |
| text/markdown — Markdown | `.md` | iconv, dos2unix, libreoffice, pandoc, calibre | pandoc |
| application/vnd.oasis.opendocument.text — OpenDocument text | `.odt` | libreoffice, pandoc | libreoffice, pandoc |
| text/org — Org mode | `.org` | pandoc | pandoc |
| application/pdf — PDF | `.pdf` | imagemagick, exiftool, qpdf, ghostscript, pdftotext, pdftoppm, pdftocairo | imagemagick, qpdf, ghostscript |
| text/x-ps — PostScript | `.ps` | ghostscript | — |
| text/x-rst — reStructuredText | `.rst` | pandoc | pandoc |
| application/rtf — Rich Text | `.rtf` | libreoffice, pandoc | pandoc |
| text/x-tex — LaTeX | `.tex` | pandoc | pandoc |
| text/plain — Plain text | `.txt` | iconv, dos2unix, libreoffice, pandoc, calibre | libreoffice, pandoc, calibre |
| text/x-typst — Typst | `.typ` | pandoc | — |

## Ebooks

Pivot formats (the router's interchanges): `.epub`, `.pdf`

| Format | Ext | Reads (engines) | Writes (engines) |
|---|---|---|---|
| application/vnd.amazon.ebook — Kindle AZW3 | `.azw3` | calibre | calibre |
| application/vnd.comicbook+zip — Comic book ZIP | `.cbz` | calibre | — |
| application/epub+zip — EPUB | `.epub` | pandoc, calibre | pandoc, calibre |
| application/x-fictionbook+xml — FictionBook | `.fb2` | calibre | — |
| application/x-mobipocket-ebook — Mobipocket | `.mobi` | calibre | calibre |

## Fonts

Pivot formats (the router's interchanges): `.ttf`

| Format | Ext | Reads (engines) | Writes (engines) |
|---|---|---|---|
| font/otf — OpenType | `.otf` | fonttools | — |
| font/ttf — TrueType | `.ttf` | fonttools | — |
| font/woff — WOFF | `.woff` | fonttools | — |
| font/woff2 — WOFF2 | `.woff2` | fonttools | — |

## Geospatial

Pivot formats (the router's interchanges): `.geojson`

| Format | Ext | Reads (engines) | Writes (engines) |
|---|---|---|---|
| application/geo+json — GeoJSON | `.geojson` | ogr2ogr | ogr2ogr |
| application/geopackage+sqlite3 — GeoPackage | `.gpkg` | ogr2ogr | ogr2ogr |
| application/vnd.google-earth.kml+xml — KML | `.kml` | ogr2ogr | ogr2ogr |

## Images

Pivot formats (the router's interchanges): `.png`, `.jpg`

| Format | Ext | Reads (engines) | Writes (engines) |
|---|---|---|---|
| image/x-arw — Sony RAW | `.arw` | darktable-cli | — |
| image/avif — AVIF | `.avif` | glm-ocr, vips, imagemagick, exiftool | vips, imagemagick |
| image/bmp — BMP | `.bmp` | glm-ocr, vips, imagemagick, potrace, tesseract | vips, imagemagick |
| image/x-cr2 — Canon RAW 2 | `.cr2` | darktable-cli | — |
| image/x-cr3 — Canon RAW 3 | `.cr3` | darktable-cli | — |
| image/x-dng — Digital Negative RAW | `.dng` | darktable-cli | — |
| image/gif — GIF | `.gif` | glm-ocr, gifsicle, vips, imagemagick | gifsicle, vips, imagemagick |
| image/heic — HEIC | `.heic` | glm-ocr, vips, imagemagick, heif-convert, exiftool | — |
| image/vnd.microsoft.icon — Windows icon | `.ico` | vips, imagemagick | vips, imagemagick |
| image/jpeg — JPEG | `.jpg` | glm-ocr, vips, imagemagick, avifenc, cjxl, exiftool, img2pdf, tesseract | vips, imagemagick |
| image/jxl — JPEG XL | `.jxl` | glm-ocr, vips, imagemagick, djxl, exiftool | vips, imagemagick |
| image/x-nef — Nikon RAW | `.nef` | darktable-cli | — |
| image/x-orf — Olympus RAW | `.orf` | darktable-cli | — |
| image/png — PNG | `.png` | glm-ocr, vips, imagemagick, avifenc, cjxl, oxipng, pngquant, exiftool, img2pdf, tesseract | vips, imagemagick, oxipng, pngquant |
| image/vnd.adobe.photoshop — Photoshop | `.psd` | vips, imagemagick | — |
| image/x-raf — Fujifilm RAW | `.raf` | darktable-cli | — |
| image/x-rw2 — Panasonic RAW | `.rw2` | darktable-cli | — |
| image/svg+xml — SVG vector | `.svg` | vips, imagemagick, inkscape, rsvg-convert | — |
| image/x-tga — Truevision TGA | `.tga` | vips, imagemagick | vips, imagemagick |
| image/tiff — TIFF | `.tiff` | glm-ocr, vips, imagemagick, exiftool, img2pdf, tesseract | vips, imagemagick |
| image/webp — WebP | `.webp` | glm-ocr, vips, imagemagick, exiftool | vips, imagemagick |
| image/x-xcf — GIMP XCF | `.xcf` | vips, imagemagick | — |

## 3D models

Pivot formats (the router's interchanges): `.glb`, `.obj`

| Format | Ext | Reads (engines) | Writes (engines) |
|---|---|---|---|
| model/3ds — Autodesk 3DS | `.3ds` | assimp | — |
| model/3mf — 3MF | `.3mf` | — | — |
| model/x-blend — Blender | `.blend` | — | — |
| model/vnd.collada+xml — COLLADA | `.dae` | assimp | assimp |
| model/fbx — Autodesk FBX | `.fbx` | assimp | assimp |
| model/gltf-binary — glTF binary | `.glb` | assimp | assimp |
| model/gltf+json — glTF | `.gltf` | assimp | assimp |
| model/obj — Wavefront OBJ | `.obj` | assimp | assimp |
| model/ply — Stanford PLY | `.ply` | assimp | assimp |
| model/stl — STL | `.stl` | assimp | assimp |
| model/x3d — X3D | `.x3d` | assimp | assimp |

## Presentations

Pivot formats (the router's interchanges): `.pdf`

| Format | Ext | Reads (engines) | Writes (engines) |
|---|---|---|---|
| application/vnd.oasis.opendocument.presentation — OpenDocument slides | `.odp` | libreoffice | — |
| application/vnd.ms-powerpoint — PowerPoint (legacy) | `.ppt` | libreoffice | — |
| application/vnd.openxmlformats-officedocument.presentationml.presentation — PowerPoint (OOXML) | `.pptx` | libreoffice | — |

## Spreadsheets

Pivot formats (the router's interchanges): `.csv`, `.pdf`

| Format | Ext | Reads (engines) | Writes (engines) |
|---|---|---|---|
| text/csv — CSV | `.csv` | yq, miller, duckdb, iconv, dos2unix, libreoffice | yq, miller, libreoffice |
| application/vnd.oasis.opendocument.spreadsheet — OpenDocument sheet | `.ods` | libreoffice | libreoffice |
| application/x-parquet — Apache Parquet | `.parquet` | duckdb | — |
| text/tab-separated-values — TSV | `.tsv` | yq, miller, libreoffice | yq, miller |
| application/vnd.ms-excel — Excel (legacy) | `.xls` | libreoffice | — |
| application/vnd.openxmlformats-officedocument.spreadsheetml.sheet — Excel (OOXML) | `.xlsx` | libreoffice | libreoffice |

## Subtitles

Pivot formats (the router's interchanges): `.srt`

| Format | Ext | Reads (engines) | Writes (engines) |
|---|---|---|---|
| text/x-ssa — SSA/ASS | `.ass` | — | — |
| application/x-subrip — SubRip | `.srt` | — | — |
| text/vtt — WebVTT | `.vtt` | — | — |

## Video

Pivot formats (the router's interchanges): `.mkv`, `.mp4`

| Format | Ext | Reads (engines) | Writes (engines) |
|---|---|---|---|
| video/x-msvideo — AVI | `.avi` | whisper, ffmpeg | ffmpeg |
| video/x-flv — Flash Video | `.flv` | whisper, ffmpeg | ffmpeg |
| video/x-m4v — iTunes video | `.m4v` | whisper, ffmpeg | ffmpeg |
| video/x-matroska — Matroska | `.mkv` | whisper, ffmpeg | ffmpeg |
| video/quicktime — QuickTime | `.mov` | whisper, ffmpeg | ffmpeg |
| video/mp4 — MPEG-4 video | `.mp4` | whisper, ffmpeg | ffmpeg |
| video/mpeg — MPEG program stream | `.mpeg` | whisper, ffmpeg | ffmpeg |
| video/ogg — Ogg video | `.ogv` | whisper, ffmpeg | ffmpeg |
| video/mp2t — MPEG transport stream | `.ts` | whisper, ffmpeg | ffmpeg |
| video/webm — WebM | `.webm` | whisper, ffmpeg | ffmpeg |

## Cross-domain routes (examples)

| From | To | Chain |
|---|---|---|
| `.docx` | `.png` | calibre → pdftoppm (lossy) |
| `.heic` | `.png` | heif-convert (lossy) |
| `.mp4` | `.png` | ffmpeg (lossy) |
| `.flac` | `.png` | ffmpeg → ffmpeg (lossy) |
| `.png` | `.pdf` | img2pdf (lossless) |
| `.epub` | `.png` | calibre → pdftoppm (lossy) |
| `.xlsx` | `.png` | libreoffice → pdftoppm (lossy) |
| `.obj` | `.glb` | assimp (lossy) |
| `.qcow2` | `.vdi` | qemu-img (lossless) |
| `.geojson` | `.gpkg` | ogr2ogr (lossy) |
| `.mp3` | `.png` | ffmpeg → ffmpeg (lossy) |
| `.json` | `.png` | yq → libreoffice → pdftoppm (lossy) |

---

_Auto-generated by `scripts/generate_format_map.py`. Regenerate after registry changes._
