/**
 * The living core: a 3D-rotating particle sphere with six satellite nodes
 * (Network, Performance, Security, Crashes, Tune-up, Matrix AI), curved
 * connector lines with traveling data dots, orbit rings, and particle
 * bursts for new events. Ported from design/matrix-living-core.html's
 * canvas engine -- this is the agreed-on look, driven by real state instead
 * of the mockup's sample random walk.
 *
 * A persistent component (like NetworkMap): built once, then updated and
 * re-parented into the current Overview mount on every poll so the canvas
 * and its animation loop never restart.
 */
const ORDER = ['network', 'system', 'security', 'crashes', 'tuneup', 'ai'];
const ANGLES = [-120, -60, 0, 60, 120, 180].map((a) => (a * Math.PI) / 180);
const CRIT = '#ff4d6d';
const AREA_VIEW = { network: 'network', system: 'performance', security: 'security', crashes: 'events', tuneup: 'tuneup', ai: null };
const REDUCED_MOTION = typeof window.matchMedia === 'function'
  && window.matchMedia('(prefers-reduced-motion: reduce)').matches;

function rnd(a, b) { return a + Math.random() * (b - a); }

export class LivingCore {
  constructor() {
    this.el = document.createElement('div');
    this.el.className = 'living-core';
    this.el.innerHTML = `
      <canvas class="core-canvas" role="img" aria-label="Your PC as a sphere of recent readings, with Network, Performance, Security, Crashes, Tune-up and Matrix AI orbiting it"></canvas>
      <div class="scene-head">
        <strong data-ref="headline">ALL WATCHED</strong>
        <span data-ref="subline"></span>
      </div>
      <button type="button" class="core-motion-toggle" data-motion-toggle title="Pause background motion" aria-label="Pause background motion"></button>
      <section class="core-legend" aria-label="What the particles are">
        <p>Each particle is one reading Matrix took recently, colored by where it came from.</p>
        <ul data-ref="legend"></ul>
      </section>`;
    this.canvas = this.el.querySelector('.core-canvas');
    this.ctx = this.canvas.getContext('2d');

    this.AREAS = {
      network: { label: 'Network', color: '#5fd4ff', status: '', weight: 0.2, critical: false },
      system: { label: 'Performance', color: '#36e2b4', status: '', weight: 0.2, critical: false },
      security: { label: 'Security', color: '#8c9bff', status: '', weight: 0.15, critical: false },
      crashes: { label: 'Crashes', color: '#c792ff', status: '', weight: 0.12, critical: false },
      tuneup: { label: 'Tune-up', color: '#ff9ecf', status: '', weight: 0.15, critical: false },
      ai: { label: 'Matrix AI', color: '#f5d27a', status: '', weight: 0.18, critical: false },
    };

    const legend = this.el.querySelector('[data-ref="legend"]');
    ORDER.forEach((k) => {
      const li = document.createElement('li');
      li.innerHTML = `<i style="background:${this.AREAS[k].color};box-shadow:0 0 8px ${this.AREAS[k].color}"></i>${this.AREAS[k].label}`;
      legend.appendChild(li);
    });

    this.t = 3;
    this.last = performance.now();
    this.running = !REDUCED_MOTION;
    this.alert = false;
    this.userPaused = false;
    this.throttled = false;
    this.sats = [];
    this.comets = [];
    this.hover = null;
    this.seen = new Set();
    this.firstUpdate = true;

    this.canvas.addEventListener('pointermove', (e) => this._pointerMove(e));
    this.canvas.addEventListener('pointerleave', () => { this.hover = null; this.canvas.style.cursor = 'default'; });
    this.canvas.addEventListener('click', (e) => this._click(e));
    window.addEventListener('resize', () => this._resize());
    document.addEventListener('visibilitychange', () => this._applyRunning());

    this._resize();
    if (this.running) requestAnimationFrame((now) => this._loop(now));
  }

