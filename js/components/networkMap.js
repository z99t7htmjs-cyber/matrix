import { getDeviceType } from '../data/deviceTypes.js';
import { formatRate } from '../utils/format.js';
import { isSecurityAlert, normalizeSeverity } from '../utils/alerts.js';

const SVG_NS = 'http://www.w3.org/2000/svg';
const SERIOUS = new Set(['critical', 'high']);

// Drawing coordinates. The SVG scales to fit its container via viewBox.
const VIEW_W = 1000;
const VIEW_H = 620; // base height; grows when the layout needs more rows
const NODE_R = 36;
const MAX_NAME_CHARS = 22;

/** Small helper for creating SVG elements. */
function svgEl(tag, attrs = {}, text) {
  const el = document.createElementNS(SVG_NS, tag);
  for (const [key, value] of Object.entries(attrs)) el.setAttribute(key, value);
  if (text !== undefined) el.textContent = text;
  return el;
}

/** Node positions are stored as fractions of the base size; convert to SVG coordinates. */
function toView({ x, y }) {
  return [x * VIEW_W, y * VIEW_H];
}

/** A gentle S-curve between two points, instead of a straight/angular line -- the same
 *  soft, organic connector language as the Living Look's satellite links. */
function curvePath([x1, y1], [x2, y2]) {
  const midY = (y1 + y2) / 2;
  return `M ${x1} ${y1} C ${x1} ${midY}, ${x2} ${midY}, ${x2} ${y2}`;
}

function truncate(text, max) {
  return text.length > max ? `${text.slice(0, max - 1)}…` : text;
}

/** Text under a node: live traffic, "OFFLINE", or nothing when traffic isn't visible. */
function trafficLabel(node) {
  if (node.status !== 'online') return 'OFFLINE';
  if (!node.traffic) return '';
  return `↓ ${formatRate(node.traffic.inKbps)}  ↑ ${formatRate(node.traffic.outKbps)}`;
}

/**
 * Draws the topology as SVG.
 *
 * render(snapshot) can be called as often as new data arrives: elements are
 * created on first sight of a node/link, updated afterwards, and removed when
 * they disappear from the data.
 */
export class NetworkMap {
  constructor(container, { onSelect }) {
    this.onSelect = onSelect;
    this.nodeEls = new Map(); // node id -> element references
    this.linkEls = new Map(); // "source->target" -> element references

    this.svg = svgEl('svg', {
      viewBox: `0 0 ${VIEW_W} ${VIEW_H}`,
      class: 'network-svg',
      role: 'group',
      'aria-label': 'Network topology',
    });
    this.linkLayer = svgEl('g', { class: 'links' });
    this.nodeLayer = svgEl('g', { class: 'nodes' });
    this.svg.append(this.linkLayer, this.nodeLayer);
    container.append(this.svg);

    // Clicking empty space clears the selection.
    this.svg.addEventListener('click', (e) => {
      if (e.target === this.svg) this.onSelect(null);
    });
  }

  render({ nodes, links }) {
    const byId = new Map(nodes.map((n) => [n.id, n]));
    this.fitHeight(nodes);
    this.removeMissing(byId, links);
    for (const link of links) this.renderLink(link, byId);
    for (const node of nodes) this.renderNode(node);
  }

  /** Grow the drawing area when there are more rows than the base height holds. */
  fitHeight(nodes) {
    const lowest = Math.max(0, ...nodes.map((n) => n.position.y));
    const height = Math.max(VIEW_H, Math.ceil(lowest * VIEW_H + NODE_R + 80));
    this.svg.setAttribute('viewBox', `0 0 ${VIEW_W} ${height}`);
  }

  /** Drop elements for nodes and links that are no longer in the data. */
  removeMissing(byId, links) {
    for (const [id, els] of this.nodeEls) {
      if (!byId.has(id)) {
        els.group.remove();
        this.nodeEls.delete(id);
      }
    }
    const linkKeys = new Set(links.map((l) => `${l.source}->${l.target}`));
    for (const [key, els] of this.linkEls) {
      if (!linkKeys.has(key)) {
        els.line.remove();
        els.flow.remove();
        this.linkEls.delete(key);
      }
    }
  }

  setSelected(selectedId) {
    for (const [id, { group }] of this.nodeEls) {
      group.classList.toggle('is-selected', id === selectedId);
    }
  }

  // --- links ---------------------------------------------------------------

