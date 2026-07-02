const TOKEN_KEY = 'flint_access_token';
const ID_TOKEN_KEY = 'flint_id_token';
const VERIFIER_KEY = 'flint_pkce_verifier';
const RETURN_PATH_KEY = 'flint_return_path';

export function getToken(): string | null {
  return sessionStorage.getItem(TOKEN_KEY);
}

export function setToken(token: string): void {
  sessionStorage.setItem(TOKEN_KEY, token);
}

export function getIdToken(): string | null {
  return sessionStorage.getItem(ID_TOKEN_KEY);
}

export function setIdToken(token: string): void {
  sessionStorage.setItem(ID_TOKEN_KEY, token);
}

export function clearToken(): void {
  sessionStorage.removeItem(TOKEN_KEY);
  sessionStorage.removeItem(ID_TOKEN_KEY);
  sessionStorage.removeItem(VERIFIER_KEY);
  sessionStorage.removeItem(RETURN_PATH_KEY);
}

export function getVerifier(): string | null {
  return sessionStorage.getItem(VERIFIER_KEY);
}

export function setVerifier(v: string): void {
  sessionStorage.setItem(VERIFIER_KEY, v);
}

export function clearVerifier(): void {
  sessionStorage.removeItem(VERIFIER_KEY);
}

export function getReturnPath(): string {
  return sessionStorage.getItem(RETURN_PATH_KEY) || '/';
}

export function setReturnPath(path: string): void {
  sessionStorage.setItem(RETURN_PATH_KEY, path);
}

export function clearReturnPath(): void {
  sessionStorage.removeItem(RETURN_PATH_KEY);
}

export function parseTokenPayload(token: string): Record<string, unknown> {
  try {
    const [, payload] = token.split('.');
    const b64 = payload.replace(/-/g, '+').replace(/_/g, '/');
    const padded = b64 + '='.repeat((4 - (b64.length % 4)) % 4);
    return JSON.parse(atob(padded));
  } catch {
    return {};
  }
}
