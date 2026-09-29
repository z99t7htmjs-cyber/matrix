import { escapeHtml } from '../utils/format.js';
import { card, healthRows } from '../components/widgets.js';
import { sortAlerts, normalizeSeverity } from '../utils/alerts.js';

/** Security: Windows protection with buttons to fix, what this PC exposes, and who it's talking to. */
export function renderSecurity(root, state) {
  const pc = state.network.nodes.find((n) => n.id === 'this-pc');
  root.innerHTML = `
    <header class="view-head">
      <h1>Security</h1>
      <p class="dim">Windows protection, what this PC exposes to your network, and what it's connected to.</p>
    </header>
    <div class="cards">
      ${card('Windows protection', healthRows(state.health, { buttons: true }), { wide: true })}
      ${card('Exposed to your network', exposure(pc))}
      ${card('Open connections from this PC', connections(pc), { wide: true })}
    </div>`;
}

function exposure(pc) {
  const alerts = sortAlerts(pc?.alerts || []);
  if (!alerts.length) return '<p class="empty">Nothing on this PC is listening for connections from other devices.</p>';
  return `<ul class="alerts">${alerts.map((a) => `
    <li class="alert alert--${normalizeSeverity(a.severity)}">
      <div class="alert-head"><span class="sev-tag">${normalizeSeverity(a.severity)}</span>
        <span class="alert-title">${escapeHtml(a.title)}</span></div>
      <p class="alert-detail">${escapeHtml(a.detail)}</p>
    </li>`).join('')}</ul>`;
}

function connections(pc) {
  const rows = pc?.connections || [];
  if (!rows.length) return '<p class="empty">No open connections reported (connections are read on Windows only).</p>';
  return `
    <table class="data-table">
      <thead><tr><th>Program</th><th>Connected to</th><th>Service</th></tr></thead>
      <tbody>${rows.map((c) => `
        <tr>
          <td>${escapeHtml(c.process || 'unknown')}</td>
          <td class="mono">${escapeHtml(c.remote)}:${escapeHtml(c.port)}</td>
          <td class="dim">${escapeHtml(c.service)}</td>
        </tr>`).join('')}
      </tbody>
    </table>
    <p class="hint">An address you don't recognize isn't necessarily bad; apps talk to many servers. Ask Matrix about anything that looks odd.</p>`;
}
