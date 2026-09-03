# Tauri & Windows GUI — capabilities assessment

*What we can and cannot design, what a Tauri port would mean for Cirax, and what we
recommend. Written 2026-09-03, after the v0.4.3 PySide6 multi-page redesign.*

---

## 1. What the current shell is

The desktop app is **PySide6 (Qt Widgets)** in `desktop/cirax_app.py`, shipped as a
PyInstaller onedir bundle. It talks to the conversion core **in-process** (imports
`cirax.registry/router/executor` directly). The styling is QSS (Qt's CSS subset) with a
painted gradient backdrop — our "glass" is translucency over a gradient, not real blur.

## 2. What Tauri actually gives you

Tauri 2 = a Rust host process + the OS webview. On Windows that is **WebView2
(evergreen, Chromium-based, preinstalled on Win10 21H2+/Win11)**; on Linux, WebKitGTK.

| Capability | PySide6 today | Tauri 2 |
|---|---|---|
| **True backdrop blur** (Windows Mica / Acrylic) | ❌ painted gradient only | ✅ `window-vibrancy` crate (`apply_mica`, `apply_acrylic`) — the real glassmorphism |
| Design freedom | QSS (CSS-subset, no flex/grid, no pseudo-elements beyond basics, limited selectors) | full web stack: grid/flex, custom properties, `backdrop-filter`, inline SVG, web fonts, animations, component libraries |
| Motion | QPropertyAnimation (manual) | CSS/JS animation, Framer Motion, view transitions |
| Per-domain themed pages | one QSS for everything | each domain page can carry its own accent token effortlessly |
| Custom window chrome | limited | `decorations: false` + custom titlebar (standard for "modern UI" look) |
| System tray / global shortcuts / notifications / autostart / deep links | partial (QSystemTrayIcon) | first-class plugins |
| Auto-update | manual | built-in updater plugin |
| Installer | Inno Setup (what we already ship) | NSIS/MSI bundlers built in (`tauri build`) |
| Binary size | ~90 MB (Python + Qt bundled) | ~10–20 MB (Rust + webview, engine-less) |
| RAM at idle | ~150–250 MB (Qt) | ~80–150 MB (WebView2 shares the evergreen runtime) |
| Cross-platform risk | none | Linux WebKitGTK quirks (we only need Linux for dev; releases are Win + AppImage — AppImage + WebKitGTK is the known pain point) |

**The blunt summary:** everything the "modern app" checklist asks for — glassmorphism
that actually blurs, multi-page navigation with animated transitions, a design system in
real CSS, Windows Fluent/Mica integration — is either impossible or painful in Qt Widgets
and native in Tauri.

## 3. The architecture question: where does conversion logic live?

Cirax's value is the registry + router + executor. Three options:

### A. Full Rust port ❌
Reimplement registry/router/chains in Rust. Kills the "adding an engine is a YAML stanza"
property (or forces a YAML engine in Rust anyway), doubles maintenance, loses Python's
subprocess ergonomics. **Rejected.**

### B. Tauri shell + Python sidecar ✅ (recommended)
The shipped PyInstaller CLI already has everything needed: `cirax serve --api` becomes a
small JSON API (the web UI's endpoints — `/api/formats`, `/api/engines`,
`/api/convert?to=`, plus `/api/plan` for route previews). Tauri declares the PyInstaller
`cirax.exe` as a **sidecar**; the web frontend talks HTTP on a loopback port; the Rust
layer handles windows, Mica, tray, updater.

- The conversion core stays exactly as it is — one brain, three faces (CLI / web / GUI).
- The desktop app becomes a thin, beautiful shell over the same API the web UI uses.
- Packaging: the Windows installer ships `cirax-app.exe` (Tauri) + `cirax.exe` (sidecar).
  Same shape as today, plus ~15 MB of Rust.
- CI: `windows-latest` builds the sidecar (PyInstaller) and the shell (Tauri) — both
  already proven steps in our pipeline.

### C. Stay PySide6 ✅ (acceptable for now)
The v0.4.3+ app works and is shipped. Its ceiling: no real blur, no rich motion, QSS
ceiling, every design idea costs 3× the code it would in CSS.

## 4. What we would design in Tauri (the actual UI)

- **Convert page** — drop zone as the hero; detected-format chips; the target list as
  selectable cards with route-chain mini-boards (`webp ─ vips → png`, loss tag colored);
  per-job rows with real progress and result previews (thumbnail for images — WebView2
  renders them natively, which QWidgets cannot without custom code).
- **Format pages** — one page per domain (Image / Video / Audio / Documents / …), each
  carrying its **line color** (the transit-map identity from the CLI docs): formats grid,
  engines serving the domain, capability matrix from `/api/engines`.
- **Windows integration** — Mica backdrop, jump list ("Convert to PDF" pinned), taskbar
  progress on the running jobs, toast when the queue drains, tray icon with queue state.
- **Design system** — the tokens from `docs/FORMATS.md` + the CLI banner: ink base,
  signal cyan, per-domain line colors, mono route boards. In Tauri these become CSS
  custom properties consumed identically by web UI and desktop.

## 5. Recommendation

1. **Now (v0.7):** redesign the PySide6 app per the new design system (per-domain pages,
   route boards, domain colors) — it ships today and keeps Linux/Windows releases moving.
2. **Next (v1.0):** build the Tauri shell over `cirax serve --api` as the Windows-first
   desktop app; Linux keeps PySide6 until WebKitGTK pain is measured. The sidecar seam
   (`cirax serve`) is the whole migration strategy — build that API well and the shell
   becomes swappable.
3. **Never:** a Rust port of the conversion core.

---

## Appendix: Tauri 2 quick facts for this project

- Sidecar: `tauri.conf.json` → `bundle.externalBin: ["binaries/cirax"]`; spawn via
  `Command::new_sidecar`. License note: PyInstaller output stays MIT; sidecar is ours.
- Window effects: `window-vibrancy` → `apply_mica(window, None)` (Win11) /
  `apply_acrylic` (Win10); on Linux, no equivalent — fall back to opaque.
- WebView2 runtime: preinstalled Win11; Tauri's installer bootstraps it otherwise.
- Auto-update: `tauri-plugin-updater` needs release manifest + signing keys — wire when
  Windows releases stabilize.
- Useful plugins for our UX: `tray-icon`, `global-shortcut` (drop-hotkey), `dialog`,
  `opener` (result opening — replaces our xdg-open dance), `notification` (queue done),
  `single-instance`.
