import { escapeHtml } from '../utils/format.js';
import { getJson } from '../services/api.js';

/**
 * Timeline: everything Matrix noticed, newest first: devices joining, crashes,
 * alerts raised and resolved, repairs detected, what you set aside, AI notes.
 * Loaded when you open the view and refreshed every 30 seconds while it's open.
 */
const KINDS = {
  alert: { icon: '!', label: 'Alert', tone: 'warn' },
  resolved: { icon: '✓', label: 'Resolved', tone: 'ok' },
  crash: { icon: '✕', label: 'Crash', tone: 'bad' },
  repair: { icon: '⚙', label: 'Repair', tone: 'ok' },
  device: { icon: '◉', label: 'Device', tone: 'info' },
  trusted: { icon: '✓', label: 'Network', tone: 'ok' },
  snoozed: { icon: 'z', label: 'Snoozed', tone: 'dim' },
  kept: { icon: '•', label: 'Kept', tone: 'dim' },
  acknowledged: { icon: '•', label: 'Seen', tone: 'dim' },
  archived: { icon: '•', label: 'Archived', tone: 'dim' },
  ai: { icon: '✦', label: 'Matrix says', tone: 'info' },
  matrix: { icon: '▸', label: 'Matrix', tone: 'dim' },
  changes: { icon: '↕', label: 'What changed', tone: 'info' },
  mode: { icon: '⚡', label: 'Mode', tone: 'ok' },
  digest: { icon: '✦', label: 'Weekly digest', tone: 'info' },
};
const FILTERS = [
  ['all', 'Everything'],
  ['important', 'Alerts & crashes'],
  ['device', 'Devices'],
  ['repair', 'Repairs'],
];

export class TimelineView {
  constructor(root) {
    this.root = root;
    this.filter = 'important';
    this.items = [];
    root.addEventListener('click', (e) => {
      const f = e.target.closest('[data-filter]');
      if (f) {
        this.filter = f.dataset.filter;
        this.render();
      }
    });
  }

  async show() {
    await this.load();
    clearInterval(this.timer);
    this.timer = setInterval(() => (this.root.hidden ? clearInterval(this.timer) : this.load()), 30000);
  }

  async load() {
    try {
      this.items = (await getJson('/api/timeline?limit=300')).items;
    } catch {
      this.items = [];
    }
    this.render();
  }

  render() {
    const keep = {
      all: () => true,
      important: (i) => ['alert', 'resolved', 'crash', 'repair', 'ai', 'trusted', 'changes', 'mode', 'digest'].includes(i.kind)
        || (i.kind === 'device' && i.title.startsWith('New')),
      device: (i) => i.kind === 'device' || i.kind === 'trusted',
      repair: (i) => i.kind === 'repair' || (i.kind === 'resolved' && i.title.startsWith('Crashes')),
    }[this.filter];
    const items = this.items.filter(keep);

    // Group by day
    const groups = [];
    for (const item of items) {
      const day = new Date(item.ts * 1000).toLocaleDateString([], { weekday: 'long', month: 'short', day: 'numeric' });
      if (!groups.length || groups[groups.length - 1].day !== day) groups.push({ day, items: [] });
      groups[groups.length - 1].items.push(item);
    }

    this.root.innerHTML = `
      <header class="view-head">
        <h1>Timeline</h1>
        <p class="dim">What Matrix noticed, newest first. Kept for a year.</p>
        <div class="view-actions segmented">
          ${FILTERS.map(([id, label]) => `<button type="button" class="${id === this.filter ? 'is-active' : ''}" data-filter="${id}">${label}</button>`).join('')}
        </div>
      </header>
      ${groups.length ? groups.map((g) => `
        <section class="tl-day">
          <h3>${escapeHtml(g.day)}</h3>
          <ul class="tl">${g.items.map(row).join('')}</ul>
        </section>`).join('') : '<p class="empty">Nothing here yet. Matrix records events as they happen.</p>'}`;
  }
}

function row(item) {
  const k = KINDS[item.kind] || KINDS.matrix;
  const time = new Date(item.ts * 1000).toLocaleTimeString([], { hour: 'numeric', minute: '2-digit' });
  return `
    <li class="tl-item tl-item--${k.tone}">
      <span class="tl-time">${time}</span>
      <span class="tl-icon" aria-hidden="true">${k.icon}</span>
      <div class="tl-body">
        <span class="tl-kind">${k.label}</span>
        <strong>${escapeHtml(item.title)}</strong>
        ${item.detail ? `<p>${escapeHtml(item.detail)}</p>` : ''}
      </div>
    </li>`;
}