  mount(container) {
    if (container && this.el.parentElement !== container) {
      container.appendChild(this.el);
      this._resize();
    }
  }

  setThrottled(on) { this.throttled = on; this._applyRunning(); }
  setUserPaused(paused) { this.userPaused = paused; this._applyRunning(); }

  _applyRunning() {
    const shouldRun = !REDUCED_MOTION && !this.userPaused && !this.throttled && document.visibilityState !== 'hidden';
    if (shouldRun === this.running) return;
    this.running = shouldRun;
    if (shouldRun) { this.last = performance.now(); requestAnimationFrame((now) => this._loop(now)); }
  }

  update(state, { recent = [], lastVisit = 0 } = {}) {
    const advice = state.advice || [];
    const byArea = (area) => advice.filter((a) => a.area === area);
    const critical = advice.filter((a) => a.urgency === 'critical');

    const net = byArea('network');
    const away = !!(state.network.awayFromHome ?? state.meta?.awayFromHome);
    // Declared outside the branch below: the summary line at the bottom of this
    // method needs it regardless of whether the network satellite shows it too.
    const online = (state.network.nodes || []).filter((n) => n.status === 'online' && !n.ignored && n.id !== 'internet').length;
    if (away) {
      this._area('network', [], 'Away from home');
    } else {
      const newDevices = (state.network.nodes || []).filter((n) => n.alerts?.some((a) => a.kind === 'new-device')).length;
      this._area('network', net, `${online} device${online === 1 ? '' : 's'}${newDevices ? ` · ${newDevices} new` : ''}`);
    }

    const sys = state.system || {};
    const cpu = sys.cpu?.usage;
    const gpu = sys.gpus?.[0];
    this._area('system', byArea('performance'), cpu != null ? `CPU ${Math.round(cpu)}%${gpu ? ` · ${Math.round(gpu.tempC ?? 0)}°C` : ''}` : 'Vitals need psutil');

    const health = state.health || {};
    const fwOff = (health.firewall || []).some((p) => !p.enabled);
    const shieldsOff = health.defender ? !health.defender.realtime || fwOff || health.rebootPending : false;
    this._area('security', byArea('security'), health.supported === false ? 'Windows only' : shieldsOff ? 'Check needed' : 'All shields on');

    const crashCount = state.plans?.crashes?.counted?.length || 0;
    this._area('crashes', byArea('stability'), crashCount ? `${crashCount} this week` : 'None recently');

    const flagged = (state.tuneup?.flagged || []).length;
    this._area('tuneup', byArea('tune-up').concat(byArea('maintenance')), flagged ? `${flagged} idea${flagged === 1 ? '' : 's'}` : 'Nothing flagged');

    const freshVoice = recent.some((i) => (i.kind === 'ai' || i.kind === 'digest') && lastVisit && i.ts > lastVisit);
    this._area('ai', [], freshVoice ? 'New note' : `${state.meta?.model || 'local model'} · idle`, freshVoice);

    this.alert = critical.length > 0;
    this.el.dataset.status = this.alert ? 'critical' : advice.some((a) => a.urgency === 'attention') ? 'attention' : 'ok';

    const headline = this.el.querySelector('[data-ref="headline"]');
    const subline = this.el.querySelector('[data-ref="subline"]');
    headline.textContent = this.alert ? (critical[0].title || 'NEEDS ATTENTION').toUpperCase() : 'ALL WATCHED';
    subline.textContent = `${online} device${online === 1 ? '' : 's'} · ${crashCount} crash${crashCount === 1 ? '' : 'es'} this week`;

    this._burst(recent);
  }

  _area(key, items, status, forceCritical) {
    const a = this.AREAS[key];
    a.status = status;
    a.critical = forceCritical || items.some((i) => i.urgency === 'critical');
    a.attention = items.some((i) => i.urgency === 'attention');
  }

