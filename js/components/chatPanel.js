import { escapeHtml } from '../utils/format.js';
import { renderMarkdown } from '../utils/markdown.js';

/**
 * "Ask Matrix": a typed chat with the local AI model (via the Matrix server
 * and Ollama). Answers stream in word by word; the server adds a summary of
 * the live dashboard to every question, so the model sees current readings.
 */
const SUGGESTIONS = [
  'Why is my PC slow right now?',
  'Is anything on my network suspicious?',
  'What should I fix first?',
  'Explain my Windows health in plain English',
];

export class ChatPanel {
  constructor(root, { getAlerts } = {}) {
    this.root = root;
    this.getAlerts = getAlerts || (() => new Map());
    this.messages = []; // { role, content, thinking?, error?, stopped? }
    this.controller = null; // AbortController while an answer is streaming

    root.innerHTML = `
      <div class="chat-status" data-ref="status"><span class="status-dot"></span><span>Checking AI…</span></div>
      <div class="chat-log" data-ref="log" aria-live="polite"></div>
      <form class="chat-form" data-ref="form">
        <textarea name="question" rows="2" maxlength="2000"
          placeholder="Ask about your PC, Windows or network…  (Enter to send)"></textarea>
        <div class="chat-controls">
          <label class="think-toggle"><input type="checkbox" name="think"> Deep think <span class="dim">(slower)</span></label>
          <button class="btn btn--ghost btn--small" type="button" data-action="clear">Clear</button>
          <button class="btn btn--ghost btn--small" type="button" data-action="stop" hidden>Stop</button>
          <button class="btn btn--primary btn--small" type="submit" data-ref="send">Send</button>
        </div>
      </form>`;

    const ref = (name) => root.querySelector(`[data-ref="${name}"]`);
    this.status = ref('status');
    this.log = ref('log');
    this.form = ref('form');
    this.input = this.form.elements.question;

    this.form.addEventListener('submit', (e) => {
      e.preventDefault();
      this.ask(this.input.value);
    });
    // Enter sends; Shift+Enter makes a new line.
    this.input.addEventListener('keydown', (e) => {
      if (e.key === 'Enter' && !e.shiftKey) {
        e.preventDefault();
        this.form.requestSubmit();
      }
    });
    root.addEventListener('click', (e) => {
      const button = e.target.closest('[data-action]');
      if (!button) return;
      if (button.dataset.action === 'suggest') this.ask(button.dataset.text);
      if (button.dataset.action === 'clear') this.clear();
      if (button.dataset.action === 'stop') this.controller?.abort();
    });

    // If you scroll while an answer is arriving, stop steering the scroll position.
    for (const evt of ['wheel', 'touchmove', 'keydown']) {
      this.log.addEventListener(evt, () => (this.pinTarget = null), { passive: true });
    }

    this.renderLog();
    this.checkStatus();
    setInterval(() => this.checkStatus(), 30000);
  }

  /** Ask the server whether Ollama is running and the model is downloaded. */
  async checkStatus() {
    let text;
    let level;
    try {
      const s = await (await fetch('/api/ai', { cache: 'no-store' })).json();
      if (!s.running) [text, level] = ['Ollama isn\'t running. Open it from the Start menu.', 'danger'];
      else if (!s.installed) [text, level] = [`Model not downloaded. Run: ollama pull ${s.model}`, 'warn'];
      else [text, level] = [`Local AI ready · ${s.model} · private, on this PC`, 'ok'];
    } catch {
      [text, level] = ['Matrix server not reachable', 'danger'];
    }
    this.status.dataset.level = level;
    this.status.lastElementChild.textContent = text;
  }

  focus() {
    this.input.focus();
  }

  clear() {
    this.controller?.abort();
    this.messages = [];
    this.renderLog();
  }

