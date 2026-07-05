import { createContext, useContext, useEffect, useState, ReactNode } from 'react';
import {
  getToken, setToken, clearToken,
  getIdToken, setIdToken,
  getVerifier, setVerifier, clearVerifier,
  setReturnPath,
  parseTokenPayload,
} from '../lib/auth';
import { generateCodeVerifier, generateCodeChallenge } from '../lib/pkce';

interface SmartConfig {
  auth_required: boolean;
  authorization_endpoint?: string;
  token_endpoint: string;
  userinfo_endpoint?: string;
  end_session_endpoint?: string;
}

export interface AuthState {
  loading: boolean;
  authRequired: boolean;
  isAuthenticated: boolean;
  loggedOut: boolean;
  token: string | null;
  username: string | null;
  login: () => Promise<void>;
  logout: () => void;
  handleCallback: (code: string) => Promise<void>;
}

const AuthContext = createContext<AuthState | null>(null);

export function AuthProvider({ children }: { children: ReactNode }) {
  const [loading, setLoading] = useState(true);
  const [smartConfig, setSmartConfig] = useState<SmartConfig | null>(null);
  const [token, setTokenState] = useState<string | null>(getToken());
  const [username, setUsername] = useState<string | null>(() => {
    const idToken = getIdToken();
    if (!idToken) return null;
    const p = parseTokenPayload(idToken);
    return (p.name as string)
      || ((p.given_name || p.family_name) ? `${p.given_name ?? ''} ${p.family_name ?? ''}`.trim() : null)
      || (p.preferred_username as string)
      || (p.email as string)
      || null;
  });
  const [loggedOut, setLoggedOut] = useState(false);

  useEffect(() => {
    const idToken = getIdToken();
    console.log('[auth] mount: idToken present:', !!idToken);
    if (idToken) console.log('[auth] mount: idToken payload:', parseTokenPayload(idToken));

    fetch('/.well-known/smart-configuration')
      .then(r => r.json() as Promise<SmartConfig>)
      .then(cfg => { setSmartConfig(cfg); setLoading(false); })
      .catch(() => { setSmartConfig(null); setLoading(false); });

    // Restore display name from userinfo if a token is already stored
    const existingToken = getToken();
    if (existingToken) {
      fetch('/auth/userinfo', { headers: { Authorization: `Bearer ${existingToken}` } })
        .then(r => { console.log('[auth] mount: userinfo status:', r.status); return r.ok ? r.json() : null; })
        .then((info: Record<string, string> | null) => {
          console.log('[auth] mount: userinfo response:', info);
          if (info) {
            const name = info.name
              || (info.given_name || info.family_name ? `${info.given_name ?? ''} ${info.family_name ?? ''}`.trim() : null)
              || info.preferred_username
              || info.email
              || null;
            if (name) setUsername(name);
          }
        })
        .catch(() => {});
    }
  }, []);


  const login = async () => {
    if (!smartConfig?.authorization_endpoint) return;
    const verifier = generateCodeVerifier();
    const challenge = await generateCodeChallenge(verifier);
    setVerifier(verifier);
    setReturnPath(window.location.pathname);
    const params = new URLSearchParams({
      client_id: 'flint-app',
      redirect_uri: `${window.location.origin}/callback`,
      response_type: 'code',
      scope: 'openid user/*.read user/*.write',
      code_challenge: challenge,
      code_challenge_method: 'S256',
    });
    window.location.href = `${smartConfig.authorization_endpoint}?${params}`;
  };

  const handleCallback = async (code: string) => {
    if (!smartConfig?.token_endpoint) throw new Error('No token endpoint configured');
    const verifier = getVerifier();
    if (!verifier) throw new Error('Missing PKCE code verifier');
    const body = new URLSearchParams({
      grant_type: 'authorization_code',
      client_id: 'flint-app',
      redirect_uri: `${window.location.origin}/callback`,
      code,
      code_verifier: verifier,
    });
    const resp = await fetch(smartConfig.token_endpoint, {
      method: 'POST',
      headers: { 'Content-Type': 'application/x-www-form-urlencoded' },
      body: body.toString(),
    });
    if (!resp.ok) {
      const msg = await resp.text().catch(() => `HTTP ${resp.status}`);
      throw new Error(`Token exchange failed: ${msg}`);
    }
    const data = await resp.json() as { access_token: string; id_token?: string };
    console.log('[auth] token response keys:', Object.keys(data));
    console.log('[auth] id_token present:', !!data.id_token);
    if (data.id_token) console.log('[auth] id_token payload:', parseTokenPayload(data.id_token));
    clearVerifier();
    setToken(data.access_token);
    setLoggedOut(false);
    setTokenState(data.access_token);
    // Extract display name from the ID token immediately (synchronous, no network needed)
    if (data.id_token) {
      setIdToken(data.id_token);
      const p = parseTokenPayload(data.id_token);
      const name = (p.name as string)
        || ((p.given_name || p.family_name) ? `${p.given_name ?? ''} ${p.family_name ?? ''}`.trim() : null)
        || (p.preferred_username as string)
        || (p.email as string)
        || null;
      console.log('[auth] name from id_token:', name);
      if (name) setUsername(name);
    }
    // Fallback: fetch from userinfo proxy in case ID token lacks profile claims
    fetch('/auth/userinfo', { headers: { Authorization: `Bearer ${data.access_token}` } })
      .then(r => { console.log('[auth] userinfo status:', r.status); return r.ok ? r.json() : null; })
      .then((info: Record<string, string> | null) => {
        console.log('[auth] userinfo response:', info);
        if (info) {
          const name = info.name
            || (info.given_name || info.family_name ? `${info.given_name ?? ''} ${info.family_name ?? ''}`.trim() : null)
            || info.preferred_username
            || info.email
            || null;
          if (name) setUsername(name);
        }
      })
      .catch(() => {});
  };

  const logout = () => {
    const idToken = getIdToken();
    clearToken();
    setTokenState(null);
    setUsername(null);
    setLoggedOut(true);
    if (smartConfig?.end_session_endpoint) {
      const params = new URLSearchParams({
        client_id: 'flint-app',
        post_logout_redirect_uri: window.location.origin + '/',
      });
      if (idToken) params.set('id_token_hint', idToken);
      window.location.href = `${smartConfig.end_session_endpoint}?${params}`;
    }
  };

  return (
    <AuthContext.Provider value={{
      loading,
      authRequired: smartConfig?.auth_required ?? false,
      isAuthenticated: !!token,
      loggedOut,
      token,
      username,
      login,
      logout,
      handleCallback,
    }}>
      {children}
    </AuthContext.Provider>
  );
}

export function useAuth(): AuthState {
  const ctx = useContext(AuthContext);
  if (!ctx) throw new Error('useAuth must be used within AuthProvider');
  return ctx;
}
