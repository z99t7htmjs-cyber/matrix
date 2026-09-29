import { escapeHtml } from '../utils/format.js';
import { getDeviceType, TYPE_LEGEND } from '../data/deviceTypes.js';
import { NetworkMap } from '../components/networkMap.js';
import { layoutNodes } from '../utils/layout.js';
import { formatWhen } from '../components/widgets.js';
import { post } from '../services/api.js';

const SHOW_IGNORED_KEY = 'matrix.showIgnored';

/**
 * Network: the map, a list of every device, and household controls
 * (trust everything currently here; show or hide ignored devices).
 *
 * The map element is created once and kept; only the toolbar and list are
 * redrawn when new data arrives.
 */
export class NetworkView {
  constructor(root, { onSelect, onChanged }) {
    this.onChanged = onChanged;
    this.showIgnored = readPref();
    root.innerHTML = `
      <header class="view-head">
        <h1>Network</h1>
        <p class="dim" data-ref="summary"></p>
        <div class="view-actions">
          <label class="toggle-inline"><input type="checkbox" data-ref="show-ignored" ${this.showIgnored ? 'checked' : ''}>
            Show ignored <span data-ref="ignored-count"></span></label>
          <button class="btn btn--primary btn--small" type="button" data-action="trust-all">Trust all current devices</button>
        </div>
      </header>
      <p class="hint trust-hint" data-ref="trust-hint"></p>
      <section class="card card--flat away-banner" data-ref="away-banner" hidden>
        <header class="card-head"><h3>Away from home network</h3></header>
        <p class="hint" data-ref="away-text"></p>
      </section>
      <section class="map-area hud-frame" data-ref="map" aria-label="Network map"></section>
      <div class="map-legend" aria-hidden="true">
        ${TYPE_LEGEND.map((t) => `<span style="--type-color: ${t.color}"><i></i>${escapeHtml(t.label)}</span>`).join('')}
      </div>
      <section class="card card--flat" data-ref="devices-card">
        <header class="card-head"><h3>All devices</h3></header>
        <div data-ref="list"></div>
      </section>`;

    const ref = (name) => root.querySelector(`[data-ref="${name}"]`);
    this.refs = {
      summary: ref('summary'), list: ref('list'), hint: ref('trust-hint'), ignoredCount: ref('ignored-count'),
      awayBanner: ref('away-banner'), awayText: ref('away-text'), map: ref('map'), devicesCard: ref('devices-card'),
      mapLegend: root.querySelector('.map-legend'),
    };
    this.map = new NetworkMap(ref('map'), { onSelect });

    ref('show-ignored').addEventListener('change', (e) => {
      this.showIgnored = e.target.checked;
      writePref(this.showIgnored);
      this.render(this.state, this.selectedId);
    });
    root.querySelector('[data-action="trust-all"]').addEventListener('click', () => this.trustAll());
    this.refs.list.addEventListener('click', (e) => {
      const row = e.target.closest('[data-node]');
      if (row) onSelect(row.dataset.node);
    });
  }

  /** Nodes the map should draw: ignored devices only when "Show ignored" is on. */
  visibleNetwork(network) {
    const nodes = network.nodes.filter((n) => this.showIgnored || !n.ignored);
    const ids = new Set(nodes.map((n) => n.id));
    return {
      nodes: layoutNodes(nodes.map(({ position, ...rest }) => rest)), // lay out only what's shown
      links: network.links.filter((l) => ids.has(l.source) && ids.has(l.target)),
    };
  }

