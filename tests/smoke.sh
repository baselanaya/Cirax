#!/usr/bin/env bash
# Cirax Phase 0 smoke test: exercises doctor, plan, and a set of real
# conversions spanning single-hop, chained, and staged routes.
set -euo pipefail

cd "$(dirname "$0")/.."
ROOT="$PWD"
CIRAX="${CIRAX:-$ROOT/.venv/bin/cirax}"

T=$(mktemp -d /tmp/cirax-smoke-XXXXXX)
trap 'rm -rf "$T"' EXIT
cd "$T"
pass=0; fail=0

check() { # check <name> <file-to-verify> <expected-mime-substring>
  if [ -f "$2" ] && file -b --mime-type "$2" | grep -qi "$3"; then
    pass=$((pass+1)); echo "  ok  $1"
  else
    fail=$((fail+1)); echo "FAIL  $1 ($(file -b --mime-type "$2" 2>/dev/null || echo missing))"
  fi
}

echo "== samples =="
ffmpeg -y -hide_banner -loglevel error -f lavfi -i testsrc=duration=1:size=320x240:rate=10 -f lavfi -i sine=duration=1 -c:v libx264 -pix_fmt yuv420p -c:a aac sample.mp4
ffmpeg -y -hide_banner -loglevel error -f lavfi -i sine=duration=1 -c:a pcm_s16le sample.wav
magick -size 200x100 gradient:blue-green sample.png
magick -size 100x50 gradient:red-blue photo.jpg
magick -size 200x200 gradient:green-blue big.png
printf 'hello cirax\nsecond line\n' > doc.txt
printf '%%!PS\n/Helvetica findfont 24 scalefont setfont 72 720 moveto (Hello Cirax) show showpage 72 700 moveto (Page Two) show showpage\n' > doc.ps

echo "== doctor / plan =="
"$CIRAX" doctor >/dev/null && { pass=$((pass+1)); echo "  ok  doctor exits 0"; } || { fail=$((fail+1)); echo "FAIL  doctor"; }
"$CIRAX" plan sample.png webp | grep -q "route" && { pass=$((pass+1)); echo "  ok  plan prints a route"; } || { fail=$((fail+1)); echo "FAIL  plan"; }
"$CIRAX" convert doc.txt -t zst -n >/dev/null && { pass=$((pass+1)); echo "  ok  dry-run"; } || { fail=$((fail+1)); echo "FAIL  dry-run"; }
"$CIRAX" presets >/dev/null && { pass=$((pass+1)); echo "  ok  presets listing"; } || { fail=$((fail+1)); echo "FAIL  presets"; }

echo "== single-hop =="
"$CIRAX" convert -q sample.png -t webp;    check "png->webp"  sample.webp image/webp
"$CIRAX" convert -q sample.wav -t mp3;     check "wav->mp3"   sample.mp3  audio/mpeg
"$CIRAX" convert -q sample.mp4 -t gif;     check "mp4->gif"   sample.gif  image/gif
"$CIRAX" convert -q sample.png -t pdf;     check "png->pdf"   sample.pdf  application/pdf
"$CIRAX" convert -q doc.txt -t zst;        check "txt->zst"   doc.zst     application/zstd

echo "== chained / staged =="
"$CIRAX" convert -q doc.ps docps.pdf;      check "ps->pdf (ghostscript)"   docps.pdf application/pdf
if "$CIRAX" convert -q docps.pdf -t txt && grep -qi "cirax" docps.txt; then
  pass=$((pass+1)); echo "  ok  ps->pdf->txt (chained, text survives)"
else
  fail=$((fail+1)); echo "FAIL  ps->pdf->txt (chained)"
fi
"$CIRAX" convert -q sample.pdf page.png;   check "pdf->png (explicit out)" page.png  image/png
7z a -bso0 archive.zip doc.txt sample.png
"$CIRAX" convert -q archive.zip -t 7z;     check "zip->7z (staged tree)"   archive.7z application/x-7z-compressed

echo "== phase 1 features =="
"$CIRAX" convert -q sample.mp4 vid.mkv --preset web720 && \
  check "preset web720 (mkv)" vid.mkv video/x-matroska
"$CIRAX" convert -q docps.pdf pg.png --pages all
n=$(ls pg-*.png 2>/dev/null | wc -l)
if [ "$n" -ge 2 ]; then pass=$((pass+1)); echo "  ok  pages all ($n pages)"
else fail=$((fail+1)); echo "FAIL  pages all"; fi
"$CIRAX" convert -q docps.pdf one.png --pages 1 && \
  check "pages 1 (single)" one.png image/png
