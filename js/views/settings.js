import { escapeHtml } from '../utils/format.js';
import { formatWhen } from '../components/widgets.js';
import { getJson, post } from '../services/api.js';

/**
 * Settings: auto-start, household devices, where data lives, stopping Matrix.
 * Drawn when you open it (not on every live update), so switches don't jump.
 */
export class SettingsView {
  constructor(root) {
    this.root = root;
    root.addEventListener('change', (e) => {
      if (e.target.name === 'autostart') this.save({ autostart: e.target.checked });
      if (e.target.name === 'openWindowAtLogin') this.save({ openWindowAtLogin: e.target.checked });
      if (e.target.name === 'personaEnabled') this.save({ personaEnabled: e.target.checked });
      if (e.target.name === 'autoVoiceEnabled') this.save({ autoVoiceEnabled: e.target.checked });
      if (e.target.name === 'livingLook') this.save({ livingLook: e.target.checked });
      if (e.target.name === 'awayFromHome') this.save({ awayFromHome: e.target.checked });
      if (e.target.name === 'autoSwitchPower') this.save({ autoSwitchPower: e.target.checked });
      if (e.target.name === 'showPowerModeDot') this.save({ showPowerModeDot: e.target.checked });
    });
    root.addEventListener('click', (e) => {
      if (e.target.closest('[data-action="quit"]')) this.quit();
    });
  }

  async show() {
    try {
      this.render(await getJson('/api/settings'));
    } catch {
      this.root.innerHTML = '<p class="empty">Couldn\'t load settings.</p>';
    }
  }

  async save(changes) {
    const status = this.root.querySelector('[data-ref="status"]');
    try {
      this.render(await post('/api/settings', changes));
      this.root.querySelector('[data-ref="status"]').textContent = 'Saved ✓';
    } catch (err) {
      if (status) status.textContent = err.message;
    }
  }

  async quit() {
    if (!confirm('Stop Matrix? The dashboard will close its connection. Start it again from the Start menu.')) return;
    try {
      await post('/api/quit', {});
    } catch {
      // the server may close the connection as it stops
    }
  }

