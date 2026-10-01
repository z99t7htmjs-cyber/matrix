import { escapeHtml } from '../utils/format.js';
import { card, formatMb, statusRow } from '../components/widgets.js';

/** Tune-up: startup apps, preinstalled extras, big apps, power settings and what changed. */
export function renderTuneup(root, state) {
  const t = state.tuneup;
  const head = `
    <header class="view-head">
      <h1>Tune-up</h1>
      <p class="dim">Suggestions only: Matrix opens the right Windows page and you decide. It sticks to settings Microsoft supports.</p>
    </header>`;
  if (!t.supported) {
    root.innerHTML = `${head}<p class="empty">Tune-up checks run on Windows only.</p>`;
    return;
  }
  if (!t.checked) {
    root.innerHTML = `${head}<p class="empty">Looking through apps and settings… this takes up to a minute after Matrix starts.</p>`;
    return;
  }
  root.innerHTML = `
    ${head}
    <div class="cards">
      ${card('Settings worth checking', settingsRows(t))}
      ${t.power ? card('Battery vs. plugged in', powerRows(t.power, t.batteryHealth)) : ''}
      ${state.drives ? card('Drive health', driveRows(state.drives)) : ''}
      ${state.thermalTrend?.supported ? card('Cooling trend', thermalRows(state.thermalTrend)) : ''}
      ${state.health?.bios ? card('System', systemFacts(state.health.bios)) : ''}
      ${card('Free up space', cleanupBody(state.cleanup), { wide: true })}
      ${card('What changed', changesBody(state.changes), { wide: true })}
      ${card('Preinstalled extras', flagged(t.flagged), { extra: '<button class="btn btn--ghost btn--small card-btn" type="button" data-open="apps">Installed apps</button>' })}
      ${card('Starts with Windows', startup(t.startup), { wide: true, extra: '<button class="btn btn--ghost btn--small card-btn" type="button" data-open="startupapps">Startup settings</button>' })}
      ${card('Largest programs', largest(t.largest), { extra: '<button class="btn btn--ghost btn--small card-btn" type="button" data-open="apps">Installed apps</button>' })}
    </div>`;
}

function settingsRows(t) {
  const rows = [
    statusRow(t.gameMode, 'Game Mode', t.gameMode ? 'On' : 'Off', 'gamemode'),
    statusRow(t.gpuScheduling == null ? null : t.gpuScheduling, 'GPU scheduling',
      t.gpuScheduling == null ? 'Not reported' : t.gpuScheduling ? 'On' : 'Off', 'graphics'),
    statusRow(t.storageSense, 'Storage Sense', t.storageSense ? 'On: cleans up automatically' : 'Off', 'storage'),
    statusRow((t.tempMb ?? 0) < 2000, 'Temporary files', formatMb(t.tempMb), 'storage'),
    statusRow(null, 'Power plan', t.powerPlan || 'Unknown', 'power'),
  ];
  return `<ul class="health health--buttons">${rows.join('')}</ul>
    <p class="hint">On ROG laptops, performance modes (Silent / Performance / Turbo) live in Armoury Crate, not Windows.
    See <a href="#modes" data-go="modes">Modes</a> for one-click switches you set up yourself.</p>`;
}

function driveRows(drives) {
  if (!drives.supported) return '<p class="empty">Drive health checks run on Windows only.</p>';
  if (!drives.checkedAt) return '<p class="empty">Reading drive health… this takes a minute after Matrix starts.</p>';
  if (!drives.disks?.length) return '<p class="empty">No drives reported.</p>';
  const rows = drives.disks.map((d) => {
    const name = d.model || `Drive ${d.id}`;
    const status = d.healthStatus || 'Unknown';
    const ok = status === 'Healthy';
    const bits = [status];
    if (d.wearPercent != null) bits.push(`${d.wearPercent}% worn`);
    if (d.tempC != null) bits.push(`${d.tempC}°C`);
    return statusRow(status === 'Unknown' ? null : ok, name, bits.join(' · '), 'storage');
  });
  return `<ul class="health health--buttons">${rows.join('')}</ul>
    <p class="hint">This is Windows' own overall read on each physical drive (not the same thing as free space).
    Wear % and temperature aren't available on every drive.</p>`;
}

