import { escapeHtml } from './format.js';

/**
 * A deliberately tiny Markdown renderer for AI answers.
 *
 * Everything is HTML-escaped FIRST, then only a few patterns are turned back
 * into tags: ``` code blocks ```, `inline code`, **bold**, headings (shown as
 * bold), and bulleted/numbered lists. Nothing the model writes can inject
 * links, scripts or styles into the page.
 */
export function renderMarkdown(text, { alerts = null } = {}) {
  // Some models leave their private reasoning inside <think> tags; hide it.
  const cleaned = text.replace(/<think>[\s\S]*?(<\/think>|$)/g, '').trim();
  const parts = escapeHtml(cleaned).split('```'); // odd parts are code blocks
  const html = parts
    .map((part, i) => (i % 2 ? `<pre><code>${part.replace(/^[\w-]*\n/, '')}</code></pre>` : renderBlocks(part)))
    .join('');
  return alerts ? actionButtons(html, alerts) : html;
}

/**
 * Ask Matrix may offer to set an Advisor item aside with a token such as
 * [[snooze:uptime:7]]. It becomes a button you click to confirm, and only if
 * that item is showing right now. The AI can never do it by itself.
 * `alerts` maps item id -> title for the items currently showing.
 */
function actionButtons(html, alerts) {
  const button = (action, key, days) => {
    const title = alerts.get(key.replace(/&amp;/g, '&'));
    if (!title) return '<span class="dim">(suggested action for an item that isn\'t showing any more)</span>';
    const label = { acknowledge: 'Mark as seen', keep: 'Keep as is', snooze: `Snooze ${days === '1' ? '1 day' : `${days} days`}` }[action];
    return `<button class="btn btn--ghost btn--small chat-action" type="button" data-alert="${action}" data-key="${key}"
      ${days ? `data-days="${days}"` : ''}>${label}: ${escapeHtml(title)}</button>`;
  };
  return html
    .replace(/\[\[snooze:(.+?):(\d+)\]\]/g, (_, key, days) => button('snooze', key, days))
    .replace(/\[\[(acknowledge|keep):(.+?)\]\]/g, (_, action, key) => button(action, key));
}

function inline(text) {
  return text
    .replace(/`([^`]+)`/g, '<code>$1</code>')
    .replace(/\*\*([^*]+)\*\*/g, '<strong>$1</strong>');
}

function renderBlocks(text) {
  const out = [];
  let list = null; // 'ul' | 'ol' while inside a list

  const closeList = () => {
    if (list) out.push(`</${list}>`);
    list = null;
  };
  const openList = (kind) => {
    if (list !== kind) {
      closeList();
      out.push(`<${kind}>`);
      list = kind;
    }
  };

  for (const line of text.split('\n')) {
    let m;
    if ((m = line.match(/^\s*[-*•]\s+(.*)/))) {
      openList('ul');
      out.push(`<li>${inline(m[1])}</li>`);
    } else if ((m = line.match(/^\s*\d+[.)]\s+(.*)/))) {
      openList('ol');
      out.push(`<li>${inline(m[1])}</li>`);
    } else if ((m = line.match(/^#{1,6}\s+(.*)/))) {
      closeList();
      out.push(`<p><strong>${inline(m[1])}</strong></p>`);
    } else if (line.trim()) {
      closeList();
      out.push(`<p>${inline(line.trim())}</p>`);
    } else {
      closeList();
    }
  }
  closeList();
  return out.join('');
}
