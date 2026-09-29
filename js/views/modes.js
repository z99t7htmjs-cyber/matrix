import { escapeHtml } from '../utils/format.js';
import { formatWhen } from '../components/widgets.js';
import { getJson, post } from '../services/api.js';
import { quip } from '../utils/personaQuips.js';

/**
 * Modes: one-click Game / Homework / Battery switches, entirely as you
 * configure them. The only view where Matrix changes a setting instead of
 * just pointing at it -- so every apply asks for confirmation first, with
 * the exact list of changes it's about to make.
 */
export class ModesView {
  constructor(root) {
    this.root = root;
    this.editing = null;
    this.data = null;
    root.addEventListener('click', (e) => this.onClick(e));
    root.addEventListener('submit', (e) => this.onSubmit(e));
  }

  async show() {
    try {
      this.data = await getJson('/api/modes');
    } catch {
      this.data = null;
    }
    this.render();
  }

  status(text) {
    const el = this.root.querySelector('[data-ref="status"]');
    if (el) el.textContent = text;
  }

  async onClick(e) {
    const applyBtn = e.target.closest('[data-mode-apply]');
    const configBtn = e.target.closest('[data-mode-config]');
    const cancelBtn = e.target.closest('[data-mode-cancel]');
    const normalBtn = e.target.closest('[data-mode-normal]');
    if (applyBtn) return this.apply(applyBtn.dataset.modeApply);
    if (normalBtn) return this.normal();
    if (configBtn) {
      this.editing = configBtn.dataset.modeConfig;
      this.render();
    } else if (cancelBtn) {
      this.editing = null;
      this.render();
    }
  }

  async apply(id) {
    try {
      const { changes } = await post('/api/modes', { action: 'preview', id });
      if (!confirm(`This will:\n\n${changes.map((c) => `• ${c}`).join('\n')}\n\nApply these changes?`)) return;
      const result = await post('/api/modes', { action: 'apply', id });
      await this.show();
      const personaOn = window.__matrixState?.meta?.personaEnabled;
      this.status(`${personaOn ? quip('modeApplied') : `Applied ${result.name}`}: ${result.changes.join('; ')}`);
    } catch (err) {
      this.status(err.message);
    }
  }

  async normal() {
    if (!confirm("Put the power plan and Game Mode back to how they were before the last mode?\n\n"
      + "Apps that were closed or opened aren't touched -- Windows doesn't remember what was open before.")) return;
    try {
      const result = await post('/api/modes', { action: 'normal' });
      await this.show();
      this.status(result.changes.join('; '));
    } catch (err) {
      this.status(err.message);
    }
  }

  async onSubmit(e) {
    e.preventDefault();
    const form = e.target.closest('form[data-mode-form]');
    if (!form || !this.data) return;
    const id = form.dataset.modeForm;
    const fd = new FormData(form);
    const gameMode = fd.get('gameMode');
    const modes = this.data.modes.map((m) => (m.id !== id ? m : {
      ...m,
      name: (fd.get('name') || '').toString().trim() || m.name,
      powerPlan: fd.get('powerPlan') || null,
      gameMode: gameMode === '' ? null : gameMode === 'on',
      closeApps: splitList(fd.get('closeApps')),
      openApps: splitList(fd.get('openApps')),
    }));
    try {
      const result = await post('/api/modes', { action: 'save', modes });
      this.data.modes = result.modes;
      this.editing = null;
      this.render();
    } catch (err) {
      this.status(err.message);
    }
  }

  render() {
    if (!this.data) {
      this.root.innerHTML = '<header class="view-head"><h1>Modes</h1></header><p class="empty">Couldn\'t load modes.</p>';
      return;
    }
    const { supported, modes, modeState, schemes } = this.data;
    const head = `
      <header class="view-head">
        <h1>Modes</h1>
        <p class="dim">One-click switches for what you set up below. Matrix always shows the exact changes first.</p>
        <p><span data-ref="status" class="ok-text"></span></p>
      </header>`;
    if (!supported) {
      this.root.innerHTML = `${head}<p class="empty">Modes work on Windows only.</p>`;
      return;
    }
    const active = modeState.active ? modes.find((m) => m.id === modeState.active) : null;
    this.root.innerHTML = `
      ${head}
      ${active ? `
        <p class="hint">Active: <strong>${escapeHtml(active.name)}</strong> since ${formatWhen(modeState.appliedAt)}.
          <button class="btn btn--ghost btn--small" type="button" data-mode-normal>Back to normal</button></p>` : ''}
      <div class="cards">${modes.map((m) => this.card(m, schemes)).join('')}</div>`;
  }

  card(mode, schemes) {
    const summary = [
      mode.powerPlan ? `Power plan → ${mode.powerPlan}` : null,
      mode.gameMode == null ? null : `Game Mode → ${mode.gameMode ? 'on' : 'off'}`,
      mode.closeApps.length ? `Close: ${mode.closeApps.join(', ')}` : null,
      mode.openApps.length ? `Open: ${mode.openApps.join(', ')}` : null,
    ].filter(Boolean);
    const body = this.editing === mode.id ? this.form(mode, schemes) : `
      ${summary.length
        ? `<ul class="plain-list plain-list--notes"><li>${summary.map(escapeHtml).join('</li><li>')}</li></ul>`
        : '<p class="empty">Nothing configured yet -- click Configure.</p>'}
      <div class="form-actions">
        <button class="btn btn--primary btn--small" type="button" data-mode-apply="${mode.id}" ${summary.length ? '' : 'disabled'}>Apply</button>
        <button class="btn btn--ghost btn--small" type="button" data-mode-config="${mode.id}">Configure</button>
      </div>`;
    return `<article class="card"><header class="card-head"><h3>${escapeHtml(mode.name)}</h3></header>${body}</article>`;
  }

  form(mode, schemes) {
    const options = ['<option value="">Don\'t change</option>', ...schemes.map((s) =>
      `<option value="${escapeHtml(s)}" ${mode.powerPlan === s ? 'selected' : ''}>${escapeHtml(s)}</option>`)].join('');
    return `
      <form data-mode-form="${mode.id}" autocomplete="off">
        <label class="field"><span>Name</span><input name="name" maxlength="40" value="${escapeHtml(mode.name)}"></label>
        <label class="field"><span>Power plan</span><select name="powerPlan">${options}</select></label>
        <label class="field"><span>Game Mode</span>
          <select name="gameMode">
            <option value="" ${mode.gameMode == null ? 'selected' : ''}>Don't change</option>
            <option value="on" ${mode.gameMode === true ? 'selected' : ''}>Turn on</option>
            <option value="off" ${mode.gameMode === false ? 'selected' : ''}>Turn off</option>
          </select>
        </label>
        <label class="field"><span>Apps to close (comma separated, e.g. Steam.exe, Discord.exe)</span>
          <input name="closeApps" value="${escapeHtml(mode.closeApps.join(', '))}"></label>
        <label class="field"><span>Apps to open (comma separated -- a path, or a name Windows can find, like notepad)</span>
          <input name="openApps" value="${escapeHtml(mode.openApps.join(', '))}"></label>
        <div class="form-actions">
          <button class="btn btn--primary btn--small" type="submit">Save</button>
          <button class="btn btn--ghost btn--small" type="button" data-mode-cancel>Cancel</button>
        </div>
      </form>`;
  }
}

function splitList(value) {
  return (value || '').toString().split(',').map((v) => v.trim()).filter(Boolean);
}
