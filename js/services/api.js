/** Small helpers for talking to the Matrix server. */

export async function post(path, body) {
  const response = await fetch(path, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(body),
  });
  const result = await response.json().catch(() => ({}));
  if (!response.ok || result.ok === false) throw new Error(result.error || `Request failed (${response.status})`);
  return result;
}

export async function getJson(path) {
  const response = await fetch(path, { cache: 'no-store' });
  if (!response.ok) throw new Error(`Request failed (${response.status})`);
  return response.json();
}

/** Open a Windows settings page or tool by name (the server only accepts names from a fixed list). */
export const openWindowsPage = (target) => post('/api/open', { target });