  _pointerMove(e) {
    const s = this._satAt(e);
    this.hover = s ? s.k : null;
    this.canvas.style.cursor = s ? 'pointer' : 'default';
    if (!this.running) this._frame(true);
  }

  _click(e) {
    const s = this._satAt(e);
    if (!s) return;
    const view = AREA_VIEW[s.k];
    if (view) location.hash = view;
  }

  _satAt(e) {
    const r = this.canvas.getBoundingClientRect();
    const x = e.clientX - r.left;
    const y = e.clientY - r.top;
    return this.sats.find((s) => Math.hypot(s.x - x, s.y - y) < 26);
  }

  _resize() {
    const dpr = Math.min(window.devicePixelRatio || 1, 1.5);
    const r = this.el.getBoundingClientRect();
    const w = Math.max(1, r.width * dpr);
    const h = Math.max(1, r.height * dpr);
    // mount() calls _resize() every time it re-parents this.el -- which, because Overview
    // rebuilds its whole HTML from scratch every poll (~every 3s), is EVERY poll, not just
    // on an actual window resize. Rebuilding unconditionally here meant the entire 3200-
    // particle field was thrown away and re-randomized every 3 seconds -- a real, visible
    // "jump" in the scene in sync with polling, on top of (and worse than) any rotation-
    // speed issue. Skip the rebuild entirely when the canvas is already the right size;
    // only a genuine size change (first mount, real window resize) needs new particles.
    if (w === this.canvas.width && h === this.canvas.height) return;
    this.canvas.width = w;
    this.canvas.height = h;
    this.ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
    this._buildParticles();
    this._frame(true);
  }

  _geom() {
    const W = this.canvas.width / (this.ctx.getTransform().a || 1);
    const H = this.canvas.height / (this.ctx.getTransform().d || 1);
    const R = Math.max(50, Math.min(W * 0.19, H * 0.28));
    return { W, H, R, cx: W / 2, cy: H / 2 + H * 0.02 };
  }

  _buildParticles() {
    const { R } = this._geom();
    const N = Math.round(3200 * Math.min(1, R / 150));
    this.particles = [];
    this.byColor = {};
    let acc = 0;
    const cum = ORDER.map((k) => (acc += this.AREAS[k].weight));
    for (let i = 0; i < N; i++) {
      const u = Math.random() * acc;
      let ci = cum.findIndex((c) => u <= c);
      if (ci < 0) ci = 0;
      const r = 0.06 + 0.94 * Math.pow(Math.random(), 0.65);
      const th = Math.random() * 6.283;
      const ph = Math.acos(2 * Math.random() - 1);
      const p = { x: r * Math.sin(ph) * Math.cos(th), y: r * Math.cos(ph) * 0.92, z: r * Math.sin(ph) * Math.sin(th), s: Math.random(), tw: Math.random() * 6.28, c: ORDER[ci] };
      this.particles.push(p);
      (this.byColor[p.c] = this.byColor[p.c] || []).push(p);
    }
  }

  _arc(x, y, r, a0, a1) { const c = this.ctx; c.beginPath(); c.arc(x, y, r, a0, a1); c.stroke(); }

  _satPositions(G, t) {
    return ORDER.map((k, i) => {
      const a = ANGLES[i] + Math.sin(t * 0.15 + i) * 0.04;
      const rx = Math.min(G.R * 1.65, G.W / 2 - 90);
      const ry = Math.min(G.R * 1.42, G.H / 2 - 30);
      return { k, a, x: G.cx + Math.cos(a) * Math.max(G.R * 1.25, rx), y: G.cy + Math.sin(a) * Math.max(G.R * 1.2, ry) };
    });
  }

