#!/usr/bin/env bash
# Build macOS artifacts: Cirax.app (desktop app + CLI inside) and a .dmg.
# Designed for CI (macos-latest); needs uv + sips/iconutil (macOS built-ins).
set -euo pipefail
cd "$(dirname "$0")/../.."
ROOT="$PWD"
VER="$(python3 -c 'import tomllib; print(tomllib.load(open("pyproject.toml","rb"))["project"]["version"])')"
OUT="$ROOT/dist/packages"
ARCH="$(uname -m)"

echo "==> building cirax $VER for macOS $ARCH"

uv sync --group desktop --quiet
uv pip install --quiet pyinstaller

# 1. binaries
uv run pyinstaller --onefile --name cirax --clean --noconfirm \
  --paths src --add-data "src/cirax/data:cirax/data" \
  desktop/cirax_cli_entry.py >/dev/null
uv run pyinstaller --onedir --windowed --name cirax-app --clean --noconfirm \
  --paths src --add-data "src/cirax/data:cirax/data" \
  desktop/cirax_app_entry.py >/dev/null

# 2. icon (png -> icns via built-ins)
rm -rf cirax.iconset cirax.icns
mkdir -p cirax.iconset
for spec in "16 icon_16x16" "32 icon_16x16@2x" "32 icon_32x32" \
            "64 icon_32x32@2x" "128 icon_128x128" "256 icon_128x128@2x" \
            "256 icon_256x256" "512 icon_256x256@2x" "512 icon_512x512" \
            "1024 icon_512x512@2x"; do
  size="${spec%% *}"; name="${spec#* }"
  sips -z "$size" "$size" assets/cirax.png --out "cirax.iconset/${name}.png" >/dev/null
done
iconutil -c icns cirax.iconset -o cirax.icns

# 3. .app bundle
APP="Cirax.app"
rm -rf "$APP"
mkdir -p "$APP/Contents/MacOS" "$APP/Contents/Resources"
cp cirax.icns "$APP/Contents/Resources/cirax.icns"
cp -r dist/cirax-app "$APP/Contents/MacOS/cirax-app"
cp dist/cirax "$APP/Contents/MacOS/cirax"
cat > "$APP/Contents/Info.plist" <<EOF
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN"
 "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
  <key>CFBundleName</key><string>Cirax</string>
  <key>CFBundleDisplayName</key><string>Cirax</string>
  <key>CFBundleExecutable</key><string>Cirax</string>
  <key>CFBundleIconFile</key><string>cirax.icns</string>
  <key>CFBundleIdentifier</key><string>co.maximlabs.cirax</string>
  <key>CFBundleShortVersionString</key><string>$VER</string>
  <key>CFBundleVersion</key><string>$VER</string>
  <key>CFBundlePackageType</key><string>APPL</string>
  <key>LSMinimumSystemVersion</key><string>11.0</string>
  <key>NSHighResolutionCapable</key><true/>
</dict>
</plist>
EOF
cat > "$APP/Contents/MacOS/Cirax" <<'EOF'
#!/bin/sh
exec "$(dirname "$0")/cirax-app/cirax-app" "$@"
EOF
chmod +x "$APP/Contents/MacOS/Cirax"

# 4. dmg + cli zip
mkdir -p "$OUT"
rm -f "$OUT/Cirax-$VER-macos.dmg" "$OUT/cirax-$VER-macos-cli.zip"
hdiutil create -volname Cirax -srcfolder "$APP" -ov -format UDZO \
  "$OUT/Cirax-$VER-macos-$ARCH.dmg" >/dev/null
( cd dist && zip -qry "$OUT/cirax-$VER-macos-cli.zip" cirax )

echo "==> artifacts:"
ls -la "$OUT"
