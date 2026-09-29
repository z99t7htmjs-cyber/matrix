import { getDeviceType, TYPE_GROUPS } from '../data/deviceTypes.js';
import { getAlertLesson } from '../data/alertLibrary.js';
import { escapeHtml, formatInline, formatRate, formatRelativeTime } from '../utils/format.js';
import { sortAlerts, normalizeSeverity, isSecurityAlert } from '../utils/alerts.js';
import { getJson, post } from '../services/api.js';

/**
 * Side panel showing everything known about one device, plus a form to name it.
 *
 * The panel refreshes with every live update, but the form is kept separate
 * and only redrawn when you pick a different device (or after saving), so
 * live updates never wipe out what you're typing.
 */
export class DetailsPanel {
  constructor(root, { onClose, onSaved }) {
    this.root = root;
    this.onSaved = onSaved;
    this.nodeId = null;
    this.editing = false; // true once the user has typed in the form
    this.openLessons = new Set(); // "Learn more" sections kept open across refreshes

    root.innerHTML = '<div data-part="top"></div><div data-part="identify"></div><div data-part="form"></div><div data-part="rest"></div>';
    this.parts = {
      top: root.querySelector('[data-part="top"]'),
      identify: root.querySelector('[data-part="identify"]'),
      form: root.querySelector('[data-part="form"]'),
      rest: root.querySelector('[data-part="rest"]'),
    };
    this.id = {}; // Identify results and history for the device showing

    // Delegated listeners survive every re-render.
    root.addEventListener('click', (e) => {
      const action = e.target.closest('[data-action]')?.dataset.action;
      if (action === 'close') onClose();
      if (action === 'forget') this.save({ action: 'forget' });
      if (action === 'ignore') this.save({ action: 'ignore', name: this.node.name, type: this.node.type });
      if (action === 'unignore') this.save({ action: 'unignore' });
      if (action === 'identify') this.identify();
      if (action === 'use-identity') this.useIdentity();
      if (action === 'edit' || action === 'cancel-edit') {
        this.expanded = action === 'edit';
        this.drawForm();
        this.parts.form.querySelector('input[name=name]')?.focus();
      }
    });
    root.addEventListener('input', () => (this.editing = true));
    root.addEventListener('submit', (e) => {
      e.preventDefault();
      const form = new FormData(e.target);
      this.save({ name: form.get('name'), type: form.get('type') });
    });
    // "toggle" doesn't bubble, so listen during the capture phase.
    root.addEventListener(
      'toggle',
      (e) => {
        const id = e.target.dataset?.alertId;
        if (!id) return;
        if (e.target.open) this.openLessons.add(id);
        else this.openLessons.delete(id);
      },
      true,
    );
  }

  show(node) {
    const switched = node.id !== this.nodeId;
    if (switched) {
      this.expanded = false;
      this.id = { nodeId: node.id };
      this.loadPresence(node);
    }
    this.nodeId = node.id;
    this.node = node;
    this.parts.top.innerHTML = renderTop(node);
    this.drawIdentify();
    this.parts.rest.innerHTML = renderRest(node, this.openLessons);

    // Redraw the form only when you pick another device, or when its saved
    // name/type actually changed, and never while you're using it (typing,
    // or with the Type dropdown open).
    const formKey = [node.id, node.name, node.type, node.saved, node.ignored].join('|');
    const inUse = this.editing || this.parts.form.contains(document.activeElement);
    if (switched || (!inUse && formKey !== this.formKey)) {
      this.formKey = formKey;
      this.drawForm();
    }
    this.root.hidden = false;
  }

  drawForm() {
    this.editing = false;
    this.parts.form.innerHTML = renderForm(this.node, this.expanded);
  }

  // --- Identify ----------------------------------------------------------------

  async loadPresence(node) {
    if (!node.mac || node.id === 'this-pc') return;
    try {
      const data = await getJson(`/api/device?mac=${encodeURIComponent(node.mac)}`);
      if (this.id.nodeId !== node.id) return;
      this.id.history = data;
      this.drawIdentify();
    } catch {
      // history is a bonus; ignore failures
    }
  }

  async identify() {
    const nodeId = this.node.id;
    this.id = { ...this.id, loading: true, error: null };
    this.drawIdentify();
    try {
      const result = await post('/api/identify', { mac: this.node.mac });
      if (this.id.nodeId !== nodeId) return;
      this.id = { ...this.id, loading: false, result };
    } catch (err) {
      this.id = { ...this.id, loading: false, error: err.message };
    }
    this.drawIdentify();
  }

