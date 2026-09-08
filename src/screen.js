// Screen/window capture via desktopCapturer (main process).
// - Screen mode: captures the display under the cursor (multi-monitor aware),
//   falling back to the primary display.
// - Window mode ('window'): captures the largest non-cirax window on that
//   display — for when the interesting content is a single app window.
// Output is JPEG (quality 80) downscaled to max 1600px wide: vision models
// downscale anyway, and a full-res PNG costs ~5x the tokens for no accuracy.
const { desktopCapturer, screen } = require('electron');

const MAX_WIDTH = 1600;
const JPEG_QUALITY = 80;
const OWN_APP_RE = /cirax/i;

async function captureScreenshot({ mode = 'screen' } = {}) {
  const cursor = screen.getCursorScreenPoint();
  const display = (cursor && screen.getDisplayNearestPoint(cursor)) ||
    screen.getPrimaryDisplay();
  const scale = display.scaleFactor || 1;
  const types = mode === 'window' ? ['window', 'screen'] : ['screen'];
  const sources = await desktopCapturer.getSources({
    types,
    thumbnailSize: {
      width: Math.floor(display.size.width * scale),
      height: Math.floor(display.size.height * scale)
    }
  });
  if (!sources.length) return null;

  let src = null;
  if (mode === 'window') {
    const windows = sources.filter(
      (s) => s.name && !OWN_APP_RE.test(s.name) &&
             s.thumbnail && !s.thumbnail.isEmpty()
    );
    src = windows[0] || null;
  }
  if (!src) {
    src = sources.find((s) => String(s.display_id) === String(display.id)) ||
          sources.find((s) => s.thumbnail && !s.thumbnail.isEmpty()) ||
          sources[0];
  }
  let img = src && src.thumbnail;
  if (!img || img.isEmpty()) return null;
  if (img.getSize().width > MAX_WIDTH) img = img.resize({ width: MAX_WIDTH });
  return 'data:image/jpeg;base64,' + img.toJPEG(JPEG_QUALITY);
}

module.exports = { captureScreenshot };
