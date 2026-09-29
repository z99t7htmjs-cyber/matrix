/**
 * Small, client-side ARGUS lines for the moment something happens (a check
 * passes, a mode applies, a snooze). These are separate from the server-side
 * persona lines on Advisor cards -- purely decorative toast text, no data
 * behind them, so they're fine to pick randomly per click.
 */
const CHECK_RESOLVED = [
  'Checked: resolved. Was that so hard?',
  "Checked: fixed. I'll allow myself a small amount of satisfaction.",
  'Checked: resolved ✓',
];
const CHECK_STILL = [
  'Checked: still needs attention. Unsurprising.',
  "Checked: still there. I did mention this.",
];
const MODE_APPLIED = [
  'Applied. Against my better judgment, which is considerable.',
  'Done. Try to enjoy it.',
];
const SNOOZED = [
  'Snoozed. Noted, as ever.',
  "Snoozed. I'll mention it again right on schedule.",
];

function pick(list) {
  return list[Math.floor(Math.random() * list.length)];
}

export function quip(kind) {
  const banks = { checkResolved: CHECK_RESOLVED, checkStill: CHECK_STILL, modeApplied: MODE_APPLIED, snoozed: SNOOZED };
  const bank = banks[kind];
  return bank ? pick(bank) : null;
}