  /** Put Identify's suggested name and type into the naming form, ready to save. */
  useIdentity() {
    const r = this.id.result;
    this.expanded = true;
    this.drawForm();
    const form = this.parts.form;
    if (r.suggestedName) form.querySelector('input[name=name]').value = r.suggestedName;
    const select = form.querySelector('select[name=type]');
    if (select && r.suggestedType && r.suggestedType !== 'unknown') select.value = r.suggestedType;
    this.editing = true;
    form.querySelector('input[name=name]')?.focus();
  }

  drawIdentify() {
    this.parts.identify.innerHTML = renderIdentify(this.node, this.id);
  }

  hide() {
    this.nodeId = null;
    this.editing = false;
    this.root.hidden = true;
  }

  /** Send a save, forget or ignore request to the Matrix server. */
  async save(body) {
    const status = this.parts.form.querySelector('.form-status');
    const setStatus = (text, tone = '') => {
      if (!status) return;
      status.textContent = text;
      status.dataset.tone = tone;
    };
    setStatus('Saving…');
    try {
      const response = await fetch('/api/devices', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ mac: this.node.mac, ...body }),
      });
      const result = await response.json();
      if (!result.ok) throw new Error(result.error || 'Save failed.');
      setStatus({ forget: 'Forgotten', ignore: 'Ignored', unignore: 'No longer ignored' }[body.action] || 'Saved ✓', 'ok');
      this.editing = false; // let the next update redraw the form with the saved values
      this.expanded = false; // once saved, collapse back to the one-line summary
      document.activeElement?.blur();
      this.onSaved?.();
    } catch (err) {
      setStatus(err.message || 'Could not reach the Matrix server.', 'error');
    }
  }
}

// --- templates ---------------------------------------------------------------

function renderIdentify(node, id) {
  if (!node.mac || node.id === 'this-pc' || node.type === 'router') return '';
  const h = id.history;
  const first = h?.device?.first_seen ? new Date(h.device.first_seen * 1000).toLocaleDateString([], { month: 'short', day: 'numeric', year: 'numeric' }) : null;
  const p = h?.presence;
  const seen = first ? `
    <dl class="kv kv--compact">
      <dt>First seen</dt><dd>${escapeHtml(first)}</dd>
      ${p?.alwaysOn ? '<dt>Online</dt><dd>Almost always (like a TV, speaker or smart plug)</dd>'
        : p?.usualHours ? `<dt>Usually online</dt><dd>${escapeHtml(p.usualHours)}${p.busiestDay ? ` · most on ${p.busiestDay}` : ''}</dd>` : ''}
    </dl>` : '';

  let body = '';
  if (id.loading) body = '<p class="dim">Checking… (a few seconds)</p>';
  else if (id.error) body = `<p class="bad-text">${escapeHtml(id.error)}</p>`;
  else if (id.result) {
    const r = id.result;
    body = `
      ${r.findings.length ? `<ul class="findings">${r.findings.map((f) => `<li><strong>${escapeHtml(f.clue)}</strong><span class="dim">${escapeHtml(f.why)}</span></li>`).join('')}</ul>` : ''}
      ${r.summary ? `<p class="hint">${escapeHtml(r.summary)}</p>` : ''}
      ${(r.suggestedName || (r.suggestedType && r.suggestedType !== 'unknown'))
        ? `<p>Best guess: <strong>${escapeHtml([r.suggestedName, r.suggestedType && r.suggestedType !== 'unknown' ? getDeviceType(r.suggestedType).label : null].filter(Boolean).join(' · '))}</strong>
             <button class="btn btn--ghost btn--small" type="button" data-action="use-identity">Use this</button></p>` : ''}`;
  }

  return `
    <section class="panel-section">
      <h3>Identify</h3>
      ${seen}
      ${body || `<p class="hint">Runs a few quick, harmless checks on this one device (its network name and whether it answers
        like an iPhone, Chromecast, printer, Windows PC…). Takes a few seconds.</p>`}
      ${node.status === 'online' && !id.loading ? `<button class="btn btn--ghost btn--small" type="button" data-action="identify">${id.result ? 'Check again' : 'Identify this device'}</button>`
        : node.status !== 'online' ? '<p class="dim">Offline right now, so it can\'t be checked.</p>' : ''}
    </section>`;
}

