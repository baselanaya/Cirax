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
printf 'hello cirax\nsecond line\n' > doc.txt
printf '%%!PS\n/Helvetica findfont 24 scalefont setfont 72 720 moveto (Hello Cirax) show showpage 72 700 moveto (Page Two) show showpage\n' > doc.ps

echo "== doctor / plan =="
"$CIRAX" doctor >/dev/null && echo "  ok  doctor exits 0"
"$CIRAX" plan sample.png webp | grep -q "route" && echo "  ok  plan prints a route"
"$CIRAX" convert doc.txt -t zst -n >/dev/null && echo "  ok  dry-run"
"$CIRAX" presets >/dev/null && echo "  ok  presets listing"

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

echo
echo "passed: $pass  failed: $fail"
[ "$fail" -eq 0 ]
