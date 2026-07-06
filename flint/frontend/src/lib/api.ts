import { getToken, clearToken } from './auth';

const _API_KEY = import.meta.env.VITE_ADMIN_API_KEY as string | undefined;

export function getHeaders(path: string): Record<string, string> {
  const headers: Record<string, string> = { 'Accept': 'application/fhir+json' };
  const token = getToken();
  if (token) {
    headers['Authorization'] = `Bearer ${token}`;
  } else if (_API_KEY && (path.startsWith('/ai/') || path.startsWith('/admin/'))) {
    headers['X-API-Key'] = _API_KEY;
  }
  return headers;
}

export async function apiFetch<T>(path: string): Promise<T> {
  const safePath = path.startsWith('/') ? path : `/${path}`;
  const resp = await fetch(safePath, { headers: getHeaders(safePath) });
  if (resp.status === 401) {
    // Token expired or revoked — clear it and reload so LoginGate triggers re-login
    clearToken();
    window.location.reload();
    throw new Error('Session expired. Please log in again.');
  }
  if (!resp.ok) throw new Error(`${resp.status} ${resp.statusText} — ${path}`);
  return resp.json() as Promise<T>;
}

export async function apiFetchMut<T>(
  method: 'POST' | 'PUT' | 'PATCH' | 'DELETE',
  path: string,
  body?: unknown,
): Promise<T> {
  const safePath = path.startsWith('/') ? path : `/${path}`;
  const headers: Record<string, string> = { ...getHeaders(safePath), 'Content-Type': 'application/json' };
  const resp = await fetch(safePath, {
    method,
    headers,
    body: body !== undefined ? JSON.stringify(body) : undefined,
  });
  if (resp.status === 401) {
    clearToken();
    window.location.reload();
    throw new Error('Session expired. Please log in again.');
  }
  if (!resp.ok) {
    const msg = await resp.text().catch(() => `${resp.status} ${resp.statusText}`);
    throw new Error(msg || `${resp.status} ${resp.statusText}`);
  }
  if (resp.status === 204 || resp.headers.get('content-length') === '0') return undefined as unknown as T;
  return resp.json() as Promise<T>;
}
