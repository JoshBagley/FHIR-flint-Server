const _API_KEY = import.meta.env.VITE_ADMIN_API_KEY as string | undefined;

export function getHeaders(path: string): Record<string, string> {
  const headers: Record<string, string> = { 'Accept': 'application/fhir+json' };
  if (_API_KEY && (path.startsWith('/ai/') || path.startsWith('/admin/'))) {
    headers['X-API-Key'] = _API_KEY;
  }
  return headers;
}

export async function apiFetch<T>(path: string): Promise<T> {
  const safePath = path.startsWith('/') ? path : `/${path}`;
  const resp = await fetch(safePath, { headers: getHeaders(safePath) });
  if (!resp.ok) throw new Error(`${resp.status} ${resp.statusText} — ${path}`);
  return resp.json() as Promise<T>;
}
