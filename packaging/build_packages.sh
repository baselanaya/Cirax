#!/usr/bin/env bash
# Build release artifacts: PyInstaller CLI + desktop app, then
# .deb, .rpm and .AppImage packages into dist/packages/.
#
# Requires: uv, appimagetool (packaging/tools/), rpmbuild, ar (binutils).
set -euo pipefail
cd "$(dirname "$0")/.."
ROOT="$PWD"
VER="$(python3 -c 'import tomllib; print(tomllib.load(open("pyproject.toml","rb"))["project"]["version"])')"
OUT="$ROOT/dist/packages"
ARCH="$(uname -m)"

echo "==> building cirax $VER for $ARCH"

# 1. build venv with desktop extras (pyside6, pyinstaller)
uv sync --group desktop --quiet
uv pip install --quiet pyinstaller

BUNDLES="$ROOT/dist/bundles"
rm -rf "$BUNDLES" "$OUT"
mkdir -p "$BUNDLES" "$OUT"

# 2. CLI binary (onefile)
uv run pyinstaller --onefile --name cirax --clean --noconfirm \
  --paths src --add-data "src/cirax/data:cirax/data" \
  desktop/cirax_cli_entry.py -y >/dev/null
cp dist/cirax "$BUNDLES/cirax"

# 3. desktop app (onedir, windowed)
uv run pyinstaller --onedir --name cirax-app --clean --noconfirm --windowed \
  --paths src --add-data "src/cirax/data:cirax/data" \
  desktop/cirax_app_entry.py >/dev/null

# 4. AppImage
APPDIR="$BUNDLES/Cirax.AppDir"
mkdir -p "$APPDIR/usr/bin" "$APPDIR/usr/share/applications" \
         "$APPDIR/usr/share/icons/hicolor/256x256/apps" "$APPDIR/usr/lib"
cp -r "dist/cirax-app" "$APPDIR/usr/lib/"
cp assets/cirax.png "$APPDIR/usr/share/icons/hicolor/256x256/apps/cirax.png"
cp assets/cirax.png "$APPDIR/cirax.png"
cp desktop/cirax.desktop "$APPDIR/usr/share/applications/cirax.desktop"
cat > "$APPDIR/cirax.desktop" <<EOF
[Desktop Entry]
Type=Application
Name=Cirax
GenericName=File Converter
Comment=Every format to every format — fully local, sandboxed
Exec=AppRun
Icon=cirax
Terminal=false
Categories=Utility;Office;AudioVideo;Graphics;
EOF
cat > "$APPDIR/AppRun" <<EOF
#!/bin/sh
exec "\$(dirname "\$0")/usr/lib/cirax-app/cirax-app" "\$@"
EOF
chmod +x "$APPDIR/AppRun"
ln -sf usr/lib/cirax-app/cirax-app "$APPDIR/usr/bin/cirax-app"
packaging/tools/appimagetool --appimage-extract-and-run \
  --comp zstd "$APPDIR" "$OUT/Cirax-$VER-$ARCH.AppImage" >/dev/null

# 5. .deb (manual archive — a .deb is an ar of three members)
DEBDIR="$BUNDLES/deb"
mkdir -p "$DEBDIR/DEBIAN" "$DEBDIR/usr/bin" "$DEBDIR/usr/lib/cirax" \
         "$DEBDIR/usr/share/applications" \
         "$DEBDIR/usr/share/icons/hicolor/256x256/apps"
cp -r "dist/cirax-app" "$DEBDIR/usr/lib/cirax/"
ln -sf /usr/lib/cirax/cirax-app/cirax-app "$DEBDIR/usr/bin/cirax-app"
cp "$BUNDLES/cirax" "$DEBDIR/usr/bin/cirax"
cp assets/cirax.png "$DEBDIR/usr/share/icons/hicolor/256x256/apps/cirax.png"
cp desktop/cirax.desktop "$DEBDIR/usr/share/applications/cirax.desktop"
cat > "$DEBDIR/DEBIAN/control" <<EOF
Package: cirax
Version: $VER
Section: utils
Priority: optional
Architecture: $([ "$ARCH" = "x86_64" ] && echo amd64 || echo "$ARCH")
Maintainer: Basel Anaya <baselanaya@gmail.com>
Depends: libc6 (>= 2.31), libgl1, libegl1, libxkbcommon0, libfontconfig1, libdbus-1-3
Description: Universal local conversion hub — desktop app + CLI
 Every format to every format, fully offline. Wraps best-in-class
 engines (ffmpeg, libvips, LibreOffice, pandoc, 7-Zip, qpdf, ...)
 with chain routing, bwrap sandboxing and optional local AI OCR.
Homepage: https://github.com/baselanaya/Cirax
EOF
( cd "$DEBDIR" && tar czf control.tar.gz -C DEBIAN . && tar czf data.tar.gz usr \
  && echo "2.0" > debian-binary \
  && ar rc "$OUT/cirax_${VER}_$([ "$ARCH" = "x86_64" ] && echo amd64 || echo "$ARCH").deb" \
     debian-binary control.tar.gz data.tar.gz )

# 6. .rpm (rpmbuild)
RPMROOT="$BUNDLES/rpmbuild"
mkdir -p "$RPMROOT"/{BUILD,RPMS,SOURCES,SPECS,SRPMS}
cp -r "dist/cirax-app" "$BUNDLES/cirax-app"
cp assets/cirax.png "$BUNDLES/cirax.png"
tar czf "$RPMROOT/SOURCES/cirax-$VER.tar.gz" -C "$BUNDLES" \
  cirax cirax-app cirax.png
cat > "$RPMROOT/SPECS/cirax.spec" <<EOF
Name:           cirax
Version:        $VER
Release:        1%{?dist}
Summary:        Universal local conversion hub — desktop app + CLI
License:        MIT
URL:            https://github.com/baselanaya/Cirax
Source0:        cirax-$VER.tar.gz
ExclusiveArch:  x86_64
%description
Every format to every format, fully offline. Desktop app + CLI wrapping
best-in-class local engines with chain routing and bwrap sandboxing.
%prep
%setup -c
%install
mkdir -p %{buildroot}/opt/cirax %{buildroot}%{_bindir} \
         %{buildroot}%{_datadir}/applications \
         %{buildroot}%{_datadir}/icons/hicolor/256x256/apps
cp -r cirax-app %{buildroot}/opt/cirax/
cp cirax %{buildroot}/opt/cirax/
ln -sf /opt/cirax/cirax-app/cirax-app %{buildroot}%{_bindir}/cirax-app
ln -sf /opt/cirax/cirax %{buildroot}%{_bindir}/cirax
printf '[Desktop Entry]\nType=Application\nName=Cirax\nGenericName=File Converter\nComment=Every format to every format - fully local, sandboxed\nExec=cirax-app\nIcon=cirax\nTerminal=false\nCategories=Utility;Office;AudioVideo;Graphics;\n' > %{buildroot}%{_datadir}/applications/cirax.desktop
cp cirax.png %{buildroot}%{_datadir}/icons/hicolor/256x256/apps/cirax.png
%files
/opt/cirax
%{_bindir}/cirax
%{_bindir}/cirax-app
%{_datadir}/applications/cirax.desktop
%{_datadir}/icons/hicolor/256x256/apps/cirax.png
EOF
rpmbuild -bb --undefine dist --define "_topdir $RPMROOT" \
  "$RPMROOT/SPECS/cirax.spec" >/dev/null
find "$RPMROOT/RPMS" -name '*.rpm' ! -name '*debuginfo*' \
  -exec cp {} "$OUT/" \;

echo "==> artifacts:"
ls -la "$OUT"