function renderTop(node) {
  const type = getDeviceType(node.type);
  const online = node.status === 'online';

  // Optional identity fields only appear when the server provides them.
  const optionalRows = [
    ['Hostname', node.hostname],
    ['MAC address', node.mac],
    ['Manufacturer', node.vendor],
  ]
    .filter(([, value]) => value)
    .map(([label, value]) => `<dt>${label}</dt><dd class="mono">${escapeHtml(value)}</dd>`)
    .join('');

  return `
    <header class="panel-header">
      <div class="panel-glyph">${escapeHtml(type.glyph)}</div>
      <div class="panel-title">
        <h2>${escapeHtml(node.name)}</h2>
        <p class="mono">${escapeHtml(node.id)}</p>
      </div>
      <button class="panel-close" type="button" data-action="close" aria-label="Close details">×</button>
    </header>

    <section class="panel-section">
      <dl class="kv">
        <dt>Status</dt>
        <dd><span class="status-pill status-pill--${online ? 'online' : 'offline'}">${online ? 'online' : 'offline'}</span></dd>
        <dt>Device type</dt>
        <dd>${escapeHtml(type.label)}${node.known ? '' : ' <span class="dim">(guess)</span>'}</dd>
        <dt>Identity</dt>
        <dd>${node.ignored ? '<span class="dim">Ignored</span>' : node.known ? '<span class="ok-text">Confirmed</span>' : '<span class="warn-text">Not confirmed</span>'}</dd>
        <dt>IP address</dt>
        <dd class="mono">${node.ip ? escapeHtml(node.ip) : '<span class="empty">Not known</span>'}</dd>
        ${optionalRows}
      </dl>
    </section>`;
}

// Placeholder names the server uses when it knows nothing; don't prefill those.
const GENERIC_NAMES = new Set(['Unknown device', 'Private device', 'Known device', 'Router']);

/**
 * Naming section. Saved devices show a one-line summary with Edit / Ignore /
 * Forget; the full form appears for new devices or after pressing Edit.
 */
function renderForm(node, expanded) {
  if (!node.mac) return '';
  const fixed = node.id === 'this-pc' || node.type === 'router'; // can't be ignored or forgotten

  if (node.ignored && !expanded) {
    return `
      <section class="panel-section saved-summary">
        <p><span class="dim">⊘ Ignored</span>: hidden from the map and never alerted on.</p>
        <div class="form-actions">
          <button class="btn btn--ghost btn--small" type="button" data-action="unignore">Stop ignoring</button>
          <span class="form-status" role="status"></span>
        </div>
      </section>`;
  }

  if ((node.saved || node.known) && !expanded) {
    return `
      <section class="panel-section saved-summary">
        <p><span class="ok-text">✓ ${node.saved ? 'Saved' : 'Named automatically'}</span> as
          <strong>${escapeHtml(node.name)}</strong> · ${escapeHtml(getDeviceType(node.type).label)}</p>
        <div class="form-actions">
          <button class="btn btn--ghost btn--small" type="button" data-action="edit">${node.saved ? 'Edit' : 'Rename'}</button>
          ${fixed ? '' : '<button class="btn btn--ghost btn--small" type="button" data-action="ignore">Ignore</button>'}
          ${node.saved && !fixed ? '<button class="btn btn--ghost btn--small" type="button" data-action="forget">Forget</button>' : ''}
          <span class="form-status" role="status"></span>
        </div>
      </section>`;
  }

  const isRouter = node.type === 'router';
  const prefill = node.saved || !(GENERIC_NAMES.has(node.name) || node.name.startsWith('This PC (')) ? node.name : '';
  const typeField = isRouter
    ? '<input type="hidden" name="type" value="router">'
    : `<label class="field">
         <span>Type</span>
         <select name="type">
           ${TYPE_GROUPS.map(([group, types]) => `
             <optgroup label="${group}">
               ${types.map((t) => `<option value="${t}" ${t === node.type ? 'selected' : ''}>${escapeHtml(getDeviceType(t).label)}</option>`).join('')}
             </optgroup>`).join('')}
         </select>
       </label>`;

  return `
    <section class="panel-section">
      <h3>${node.saved ? 'Edit name & type' : 'Name this device'}</h3>
      ${node.saved || expanded ? '' : '<p class="hint">Recognize it? Give it a name and Matrix will remember it. Not yours to worry about? Ignore it.</p>'}
      <form class="name-form" autocomplete="off">
        <label class="field">
          <span>Name</span>
          <input name="name" maxlength="40" required value="${escapeHtml(prefill)}" placeholder="e.g. Living room TV">
        </label>
        ${typeField}
        <div class="form-actions">
          <button class="btn btn--primary btn--small" type="submit">Save</button>
          ${expanded ? '<button class="btn btn--ghost btn--small" type="button" data-action="cancel-edit">Cancel</button>' : ''}
          ${!expanded && !fixed ? '<button class="btn btn--ghost btn--small" type="button" data-action="ignore">Ignore</button>' : ''}
          <span class="form-status" role="status"></span>
        </div>
      </form>
    </section>`;
}

