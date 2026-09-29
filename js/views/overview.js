import { escapeHtml } from '../utils/format.js';
import { card, daysSince, diskBars, formatUptime, formatWhen, healthRows, systemGauges } from '../components/widgets.js';
import { getJson, post } from '../services/api.js';

let digestCache = null; // loaded once per page load; refreshed after "Generate now"

/** Home screen: one card per area, each leading to its detailed view. */
export function renderOverview(root, state, { recent = null, lastVisit = 0 } = {}) {
  const { system, health, events, tuneup, network } = state;
  root.innerHTML = `
    ${state.meta.livingLook ? '<div id="living-core-mount"></div>' : `
    <header class="view-head">
      <h1>Overview</h1>
      <p class="dim">${escapeHtml(system.hostname || 'This PC')} · ${escapeHtml(system.os || '')}</p>
    </header>`}
    <div class="cards">
      ${recent ? card('Since your last visit', recentBody(recent, lastVisit), { go: 'timeline', wide: true }) : ''}
      ${card('This PC', pcBody(system), { go: 'performance' })}
      ${card('Windows protection', healthRows(health), { go: 'security' })}
      ${card('Network', networkBody(network, state.meta), { go: 'network' })}
      ${card('Stability', stabilityBody(events), { go: 'events' })}
      ${card('Tune-up', tuneupBody(tuneup), { go: 'tuneup' })}
      ${card('Storage', diskBars(system.disks), { go: 'tuneup' })}
      ${card('Busiest programs', programsBody(system), { go: 'performance' })}
      <article class="card card--wide" id="digest-card">${digestBody(digestCache)}</article>
    </div>`;
  if (digestCache === null) loadDigest(root);
  root.querySelector('[data-digest-generate]')?.addEventListener('click', () => generateDigest(root));
}

async function loadDigest(root) {
  try {
    digestCache = await getJson('/api/digest');
  } catch {
    digestCache = { digest: null, due: false };
  }
  const el = root.querySelector('#digest-card');
  if (el) el.innerHTML = digestBody(digestCache);
  root.querySelector('[data-digest-generate]')?.addEventListener('click', () => generateDigest(root));
}

async function generateDigest(root) {
  const btn = root.querySelector('[data-digest-generate]');
  if (btn) {
    btn.disabled = true;
    btn.textContent = 'Writing… (can take a minute)';
  }
  try {
    const result = await post('/api/digest', { action: 'generate' });
    digestCache = { digest: { text: result.text, ts: Date.now() / 1000 }, due: false };
  } catch (err) {
    digestCache = { digest: digestCache?.digest || null, due: true, error: err.message };
  }
  const el = root.querySelector('#digest-card');
  if (el) el.innerHTML = digestBody(digestCache);
  root.querySelector('[data-digest-generate]')?.addEventListener('click', () => generateDigest(root));
}

function digestBody(data) {
  const head = '<header class="card-head"><h3>Weekly digest</h3></header>';
  if (data === null) return `${head}<p class="empty">Loading…</p>`;
  const btn = '<button class="btn btn--ghost btn--small" type="button" data-digest-generate>Generate now</button>';
  if (data.error) return `${head}<p class="empty">${escapeHtml(data.error)}</p>${btn}`;
  if (!data.digest) {
    return `${head}<p class="empty">Once a week, the local AI reads what happened and writes a short summary here. Nothing yet.</p>${btn}`;
  }
  return `${head}
    <p class="dim">${formatWhen(new Date(data.digest.ts * 1000).toISOString())}</p>
    <p class="digest-text">${escapeHtml(data.digest.text)}</p>
    ${btn}
    <button class="link-btn speak-btn" type="button" data-speak="${escapeHtml(data.digest.text)}" data-voice="argus" title="Read aloud">🔊 Read aloud</button>`;
}

function pcBody(system) {
  if (!system.available) return '<p class="empty">Live vitals need psutil. Run "Install or Update Matrix" again.</p>';
  return `
    ${systemGauges(system)}
    <div class="facts">
      <div><span>Uptime</span><strong>${formatUptime(system.uptimeSeconds)}</strong></div>
      ${system.battery ? `<div><span>Battery</span><strong>${system.battery.percent}%${system.battery.plugged ? ' ⚡' : ''}</strong></div>` : ''}
      <div><span>Processor</span><strong class="truncate">${escapeHtml((system.cpuName || '').replace(/ with .*/, ''))}</strong></div>
    </div>`;
}

