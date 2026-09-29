/**
 * Entry point. Subscribes to the Matrix server, keeps track of which view is
 * showing, and hands each part of the live state to whatever displays it.
 *
 * Buttons anywhere on the page use data attributes, handled once here:
 *   data-go="network"              switch view
 *   data-open="windowsupdate"      open a Windows settings page (via the server)
 *   data-ask="question…"           ask the question in the Ask Matrix tab
 *   data-alert="snooze" data-key   acknowledge / snooze / keep / restore an Advisor item
 *   data-check="health" data-for   "Check again": re-run a check now
 *   data-step="sfc" data-done      mark a troubleshooting step done (or undo)
 */
import { LiveDataSource } from './services/dataService.js';
import { getJson, openWindowsPage, post } from './services/api.js';
import { DetailsPanel } from './components/detailsPanel.js';
import { AdvisorPanel } from './components/advisorPanel.js';
import { ChatPanel } from './components/chatPanel.js';
import { NetworkView } from './views/network.js';
import { SettingsView } from './views/settings.js';
import { TimelineView } from './views/timeline.js';
import { ModesView } from './views/modes.js';
import { renderOverview } from './views/overview.js';
import { renderPerformance } from './views/performance.js';
import { renderSecurity } from './views/security.js';
import { renderEvents } from './views/events.js';
import { renderTuneup } from './views/tuneup.js';
import { daysSince } from './components/widgets.js';
import { speak, voiceAvailable } from './utils/voice.js';
import { quip } from './utils/personaQuips.js';
import { LivingCore } from './components/livingCore.js';
import { LivingBackground } from './components/livingBackground.js';

const $ = (id) => document.getElementById(id);
const VIEWS = ['overview', 'network', 'performance', 'security', 'events', 'tuneup', 'modes', 'timeline', 'settings'];

let state = null;
let selectedId = null;
let currentView = null;
const busy = new Set(); // Advisor items being re-checked right now
const autoSpoken = new Set(); // critical item ids already read aloud automatically this session

// "New" badges and the "Since your last visit" card compare against the last time the window was open.
const LAST_VISIT_KEY = 'matrix.lastVisit';
const lastVisit = readNumber(LAST_VISIT_KEY) || Math.floor(Date.now() / 1000);
let recentSinceVisit = null;

const source = new LiveDataSource();
const details = new DetailsPanel($('details'), {
  onClose: () => selectNode(null),
  onSaved: () => source.refreshSoon(), // the server rescans right away; fetch the result
});
const chat = new ChatPanel($('chat'), {
  getAlerts: () => new Map((state?.advice || []).map((a) => [a.id, a.title])),
});
const advisor = new AdvisorPanel($('advisor'));
const networkView = new NetworkView($('view-network'), { onSelect: selectNode, onChanged: () => source.refreshSoon(500) });
const settingsView = new SettingsView($('view-settings'));
const timelineView = new TimelineView($('view-timeline'));
const modesView = new ModesView($('view-modes'));
const livingCore = new LivingCore();
const livingBackground = new LivingBackground();
const MOTION_PAUSED_KEY = 'matrix.motionPaused';
let motionPaused = localStorage.getItem(MOTION_PAUSED_KEY) === '1';
livingBackground.setUserPaused(motionPaused);
livingCore.setUserPaused(motionPaused);

function toggleMotionPause() {
  motionPaused = !motionPaused;
  try {
    localStorage.setItem(MOTION_PAUSED_KEY, motionPaused ? '1' : '0');
  } catch {
    // private browsing / storage disabled -- the toggle still works for this session
  }
  livingBackground.setUserPaused(motionPaused);
  livingCore.setUserPaused(motionPaused);
  document.body.classList.toggle('motion-paused', motionPaused);
}
document.body.classList.toggle('motion-paused', motionPaused);

// Views redrawn from live data (network, timeline and settings manage themselves).
const renderers = {
  overview: (root, s) => renderOverview(root, s, { recent: recentSinceVisit, lastVisit }),
  performance: renderPerformance,
  security: renderSecurity,
  events: renderEvents,
  tuneup: renderTuneup,
};

// --- navigation ------------------------------------------------------------------------

function showView(name) {
  if (!VIEWS.includes(name)) name = 'overview';
  if (name === currentView) return;
  currentView = name;
  document.querySelectorAll('.view').forEach((v) => (v.hidden = v.dataset.view !== name));
  document.querySelectorAll('.rail-item').forEach((a) => a.classList.toggle('is-active', a.dataset.view === name));
  $(`view-${name}`).scrollTop = 0;
  if (name === 'settings') settingsView.show();
  if (name === 'timeline') timelineView.show();
  if (name === 'modes') modesView.show();
  renderView();
}

