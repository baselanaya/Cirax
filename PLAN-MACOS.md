# Cirax on macOS — plan & status

**Goal:** Cirax (CLI + desktop app) runs natively on macOS 11+ (Apple Silicon and Intel),
installs as a drag-to-Applications `.app` inside a `.dmg`, discovers engines from
Homebrew, and ships from the same tag-triggered pipeline as Linux and Windows.

> Status: **W1–W2 shipped in v0.9.0** (macOS CI green, `.app` + `.dmg` built by CI).
> Remaining: notarization (needs an Apple Developer account), broader engine testing on
> real hardware.

---

## Portability audit (same method as PLAN-WINDOWS.md)

| Location | Issue | Fix |
|---|---|---|
| `paths.py` | — | ✅ darwin handled from day one (`~/Library/Application Support/Cirax`) |
| `sandbox.py` | bwrap is Linux-only | ✅ honest "off" outside Linux (already shipped in W1) |
| `probe.py` / `executor.py` | cask apps (LibreOffice, Calibre, darktable) never land on PATH | ✅ `search_macos` patterns under `/Applications`; `binaries_macos` alias (sevenzip → `7zz`) |
| `cli.py` doctor | pacman-shaped hints | ✅ three-platform hints (`install_macos`: brew/cask/pip) |
| `desktop/cirax_app.py` | xdg-open only | ✅ `open` on macOS via scrubbed-env subprocess |
| Engine specs | no macOS hints | ✅ 37 `install_macos` brew/cask/pip hints + 3 `search_macos` + 1 `binaries_macos` |

## Engine coverage on macOS

Homebrew is the source of truth. Verified-in-CI subset: vips, sevenzip (`7zz`),
ghostscript, poppler. Expected-green from brew: ffmpeg, imagemagick, pandoc, calibre
(cask), libreoffice (cask), inkscape (cask), darktable (cask), exiftool, jq, yq, miller,
duckdb, zstd, sox, mkvtoolnix, gifsicle, potrace, pngquant, oxipng, qemu, assimp, typst,
ollama, img2pdf/ocrmypdf/weasyprint/fonttools (pip). Tiering matches the Windows plan.

## Packaging

- `packaging/macos/build_macos.sh` — PyInstaller CLI (onefile) + app (onedir), wrapped
  into `Cirax.app` (Info.plist, icns generated from the PNG via sips/iconutil), then
  `hdiutil` → `Cirax-<ver>-macos-<arch>.dmg`; CLI also zipped separately.
- **Not signed / not notarized** — first launch needs right-click → Open (Gatekeeper),
  or `xattr -cr /Applications/Cirax.app`. Notarization requires the $99/yr Apple
  Developer Program; revisit like Windows code signing.

## Remaining

- Notarized + signed builds (Apple Developer account).
- Real-hardware passes: Apple Silicon + Intel, drag-and-drop from Finder, os.open of
  results, watch folders across sleep/wake.
- Windows-style universal binary question (arm64 + x86_64 → lipo) when PyPI demand shows.