function networkBody(network, meta) {
  const away = !!(network.awayFromHome ?? meta.awayFromHome);
  if (away) {
    return `<p class="hint">Away from home -- Matrix isn't reading or listing other devices on this network, only watching this PC.</p>`;
  }
  const nodes = network.nodes.filter((n) => n.id !== 'internet' && !n.ignored);
  const online = nodes.filter((n) => n.status === 'online').length;
  const internet = network.nodes.find((n) => n.id === 'internet');
  const fresh = nodes.filter((n) => n.alerts.some((a) => a.kind === 'new-device'));
  return `
    <div class="big-stats">
      <div><strong>${online}</strong><span>devices online</span></div>
      <div class="${fresh.length ? 'warn-text' : ''}"><strong>${fresh.length}</strong><span>${meta.baselineAt ? 'new since trusted' : 'unrecognized'}</span></div>
      <div class="${internet?.status === 'online' ? 'ok-text' : 'bad-text'}"><strong>${internet?.status === 'online' ? '✓' : '✕'}</strong><span>internet</span></div>
    </div>
    ${fresh.length ? `<p class="hint">${fresh.slice(0, 3).map((n) => escapeHtml(n.name)).join(', ')}${fresh.length > 3 ? '…' : ''}</p>` : ''}`;
}

function stabilityBody(events) {
  if (!events.supported) return '<p class="empty">Event logs are read on Windows only.</p>';
  if (!events.checkedAt) return '<p class="empty">Reading Windows event logs…</p>';
  const crashes = events.crashes || [];
  const week = crashes.filter((c) => daysSince(c.time) <= 7).length;
  const apps = (events.apps || []).reduce((sum, a) => sum + a.crashes + a.hangs, 0);
  const latest = crashes[0];
  return `
    <div class="big-stats">
      <div class="${week ? 'bad-text' : 'ok-text'}"><strong>${week}</strong><span>crashes this week</span></div>
      <div><strong>${crashes.length}</strong><span>in 30 days</span></div>
      <div class="${apps ? 'warn-text' : ''}"><strong>${apps}</strong><span>app crashes (14d)</span></div>
    </div>
    <p class="hint">${latest ? `Last: ${escapeHtml(latest.title)} · ${formatWhen(latest.time)}` : 'No crashes or unexpected shutdowns in 30 days.'}</p>`;
}

function tuneupBody(t) {
  if (!t.supported) return '<p class="empty">Tune-up checks run on Windows only.</p>';
  if (!t.checked) return '<p class="empty">Looking through apps and settings…</p>';
  const enabled = (t.startup || []).filter((s) => s.enabled).length;
  return `
    <div class="big-stats">
      <div class="${enabled > 8 ? 'warn-text' : ''}"><strong>${enabled}</strong><span>startup apps</span></div>
      <div class="${t.flagged?.length ? 'warn-text' : ''}"><strong>${t.flagged?.length ?? 0}</strong><span>preinstalled extras</span></div>
      <div><strong>${((t.tempMb || 0) / 1000).toFixed(1)}</strong><span>GB temp files</span></div>
    </div>`;
}

function programsBody(system) {
  const rows = (system.processes || []).slice(0, 5);
  if (!rows.length) return '<p class="empty">No data yet.</p>';
  return `
    <table class="proc-table">
      <tbody>${rows.map((p) => `
        <tr><td>${escapeHtml(p.name)}</td><td class="num">${p.cpu.toFixed(1)}%</td>
            <td class="num">${p.memMb >= 1000 ? `${(p.memMb / 1000).toFixed(1)} GB` : `${p.memMb} MB`}</td></tr>`).join('')}
      </tbody>
    </table>`;
}

const RECENT_ICONS = {
  alert: '!', resolved: '✓', crash: '✕', repair: '⚙', device: '◉', ai: '✦', trusted: '✓',
  changes: '↕', mode: '⚡', digest: '✦',
};

function recentBody(items, lastVisit) {
  const shown = items.filter((i) => RECENT_ICONS[i.kind]).slice(0, 6);
  const when = lastVisit ? new Date(lastVisit * 1000).toLocaleString([], { weekday: 'short', hour: 'numeric', minute: '2-digit' }) : '';
  if (!shown.length) return `<p class="empty">Nothing new since ${escapeHtml(when)}. Matrix kept watching.</p>`;
  return `
    <ul class="recent">${shown.map((i) => `
      <li class="recent--${i.kind}">
        <span class="recent-icon" aria-hidden="true">${RECENT_ICONS[i.kind]}</span>
        <span>${escapeHtml(i.title)}</span>
        <span class="dim">${new Date(i.ts * 1000).toLocaleString([], { weekday: 'short', hour: 'numeric', minute: '2-digit' })}</span>
      </li>`).join('')}
    </ul>
    ${items.length > shown.length ? `<p class="hint">and ${items.length - shown.length} more in the Timeline.</p>` : ''}`;
}