function thermalRows(trend) {
  if (!trend.hasEnoughHistory) {
    const left = Math.max(0, trend.minDaysNeeded - trend.sampleDays);
    const latest = trend.latestIdleTempC != null
      ? `Coolest idle reading so far: ${trend.latestIdleTempC}°C (${trend.sampleDays} day${trend.sampleDays === 1 ? '' : 's'} recorded).`
      : "Matrix hasn't caught this PC sitting idle yet -- it only samples when CPU and GPU load are both low.";
    return `<p class="empty">${latest} ${left > 0 ? `About ${left} more day${left === 1 ? '' : 's'} of occasional idle time before there's enough history to spot a trend.` : ''}</p>`;
  }
  const risen = trend.risenC;
  const ok = risen < 8;
  const rows = [
    statusRow(ok, 'Resting GPU temperature', `${trend.baselineC}°C → ${trend.recentC}°C over ${trend.sampleDays} days on record`),
  ];
  return `<ul class="health health--buttons">${rows.join('')}</ul>
    <p class="hint">Sampled only while the PC is basically idle (low CPU and GPU load), once a day at most -- a rough
    stand-in for fan/dust health since Matrix has no way to read actual fan RPM. Room temperature and where the
    laptop sits can shift this too, so treat a small change as noise.</p>`;
}

function powerRows(power, health) {
  const minutes = (v) => (v == null ? '—' : v === 0 ? 'Never' : `${v} min`);
  const rows = `
    <table class="data-table">
      <thead><tr><th></th><th>Plugged in</th><th>On battery</th></tr></thead>
      <tbody>
        <tr><td>Screen turns off</td><td class="num">${minutes(power.screenTimeoutMin.ac)}</td><td class="num">${minutes(power.screenTimeoutMin.dc)}</td></tr>
        <tr><td>PC sleeps</td><td class="num">${minutes(power.sleepTimeoutMin.ac)}</td><td class="num">${minutes(power.sleepTimeoutMin.dc)}</td></tr>
        <tr><td>Max processor power</td>
          <td class="num">${power.processorMaxPercent.ac == null ? '—' : `${power.processorMaxPercent.ac}%`}</td>
          <td class="num">${power.processorMaxPercent.dc == null ? '—' : `${power.processorMaxPercent.dc}%`}</td></tr>
      </tbody>
    </table>
    ${power.maxedOutOnBattery ? '<p class="hint bad-text">The processor isn\'t capped on battery, so it drains just as fast unplugged.</p>' : ''}
    <button class="btn btn--ghost btn--small card-btn" type="button" data-open="power">Power settings</button>`;
  if (!health) return rows;
  const tone = health.healthPercent >= 80 ? 'ok-text' : health.healthPercent >= 60 ? 'warn-text' : 'bad-text';
  return `${rows}
    <div class="facts" style="margin-top:12px">
      <div><span>Battery health</span><strong class="${tone}">${health.healthPercent}% of new</strong></div>
      ${health.cycleCount ? `<div><span>Charge cycles</span><strong>${health.cycleCount}</strong></div>` : ''}
    </div>`;
}

function systemFacts(bios) {
  return `
    <div class="facts">
      <div><span>BIOS version</span><strong>${escapeHtml(bios.version || 'Unknown')}</strong></div>
      ${bios.releaseDate ? `<div><span>BIOS date</span><strong>${escapeHtml(bios.releaseDate)}</strong></div>` : ''}
    </div>
    <p class="hint">What's installed, not whether something newer exists -- same spirit as the driver reminder above.</p>`;
}