  render(state, selectedId) {
    this.state = state;
    this.selectedId = selectedId;
    const away = !!(state.network.awayFromHome ?? state.meta.awayFromHome);
    const all = state.network.nodes;
    const devices = all.filter((n) => n.id !== 'internet');
    const ignored = devices.filter((n) => n.ignored);
    const online = devices.filter((n) => n.status === 'online' && !n.ignored).length;

    this.refs.awayBanner.hidden = !away;
    this.refs.map.hidden = away;
    this.refs.devicesCard.hidden = away;
    this.refs.mapLegend.hidden = away;
    if (away) {
      const homeKnown = state.network.homeKnown ?? state.meta.homeKnown;
      this.refs.awayText.textContent = homeKnown
        ? "This doesn't look like your home network, so Matrix isn't reading or listing other devices here -- it's only watching this PC. Turn this back on in Settings if that's wrong."
        : "Device scanning is paused (turned off in Settings) -- Matrix is only watching this PC right now.";
      this.refs.summary.textContent = 'Away from home · watching this PC only';
      this.refs.hint.textContent = '';
      return;
    }

    this.refs.summary.textContent = `${online} online · ${devices.length - ignored.length} known to Matrix` +
      (ignored.length ? ` · ${ignored.length} ignored` : '');
    this.refs.ignoredCount.textContent = ignored.length ? `(${ignored.length})` : '';
    const baseline = state.meta.baselineAt;
    this.refs.hint.textContent = baseline
      ? `Trusted on ${formatWhen(baseline)}. Only devices that joined after that are flagged as new.`
      : 'Live with other people? "Trust all current devices" marks everything here now as normal, so Matrix only alerts you about devices that show up later.';

    this.map.render(this.visibleNetwork(state.network));
    this.map.setSelected(selectedId);
    this.refs.list.innerHTML = deviceTable(devices, selectedId, this.showIgnored);
  }

  async trustAll() {
    const count = this.state.network.nodes.filter((n) => n.mac && !n.saved && n.id !== 'this-pc').length;
    const ok = confirm(`Mark ${count} device${count === 1 ? '' : 's'} currently on your network as trusted?\n\n` +
      'They keep their current names (you can rename them any time). From now on, Matrix only flags devices that join later.');
    if (!ok) return;
    try {
      await post('/api/devices', { action: 'trust-all' });
      this.onChanged();
    } catch (err) {
      alert(err.message);
    }
  }
}

function deviceTable(devices, selectedId, showIgnored) {
  const rows = devices
    .filter((n) => showIgnored || !n.ignored)
    .sort((a, b) => (a.status === b.status ? a.name.localeCompare(b.name) : a.status === 'online' ? -1 : 1));
  if (!rows.length) return '<p class="empty">No devices yet.</p>';
  return `
    <table class="data-table data-table--clickable">
      <thead><tr><th></th><th>Name</th><th>Type</th><th>IP address</th><th>Maker</th><th>Status</th></tr></thead>
      <tbody>${rows.map((n) => `
        <tr data-node="${escapeHtml(n.id)}" class="${n.id === selectedId ? 'is-selected' : ''} ${n.ignored ? 'is-dim' : ''}" tabindex="0">
          <td><span class="dot dot--${n.status === 'online' ? 'on' : 'off'}" title="${n.status}"></span></td>
          <td>${escapeHtml(n.name)}</td>
          <td class="dim">${escapeHtml(getDeviceType(n.type).label)}</td>
          <td class="mono">${escapeHtml(n.ip || '—')}</td>
          <td class="dim">${escapeHtml(n.vendor || '—')}</td>
          <td>${identity(n)}</td>
        </tr>`).join('')}
      </tbody>
    </table>`;
}

function identity(n) {
  if (n.ignored) return '<span class="dim">Ignored</span>';
  if (n.alerts.some((a) => a.kind === 'new-device')) return '<span class="warn-text">New / unknown</span>';
  if (n.saved || n.known) return '<span class="ok-text">Trusted</span>';
  return '<span class="dim">Guessed</span>';
}

function readPref() {
  try {
    return localStorage.getItem(SHOW_IGNORED_KEY) === '1';
  } catch {
    return false;
  }
}

function writePref(value) {
  try {
    localStorage.setItem(SHOW_IGNORED_KEY, value ? '1' : '0');
  } catch {
    // storage unavailable; the choice just won't be remembered
  }
}