  ask(question) {
    const text = (question || '').trim();
    if (!text || this.controller) return;
    this.input.value = '';
    this.messages.push({ role: 'user', content: text });
    this.messages.push({ role: 'assistant', content: '', thinking: '' });
    this.renderLog();
    // Scroll so your question sits at the top, then hold it there while the answer
    // grows below (no chasing the bottom of a long answer).
    const questionEl = this.log.children[this.log.children.length - 2];
    this.pinTarget = questionEl.offsetTop - 12;
    this.followPin();
    this.stream(this.form.elements.think.checked);
  }

  async stream(think) {
    const reply = this.messages[this.messages.length - 1];
    // Earlier turns give the model context; skip failed or empty answers.
    const history = this.messages
      .slice(0, -1)
      .filter((m) => m.content && !m.error)
      .map(({ role, content }) => ({ role, content }));

    this.controller = new AbortController();
    this.setBusy(true);
    try {
      const response = await fetch('/api/chat', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ messages: history, think }),
        signal: this.controller.signal,
      });
      if (!response.ok) {
        const body = await response.json().catch(() => ({}));
        throw new Error(body.error || `Request failed (${response.status})`);
      }

      // The server sends one JSON event per line as the answer is generated.
      const reader = response.body.getReader();
      const decoder = new TextDecoder();
      let buffer = '';
      for (;;) {
        const { value, done } = await reader.read();
        if (done) break;
        buffer += decoder.decode(value, { stream: true });
        const lines = buffer.split('\n');
        buffer = lines.pop(); // keep a partial last line for the next read
        for (const line of lines) {
          if (!line.trim()) continue;
          const event = JSON.parse(line);
          if (event.type === 'thinking') reply.thinking += event.text;
          if (event.type === 'content') reply.content += event.text;
          if (event.type === 'error') reply.error = event.text;
        }
        this.updateLast();
      }
    } catch (err) {
      if (err.name === 'AbortError') reply.stopped = true;
      else reply.error = err.message || 'Could not reach the Matrix server.';
    } finally {
      this.controller = null;
      this.setBusy(false);
      this.updateLast();
    }
  }

  setBusy(busy) {
    this.root.querySelector('[data-action="stop"]').hidden = !busy;
    this.root.querySelector('[data-ref="send"]').disabled = busy;
  }

  // --- rendering ---------------------------------------------------------------

  renderLog() {
    if (this.messages.length === 0) {
      this.log.innerHTML = `
        <div class="chat-welcome">
          <p><strong>Ask anything about this PC, Windows or your network.</strong></p>
          <p class="dim">Matrix gives the AI your live readings with every question. It runs entirely on
            your PC, so nothing leaves this computer.</p>
          <div class="chips">
            ${SUGGESTIONS.map((s) => `<button class="chip" type="button" data-action="suggest" data-text="${escapeHtml(s)}">${escapeHtml(s)}</button>`).join('')}
          </div>
        </div>`;
      return;
    }
    const alerts = this.getAlerts();
    this.log.innerHTML = this.messages.map((m) => `<div class="msg msg--${m.role}">${renderMessage(m, alerts)}</div>`).join('');
  }

  /** Only the last message changes while streaming; redraw just that one. */
  updateLast() {
    const last = this.log.lastElementChild;
    if (!last) return;
    last.innerHTML = renderMessage(this.messages[this.messages.length - 1], this.getAlerts());
    this.followPin();
  }

  /** Scroll toward the question's position, never past it (the answer is short at first). */
  followPin() {
    if (this.pinTarget == null) return;
    this.log.scrollTop = Math.min(this.pinTarget, this.log.scrollHeight - this.log.clientHeight);
  }
}

function renderMessage(m, alerts) {
  if (m.role === 'user') return `<p>${escapeHtml(m.content)}</p>`;

  let html = '';
  if (m.content) html += renderMarkdown(m.content, { alerts });
  else if (!m.error && !m.stopped) {
    html += m.thinking
      ? '<p class="dim">Thinking it through<span class="dots"></span></p>'
      : '<p class="dim">Reading your live data<span class="dots"></span></p>';
  }
  if (m.error) html += `<p class="msg-error">${escapeHtml(m.error)}</p>`;
  if (m.stopped) html += '<p class="dim">(stopped)</p>';
  return html;
}
