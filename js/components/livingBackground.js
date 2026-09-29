/**
 * The flowing background: a full-page canvas of thin strand bundles that
 * ripple and bend toward the living core, plus short circuit traces with
 * traveling data dots. Ported from design/matrix-living-core.html -- this
 * IS the agreed-on look, not an approximation of it.
 *
 * Panels have no background of their own now ("no boxes" -- see .hud-frame),
 * so this canvas is what everything else visually sits on. It focuses on
 * whatever point the caller sets (the Overview scene's center when that
 * view is open; the viewport center otherwise) via `setFocusEl`.
 */
const REDUCED_MOTION = typeof window.matchMedia === 'function'
  && window.matchMedia('(prefers-reduced-motion: reduce)').matches;

function rnd(a, b) { return a + Math.random() * (b - a); }

export class LivingBackground {
  constructor() {
    this.canvas = document.createElement('canvas');
    this.canvas.className = 'living-bg';
    this.canvas.setAttribute('aria-hidden', 'true');
    document.body.prepend(this.canvas);
    this.ctx = this.canvas.getContext('2d');

    this.enabled = true; // the background itself is always on; only the core widget is optional
    this.userPaused = false;
    this.throttled = false;
    this.alert = false;
    this.focusEl = null;
    this.t = REDUCED_MOTION ? 3 : 0;
    this.last = performance.now();
    this.running = !REDUCED_MOTION;

    this._resize();
    window.addEventListener('resize', () => this._resize());
    document.addEventListener('visibilitychange', () => this._applyRunning());
    this._frame(true);
    if (this.running) requestAnimationFrame((now) => this._loop(now));
  }

  /** Focus the flow toward this element's center (the living-core scene), or null for viewport center. */
  setFocusEl(el) { this.focusEl = el; }

  setCritical(on) { this.alert = on; }
  setUserPaused(paused) { this.userPaused = paused; this._applyRunning(); }
  setThrottled(on) { this.throttled = on; this._applyRunning(); }

  _applyRunning() {
    const shouldRun = !REDUCED_MOTION && !this.userPaused && !this.throttled && document.visibilityState !== 'hidden';
    if (shouldRun === this.running) return;
    this.running = shouldRun;
    this.canvas.classList.toggle('is-paused', !shouldRun);
    if (shouldRun) { this.last = performance.now(); requestAnimationFrame((now) => this._loop(now)); }
  }

  _resize() {
    this.dpr = Math.min(window.devicePixelRatio || 1, 1.5);
    this.w = window.innerWidth;
    this.h = window.innerHeight;
    this.canvas.width = this.w * this.dpr;
    this.canvas.height = this.h * this.dpr;
    this.ctx.setTransform(this.dpr, 0, 0, this.dpr, 0, 0);
    this._buildStrands();
    this._buildTraces();
    this._frame(true);
  }

  _buildStrands() {
    this.strands = [];
    const n = this.w < 700 ? 11 : 18;
    for (let i = 0; i < n; i++) {
      this.strands.push({
        y0: this.h * (0.06 + 0.88 * (i + rnd(-0.3, 0.3)) / n), A: rnd(30, 90), f: rnd(0.0018, 0.0035), f2: rnd(0.004, 0.007),
        sp: rnd(0.5, 1.0), sp2: rnd(0.3, 0.6), ph: rnd(0, 6.28), pull: rnd(0.35, 0.85),
        fibers: this.w < 700 ? 5 : 7, spread: rnd(3, 7), tw: rnd(0.1, 0.22),
        col: Math.random() < 0.1 ? '#f5d27a' : (Math.random() < 0.18 ? '#8c9bff' : '#5fd4ff'),
      });
    }
  }

  _buildTraces() {
    this.traces = [];
    for (let i = 0; i < 8; i++) {
      const left = i % 2 === 0;
      const y = this.h * rnd(0.12, 0.9);
      const x0 = left ? rnd(8, 40) : this.w - rnd(8, 40);
      const dir = left ? 1 : -1;
      const l1 = rnd(60, 160);
      const d = rnd(18, 40) * (Math.random() < 0.5 ? -1 : 1);
      const l2 = rnd(40, 120);
      this.traces.push({ pts: [[x0, y], [x0 + dir * l1, y], [x0 + dir * (l1 + Math.abs(d)), y + d], [x0 + dir * (l1 + Math.abs(d) + l2), y + d]], ph: rnd(0, 6) });
    }
  }

