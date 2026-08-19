import { useEffect } from 'react';
import { Outlet } from 'react-router-dom';
import { useAuth } from '../contexts/AuthContext';
import AppLogo from './AppLogo';

function BrandedScreen({ children }: { children: React.ReactNode }) {
  return (
    <div className="flex flex-col items-center justify-center min-h-screen bg-slate-950">
      <div className="flex flex-col items-center gap-6 text-center">
        <AppLogo size={72} />
        <div>
          <h1 className="text-2xl font-bold text-white tracking-tight">Flint</h1>
          <p className="text-sm text-slate-400 mt-1">FHIR<sup>®</sup> R4 Server</p>
        </div>
        {children}
        <p className="text-xs text-slate-600 max-w-xs mt-4">
          FHIR<sup>®</sup> is the registered trademark of HL7 and is used with the permission of HL7.
        </p>
      </div>
    </div>
  );
}

export default function LoginGate() {
  const { loading, authRequired, isAuthenticated, loggedOut, login } = useAuth();

  useEffect(() => {
    if (!loading && authRequired && !isAuthenticated && !loggedOut) {
      login();
    }
  }, [loading, authRequired, isAuthenticated, loggedOut]); // eslint-disable-line react-hooks/exhaustive-deps

  if (loading) {
    return (
      <BrandedScreen>
        <p className="text-slate-500 text-sm animate-pulse">Loading…</p>
      </BrandedScreen>
    );
  }

  if (authRequired && !isAuthenticated) {
    return (
      <BrandedScreen>
        {loggedOut ? (
          <div className="flex flex-col items-center gap-3">
            <p className="text-slate-400 text-sm">You have been signed out.</p>
            <button
              onClick={login}
              className="px-5 py-2 bg-orange-500 hover:bg-orange-600 text-white text-sm font-medium rounded-lg transition-colors"
            >
              Sign in
            </button>
          </div>
        ) : (
          <div className="flex flex-col items-center gap-3">
            <p className="text-slate-500 text-sm animate-pulse">Redirecting to sign-in…</p>
            <button
              onClick={login}
              className="px-5 py-2 bg-orange-500 hover:bg-orange-600 text-white text-sm font-medium rounded-lg transition-colors"
            >
              Sign in
            </button>
          </div>
        )}
      </BrandedScreen>
    );
  }

  return <Outlet />;
}