window.addEventListener('hashchange', () => showView(location.hash.slice(1)));

/** Right column tabs: Advisor or Ask Matrix. */
function showTab(name) {
  selectNode(null); // close device details so the tab is visible
  document.querySelectorAll('.tab').forEach((t) => t.classList.toggle('is-active', t.dataset.tab === name));
  $('advisor').hidden = name !== 'advisor';
  $('chat').hidden = name !== 'chat';
  if (name === 'chat') chat.focus();
}
document.querySelectorAll('.tab').forEach((t) => t.addEventListener('click', () => showTab(t.dataset.tab)));

/** Clicking the selected device again deselects it. */
function selectNode(id) {
  selectedId = id === null || id === selectedId ? null : id;
  if (selectedId && currentView !== 'network') location.hash = 'network';
  renderDetails();
  if (state) networkView.render(state, selectedId);
}

// --- buttons anywhere on the page -------------------------------------------------------

document.addEventListener('click', async (e) => {
  const el = (sel) => e.target.closest(sel);
  const go = el('[data-go]');
  const open = el('[data-open]');
  const ask = el('[data-ask]');
  const alertBtn = el('[data-alert]');
  const check = el('[data-check]');
  const step = el('[data-step]');
  const tool = el('[data-tool]');
  const speakBtn = el('[data-speak]');
  const motionToggle = el('[data-motion-toggle]');

  if (motionToggle) {
    e.stopPropagation();
    toggleMotionPause();
  } else if (speakBtn) {
    speak(speakBtn.dataset.speak, speakBtn.dataset.voice);
  } else if (open) {
    e.stopPropagation();
    run(() => openWindowsPage(open.dataset.open), 'Opened in Windows');
  } else if (alertBtn) {
    const { alert: action, key, days } = alertBtn.dataset;
    const personaOn = state?.meta?.personaEnabled;
    const done = action === 'snooze' && personaOn ? quip('snoozed')
      : { snooze: `Snoozed for ${days === '1' ? 'a day' : `${days} days`}`, keep: 'Kept as is', acknowledge: 'Marked as seen', restore: 'Brought back' }[action];
    run(() => post('/api/alerts', { key, action, days: days ? Number(days) : undefined }), done, true);
  } else if (check) {
    const { check: target, for: id } = check.dataset;
    busy.add(id);
    renderAdvisor();
    await run(() => post('/api/check', { target }), null, true);
    busy.delete(id);
    const stillThere = state?.advice.some((a) => a.id === id);
    const personaOn = state?.meta?.personaEnabled;
    const text = personaOn ? quip(stillThere ? 'checkStill' : 'checkResolved')
      : (stillThere ? 'Checked: still needs attention' : 'Checked: resolved ✓');
    toast(text, stillThere);
    renderAdvisor();
  } else if (step) {
    const done = step.dataset.done === '1';
    run(() => post('/api/plan', { step: step.dataset.step, done }), done ? 'Step marked done' : 'Step unmarked', true);
  } else if (tool) {
    if (tool.dataset.tool === 'screenshot') run(() => post('/api/screenshot', {}), 'Screenshot copied. Paste it with Ctrl+V');
    if (tool.dataset.tool === 'diagnostics') copyDiagnostics();
  } else if (ask) {
    showTab('chat');
    chat.ask(ask.dataset.ask);
  } else if (go) {
    location.hash = go.dataset.go;
  }
});

// Cards and table rows act as buttons: Enter or Space opens them too.
document.addEventListener('keydown', (e) => {
  if ((e.key === 'Enter' || e.key === ' ') && e.target.matches('[data-go][role="button"], tr[data-node]')) {
    e.preventDefault();
    e.target.click();
  }
  if (e.key === 'Escape' && selectedId) selectNode(null);
});

/** Run a server action, show a notice, and refresh the data if it changed something. */
async function run(action, successText, refresh = false) {
  try {
    await action();
    if (successText) toast(successText);
    if (refresh) await refreshNow();
  } catch (err) {
    toast(err.message, true);
  }
}

async function refreshNow() {
  try {
    onState(await getJson('/api/state'));
  } catch {
    // the regular poll will catch up
  }
}

async function copyDiagnostics() {
  try {
    const { text } = await getJson('/api/diagnostics');
    await navigator.clipboard.writeText(text);
    toast('Diagnostics copied. Paste them into a chat with Ctrl+V');
  } catch (err) {
    toast(`Couldn't copy diagnostics: ${err.message}`, true);
  }
}

// --- live data ------------------------------------------------------------------------

