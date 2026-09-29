import { escapeHtml } from '../utils/format.js';

/**
 * Reusable pieces shared by several views: ring gauges, bars, line charts,
 * status rows and cards. Each returns an HTML string.
 */

// --- small formatters ----------------------------------------------------------------

export function formatUptime(seconds) {
  if (seconds == null) return '—';
  const d = Math.floor(seconds / 86400);
  const h = Math.floor((seconds % 86400) / 3600);
  const m = Math.floor((seconds % 3600) / 60);
  return d ? `${d}d ${h}h` : `${h}h ${m}m`;
}

export function daysSince(iso) {
  return Math.floor((Date.now() - new Date(iso).getTime()) / 86400000);
}

export function formatWhen(iso) {
  if (!iso) return '—';
  const date = new Date(iso);
  const days = daysSince(iso);
  const time = date.toLocaleTimeString([], { hour: 'numeric', minute: '2-digit' });
  if (days === 0) return `Today ${time}`;
  if (days === 1) return `Yesterday ${time}`;
  return `${date.toLocaleDateString([], { month: 'short', day: 'numeric' })} ${time}`;
}

export function formatMb(mb) {
  if (mb == null) return '—';
  return mb >= 1000 ? `${(mb / 1000).toFixed(1)} GB` : `${Math.round(mb)} MB`;
}

/** 'ok' below warn, 'warn' below danger, 'danger' above; 'idle' when there's no value. */
export function level(value, warn = 70, danger = 90) {
  if (value == null) return 'idle';
  if (value >= danger) return 'danger';
  if (value >= warn) return 'warn';
  return 'ok';
}

// --- gauges and bars -------------------------------------------------------------------

const RING_R = 30;
const RING_C = 2 * Math.PI * RING_R;

export function ring(label, value, { unit = '%', max = 100, warn, danger, sub = '' } = {}) {
  const pct = value == null ? 0 : Math.min(value / max, 1);
  const shown = value == null ? '—' : `${Math.round(value)}${unit}`;
  return `
    <div class="gauge gauge--${level(value == null ? null : (value / max) * 100, warn, danger)}">
      <svg viewBox="0 0 76 76" aria-hidden="true">
        <circle class="gauge-track" cx="38" cy="38" r="${RING_R}"></circle>
        <circle class="gauge-arc" cx="38" cy="38" r="${RING_R}"
          stroke-dasharray="${(pct * RING_C).toFixed(1)} ${RING_C.toFixed(1)}"></circle>
      </svg>
      <div class="gauge-value">${shown}</div>
      <div class="gauge-label">${escapeHtml(label)}</div>
      ${sub ? `<div class="gauge-sub">${escapeHtml(sub)}</div>` : ''}
    </div>`;
}

export function systemGauges(system) {
  const gpu = (system.gpus || [])[0];
  return `
    <div class="gauges">
      ${ring('CPU', system.cpu?.usage, { sub: system.cpu?.ghz ? `${system.cpu.ghz} GHz` : '' })}
      ${ring('Memory', system.memory?.usage, { warn: 80, sub: `${system.memory?.usedGb ?? '—'} / ${system.memory?.totalGb ?? '—'} GB` })}
      ${gpu ? ring('GPU', gpu.usage) : ''}
      ${gpu ? ring('GPU temp', gpu.tempC, { unit: '°', max: 100, warn: 75, danger: 85 }) : ''}
    </div>`;
}

export function diskBars(disks) {
  if (!disks?.length) return '<p class="empty">No drives reported.</p>';
  return disks
    .map((d) => `
      <div class="disk">
        <div class="disk-head"><span class="mono">${escapeHtml(d.mount)}</span>
          <span>${d.freeGb} GB free of ${d.totalGb} GB</span></div>
        <div class="bar bar--${level(d.usedPercent, 85, 95)}"><span style="width:${d.usedPercent}%"></span></div>
      </div>`)
    .join('');
}

// --- status rows -------------------------------------------------------------------

/**
 * A checklist row: good (✓), bad (!) or unknown (?), a label, a value, and an
 * optional button that opens the Windows page where it's fixed.
 */
export function statusRow(good, label, text, open) {
  const tone = good == null ? 'unknown' : good ? 'good' : 'bad';
  return `
    <li class="health-row health-row--${tone}">
      <span class="health-icon" aria-hidden="true">${good == null ? '?' : good ? '✓' : '!'}</span>
      <span class="health-label">${escapeHtml(label)}</span>
      <span class="health-text">${escapeHtml(text)}</span>
      ${open ? `<button class="btn btn--ghost btn--small" type="button" data-open="${open}">Open</button>` : '<span></span>'}
    </li>`;
}

