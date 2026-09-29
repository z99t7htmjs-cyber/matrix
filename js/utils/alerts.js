/** Lower rank = more severe. */
export const SEVERITY_RANK = { critical: 0, high: 1, medium: 2, low: 3, info: 4 };

/** Unknown severities are treated as "info" so they can't inject odd CSS classes. */
export function normalizeSeverity(severity) {
  return severity in SEVERITY_RANK ? severity : 'info';
}

/** "info" entries are status notes; everything else counts as a security alert. */
export function isSecurityAlert(alert) {
  return normalizeSeverity(alert.severity) !== 'info';
}

/** Most severe first, then newest first. */
export function sortAlerts(alerts) {
  return [...alerts].sort(
    (a, b) =>
      SEVERITY_RANK[normalizeSeverity(a.severity)] - SEVERITY_RANK[normalizeSeverity(b.severity)] ||
      new Date(b.detectedAt) - new Date(a.detectedAt),
  );
}