magick -size 30x20 xc:red b1.png
magick -size 30x20 xc:blue b2.png
"$CIRAX" convert -q b1.png b2.png -t jpg
if [ -f b1.jpg ] && [ -f b2.jpg ]; then pass=$((pass+1)); echo "  ok  batch convert"
else fail=$((fail+1)); echo "FAIL  batch convert"; fi

echo "== phase 2: office / ebooks / ops / AI OCR =="
printf '# Hello Doc\n\nSome **bold** text.\n' > doc.md
"$CIRAX" convert -q doc.md doc.docx &&        check "md->docx (pandoc)"        doc.docx application/vnd.openxml
"$CIRAX" convert -q doc.docx doc.pdf &&       check "docx->pdf (libreoffice)"  doc.pdf application/pdf
"$CIRAX" convert -q doc.md book.epub &&       check "md->epub (pandoc)"        book.epub application/epub
if "$CIRAX" convert -q book.epub book.azw3 && test -s book.azw3; then
  pass=$((pass+1)); echo "  ok  epub->azw3 (calibre)"
else
  fail=$((fail+1)); echo "FAIL  epub->azw3"
fi
"$CIRAX" convert -q photo.jpg clean.jpg &&    check "jpeg metadata strip (exiftool)" clean.jpg image/jpeg
"$CIRAX" convert -q big.png quant.png &&      check "png->png quantize (pngquant)" quant.png image/png
printf 'a\r\nb\r\n' > win.txt
if "$CIRAX" convert -q win.txt unix.txt && od -c unix.txt | grep -q 'a  \\n'; then
  pass=$((pass+1)); echo "  ok  dos2unix ops route"
else
  fail=$((fail+1)); echo "FAIL  dos2unix"
fi
printf 'caf\xe9\n' > l1.txt
if "$CIRAX" convert -q l1.txt u8.txt --engine iconv --preset latin1-utf8 && od -c u8.txt | grep -q '303 251'; then
  pass=$((pass+1)); echo "  ok  iconv charset preset"
else
  fail=$((fail+1)); echo "FAIL  iconv preset"
fi
if ollama list 2>/dev/null | grep -q glm-ocr; then
  magick -size 500x120 xc:white -pointsize 28 -fill black -annotate +30+60 "Cirax OCR Test 42" ocr.png
  if "$CIRAX" convert -q ocr.png ocr-out.txt && grep -q "Cirax OCR Test 42" ocr-out.txt; then
    pass=$((pass+1)); echo "  ok  GLM-OCR image->text"
  else
    fail=$((fail+1)); echo "FAIL  GLM-OCR"
  fi
else
  echo "skip  GLM-OCR (model not pulled; run: ollama pull glm-ocr)"
fi

echo "== phase 3: sandbox / 3D / disks / geo =="
if "$CIRAX" convert -q sample.png sb.webp --sandbox on && bwrap --ro-bind / / --tmpfs /tmp --unshare-net -- true 2>/dev/null; then
  pass=$((pass+1)); echo "  ok  sandboxed conversion (bwrap, no network)"
else
  fail=$((fail+1)); echo "FAIL  sandboxed conversion"
fi
cat > cube.obj <<'EOF'
v 0 0 0
v 1 0 0
v 1 1 0
v 0 1 0
v 0 0 1
v 1 0 1
v 1 1 1
v 0 1 1
f 1 2 3 4
f 5 6 7 8
f 1 2 6 5
f 2 3 7 6
f 3 4 8 7
f 4 1 5 8
EOF
if "$CIRAX" convert -q cube.obj cube.glb && file -b cube.glb | grep -qi glTF; then
  pass=$((pass+1)); echo "  ok  obj->glb (assimp)"
else
  fail=$((fail+1)); echo "FAIL  obj->glb"
fi
qemu-img create -f qcow2 disk.qcow2 16M >/dev/null
if "$CIRAX" convert -q disk.qcow2 disk.vdi && qemu-img info disk.vdi 2>/dev/null | grep -q vdi; then
  pass=$((pass+1)); echo "  ok  qcow2->vdi (qemu-img)"
else
  fail=$((fail+1)); echo "FAIL  qcow2->vdi"
fi
printf '{"type":"FeatureCollection","features":[{"type":"Feature","properties":{"name":"home"},"geometry":{"type":"Point","coordinates":[12.5,51.3]}}]}' > pt.geojson
if "$CIRAX" convert -q pt.geojson pt.gpkg && file -b pt.gpkg | grep -qi GeoPackage; then
  pass=$((pass+1)); echo "  ok  geojson->gpkg (gdal)"
else
  fail=$((fail+1)); echo "FAIL  geojson->gpkg"
fi

echo
echo "passed: $pass  failed: $fail"
[ "$fail" -eq 0 ]