  renderLink(link, byId) {
    const a = byId.get(link.source);
    const b = byId.get(link.target);
    if (!a || !b) return;

    const key = `${link.source}->${link.target}`;
    let els = this.linkEls.get(key);
    if (!els) {
      els = {
        line: svgEl('path', { class: 'link', fill: 'none' }),
        flow: svgEl('path', { class: 'link-flow', fill: 'none' }), // animated dashes = traffic
      };
      this.linkLayer.append(els.line, els.flow);
      this.linkEls.set(key, els);
    }

    // Positions can change when devices come and go, so set them every time.
    const p1 = toView(a.position);
    const p2 = toView(b.position);
    const d = curvePath(p1, p2);
    els.line.setAttribute('d', d);
    els.flow.setAttribute('d', d);

    const isUp = a.status === 'online' && b.status === 'online';
    els.line.classList.toggle('is-down', !isUp);
    els.flow.classList.toggle('is-down', !isUp);
  }

  // --- nodes ---------------------------------------------------------------

  renderNode(node) {
    let els = this.nodeEls.get(node.id);
    if (!els) {
      els = this.createNode(node);
      this.nodeEls.set(node.id, els);
    }

    const [x, y] = toView(node.position);
    els.group.setAttribute('transform', `translate(${x} ${y})`);

    // Name and type can change (e.g. after labelling a device in known_devices.json).
    els.name.textContent = truncate(node.name, MAX_NAME_CHARS);
    els.glyph.textContent = getDeviceType(node.type).glyph;
    els.ip.textContent = node.ip ?? '';
    els.traffic.textContent = trafficLabel(node);

    const online = node.status === 'online';
    els.group.classList.toggle('is-offline', !online);
    els.group.setAttribute('aria-label', `${node.name}, ${node.status}`);

    const alertCount = node.alerts.filter(isSecurityAlert).length;
    els.badge.classList.toggle('is-hidden', alertCount === 0);
    els.badgeText.textContent = alertCount;

    // High or critical alerts turn the node red.
    const isThreat = node.alerts.some((a) => SERIOUS.has(normalizeSeverity(a.severity)));
    els.group.classList.toggle('is-threat', isThreat);

    // Each device type gets its own color (computer, mobile, entertainment, etc.);
    // offline or threatened devices override that with their own status color.
    const typeColor = getDeviceType(node.type).color ?? 'var(--accent)';
    const effectiveColor = isThreat ? 'var(--sev-critical)' : !online ? 'var(--offline)' : typeColor;
    els.group.style.setProperty('--type-color', effectiveColor);
  }

  createNode(node) {
    const group = svgEl('g', { class: 'node', tabindex: '0', role: 'button', 'data-id': node.id });

    const glyph = svgEl('text', { class: 'node-glyph', 'dominant-baseline': 'central' });
    const name = svgEl('text', { class: 'node-name', y: NODE_R + 22 });
    const ip = svgEl('text', { class: 'node-ip', y: NODE_R + 40 });
    const traffic = svgEl('text', { class: 'node-traffic', y: NODE_R + 58 });

    const badge = svgEl('g', {
      class: 'node-badge',
      transform: `translate(${-NODE_R * 0.75} ${-NODE_R * 0.75})`,
    });
    const badgeText = svgEl('text', { class: 'node-badge-text', 'dominant-baseline': 'central' });
    badge.append(svgEl('circle', { r: 10 }), badgeText);

    // A small upward specular arc, regardless of radius -- the "glass" highlight.
    const specular = svgEl('path', {
      class: 'node-specular',
      d: `M ${-0.55 * NODE_R} ${-0.4 * NODE_R} A ${0.62 * NODE_R} ${0.62 * NODE_R} 0 0 1 ${0.55 * NODE_R} ${-0.4 * NODE_R}`,
      fill: 'none',
    });

    group.append(
      svgEl('circle', { class: 'node-halo', r: NODE_R + 12 }),
      svgEl('circle', { class: 'node-orbit', r: NODE_R + 9 }),
      svgEl('circle', { class: 'node-tint', r: NODE_R }),
      svgEl('circle', { class: 'node-core', r: NODE_R }),
      specular,
      glyph,
      svgEl('circle', { class: 'node-status', r: 7, cx: NODE_R * 0.72, cy: -NODE_R * 0.72 }),
      name,
      ip,
      traffic,
      badge,
    );

    group.addEventListener('click', () => this.onSelect(node.id));
    group.addEventListener('keydown', (e) => {
      if (e.key === 'Enter' || e.key === ' ') {
        e.preventDefault();
        this.onSelect(node.id);
      }
    });

    this.nodeLayer.append(group);
    return { group, glyph, name, ip, traffic, badge, badgeText };
  }
}