function renderRest(node, openLessons) {
  const online = node.status === 'online';
  const securityCount = node.alerts.filter(isSecurityAlert).length;
  return `
    <section class="panel-section">
      <h3>Traffic</h3>
      ${renderTraffic(node)}
    </section>

    <section class="panel-section">
      <h3>Active connections <span class="count">${node.connections.length}</span></h3>
      ${renderConnections(node.connections, online)}
    </section>

    <section class="panel-section">
      <h3>Security alerts <span class="count">${securityCount}</span></h3>
      ${renderAlerts(node.alerts, openLessons)}
    </section>`;
}

function renderTraffic(node) {
  if (!node.traffic) {
    return `<p class="empty">Not visible from this PC. A computer can only measure its own traffic;
      seeing other devices' traffic needs help from the router.</p>`;
  }
  return `
    <div class="traffic">
      <div class="traffic-tile">
        <span>↓ Inbound</span>
        <strong>${formatRate(node.traffic.inKbps)}</strong>
      </div>
      <div class="traffic-tile">
        <span>↑ Outbound</span>
        <strong>${formatRate(node.traffic.outKbps)}</strong>
      </div>
    </div>`;
}

function renderConnections(connections, online) {
  if (connections.length === 0) {
    return `<p class="empty">${online ? 'No active connections.' : 'No connections — device is offline.'}</p>`;
  }

  const rows = connections
    .map(
      (c) => `
        <tr>
          <td>${escapeHtml(c.protocol)}</td>
          <td>${escapeHtml(c.remote)}:${escapeHtml(c.port)}</td>
          <td class="conn-service">
            ${escapeHtml(c.service)}
            ${c.process ? `<span class="conn-process">${escapeHtml(c.process)}</span>` : ''}
          </td>
        </tr>`,
    )
    .join('');

  return `
    <table class="conn-table">
      <thead><tr><th>Proto</th><th>Remote</th><th>Service</th></tr></thead>
      <tbody>${rows}</tbody>
    </table>`;
}

function renderAlerts(alerts, openLessons) {
  if (alerts.length === 0) return '<p class="empty">No alerts for this device.</p>';

  const items = sortAlerts(alerts)
    .map((a) => {
      const severity = normalizeSeverity(a.severity);
      return `
        <li class="alert alert--${severity}">
          <div class="alert-head">
            <span class="sev-tag">${severity}</span>
            <span class="alert-title">${escapeHtml(a.title)}</span>
          </div>
          <p class="alert-detail">${escapeHtml(a.detail)}</p>
          <time class="alert-time" datetime="${escapeHtml(a.detectedAt)}">${formatRelativeTime(a.detectedAt)}</time>
          ${renderLesson(a, openLessons.has(a.id))}
        </li>`;
    })
    .join('');

  return `<ul class="alerts">${items}</ul>`;
}

function renderLesson(alert, isOpen) {
  const lesson = getAlertLesson(alert.kind);
  if (!lesson) return '';

  const sections = [
    ['What it is', lesson.what],
    ['Why it matters', lesson.why],
    ['How to confirm', lesson.confirm],
    ['How to fix', lesson.fix],
  ]
    .map(([label, text]) => `<dt>${label}</dt><dd>${formatInline(text)}</dd>`)
    .join('');

  return `
    <details class="alert-learn" data-alert-id="${escapeHtml(alert.id)}" ${isOpen ? 'open' : ''}>
      <summary>Learn more</summary>
      <dl class="learn">${sections}</dl>
    </details>`;
}