  _burst(recent) {
    for (const item of recent) {
      const key = `${item.kind}:${item.ts}`;
      if (this.seen.has(key)) continue;
      this.seen.add(key);
      if (this.firstUpdate) continue;
      const area = { network: 'network', ai: 'ai', digest: 'ai', alert: 'security', mode: 'system' }[item.kind] || 'network';
      this._spawnBurst(area, 26);
    }
    this.firstUpdate = false;
    if (this.seen.size > 300) this.seen.clear();
  }

  _spawnBurst(area, n) {
    const s = this.sats.find((sat) => sat.k === area);
    if (!s) return;
    const G = this._geom();
    for (let i = 0; i < (n || 30); i++) {
      this.comets.push({ x: s.x + rnd(-10, 10), y: s.y + rnd(-10, 10), mx: (s.x + G.cx) / 2 + rnd(-70, 70), my: (s.y + G.cy) / 2 + rnd(-70, 70), p: rnd(-0.35, 0), v: rnd(0.45, 0.9), col: this.AREAS[area].color });
    }
  }

  _frame(still) {
    const now = performance.now();
    // Chrome throttles requestAnimationFrame hard for a window that's visible but not
    // focused (e.g. this window sitting next to the one you're actually typing in) --
    // frames can drop to ~1/sec or slower without the tab ever counting as "hidden".
    // Clamping dt to 0.05 per frame turned that into visible slow motion: with rare
    // frames each only allowed to advance a tiny sliver of time, the whole scene
    // crawled for as long as the window wasn't focused. A much looser clamp lets a
    // sparse frame catch the animation up to roughly where it should really be --
    // fine for a looping/rotating scene like this one, where landing in a different
    // spot in the loop isn't jarring the way a jump would be for a linear animation.
    const dt = still ? 0 : Math.min(0.5, (now - this.last) / 1000);
    if (!still) { this.last = now; this.t += dt; }
    this._draw(this.t, dt);
  }

  _loop(now) {
    if (!this.running) return;
    // Do NOT set this.last = now here -- _frame() below reads a fresh performance.now()
    // and diffs it against this.last to get dt. Overwriting this.last with the current
    // frame's own timestamp right before that comparison made every dt come out as
    // essentially zero (the two clock reads are only a fraction of a millisecond apart),
    // which is why this animation crawled -- previously misdiagnosed as unfocused-window
    // throttling. _frame() already updates this.last correctly after computing dt.
    this._frame(false);
    requestAnimationFrame((n) => this._loop(n));
  }

