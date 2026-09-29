import { escapeHtml, formatInline } from '../utils/format.js';
import { formatWhen } from './widgets.js';
import { renderMarkdown } from '../utils/markdown.js';

/**
 * The Advisor column.
 *
 *   Active items, most urgent first. Each card offers what fits it:
 *     condition  "Check again" (Matrix re-runs the check; it resolves itself when fixed)
 *     choice     "Keep as is" (quiet until the situation changes)
 *     event      "Got it" (quiet until it happens again)
 *     all        Snooze (1 day / 1 week), the fix button, Ask Matrix
 *   Items with a troubleshooting plan show its steps and progress.
 *   A "Set aside" section lists snoozed / kept / acknowledged / archived items,
 *   and "Resolved recently" what was fixed.
 *
 * Buttons use data attributes handled in app.js (data-alert, data-check, data-step…).
 */
const AREA_LABELS = {
  security: 'Security',
  performance: 'Performance',
  maintenance: 'Maintenance',
  network: 'Network',
  stability: 'Stability',
  'tune-up': 'Tune-up',
  setup: 'Setup',
};
const URGENCY_LABELS = { critical: 'Critical', attention: 'Needs attention', fyi: 'FYI' };
const STATUS_LABELS = { snoozed: 'Snoozed', kept: 'Kept as is', acknowledged: 'Seen', archived: 'Archived' };
const PERSONA_LABELS = { argus: 'ARGUS', momus: 'MOMUS' };

export class AdvisorPanel {
  constructor(root) {
    this.root = root;
    this.open = new Set(); // cards whose "How to fix" is expanded, kept across refreshes
    this.sections = new Set();
    root.addEventListener(
      'toggle',
      (e) => {
        const id = e.target.dataset?.adviceId || e.target.dataset?.section;
        if (!id) return;
        const set = e.target.dataset.section ? this.sections : this.open;
        if (e.target.open) set.add(id);
        else set.delete(id);
      },
      true,
    );
  }

  /** busy: ids currently being re-checked ("Checking…"). lastVisit: unix seconds, for NEW badges. */
  render({ advice, handled, resolved, plans }, { busy = new Set(), lastVisit = 0 } = {}) {
    const scroll = this.root.scrollTop;
    const empty = `
      <div class="all-clear">
        <div class="all-clear-mark" aria-hidden="true">✓</div>
        <p><strong>All systems nominal.</strong></p>
        <p class="dim">Matrix keeps checking your PC, Windows and network. New things to look at will show up here.</p>
      </div>`;

    this.root.innerHTML = `
      ${advice.length ? `<ul class="advice-list">${advice.map((a) => this.card(a, plans, busy, lastVisit)).join('')}</ul>` : empty}
      ${handled.length ? `
        <details class="advisor-section" data-section="handled" ${this.sections.has('handled') ? 'open' : ''}>
          <summary>Set aside <span class="count">${handled.length}</span></summary>
          <ul class="mini-list">${handled.map(handledRow).join('')}</ul>
        </details>` : ''}
      ${resolved.length ? `
        <details class="advisor-section" data-section="resolved" ${this.sections.has('resolved') ? 'open' : ''}>
          <summary>Resolved recently <span class="count">${resolved.length}</span></summary>
          <ul class="mini-list">${resolved.map((r) => `
            <li><span class="ok-text">✓ ${r.personaLine ? escapeHtml(r.personaLine) : escapeHtml(r.title)}</span>
              <span class="dim">${formatWhen(new Date(r.resolvedAt * 1000).toISOString())}</span></li>`).join('')}
          </ul>
        </details>` : ''}`;
    this.root.scrollTop = scroll;
  }

  card(a, plans, busy, lastVisit) {
    const plan = a.plan ? plans?.[a.plan] : null;
    const isNew = a.raisedAt && lastVisit && a.raisedAt > lastVisit;
    const steps = !plan && a.steps.length ? `
      <details class="advice-fix" data-advice-id="${escapeHtml(a.id)}" ${this.open.has(a.id) ? 'open' : ''}>
        <summary>How to fix</summary>
        <ol>${a.steps.map((s) => `<li>${formatInline(s)}</li>`).join('')}</ol>
      </details>` : '';

    return `
      <li class="advice advice--${a.urgency}">
        <div class="advice-head">
          <span class="urgency-tag">${URGENCY_LABELS[a.urgency]}</span>
          <span class="advice-area">${escapeHtml(AREA_LABELS[a.area] || a.area)}</span>
          ${isNew ? '<span class="new-tag">New</span>' : ''}
        </div>
        <p class="advice-title">${escapeHtml(a.title)}</p>
        ${a.personaLine ? personaLine(a.persona, a.personaLine) : ''}
        <p class="advice-detail">${escapeHtml(a.detail)}</p>
        ${a.aiNote ? `
          <div class="ai-note">
            <span class="ai-note-label">${PERSONA_LABELS[a.persona] || 'Matrix'} says</span>
            ${renderMarkdown(a.aiNote)}
            ${speakButton(a.persona, a.aiNote)}
          </div>` : ''}
        ${plan && plan.steps ? planBlock(plan, !this.open.has(`${a.id}-plan-closed`), a.id) : ''}
        ${steps}
        <div class="row-actions">
          ${actionButton(a.action)}
          ${lifecycleButtons(a, busy)}
        </div>
        <button class="ask-link" type="button"
          data-ask="${escapeHtml(`Help me with this: ${a.title}. ${a.detail}`)}">Ask Matrix about this →</button>
      </li>`;
  }
}