function onState(next) {
  $('offline').hidden = next !== null;
  if (!next) {
    setStatus('offline', 'Link lost');
    $('footer-status').textContent = 'Matrix is not running';
    return;
  }
  state = next;
  window.__matrixState = state; // lets views that load extra data redraw with the latest state
  renderView();
  renderDetails();
  renderAdvisor();
  renderHeader();
  autoSpeakCritical();
}

/** Read a new critical item aloud once, if the setting's on. Never repeats an item. */
function autoSpeakCritical() {
  if (!state?.meta?.autoVoiceEnabled || !voiceAvailable()) return;
  for (const a of state.advice) {
    if (a.urgency === 'critical' && !autoSpoken.has(a.id)) {
      autoSpoken.add(a.id);
      speak(a.personaLine ? `${a.personaLine} ${a.detail}` : `${a.title}. ${a.detail}`, a.persona || 'argus');
      break; // one at a time
    }
  }
}

function renderAdvisor() {
  if (!state) return;
  advisor.render(
    { advice: state.advice, handled: state.handled || [], resolved: state.resolved || [], plans: state.plans || {} },
    { busy, lastVisit },
  );
}

function renderView() {
  if (!state) return;
  if (currentView === 'network') networkView.render(state, selectedId);
  const render = renderers[currentView];
  if (!render) return;
  const view = $(`view-${currentView}`);
  const scroll = view.scrollTop;
  render(view, state);
  // Every poll rebuilds this view's HTML from scratch (render() above is a full
  // root.innerHTML replace, not a diff), including a fresh, empty #living-core-mount
  // div. Restoring scrollTop has to happen *after* the Living Look scene is actually
  // reinserted into it below, not before -- the empty placeholder and the mounted
  // scene (a tall canvas) have different heights, and restoring scroll while it was
  // still the empty placeholder let the browser's own scroll-anchoring shove the
  // page around a moment later when the real content popped in.
  if (currentView === 'overview' && state.meta.livingLook) {
    const mount = view.querySelector('#living-core-mount');
    if (mount) {
      livingCore.mount(mount);
      livingCore.update(state, { recent: recentSinceVisit || [], lastVisit });
      livingBackground.setFocusEl(livingCore.canvas);
    }
  } else {
    livingBackground.setFocusEl(null);
  }
  view.scrollTop = scroll; // live updates shouldn't jump the page back to the top
}

function renderDetails() {
  const node = state?.network.nodes.find((n) => n.id === selectedId);
  if (node) {
    details.show(node);
  } else {
    selectedId = null;
    details.hide();
  }
}

function setStatus(level, text) {
  $('status-line').dataset.level = level;
  $('status-text').textContent = text;
}

function renderHeader() {
  const nodes = state.network.nodes.filter((n) => !n.ignored);
  const online = nodes.filter((n) => n.status === 'online').length;
  const critical = state.advice.filter((a) => a.urgency === 'critical');
  const attention = state.advice.filter((a) => a.urgency === 'attention');
  const count = critical.length + attention.length; // FYI items don't count as "needs attention"

  $('stat-online').textContent = `${online} / ${nodes.length}`; // "N / total devices online"
  $('stat-advice').textContent = count;
  $('advisor-count').textContent = count;
  $('stat-advice').classList.toggle('is-warning', count > 0);
  document.body.classList.toggle('has-critical', critical.length > 0);

  if (critical.length) setStatus('critical', critical.length === 1 ? critical[0].title : `${critical.length} critical items`);
  else if (attention.length) setStatus('warn', `${attention.length} item${attention.length > 1 ? 's' : ''} to look at`);
  else setStatus('ok', 'All systems nominal');

  livingBackground.setCritical(critical.length > 0);
  const gpuBusy = (state.system.gpus || []).some((g) => (g.usage || 0) > 85);
  livingBackground.setThrottled(gpuBusy);
  livingCore.setThrottled(gpuBusy);
  renderMeters(state.system);

  // Small counters on the side menu
  const fresh = nodes.filter((n) => n.alerts.some((a) => a.kind === 'new-device')).length;
  setBadge('badge-network', fresh);
  const crashes = state.plans?.crashes?.state === 'active' ? state.plans.crashes.counted.length : 0;
  setBadge('badge-events', crashes);

  const vendor = { loading: 'loading maker list', ready: 'maker lookup on', unavailable: 'maker lookup unavailable' };
  $('footer-status').textContent = `● Live · ${state.system.hostname || 'this PC'} · ${vendor[state.meta.vendorDb] || ''}`;
  $('footer-version').textContent = `Matrix ${state.meta.version}`;
}

function setBadge(id, count) {
  $(id).hidden = !count;
  $(id).textContent = count;
}

