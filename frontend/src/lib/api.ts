const BASE = '/api';

export async function api<T>(endpoint: string, opts?: RequestInit): Promise<T> {
  const r = await fetch(`${BASE}${endpoint}`, {
    headers: { 'Content-Type': 'application/json' },
    ...opts,
  });
  if (!r.ok) {
    const err = await r.text();
    throw new Error(err || `HTTP ${r.status}`);
  }
  return r.json() as Promise<T>;
}

export const get  = <T>(ep: string) => api<T>(ep);
export const post = <T>(ep: string, body: unknown) =>
  api<T>(ep, { method: 'POST', body: JSON.stringify(body) });