function cleanupBody(cleanup) {
  if (!cleanup) {
    return `<p class="empty">See how much space Windows' own temporary files are using.</p>
      <button class="btn btn--ghost btn--small" type="button" data-scan-cleanup>Scan</button>`;
  }
  if (!cleanup.supported) return '<p class="empty">Disk cleanup runs on Windows only.</p>';
  const item = cleanup.items[0];
  const mb = Math.round((item.sizeBytes / 1_000_000) * 10) / 10;
  return `
    <ul class="plain-list">
      <li><strong>${escapeHtml(item.label)}</strong><span>${mb} MB across ${item.fileCount} files</span></li>
    </ul>
    <p class="hint">${escapeHtml(item.detail)}</p>
    <div class="row-actions">
      <button class="btn btn--ghost btn--small" type="button" data-scan-cleanup>Rescan</button>
      ${item.fileCount ? '<button class="btn btn--small" type="button" data-clean-cleanup>Clean temporary files</button>' : ''}
    </div>`;
}

function changesBody(changes) {
  if (!changes || !changes.sections?.length) {
    return '<p class="empty">No changes to what matters since yesterday (or nothing to compare yet — check back tomorrow).</p>';
  }
  const rows = changes.sections.map((s) => {
    if (s.changed) return `<li><strong>${escapeHtml(s.label)}</strong><span>${escapeHtml(s.changed)}</span></li>`;
    const bits = [];
    if (s.added.length) bits.push(`<span class="ok-text">+ ${s.added.slice(0, 6).map(escapeHtml).join(', ')}${s.added.length > 6 ? '…' : ''}</span>`);
    if (s.removed.length) bits.push(`<span class="dim">− ${s.removed.slice(0, 6).map(escapeHtml).join(', ')}${s.removed.length > 6 ? '…' : ''}</span>`);
    return `<li><strong>${escapeHtml(s.label)}</strong><span>${bits.join(' · ')}</span></li>`;
  });
  return `
    <p class="hint">Since ${escapeHtml(changes.since)}:</p>
    <ul class="plain-list plain-list--notes">${rows.join('')}</ul>
    ${changes.effect ? `<p class="hint">${escapeHtml(changes.effect)}</p>` : ''}`;
}

function flagged(apps) {
  if (!apps?.length) return '<p class="empty">No preinstalled extras with a real cost found.</p>';
  return `<ul class="plain-list plain-list--notes">${apps.map((a) => `
    <li><strong>${escapeHtml(a.name)}</strong><span class="dim">${escapeHtml(a.flag)}${a.reasons?.length ? ` — ${a.reasons.map(escapeHtml).join(', ')}` : ''}</span></li>`).join('')}</ul>`;
}

function startup(items) {
  if (!items?.length) return '<p class="empty">No startup apps found.</p>';
  const enabled = items.filter((s) => s.enabled).length;
  return `
    <p class="hint">${enabled} of ${items.length} enabled. Disabling one doesn't uninstall it; it just won't open by itself at sign-in.</p>
    <table class="data-table">
      <thead><tr><th>App</th><th>Status</th><th>Note</th></tr></thead>
      <tbody>${items.map((s) => `
        <tr class="${s.enabled ? '' : 'is-dim'}">
          <td>${escapeHtml(s.name)}</td>
          <td>${s.enabled ? '<span class="ok-text">Enabled</span>' : '<span class="dim">Disabled</span>'}</td>
          <td class="dim">${s.keep ? escapeHtml(s.keep) : ''}</td>
        </tr>`).join('')}
      </tbody>
    </table>`;
}

function largest(apps) {
  if (!apps?.length) return '<p class="empty">No size information reported.</p>';
  return `
    <table class="data-table">
      <tbody>${apps.map((a) => `
        <tr><td>${escapeHtml(a.name)}</td><td class="num">${formatMb(a.sizeMb)}</td></tr>`).join('')}
      </tbody>
    </table>
    <p class="hint">Sizes are what each installer reports, so they're approximate. Games from Steam or Epic may not appear here.</p>`;
}
