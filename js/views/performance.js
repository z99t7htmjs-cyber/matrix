import { escapeHtml } from '../utils/format.js';
import { attachChartHover, card, diskBars, formatMb, formatUptime, lineChart, systemGauges } from '../components/widgets.js';
import { getJson } from '../services/api.js';

/**
 * Performance: live gauges, charts over a chosen range (30 minutes live, or
 * 24 hours / 7 days / 30 days from Matrix's history), busiest programs.
 */
const RANGES = [
  ['30m', '30 min'],
  ['24h', '24 hours'],
  ['7d', '7 days'],
  ['30d', '30 days'],
];

let range = '30m';
let cached = { key: null, at: 0, data: null };

async function loadHistory(key) {
  if (cached.key === key && Date.now() - cached.at < 60000) return cached.data;
  try {
    const data = await getJson(`/api/history?range=${key}`);
    cached = { key, at: Date.now(), data };
    return data;
  } catch {
    return null;
  }
}

export function renderPerformance(root, state) {
  const { system } = state;
  if (!system.available) {
    root.innerHTML = `
      <header class="view-head"><h1>Performance</h1></header>
      <p class="empty">Live vitals need psutil. Run "Install or Update Matrix" again to install it.</p>`;
    return;
  }
  if (!root.dataset.wired) {
    root.dataset.wired = '1';
    root.addEventListener('click', (e) => {
      const b = e.target.closest('[data-range]');
      if (!b) return;
      range = b.dataset.range;
      renderPerformance(root, state);
      if (range !== '30m') loadHistory(range).then(() => renderPerformance(root, window.__matrixState || state));
    });
  }

  const gpu = (system.gpus || [])[0];
  let series;
  if (range === '30m') {
    const h = system.history || { t: [], cpu: [], memory: [], gpu: [] };
    series = { t: h.t, cpu: h.cpu, cpuMax: null, memory: h.memory, gpu: h.gpu, note: 'Live, every 10 seconds.' };
  } else {
    const data = cached.key === range ? cached.data : null;
    if (!data) loadHistory(range).then(() => renderPerformance(root, window.__matrixState || state));
    const points = data?.points || [];
    series = {
      t: points.map((p) => p.t), cpu: points.map((p) => p.cpu), cpuMax: points.map((p) => p.cpu_max),
      memory: points.map((p) => p.memory), gpu: points.map((p) => p.gpu),
      note: data ? (points.length ? `Averages from Matrix's history (one point per ${Math.round(data.bucketSeconds / 60)} min). History starts when Matrix 0.9 was installed.`
        : 'No history for this range yet. Matrix records a point every minute while it runs.') : 'Loading…',
    };
  }
  const peak = series.cpuMax ? Math.max(0, ...series.cpuMax.filter((v) => v != null)) : null;

  root.innerHTML = `
    <header class="view-head">
      <h1>Performance</h1>
      <p class="dim">${escapeHtml(system.cpuName || '')} · ${system.cpu?.cores ?? '—'} threads · up ${formatUptime(system.uptimeSeconds)}</p>
      <div class="view-actions">
        <div class="segmented">${RANGES.map(([id, label]) => `<button type="button" class="${id === range ? 'is-active' : ''}" data-range="${id}">${label}</button>`).join('')}</div>
        <button class="btn btn--ghost btn--small" type="button" data-open="taskmanager">Open Task Manager</button>
      </div>
    </header>
    <div class="cards">
      ${card('Right now', systemGauges(system), { wide: true })}
      ${card(`CPU${peak != null && series.t.length ? ` · peak ${Math.round(peak)}%` : ''}`, lineChart('cpu', 'CPU', series.t, series.cpu))}
      ${card('Memory', lineChart('memory', 'Memory', series.t, series.memory))}
      ${gpu ? card(`GPU · ${gpu.name}`, lineChart('gpu', 'GPU', series.t, series.gpu)) : ''}
      ${gpu ? card('Graphics memory', `
          <div class="big-stats">
            <div><strong>${formatMb(gpu.memUsedMb)}</strong><span>in use</span></div>
            <div><strong>${formatMb(gpu.memTotalMb)}</strong><span>total</span></div>
            <div><strong>${gpu.tempC ?? '—'}°</strong><span>temperature</span></div>
          </div>
          <p class="hint">Games and the local AI model share this memory.</p>`) : ''}
      <p class="hint card--wide">${escapeHtml(series.note)}</p>
      ${card('Programs using the most right now', processTable(system.processes), { wide: true })}
      ${card('Drives', diskBars(system.disks))}
    </div>`;
  attachChartHover(root);
}

function processTable(processes) {
  if (!processes?.length) return '<p class="empty">No data yet.</p>';
  return `
    <table class="data-table">
      <thead><tr><th>Program</th><th class="num">CPU</th><th class="num">Memory</th></tr></thead>
      <tbody>${processes.map((p) => `
        <tr>
          <td>${escapeHtml(p.name)}${p.count > 1 ? ` <span class="dim">×${p.count}</span>` : ''}</td>
          <td class="num">${p.cpu.toFixed(1)}%</td>
          <td class="num">${formatMb(p.memMb)}</td>
        </tr>`).join('')}
      </tbody>
    </table>
    <p class="hint">CPU is a share of the whole processor, like Task Manager. Programs with several processes (browsers) are combined.</p>`;
}