/** Windows protection checklist (used on Overview without buttons and on Security with them). */
export function healthRows(health, { buttons = false } = {}) {
  if (!health.supported) return '<p class="empty">Windows health checks run on Windows only.</p>';
  if (!health.checkedAt) return '<p class="empty">Running the first Windows health check…</p>';
  const b = (target) => (buttons ? target : null);
  const rows = [];
  const d = health.defender;
  rows.push(d
    ? statusRow(d.realtime, 'Antivirus', d.realtime ? `On · definitions ${d.signatureAgeDays}d old` : 'Real-time protection OFF', b('security'))
    : statusRow(null, 'Antivirus', 'Defender not reporting', b('security')));
  const fw = health.firewall || [];
  const off = fw.filter((p) => !p.enabled).map((p) => p.name);
  rows.push(statusRow(fw.length ? off.length === 0 : null, 'Firewall', off.length ? `Off: ${off.join(', ')}` : 'On for all networks', b('security')));
  if (health.lastUpdate) {
    const days = daysSince(health.lastUpdate);
    rows.push(statusRow(days <= 40, 'Updates', `Last installed ${days}d ago`, b('windowsupdate')));
  }
  rows.push(statusRow(!health.rebootPending, 'Restart', health.rebootPending ? 'Needed to finish updates' : 'Not needed', b('windowsupdate')));
  if (health.uacEnabled != null) rows.push(statusRow(health.uacEnabled, 'Account control', health.uacEnabled ? 'On' : 'OFF', b('uac')));
  if (health.rdpEnabled != null) rows.push(statusRow(!health.rdpEnabled, 'Remote Desktop', health.rdpEnabled ? 'On (exposed)' : 'Off', b('remotedesktop')));
  return `<ul class="health ${buttons ? 'health--buttons' : ''}">${rows.join('')}</ul>`;
}

// --- cards ---------------------------------------------------------------------------

/** A dashboard card. With `go`, the whole card is a button that switches to that view. */
export function card(title, body, { go, extra = '', wide = false } = {}) {
  const head = `<header class="card-head"><h3>${escapeHtml(title)}</h3>${go ? '<span class="card-go" aria-hidden="true">→</span>' : ''}${extra}</header>`;
  if (go) {
    return `<article class="card card--link ${wide ? 'card--wide' : ''}" role="button" tabindex="0" data-go="${go}">${head}${body}</article>`;
  }
  return `<article class="card ${wide ? 'card--wide' : ''}">${head}${body}</article>`;
}

// --- line chart ------------------------------------------------------------------------

/**
 * One series over time (0–100 scale), as SVG. Hover shows a crosshair and the
 * value at that moment; the data rides along in data attributes so the hover
 * handler (attachChartHover) doesn't need anything else.
 */
export function lineChart(id, label, times, values, { unit = '%' } = {}) {
  const points = values.map((v, i) => [i, v]).filter(([, v]) => v != null);
  if (points.length < 2) {
    return `<div class="chart chart--empty"><p class="empty">Collecting data… the chart fills in over the next few minutes.</p></div>`;
  }
  const w = 600;
  const h = 150;
  const x = (i) => (i / (values.length - 1)) * w;
  const y = (v) => h - (Math.min(v, 100) / 100) * h;
  const line = points.map(([i, v]) => `${x(i).toFixed(1)},${y(v).toFixed(1)}`).join(' ');
  const area = `${x(points[0][0]).toFixed(1)},${h} ${line} ${x(points[points.length - 1][0]).toFixed(1)},${h}`;
  const spanSeconds = Math.max(60, times[times.length - 1] - times[0]);
  const minutes = Math.round(spanSeconds / 60);
  const ago = minutes < 90 ? `${minutes} min ago` : minutes < 2880 ? `${Math.round(minutes / 60)} h ago` : `${Math.round(minutes / 1440)} days ago`;

  return `
    <div class="chart" data-chart="${id}" data-label="${escapeHtml(label)}" data-unit="${unit}"
         data-times="${times.join(',')}" data-values="${values.map((v) => v ?? '').join(',')}">
      <div class="chart-y"><span>100${unit}</span><span>50${unit}</span><span>0</span></div>
      <div class="chart-plot">
        <svg viewBox="0 0 ${w} ${h}" preserveAspectRatio="none" aria-label="${escapeHtml(label)} since ${ago}">
          <line class="chart-grid" x1="0" y1="${h / 2}" x2="${w}" y2="${h / 2}"></line>
          <polygon class="chart-area" points="${area}"></polygon>
          <polyline class="chart-line" points="${line}"></polyline>
        </svg>
        <div class="chart-cross" hidden></div>
        <div class="chart-tip" hidden></div>
      </div>
      <div class="chart-x"><span>${ago}</span><span>now</span></div>
    </div>`;
}

/** Crosshair + tooltip for every chart inside `root`. Call after rendering. */
export function attachChartHover(root) {
  root.querySelectorAll('.chart[data-chart]').forEach((chart) => {
    const plot = chart.querySelector('.chart-plot');
    const cross = chart.querySelector('.chart-cross');
    const tip = chart.querySelector('.chart-tip');
    const times = chart.dataset.times.split(',').map(Number);
    const values = chart.dataset.values.split(',').map((v) => (v === '' ? null : Number(v)));

    plot.addEventListener('pointermove', (e) => {
      const box = plot.getBoundingClientRect();
      const ratio = Math.min(Math.max((e.clientX - box.left) / box.width, 0), 1);
      const i = Math.round(ratio * (values.length - 1));
      const xPos = (i / (values.length - 1)) * box.width;
      cross.hidden = false;
      tip.hidden = false;
      cross.style.left = `${xPos}px`;
      const multiDay = times[times.length - 1] - times[0] > 86400;
      const time = new Date(times[i] * 1000).toLocaleString([], multiDay
        ? { weekday: 'short', hour: 'numeric', minute: '2-digit' }
        : { hour: 'numeric', minute: '2-digit', second: '2-digit' });
      tip.textContent = `${time} · ${values[i] == null ? '—' : `${Math.round(values[i])}${chart.dataset.unit}`}`;
      tip.style.left = `${Math.min(Math.max(xPos, 60), box.width - 60)}px`;
    });
    plot.addEventListener('pointerleave', () => {
      cross.hidden = true;
      tip.hidden = true;
    });
  });
}
