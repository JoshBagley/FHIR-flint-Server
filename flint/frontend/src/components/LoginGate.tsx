import { useEffect } from 'react';
import { Outlet } from 'react-router-dom';
import { useAuth } from '../contexts/AuthContext';

export default function LoginGate() {
  const { loading, authRequired, isAuthenticated, loggedOut, login } = useAuth();

  useEffect(() => {
    if (!loading && authRequired && !isAuthenticated && !loggedOut) {
      login();
    }
  }, [loading, authRequired, isAuthenticated, loggedOut]); // eslint-disable-line react-hooks/exhaustive-deps

  if (loading) {
    return (
      <div className="flex items-center justify-center h-screen bg-gray-50">
        <p className="text-gray-400 text-sm">Loading…</p>
      </div>
    );
  }

  if (authRequired && !isAuthenticated) {
    return (
      <div className="flex items-center justify-center h-screen bg-gray-50">
        {loggedOut ? (
          <div className="text-center space-y-3">
            <p className="text-sm text-gray-500">You have been signed out.</p>
            <button
              onClick={login}
              className="px-4 py-2 bg-blue-600 text-white text-sm rounded-lg hover:bg-blue-700 transition-colors"
            >
              Sign in
            </button>
          </div>
        ) : (
          <p className="text-gray-400 text-sm">Redirecting to sign-in…</p>
        )}
      </div>
    );
  }

  return <Outlet />;
}
