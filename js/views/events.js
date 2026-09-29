import { escapeHtml, formatInline } from '../utils/format.js';
import { card, daysSince, formatWhen } from '../components/widgets.js';

/** Crashes & events: blue screens, unexpected restarts, app crashes and hardware errors from Windows' logs. */
export function renderEvents(root, state) {
  const events = state.events;
  const plan = state.plans?.crashes || {};
  const head = `
    <header class="view-head">
      <h1>Crashes &amp; events</h1>
      <p class="dim">From Windows' own logs: the last 30 days of crashes, 14 days of app problems.
        ${events.checkedAt ? `Checked ${formatWhen(events.checkedAt)}.` : ''}</p>
      <div class="view-actions">
        <button class="btn btn--ghost btn--small" type="button" data-open="reliability">Reliability Monitor</button>
        <button class="btn btn--ghost btn--small" type="button" data-open="eventviewer">Event Viewer</button>
      </div>
    </header>`;

  if (!events.supported) {
    root.innerHTML = `${head}<p class="empty">Event logs are read on Windows only.</p>`;
    return;
  }
  if (!events.checkedAt) {
    root.innerHTML = `${head}<p class="empty">Reading Windows event logs…</p>`;
    return;
  }

  const crashes = events.crashes || [];
  const blue = crashes.filter((c) => c.kind === 'bluescreen').length;
  const appTotal = (events.apps || []).reduce((sum, a) => sum + a.crashes + a.hangs, 0);
  const hardware = (events.hardware || []).filter((h) => !h.corrected);

  root.innerHTML = `
    ${head}
    <div class="cards">
      ${card('Summary', `
        <div class="big-stats">
          <div class="${crashes.filter((c) => daysSince(c.time) <= 7).length ? 'bad-text' : 'ok-text'}">
            <strong>${crashes.length}</strong><span>crashes / unexpected restarts</span></div>
          <div class="${blue ? 'bad-text' : ''}"><strong>${blue}</strong><span>blue screens</span></div>
          <div class="${appTotal ? 'warn-text' : ''}"><strong>${appTotal}</strong><span>app crashes &amp; freezes</span></div>
          <div class="${hardware.length ? 'bad-text' : ''}"><strong>${hardware.length}</strong><span>hardware errors</span></div>
        </div>
        <p class="hint">Last start-up: ${formatWhen(events.lastBoot)}.</p>`, { wide: true })}
      ${plan.steps ? card('Repair progress', repairProgress(plan), { wide: true }) : ''}
      ${card('System crashes', crashList(crashes, plan.fixAt), { wide: true })}
      ${card('Apps that crashed or froze', appTable(events.apps))}
      ${card('Hardware errors', hardwareList(events.hardware))}
      ${events.minidumps?.length ? card('Crash dump files', `
        <ul class="plain-list">${events.minidumps.map((d) => `<li><span class="mono">${escapeHtml(d.name)}</span> <span class="dim">${formatWhen(d.time)}</span></li>`).join('')}</ul>
        <p class="hint">Saved in C:\\Windows\\Minidump. Tools like WinDbg or BlueScreenView read them to name the driver that crashed.</p>`) : ''}
    </div>`;
}

function crashList(crashes, fixAt) {
  if (!crashes.length) {
    return '<div class="all-clear all-clear--small"><div class="all-clear-mark">✓</div><p>No crashes or unexpected shutdowns in the last 30 days.</p></div>';
  }
  return `<ul class="alerts">${crashes.map((c) => `
    <li class="alert alert--${c.kind === 'bluescreen' ? 'high' : 'medium'} ${fixAt && new Date(c.time).getTime() / 1000 < fixAt ? 'is-dim' : ''}">
      <div class="alert-head">
        <span class="sev-tag">${c.kind === 'bluescreen' ? 'blue screen' : 'restart'}</span>
        <span class="alert-title">${escapeHtml(c.title)}</span>
      </div>
      <p class="alert-detail">${formatInline(c.advice)}</p>
      <div class="row-actions">
        <time class="alert-time">${formatWhen(c.time)}${c.code ? ` · stop code ${escapeHtml(c.code)}` : ''}${fixAt && new Date(c.time).getTime() / 1000 < fixAt ? ' · before your last repair' : ''}</time>
        <button class="ask-link" type="button"
          data-ask="${escapeHtml(`My PC had a crash: ${c.title}${c.code ? ` (stop code ${c.code})` : ''} on ${formatWhen(c.time)}. What usually causes this and what should I check first?`)}">Ask Matrix about this →</button>
      </div>
    </li>`).join('')}</ul>`;
}

function appTable(apps) {
  if (!apps?.length) return '<p class="empty">No app crashes or freezes in the last 14 days.</p>';
  return `
    <ul class="app-crashes">${apps.map((a) => `
      <li>
        <div class="app-crash-head">
          <strong>${escapeHtml(a.name)}</strong>
          ${a.helper ? '<span class="helper-tag">Windows helper</span>' : ''}
          <span class="dim">${a.crashes ? `${a.crashes} crash${a.crashes > 1 ? 'es' : ''}` : ''}${a.crashes && a.hangs ? ' · ' : ''}${a.hangs ? `${a.hangs} freeze${a.hangs > 1 ? 's' : ''}` : ''} · last ${formatWhen(a.last)}</span>
        </div>
        ${a.helper ? `<p class="hint">${escapeHtml(a.helper)}</p>` : ''}
        ${a.module ? `<p class="app-module">Failing part: <span class="mono">${escapeHtml(a.module)}</span>${a.moduleOwner ? ` · ${escapeHtml(a.moduleOwner)}` : ''}</p>` : ''}
      </li>`).join('')}
    </ul>
    <p class="hint">One-off crashes are normal and not flagged. Matrix only raises an app when it keeps happening (3+ times, or 5+ for Windows helpers).</p>`;
}

function repairProgress(plan) {
  const state = {
    active: '<span class="bad-text">Crashes are still happening</span>',
    watching: plan.restartNeeded ? '<span class="warn-text">Restart to finish the repair</span>'
      : `<span class="ok-text">Watching: no crashes for ${Math.floor(plan.quietDays)} of 3 days</span>`,
  }[plan.state] || '';
  return `
    <p>${state}${plan.fixLabel ? ` · last fix: ${escapeHtml(plan.fixLabel)}` : ''}</p>
    <ol class="plan-steps plan-steps--inline">${plan.steps.map((s, i) => `
      <li class="plan-step ${s.done ? 'is-done' : ''} ${plan.next?.id === s.id ? 'is-next' : ''}">
        <span class="plan-mark">${s.done ? '✓' : i + 1}</span>
        <div class="plan-body"><strong>${escapeHtml(s.title)}</strong>
          ${s.done ? `<span class="dim">${escapeHtml(s.detail || 'Marked done')}</span>` : plan.next?.id === s.id ? '<span class="dim">Next step. See the Advisor for how.</span>' : ''}</div>
      </li>`).join('')}
    </ol>`;
}

function hardwareList(items) {
  if (!items?.length) return '<p class="empty">No hardware errors reported. Good.</p>';
  return `<ul class="alerts">${items.map((h) => `
    <li class="alert alert--${h.fatal ? 'high' : h.corrected ? 'low' : 'medium'}">
      <div class="alert-head"><span class="alert-title">${escapeHtml(h.title)}</span></div>
      <p class="alert-detail">${escapeHtml(h.detail)}</p>
      <time class="alert-time">${formatWhen(h.time)}</time>
    </li>`).join('')}</ul>
    <p class="hint">"Corrected" errors were fixed automatically and are usually harmless unless they happen constantly.</p>`;
}
