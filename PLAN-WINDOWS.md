# Cirax on Windows — Release Plan

**Goal:** Cirax (CLI + desktop app) runs natively on Windows 10/11 x64, installs via an
exe installer and winget, discovers engines from Windows package managers, and ships as a
first-class target in CI and releases — while staying 100% local and honest about what the
platform can and cannot do.

> Status: **W1–W3 shipped** (v0.4.3 Linux polish, v0.5.1 portable core + Windows CI, v0.6.2 Windows installer + portable zip on releases, v0.6.3 Scoop bucket + winget manifests). Remaining: winget PR submission (needs a winget-pkgs PR from your account), AppContainer spike. (v0.5.0 is reserved for the
> Linux polish batch). Everything here builds on the existing architecture — no fork, no
> rewrite: the core is pure Python and the engines are already behind a declarative registry.

---

## 0. The honest headline

| Layer | Linux today | Windows plan |
|---|---|---|
| Conversion core (registry, router, executor, chains) | ✅ | ✅ pure Python, portable |
| CLI (doctor/plan/convert/watch/serve) | ✅ | ✅ rich works in Windows Terminal |
| Desktop app (PySide6) | ✅ | ✅ Qt is cross-platform |
| PyPI / npm install channels | ✅ | ✅ already portable (`npm os` gate lifted in W1) |
| Engine discovery | pacman/PATH | PATH + Program Files + registry (winreg) + scoop shims |
| Engine coverage | 58 specs | ~45 realistic on Windows (tiered, see §3) |
| bubblewrap sandbox | ✅ | ❌ W1 ships without it (see §5) |
| Installers | PKGBUILD/AppImage/deb/rpm | Inno Setup exe + portable zip + winget |

---

## 1. Portability audit (what actually blocks Windows today)

Concrete touchpoints found in the code, and their fixes:

| Location | Issue | Fix |
|---|---|---|
| `sandbox.py` | bwrap is Linux-only | `resolve_mode()` returns `"off"` on Windows with a one-time notice; GUI hides the toggle (`Qt.CheckState` set from platform); W2 investigates AppContainer |
| `cli.py` (`doctor`) | pacman-only install hints | platform-aware hints: Windows → `scoop install <app>` / `winget install <id>` per engine |
| `cli.py` (`--sandbox on`) | errors when bwrap missing | same platform-aware message |
| `registry.py` schema | `binary` + `package` are single-value, Arch-shaped | add `platforms` gating + per-OS `binaries` and `install` hints (schema in §2) |
| `probe.py` | `shutil.which` only | Windows: also search `%ProgramFiles%`, `%LOCALAPPDATA%\Programs`, App Paths registry key (`winreg`, stdlib) — e.g. `soffice.exe`, `ebook-convert.exe` never land on PATH |
| `executor.py` | `_child_env()` scrubs LD_LIBRARY_PATH (harmless on Windows) | keep; also scrub `PATH` prepend noise PyInstaller leaves |
| `desktop/cirax_app.py` | `open_path()` uses xdg-open; `STATE_DIR` under `~/.local/state` | `os.startfile()` on Windows; state dir → `%LOCALAPPDATA%\Cirax` (single `paths.py` helper, no more scattered `Path.home()`) |
| `npm/package.json` | `"os": ["linux", "darwin"]` gates Windows out | add `"win32"` in W1 once the shim is verified (postinstall already branches on `win32`) |
| `install.sh` | POSIX only | new `install.ps1` (winget/scoop → `pipx`/`uv tool install cirax`) |
| CI | ubuntu only | add `windows-latest` job (§4) |
| Icon | PNG only | Windows needs `.ico` (generate from `assets/cirax.svg` via ImageMagick — one line) |

Not portable, ever (by design): AUR/PKGBUILD, `pacman` hints, bubblewrap. These simply
disappear from the Windows UX; the capability matrix degrades honestly.

---

## 2. Registry schema: platform-aware engines

Current spec fields stay. Add three optional keys — no existing stanza breaks:

```yaml
engine: libreoffice
binary: soffice            # Linux/macOS binary (unchanged)
platforms: [linux, macos, windows]        # default: all
install:                   # per-OS hints for `cirax doctor --show-missing`
  linux: "libreoffice-still"                    # pacman (as today)
  windows: "scoop bucket add extras && scoop install libreoffice"
binaries:                  # Windows override: binary name + probe paths
  windows:
    binary: soffice.exe
    search:
      - "%ProgramFiles%\\LibreOffice\\program"
      - "%ProgramFiles(x86)%\\LibreOffice\\program"
```

