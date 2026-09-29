/** Escape text before inserting it into HTML. Data may come from a backend later, so never trust it. */
export function escapeHtml(value) {
  const map = { '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' };
  return String(value ?? '').replace(/[&<>"']/g, (ch) => map[ch]);
}

/** Escape text, then turn `backtick` spans into <code>. Safe because escaping happens first. */
export function formatInline(text) {
  return escapeHtml(text).replace(/`([^`]+)`/g, '<code>$1</code>');
}

/** 1250 -> "1.3 Mbps", 420 -> "420 kbps" */
export function formatRate(kbps) {
  if (kbps >= 1000) return `${(kbps / 1000).toFixed(1)} Mbps`;
  return `${Math.round(kbps)} kbps`;
}

/** ISO timestamp -> "just now", "12 min ago", "3 h ago", or a full date. */
export function formatRelativeTime(iso) {
  const seconds = Math.round((Date.now() - new Date(iso).getTime()) / 1000);
  if (seconds < 10) return 'just now';
  if (seconds < 60) return `${seconds}s ago`;
  const minutes = Math.round(seconds / 60);
  if (minutes < 60) return `${minutes} min ago`;
  const hours = Math.round(minutes / 60);
  if (hours < 24) return `${hours} h ago`;
  return new Date(iso).toLocaleString();
}
