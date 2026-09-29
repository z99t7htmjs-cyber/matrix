/**
 * Connection to the Matrix server (server/matrix_server.py).
 *
 * Polls GET /api/state and hands each result to subscribers. When the server
 * can't be reached, subscribers get `null` so the dashboard can say so, and
 * polling continues so it reconnects on its own once the server is back.
 *
 * State shape: { network, system, health, advice, meta }
 * (each part is documented at the top of the matching server module).
 */
const POLL_MS = 3000;

export class LiveDataSource {
  constructor() {
    this.listeners = new Set();
    this.timer = null;
  }

  subscribe(listener) {
    this.listeners.add(listener);
    if (!this.timer) this.poll(0);
    return () => {
      this.listeners.delete(listener);
      if (this.listeners.size === 0) {
        clearTimeout(this.timer);
        this.timer = null;
      }
    };
  }

  /** Fetch again soon (after saving a name, say) instead of waiting for the next regular poll. */
  refreshSoon(delay = 1500) {
    clearTimeout(this.timer);
    this.poll(delay);
  }

  /**
   * Each request finishes before the next is scheduled, so slow responses never
   * pile up. The generation number makes sure only the newest loop keeps going
   * if refreshSoon() restarts polling while a request is still in flight.
   */
  poll(delay) {
    const generation = (this.generation = (this.generation ?? 0) + 1);
    this.timer = setTimeout(async () => {
      let state = null;
      try {
        const response = await fetch('/api/state', { cache: 'no-store' });
        if (response.ok) state = await response.json();
      } catch {
        // server stopped or page opened without it; report offline below
      }
      if (generation !== this.generation) return; // a newer loop has taken over
      // A listener throwing here (a rendering bug hitting a state shape it didn't expect)
      // used to abort this whole callback before reaching poll(POLL_MS) below -- which
      // silently killed polling forever, not just that one frame. Every listener gets run
      // and every exception gets caught so one bad render can't stop the next fetch.
      this.listeners.forEach((fn) => {
        try {
          fn(state);
        } catch (err) {
          console.error('[matrix] a state listener threw; polling continues', err);
        }
      });
      if (this.listeners.size > 0) this.poll(POLL_MS);
    }, delay);
  }
}