Rules:
- `platforms` omits the engine from `doctor`/router on absent OSes (calibre, ffmpeg,
  imagemagick, 7-zip, tesseract… all stay; nothing Linux-only exists in the registry
  except bwrap itself, which is infrastructure, not an engine).
- `binaries.<os>.search` entries may use env-var substitution; `probe.py` expands and
  checks them before falling back to `shutil.which`.
- `install.<os>` strings feed `doctor --show-missing` per platform.

**Windows engine source of truth: [Scoop](https://scoop.sh).** User-scope (no admin, no
UAC prompts), stable shim-based PATH, and every engine we care about exists in `main` or
`extras`. We ship **our own Scoop bucket** (`scoop bucket add cirax
https://github.com/baselanaya/Cirax-scoop`) with pinned manifests for the engines that
are missing or mis-versioned elsewhere — we control the repo, no third-party approval.

### Engine coverage tiers on Windows

| Tier | Engines | Source |
|---|---|---|
| **T1 — day one** (winget/scoop/choco official) | ffmpeg, imagemagick, 7zip, ghostscript, poppler, pandoc, calibre, libreoffice, inkscape, darktable, exiftool, jq, yq, miller, duckdb, zstd, sox, lame, opus-tools, mkvtoolnix, gifsicle, tesseract (+data), potrace, sqlite, typst, ollama, qemu, fonttools(pip), img2pdf(pip), ocrmypdf(pip) | scoop/choco/pip |
| **T2 — GitHub-release binaries** (our bucket pins them) | libheif, libjxl, libavif, libwebp, vips, assimp, gdal(mini), mupdf, opusenc, xorriso | upstream releases |
| **T3 — deferred** (no clean Windows story) | unar, handbrake-cli (GUI ok), ocrmypdf's full chain edge cases, potrace variants | revisit |

Target for W2 exit: **≥ 35 engines green on Windows** (vs 58 registered). `cirax doctor`
is the scoreboard, same as Linux.

---

## 3. Sandboxing on Windows — honesty first

- **W1:** no sandbox. `cirax doctor` prints "sandbox: unavailable on this platform".
  The GUI hides the toggle. Docs say it plainly: on Windows, Cirax runs engines directly.
- **Mitigations that ARE cheap on Windows:** subprocess env scrubbing (already in
  `_child_env()`, keep), per-job temp dirs (already), timeouts (already), and
  `Job Objects` for CPU/memory caps (small, portable-enough addition via pywin32 — optional).
- **W2 stretch:** AppContainer (LPAC) wrapper for the top-5 parsers (imagemagick,
  ghostscript, poppler, 7z, tesseract). It's a real project — scoped spike first, ship
  only if it survives real files. Do not promise it in release notes until it lands.
- Alternative honestly documented for high-risk users: run Cirax inside Windows Sandbox
  (Pro/Enterprise) — works today with zero code.

---

## 4. Build & release pipeline (GitHub Actions, windows-latest)

New job in `publish.yml` (tags), plus a matching CI job:

```
jobs:
  windows:
    runs-on: windows-latest
    steps:
      - uses: actions/checkout@v4
      - uses: astral-sh/setup-uv@v5
      - run: uv sync --group desktop
      - name: build CLI + app (PyInstaller onedir)
        run: |
          uv run pyinstaller --onefile  --name cirax     desktop/cirax_cli_entry.py  (with data)
          uv run pyinstaller --onedir   --name cirax-app desktop/cirax_app_entry.py  (with data + icon)
      - name: icon
        run: magick assets/cirax.svg -define icon:auto-resize=256,128,64,48,32,16 cirax.ico
      - name: installer (Inno Setup)
        uses: Minionguyjpro/Inno-Setup-Action@v1.2
        with: path: packaging/windows/cirax.iss
      - name: portable zip
        run: Compress-Archive dist/cirax-app-win64 → cirax-0.6.0-win64-portable.zip
      - uses: actions/upload-artifact / attach to release (softprops/action-gh-release)
```

Artifacts per release (add to the existing three Linux ones):

- `Cirax-Setup-<ver>-win64.exe` — Inno installer: installs to `%LOCALAPPDATA%\Programs\Cirax`
  (per-user, no admin), Start-menu + desktop shortcuts, adds `cirax` + `cirax-app` to PATH,
  bundles both PyInstaller trees and the icon. Optional component checkboxes: "Add to PATH",
  "Desktop shortcut".