  render(s) {
    this.root.innerHTML = `
      <header class="view-head">
        <h1>Settings</h1>
        <p class="dim">Matrix ${escapeHtml(s.version)} <span data-ref="status" class="ok-text"></span></p>
      </header>
      <div class="cards">
        <article class="card">
          <header class="card-head"><h3>Start-up</h3></header>
          ${s.windows ? `
            <label class="switch-row">
              <input type="checkbox" name="autostart" ${s.autostart ? 'checked' : ''}>
              <span><strong>Start Matrix when I sign in</strong>
                <span class="dim">Runs quietly in the background, so it's already watching (and can check for crashes) when you need it.</span></span>
            </label>
            <label class="switch-row ${s.autostart ? '' : 'is-dim'}">
              <input type="checkbox" name="openWindowAtLogin" ${s.openWindowAtLogin ? 'checked' : ''} ${s.autostart ? '' : 'disabled'}>
              <span><strong>Also open the window at sign-in</strong>
                <span class="dim">Off: open it yourself from the Start menu whenever you want.</span></span>
            </label>` : '<p class="empty">Auto-start is available on Windows.</p>'}
        </article>

        <article class="card">
          <header class="card-head"><h3>Household devices</h3></header>
          <p>${s.baselineAt ? `You trusted your network's devices on <strong>${formatWhen(s.baselineAt)}</strong>. Only devices that joined later are flagged as new.`
            : 'Not set yet. Use <strong>Trust all current devices</strong> in the Network view to mark everything on your network now as normal.'}</p>
          <p class="hint">Ignored devices never raise alerts. See them with "Show ignored" in the Network view; click one to stop ignoring it.</p>
          <button class="btn btn--ghost btn--small" type="button" data-go="network">Go to Network</button>
          <hr class="card-rule">
          ${s.homeKnown ? `<p class="hint">Matrix recognizes your home router from that baseline, and already stays quiet about other devices on any other network (school, work, a coffee shop) -- no need to flip this unless it's wrong.</p>`
            : `<p class="hint">Once you've used <strong>Trust all current devices</strong>, Matrix remembers your home router and stays quiet about other devices on any other network automatically.</p>`}
          <label class="switch-row">
            <input type="checkbox" name="awayFromHome" ${s.awayFromHome ? 'checked' : ''}>
            <span><strong>Pause device scanning right now</strong>
              <span class="dim">Use this on a network you don't want watched at all (school, work, a friend's place) -- Matrix keeps watching this PC, but stops reading or listing any other device until you turn it back off.</span></span>
          </label>
        </article>

        <article class="card">
          <header class="card-head"><h3>Ask Matrix</h3></header>
          <p>Local AI model: <span class="mono">${escapeHtml(s.model)}</span>, running through Ollama on this PC.</p>
          <p class="hint">Nothing you ask leaves your computer.</p>
        </article>

        <article class="card">
          <header class="card-head"><h3>Power</h3></header>
          <label class="switch-row">
            <input type="checkbox" name="autoSwitchPower" ${s.autoSwitchPower ? 'checked' : ''}>
            <span><strong>Auto-switch power mode when I plug in or unplug</strong>
              <span class="dim">Off by default -- the one setting that lets Matrix change something with no click
              in the moment. On: plugging in applies Desktop mode (High performance, nothing throttled); unplugging
              applies Locked-down mode (a more conservative plan, closes the RGB/lighting stack). Every switch still
              shows a notification, same as if you'd clicked it yourself. Edit either mode, including which apps
              close, from the Modes view.</span></span>
          </label>
          <label class="switch-row">
            <input type="checkbox" name="showPowerModeDot" ${s.showPowerModeDot ? 'checked' : ''}>
            <span><strong>Show the Desktop/Locked-down indicator</strong>
              <span class="dim">A small dot near the top of the app showing which power mode applies right now.</span></span>
          </label>
        </article>

        <article class="card">
          <header class="card-head"><h3>Look &amp; voice</h3></header>
          <label class="switch-row">
            <input type="checkbox" name="livingLook" ${s.livingLook ? 'checked' : ''}>
            <span><strong>Living look</strong>
              <span class="dim">The animated Overview: a living core, flowing background, orbiting status. Off: the plain card grid.</span></span>
          </label>
          <label class="switch-row">
            <input type="checkbox" name="personaEnabled" ${s.personaEnabled ? 'checked' : ''}>
            <span><strong>ARGUS &amp; MOMUS</strong>
              <span class="dim">Matrix's voice on Advisor cards, the digest and chat. Off: plain, unvoiced text.</span></span>
          </label>
          <label class="switch-row">
            <input type="checkbox" name="autoVoiceEnabled" ${s.autoVoiceEnabled ? 'checked' : ''}>
            <span><strong>Read critical alerts aloud automatically</strong>
              <span class="dim">🔊 Read aloud buttons work regardless of this setting -- this only controls automatic reading.</span></span>
          </label>
        </article>

        <article class="card">
          <header class="card-head"><h3>Your data</h3></header>
          <p class="hint">Device names, trusted and ignored devices, settings and the log file live here. Updating Matrix never touches this folder.</p>
          <p class="mono path">${escapeHtml(s.dataFolder)}</p>
          ${s.windows ? '<button class="btn btn--ghost btn--small" type="button" data-open="datafolder">Open data folder</button>' : ''}
          <p class="hint">Program folder: <span class="mono">${escapeHtml(s.appFolder)}</span></p>
        </article>

        <article class="card">
          <header class="card-head"><h3>Stop Matrix</h3></header>
          <p class="hint">Closing the window leaves Matrix watching in the background. This stops it completely until you start it again from the Start menu (or your next sign-in, if auto-start is on).</p>
          <button class="btn btn--ghost btn--small danger-btn" type="button" data-action="quit">Stop Matrix</button>
        </article>
      </div>`;
  }
}