  _focus() {
    if (this.focusEl && this.focusEl.isConnected) {
      const r = this.focusEl.getBoundingClientRect();
      return { x: r.left + r.width / 2, y: r.top + r.height / 2 };
    }
    return { x: this.w * 0.5, y: this.h * 0.42 };
  }

  _frame(still) {
    const now = performance.now();
    // Chrome throttles requestAnimationFrame hard for a window that's visible but not
    // focused -- frames can drop to ~1/sec or slower without the tab ever counting as
    // "hidden". A tight 0.05s clamp turns that into visible slow motion instead of just
    // fewer, larger steps; match the same 0.5s ceiling used in livingCore.js.
    const dt = still ? 0 : Math.min(0.5, (now - this.last) / 1000);
    if (!still) { this.last = now; this.t += dt; }
    this._draw(this.t);
  }

  _loop(now) {
    if (!this.running) return;
    // Do NOT set this.last = now here -- see the matching comment in livingCore.js.
    // _frame() reads its own fresh performance.now() and diffs it against this.last;
    // clobbering this.last with the current frame's own timestamp right before that
    // made dt come out as essentially zero every frame, which is why this crawled.
    this._frame(false);
    requestAnimationFrame((n) => this._loop(n));
  }

  _draw(t) {
    const { ctx, w, h } = this;
    const focus = this._focus();
    const g = ctx.createRadialGradient(focus.x, focus.y, 0, focus.x, focus.y, Math.max(w, h) * 0.75);
    if (this.alert) { g.addColorStop(0, '#3a0c22'); g.addColorStop(0.45, '#1a0614'); g.addColorStop(1, '#07020a'); }
    else { g.addColorStop(0, '#0c3486'); g.addColorStop(0.45, '#061a4c'); g.addColorStop(1, '#020817'); }
    ctx.globalCompositeOperation = 'source-over';
    ctx.fillStyle = g;
    ctx.fillRect(0, 0, w, h);

    ctx.lineWidth = 1;
    this.traces.forEach((tr) => {
      ctx.strokeStyle = this.alert ? 'rgba(255,77,109,.22)' : 'rgba(95,212,255,.22)';
      ctx.beginPath();
      tr.pts.forEach((p, i) => (i ? ctx.lineTo(p[0], p[1]) : ctx.moveTo(p[0], p[1])));
      ctx.stroke();
      const e = tr.pts[tr.pts.length - 1];
      const a = 0.4 + 0.6 * (0.5 + 0.5 * Math.sin(t * 1.5 + tr.ph));
      ctx.fillStyle = this.alert ? `rgba(255,107,133,${a})` : `rgba(140,225,255,${a})`;
      ctx.beginPath();
      ctx.arc(e[0], e[1], 2.5, 0, 6.283);
      ctx.fill();
    });

    ctx.globalCompositeOperation = 'lighter';
    const step = 14;
    const sig = w * 0.22;
    const ts = this.alert ? 1.7 : 1;
    this.strands.forEach((s, si) => {
      const col = this.alert ? '#ff4d6d' : s.col;
      ctx.strokeStyle = col;
      ctx.lineWidth = 1;
      for (let j = 0; j < s.fibers; j++) {
        const o = j - (s.fibers - 1) / 2;
        ctx.globalAlpha = 0.07 + 0.1 * (1 - Math.abs(o) / s.fibers);
        ctx.beginPath();
        for (let x = -40; x <= w + 40; x += step) {
          const wave = x * s.f - t * s.sp * ts + s.ph + o * s.tw;
          let y = s.y0 + s.A * Math.sin(wave) + s.A * 0.4 * Math.sin(x * s.f2 - t * s.sp2 * ts + si + o * s.tw * 1.5);
          y += o * s.spread * (0.6 + 0.6 * Math.sin(x * 0.003 - t * 0.6 * ts + si));
          const d = (x - focus.x) / sig;
          const wgt = Math.exp(-d * d) * s.pull;
          y += (focus.y + (s.y0 - h / 2) * 0.12 - y) * wgt;
          x < -39 ? ctx.moveTo(x, y) : ctx.lineTo(x, y);
        }
        ctx.stroke();
      }
    });
    ctx.globalAlpha = 1;
    ctx.globalCompositeOperation = 'source-over';
  }
}