/** The rail's thin glowing meter bars: CPU / GPU / GPU temp / Memory / Disk. */
function setMeter(key, text, pct, tone) {
  const val = $(`m-${key}`);
  const bar = $(`bar-${key}`);
  if (!val || !bar) return;
  val.textContent = text;
  bar.classList.toggle('warn', tone === 'warn');
  bar.classList.toggle('crit', tone === 'crit');
  bar.querySelector('i').style.width = `${Math.max(0, Math.min(100, pct ?? 0))}%`;
}

function renderMeters(system) {
  // `available` only means "psutil imported OK" -- for a second or two right after Matrix
  // starts (and for as long as a sample keeps failing server-side), the server can report
  // available:true with none of the per-field data sampled yet, so every field below is
  // read defensively instead of assumed to exist just because `available` is true. This
  // used to read system.cpu.usage directly, which threw the moment cpu was still missing --
  // and because this whole call happens inside the state-poll listener, that one throw
  // killed the polling loop for good (see LiveDataSource.poll() below), not just this frame.
  if (!system.available) {
    ['cpu', 'gpu', 'temp', 'mem', 'disk'].forEach((k) => setMeter(k, 'n/a', 0));
    return;
  }
  const cpu = system.cpu?.usage;
  setMeter('cpu', cpu != null ? `${Math.round(cpu)}%` : 'n/a', cpu, cpu > 90 ? 'warn' : null);
  const gpu = system.gpus?.[0];
  $('m-gpu-label').textContent = gpu ? `GPU · ${gpu.name.replace(/^NVIDIA GeForce /, '')}` : 'GPU';
  setMeter('gpu', gpu ? `${Math.round(gpu.usage)}%` : 'n/a', gpu?.usage);
  setMeter('temp', gpu ? `${Math.round(gpu.tempC)}°C` : 'n/a', gpu ? (gpu.tempC / 100) * 100 : 0, gpu?.tempC > 80 ? 'crit' : gpu?.tempC > 70 ? 'warn' : null);
  const mem = system.memory?.usage;
  setMeter('mem', mem != null ? `${Math.round(mem)}%` : 'n/a', mem, mem > 90 ? 'warn' : null);
  const disk = system.disks?.[0];
  setMeter('disk', disk ? `${disk.usedPercent}%` : 'n/a', disk?.usedPercent, disk?.usedPercent > 90 ? 'warn' : null);
}

let toastTimer;
function toast(text, isError = false) {
  const el = $('toast');
  el.textContent = text;
  el.dataset.tone = isError ? 'error' : 'ok';
  el.hidden = false;
  clearTimeout(toastTimer);
  toastTimer = setTimeout(() => (el.hidden = true), 3000);
}

function startClock() {
  const tick = () => {
    const now = new Date();
    $('clock-time').textContent = now.toLocaleTimeString([], { hour12: false });
    $('clock-date').textContent = now.toLocaleDateString([], { weekday: 'short', month: 'short', day: 'numeric' });
  };
  tick();
  setInterval(tick, 1000);
}

// --- "since your last visit" ---------------------------------------------------------------

async function loadRecent() {
  try {
    recentSinceVisit = (await getJson(`/api/timeline?since=${lastVisit}&limit=50`)).items;
  } catch {
    recentSinceVisit = null;
  }
  if (currentView === 'overview') renderView();
}

// Remember this visit (after a minute, so a quick glance doesn't wipe the "new" markers).
setTimeout(() => writeNumber(LAST_VISIT_KEY, Math.floor(Date.now() / 1000)), 60000);
window.addEventListener('pagehide', () => writeNumber(LAST_VISIT_KEY, Math.floor(Date.now() / 1000)));

function readNumber(key) {
  try {
    return Number(localStorage.getItem(key)) || 0;
  } catch {
    return 0;
  }
}

function writeNumber(key, value) {
  try {
    localStorage.setItem(key, String(value));
  } catch {
    // storage unavailable; "new" markers just won't carry over
  }
}

document.body.classList.toggle('no-voice', !voiceAvailable());

// Scrollbar only shows while actually scrolling (css/styles.css fades the thumb in/out
// off this class) -- 'scroll' doesn't bubble, so this has to listen in the capture phase
// to catch it firing on any of the inner scrollable views, not just window-level scroll.
let scrollHideTimer;
document.addEventListener('scroll', () => {
  document.body.classList.add('is-scrolling');
  clearTimeout(scrollHideTimer);
  scrollHideTimer = setTimeout(() => document.body.classList.remove('is-scrolling'), 900);
}, true);

startClock();
showView(location.hash.slice(1) || 'overview');
source.subscribe(onState);
loadRecent();