- `cirax-<ver>-win64-portable.zip` — unzip and run, for locked-down machines.
- (Later) MSIX for the Microsoft Store — separate decision, certification has its own rules.

**PyPI and npm need zero work to go live on Windows** — the wheel is universal; flip the
npm `os` gate and verify the shim's `Scripts\cirax.exe` branch (already written) on a CI
Windows box.

---

## 5. SmartScreen & code signing (the real Windows tax)

Unsigned PyInstaller exes get SmartScreen-warned and are the #1 support smell on Windows.

- **W1:** ship unsigned + document the one-click "More info → Run anyway" flow in the
  release notes; winget submission requires stable hashes, not signing — do it anyway.
- **W2:** buy a code-signing certificate (OV from ~$100/yr, e.g. Certum/Sectigo) and sign
  in CI (`signtool sign /fd sha256`). EV certs kill SmartScreen warnings instantly but cost
  more and need hardware tokens — decide by download numbers, not vibes.
- PyInstaller onefile is the most AV-flagged shape in existence: on Windows, ship **onedir
  inside the installer** (never onefile) and keep the portable zip as the niche path.

---

## 6. Testing strategy

- **CI (every push):** `windows-latest` job — choco installs T1 subset (ffmpeg, imagemagick,
  7zip, ghostscript, poppler, pandoc), `uv sync`, `cirax doctor`, then the same five
  conversions as Linux CI (webp→png, txt→zst, zip→7z, ps→pdf→txt, png→pdf).
- **GUI smoke:** PySide6 offscreen construct on the Windows runner + `PyInstaller --noconfirm`
  build success is the gate; interactive testing stays manual (you + a Win10/11 VM).
- **Manual matrix before release:** Win11 + Win10, admin & non-admin install, PATH launch
  from fresh cmd/PowerShell, drag-and-drop from Explorer, xdg-open-equivalent (os.startfile)
  result opening, sleep/resume with a running queue.

---

## 7. Roadmap

| Phase | Scope | Exit criteria |
|---|---|---|
| **W1 — portable core** (~1 wk) | `paths.py` (LOCALAPPDATA), platform-aware doctor hints, npm `os` gate lift, `install.ps1`, CI windows job (pure-Python checks + 5 conversions via choco engines), sandbox honestly "off" | CI green on windows-latest; `pip install cirax` + CLI works on a real Windows box |
| **W2 — engines & GUI** (~2 wk) | registry schema (`platforms`/`binaries`/`install`), winreg+Program Files probing, Cirax Scoop bucket, GUI: hide sandbox toggle, `os.startfile`, `.ico` icon, PyInstaller onedir verified on Windows | ≥35 engines green; GUI opens and converts on Windows |
| **W3 — installer & release** (~1 wk) | Inno Setup, portable zip, winget manifest PR, publish.yml windows job, signing spike | v0.6.0 release carries `Cirax-Setup-win64.exe` + portable zip; `winget search cirax` resolves (after MS review) |
| **W4 — stretch** | AppContainer spike, MSIX/Store, Windows-specific presets (e.g. Paint-friendly outputs) | per spike outcome |

---

## 8. Risks

| Risk | Mitigation |
|---|---|
| SmartScreen/AV flags unsigned exe | onedir + Inno (not onefile), document bypass, sign in W2 |
| Engine coverage disappoints | tiered honestly; `doctor` scoreboard; Scoop bucket fills gaps we control |
| LibreOffice/Calibre not on PATH | registry + Program Files probing (§1), documented |
| PySide6/PyInstaller Windows quirks | CI catches at build time; onedir not onefile; per-release manual matrix (§6) |
| Support burden doubles | docs per-OS; `cirax doctor` output is the required bug-report attachment |
| Scope creep into WSL2 story | out of scope — WSL2 users already have the Linux build |

---

## 9. What we are NOT doing

- No WSL2-first story (that's the Linux build running on Windows; fine, but not "a Windows version").
- No 32-bit, no Windows 7/8 (Python 3.10+ and PySide6 already require 10+).
- No bundling of engines inside the installer in W1–W3 (same engines-as-system-deps
  philosophy; the Scoop bucket is the sanctioned path). A fully-offline "fat installer"
  is a deliberate future decision with a size cost (~1 GB).
- No code signing purchase until download numbers justify it.
