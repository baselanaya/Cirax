// Context engine — builds prompt-ready context from raw state.
// Separates raw capture (audio buffers, screen URL) from normalized context
// (rolling transcript window, profile, memory) from LLM prompt construction.

const { MODES } = require('./prompts');

// Context budget: a runaway transcript is the #1 silent cost driver in a
// always-on copilot. Per-turn truncation keeps one loud speaker from eating
// the window; the total cap bounds every prompt no matter what.
const MAX_TURN_CHARS = 1200;
const MAX_TRANSCRIPT_CHARS = 8000;
const MAX_MEMORY_ITEMS = 10;

function truncate(text, max) {
  const t = String(text || '');
  return t.length <= max ? t : t.slice(0, max) + '…';
}

// Build the normalized context object. Pure, so it is unit-testable.
// state = { transcript: [{channel, text, ts}], userText, settings, memory }
function buildContext(state) {
  const { transcript = [], userText = '', settings = {} } = state;
  const capped = transcript.slice(-60).map((turn) => ({
    ...turn,
    text: truncate(turn.text, MAX_TURN_CHARS)
  }));
  // Keep the newest turns that fit the total character budget.
  let kept = [];
  let used = 0;
  for (let i = capped.length - 1; i >= 0; i--) {
    const len = capped[i].text.length;
    if (used + len > MAX_TRANSCRIPT_CHARS && kept.length) break;
    used += len;
    kept.unshift(capped[i]);
  }
  const rt = getRecent(kept, 12);
  return {
    transcript: kept,
    recent: rt,
    userText: truncate(userText, 4000),
    profile: settings.context || '',
    smart: !!settings.smart,
    memory: (state.memory || []).slice(-MAX_MEMORY_ITEMS)
  };
}

// Rolling transcript window: newest N turns, oldest first.
function getRecent(turns, n) {
  return turns.slice(-n);
}

// Compose the system prompt for a mode, weaving in profile/memory.
function buildSystem(def, ctx) {
  let system = typeof def.buildSystem === 'function' ? def.buildSystem('') : (def.system || '');
  if (ctx.profile && ['assist', 'say', 'ask'].includes(def.key)) {
    system = 'Here is my background and experience. Weave it into my answer naturally. Name the projects, the tech, the results. This keeps my answer real instead of generic.\n\n---\n' + ctx.profile + '\n---\n\n' + system;
  }
  return system;
}

// Build the user turn for a mode. Reuses MODES[].build but passes normalized context.
function buildUserTurn(def, ctx) {
  return def.build({ transcript: ctx.recent, userText: ctx.userText, memory: ctx.memory });
}

// How much of the conversation to include per mode (turns).
const MODE_WINDOW = { assist: 12, say: 14, followup: 20, recap: 0, ask: 12, leetcode: 0 };

function windowFor(mode) {
  const n = MODE_WINDOW[mode];
  return n == null ? 12 : n;
}

module.exports = { buildContext, getRecent, buildSystem, buildUserTurn, windowFor };