  _draw(t, dt) {
    const G = this._geom();
    const { W, H, R, cx, cy } = G;
    const ctx = this.ctx;
    ctx.clearRect(0, 0, W, H);
    const spd = this.alert ? 2.6 : 1;
    const ay = t * 0.12 * spd;
    const ax = 0.38 + Math.sin(t * 0.1) * 0.08;
    const cyA = Math.cos(ay), syA = Math.sin(ay), cxA = Math.cos(ax), sxA = Math.sin(ax);
    const f = 3.2;
    ctx.globalCompositeOperation = 'lighter';

    this.boost = (this.boost || 0) * 0.96;
    const pulse = 1 + 0.08 * Math.sin(t * 2) + this.boost;
    let g = ctx.createRadialGradient(cx, cy, 0, cx, cy, R * 1.05 * pulse);
    if (this.alert) { g.addColorStop(0, 'rgba(255,220,228,.85)'); g.addColorStop(0.25, 'rgba(255,77,109,.45)'); g.addColorStop(1, 'rgba(255,77,109,0)'); }
    else { g.addColorStop(0, 'rgba(255,255,255,.85)'); g.addColorStop(0.22, 'rgba(150,230,255,.45)'); g.addColorStop(0.6, 'rgba(40,120,255,.12)'); g.addColorStop(1, 'rgba(40,120,255,0)'); }
    ctx.fillStyle = g;
    ctx.beginPath();
    ctx.arc(cx, cy, R * 1.1 * pulse, 0, 6.283);
    ctx.fill();

    ORDER.forEach((k) => {
      const list = this.byColor[k];
      if (!list) return;
      ctx.fillStyle = this.alert ? (k === 'ai' || k === 'security' ? '#ffd0d8' : CRIT) : this.AREAS[k].color;
      for (const p of list) {
        let x = p.x * cyA - p.z * syA, z = p.x * syA + p.z * cyA;
        let y = p.y * cxA - z * sxA; z = p.y * sxA + z * cxA;
        const sc = f / (f - z);
        const px = cx + x * R * sc, py = cy + y * R * sc;
        const tw = 0.6 + 0.4 * Math.sin(t * 2 + p.tw);
        ctx.globalAlpha = Math.min(1, (0.4 + 0.6 * (z + 1) / 2) * tw);
        const s = (1.1 + p.s * 1.8) * sc;
        ctx.fillRect(px - s / 2, py - s / 2, s, s);
      }
    });
    ctx.globalAlpha = 1;

    for (let k = 0; k < 3; k++) {
      ctx.strokeStyle = this.alert ? 'rgba(255,120,140,.45)' : (k === 1 ? 'rgba(245,210,122,.35)' : 'rgba(140,225,255,.4)');
      ctx.lineWidth = k === 0 ? 1.6 : 1;
      ctx.beginPath();
      for (let i = 0; i <= 60; i++) {
        const s = -1 + i / 30;
        const phi = s * Math.PI * 0.9 + t * 0.7 * spd + k * 2.1;
        let x = 0.78 * s, y = 0.32 * Math.sin(phi), z = 0.32 * Math.cos(phi);
        let X = x * cyA - z * syA, Z = x * syA + z * cyA;
        let Y = y * cxA - Z * sxA; Z = y * sxA + Z * cxA;
        const sc = f / (f - Z), px = cx + X * R * sc, py = cy + Y * R * sc;
        i ? ctx.lineTo(px, py) : ctx.moveTo(px, py);
      }
      ctx.stroke();
    }

    const ring = this.alert ? CRIT : '#5fd4ff';
    ctx.strokeStyle = ring; ctx.globalAlpha = 0.2; ctx.lineWidth = 1; this._arc(cx, cy, R * 1.12, 0, 6.283);
    ctx.globalAlpha = 0.75; ctx.lineWidth = 3;
    const r1 = t * 0.15 * spd;
    [[0, 0.9], [1.1, 2.3], [2.6, 3.2], [3.5, 5.6]].forEach((s) => this._arc(cx, cy, R * 1.19, s[0] + r1, s[1] + r1));
    ctx.strokeStyle = this.alert ? '#ffd0d8' : '#f5d27a'; ctx.lineWidth = 4; ctx.globalAlpha = 0.85;
    const r2 = -t * 0.25 * spd;
    [[0.3, 0.62], [3.4, 3.9], [5.0, 5.15]].forEach((s) => this._arc(cx, cy, R * 1.26, s[0] + r2, s[1] + r2));
    ctx.strokeStyle = ring; ctx.globalAlpha = 0.35; ctx.lineWidth = 1;
    const r3 = -t * 0.05 * spd;
    ctx.beginPath();
    for (let i = 0; i < 120; i++) {
      const a = r3 + (i * 6.283) / 120, l = i % 10 === 0 ? 10 : 5;
      ctx.moveTo(cx + Math.cos(a) * R * 1.33, cy + Math.sin(a) * R * 1.33);
      ctx.lineTo(cx + Math.cos(a) * (R * 1.33 + l), cy + Math.sin(a) * (R * 1.33 + l));
    }
    ctx.stroke(); ctx.globalAlpha = 1;

    this.sats = this._satPositions(G, t);
    ctx.font = '500 12px Saira, sans-serif';
    this.sats.forEach((s, i) => {
      const A = this.AREAS[s.k];
      const critical = A.critical;
      const col = critical ? CRIT : (A.attention ? '#ffc93d' : A.color);
      const ex = cx + Math.cos(s.a) * R * 1.12, ey = cy + Math.sin(s.a) * R * 1.12;
      const mx = (ex + s.x) / 2 - Math.sin(s.a) * 24, my = (ey + s.y) / 2 + Math.cos(s.a) * 24;
      ctx.globalAlpha = 0.4; ctx.strokeStyle = col; ctx.lineWidth = 1;
      ctx.beginPath(); ctx.moveTo(ex, ey); ctx.quadraticCurveTo(mx, my, s.x, s.y); ctx.stroke();
      // Travels satellite -> ring over ~4.5s, then wraps back to start. The wrap itself
      // is instant (p resets 1 -> 0), which used to be a visible "teleport" snap every
      // couple of seconds -- fading the dot out at both ends of its run (sin envelope,
      // zero exactly at p=0 and p=1) hides that reset instead of slowing it down.
      const p = (t * 0.22 + i * 0.21) % 1, q = 1 - p;
      const dx = q * q * s.x + 2 * q * p * mx + p * p * ex, dy = q * q * s.y + 2 * q * p * my + p * p * ey;
      ctx.globalAlpha = 0.9 * Math.sin(Math.PI * p); ctx.fillStyle = col; ctx.beginPath(); ctx.arc(dx, dy, 2, 0, 6.283); ctx.fill();
      const hot = this.hover === s.k;
      ctx.globalAlpha = 1;
      ctx.lineWidth = 1.5; ctx.strokeStyle = col; this._arc(s.x, s.y, hot ? 15 : 12, 0, 6.283);
      ctx.lineWidth = 2; const ra = t * (critical ? 2.5 : 0.8) + i;
      this._arc(s.x, s.y, hot ? 21 : 18, ra, ra + 1.4);
      if (critical) { const pr = (t * 1.2) % 1; ctx.globalAlpha = (1 - pr) * 0.8; ctx.lineWidth = 1; this._arc(s.x, s.y, 14 + pr * 26, 0, 6.283); ctx.globalAlpha = 1; }
      ctx.fillStyle = col; ctx.beginPath(); ctx.arc(s.x, s.y, 4.5, 0, 6.283); ctx.fill();
      ctx.globalCompositeOperation = 'source-over';
      const right = Math.cos(s.a) > -0.2;
      ctx.textAlign = right ? 'left' : 'right';
      const lx = s.x + (right ? 24 : -24);
      ctx.fillStyle = '#ffffff'; ctx.font = '500 13px Saira, sans-serif';
      ctx.fillText(A.label.toUpperCase(), lx, s.y - 2);
      ctx.fillStyle = critical ? '#ff8da0' : '#9fb8d8'; ctx.font = '400 11px "JetBrains Mono", monospace';
      ctx.fillText(A.status || '', lx, s.y + 14);
      ctx.globalCompositeOperation = 'lighter';
    });
    ctx.globalAlpha = 1;

    for (let i = this.comets.length - 1; i >= 0; i--) {
      const c = this.comets[i];
      if (this.running) c.p += dt * c.v;
      if (c.p >= 1) { this.comets.splice(i, 1); this.boost = Math.min(0.5, (this.boost || 0) + 0.006); continue; }
      ctx.fillStyle = this.alert ? CRIT : c.col;
      for (let k = 0; k < 4; k++) {
        const p = Math.max(0, c.p - k * 0.025), q = 1 - p;
        const x = q * q * c.x + 2 * q * p * c.mx + p * p * cx, y = q * q * c.y + 2 * q * p * c.my + p * p * cy;
        ctx.globalAlpha = (1 - k / 4) * 0.9 * (1 - c.p * 0.4);
        const sz = 2.4 - k * 0.4;
        ctx.fillRect(x - sz / 2, y - sz / 2, sz, sz);
      }
    }
    ctx.globalAlpha = 1;
    ctx.globalCompositeOperation = 'source-over';
  }
}