function lifecycleButtons(a, busy) {
  const buttons = [];
  if (a.check && a.kind !== 'event') {
    buttons.push(busy.has(a.id)
      ? '<button class="btn btn--ghost btn--small" type="button" disabled>Checking…</button>'
      : `<button class="btn btn--ghost btn--small" type="button" data-check="${escapeHtml(a.check)}" data-for="${escapeHtml(a.id)}">Check again</button>`);
  }
  if (a.kind === 'event') buttons.push(`<button class="btn btn--ghost btn--small" type="button" data-alert="acknowledge" data-key="${escapeHtml(a.id)}">Got it</button>`);
  if (a.kind === 'choice') buttons.push(`<button class="btn btn--ghost btn--small" type="button" data-alert="keep" data-key="${escapeHtml(a.id)}">Keep as is</button>`);
  buttons.push(`
    <span class="snooze">
      <span class="dim">Snooze</span>
      <button class="link-btn" type="button" data-alert="snooze" data-days="1" data-key="${escapeHtml(a.id)}">1 day</button>
      <button class="link-btn" type="button" data-alert="snooze" data-days="7" data-key="${escapeHtml(a.id)}">1 week</button>
    </span>`);
  return buttons.join('');
}

function planBlock(plan, open, id) {
  const done = plan.steps.filter((s) => s.done).length;
  const rows = plan.steps.map((s, i) => {
    const isNext = plan.next && s.id === plan.next.id;
    const when = s.doneAt ? formatWhen(new Date(s.doneAt * 1000).toISOString()) : '';
    const undo = s.source === 'you' ? ` · <button class="link-btn" type="button" data-step="${s.id}" data-done="0">undo</button>` : '';
    return `
      <li class="plan-step ${s.done ? 'is-done' : ''} ${isNext ? 'is-next' : ''}">
        <span class="plan-mark" aria-hidden="true">${s.done ? '✓' : i + 1}</span>
        <div class="plan-body">
          <strong>${escapeHtml(s.title)}</strong>
          ${s.done ? `<span class="dim">${escapeHtml(s.detail || 'Marked done')} · ${when}${undo}</span>` : ''}
          ${isNext ? `
            <ol class="plan-how">${s.how.map((h) => `<li>${formatInline(h)}</li>`).join('')}</ol>
            <div class="plan-actions">
              <button class="btn btn--primary btn--small" type="button" data-step="${s.id}" data-done="1">I did this</button>
              ${s.auto ? '<span class="dim">Matrix also notices this by itself.</span>' : ''}
            </div>` : ''}
        </div>
      </li>`;
  }).join('');
  return `
    <details class="plan" ${open ? 'open' : ''}>
      <summary>Troubleshooting plan · ${done} of ${plan.steps.length} steps done</summary>
      <ol class="plan-steps">${rows}</ol>
    </details>`;
}

function handledRow(a) {
  const until = a.status === 'snoozed' && a.until ? ` until ${formatWhen(new Date(a.until * 1000).toISOString())}` : '';
  return `
    <li>
      <span>${escapeHtml(a.title)}</span>
      <span class="dim">${STATUS_LABELS[a.status] || a.status}${until} ·
        <button class="link-btn" type="button" data-alert="restore" data-key="${escapeHtml(a.id)}">bring back</button></span>
    </li>`;
}

function personaLine(voice, text) {
  return `
    <p class="persona-line persona-line--${voice || 'argus'}">
      <span class="persona-tag">${PERSONA_LABELS[voice] || 'ARGUS'}</span> ${escapeHtml(text)}
    </p>`;
}

function speakButton(voice, text) {
  return `<button class="link-btn speak-btn" type="button" data-speak="${escapeHtml(text)}" data-voice="${voice || 'argus'}" title="Read aloud">🔊 Read aloud</button>`;
}

/** The card's main button: open the Windows page that fixes it, or jump to a Matrix view. */
function actionButton(action) {
  if (!action) return '';
  const attr = action.open ? `data-open="${escapeHtml(action.open)}"` : `data-go="${escapeHtml(action.view)}"`;
  return `<button class="btn btn--ghost btn--small" type="button" ${attr}>${escapeHtml(action.label)}</button>`;
}
