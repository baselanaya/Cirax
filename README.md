<div align="center">

# Cirax

**An invisible AI copilot that floats over your screen — sees what you see, hears your meetings, and stays hidden from screen shares.**

BYOK: OpenAI · Anthropic · Google Gemini · any OpenAI-compatible endpoint. Free and self-hosted.

</div>

---

> [!IMPORTANT]
> **Please read this first.** Cirax tries to stay out of screen recordings/shares, but this is **best-effort, not guaranteed** — on macOS 15.4+ Apple can let modern capture tools see it anyway, on Windows 10 builds older than 2004 it degrades to a black box instead of true exclusion, and a phone camera always can. Using a hidden assistant during a **proctored exam, job interview, or recorded meeting** may break that platform's rules and, in some places, consent laws. Cirax is built for legitimate uses — your own notes, studying, accessibility, and practice. **You are responsible for how you use it.**

---

## What it does

Cirax floats a small glass panel on top of everything. It takes **three separate inputs** — your **screen**, your **microphone**, and your **meeting audio** (what the other person says) — and uses your own AI model to help you in real time.

| Feature | Trigger | What it uses |
|---|---|---|
| **Assist** | `Ctrl` `Enter` (configurable) | your screen + recent conversation |
| **What should I say?** | button | meeting audio + your mic |
| **Follow-up questions** | button | the whole conversation |
| **Recap** | button | the whole conversation |
| **Ask anything** | type + `Enter` | your screen + conversation |
| **Solve a coding problem** | `Ctrl` `H` | your screen only |
| **Smart** toggle | pill in the box | switches to a smarter (slower) model |

### Platform support

|  | macOS | Windows 11 / 10 2004+ | Linux (X11/Wayland) |
|---|---|---|---|
| Screen + coding help | ✅ | ✅ | ✅ (capture via PipeWire portal on Wayland) |
| Your mic (the **You** channel) | ✅ | ✅ | ✅ |
| Meeting audio (the **Them** channel) | ✅ macOS 14.4+ | ✅ | ⚠️ best-effort (PipeWire) |
| Hidden from screen shares | ⚠️ best-effort | ✅ `WDA_EXCLUDEFROMCAPTURE` | ❌ visible — flagged honestly in the app |
| Local Whisper transcription | ✅ | ✅ | ✅ |

## Install

### From source

```sh
git clone <your-fork-url> cirax
cd cirax
npm install
npm start
```

Node 22.12+ required. On Linux, also install your distro's engines if `npm start` complains about a missing Electron binary (see `docs/`).

### Packaging

```sh
npm run dist:linux        # AppImage
npm run dist:win          # Windows installer
npm run dist:mac          # macOS zip
```

## Configuration

Open the settings (gear) and add **any one** of:

- **OpenAI** key — or any OpenAI-compatible endpoint (Groq, Ollama, LM Studio, custom base URL)
- **Anthropic** key
- **Google Gemini** key
- **Azure AI Foundry** endpoint + key

Optional: a **Deepgram** key for cloud streaming transcription, or enable **local Whisper** for fully offline speech-to-text.

## Privacy

- Everything runs **locally** — screenshots, audio, and transcripts go only to the LLM provider you configure. No telemetry.
- API keys are stored **encrypted** via the OS keyring (Electron safeStorage) when available.
- The optional camera/eye-contact companion (`companion/`) also runs fully locally.

## Linux notes

- The overlay runs under XWayland by default; Wayland screen capture goes through the PipeWire portal (`WebRTCPipeWireCapturer` is enabled automatically).
- **The overlay is hidden from your taskbar and Alt+Tab, but NOT from screen shares on Linux** — the app tells you this at startup. There is no OS mechanism (X11 or Wayland) for per-window capture exclusion yet.
- Some distros print `Fontconfig warning` lines at launch from Chromium's bundled fontconfig — harmless noise, not a Cirax error.

## Credits & license

GPL-3.0-or-later. Maintained by Basel Anaya. Contains code derived from
[cue](https://github.com/Blueturboguy07/cue) (GPL-3.0).
