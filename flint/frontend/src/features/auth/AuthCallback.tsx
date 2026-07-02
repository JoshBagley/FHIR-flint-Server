import { useEffect, useState } from 'react';
import { useNavigate, useSearchParams } from 'react-router-dom';
import { useAuth } from '../../contexts/AuthContext';
import { getReturnPath, clearReturnPath } from '../../lib/auth';

export default function AuthCallback() {
  const [error, setError] = useState<string | null>(null);
  const [exchanged, setExchanged] = useState(false);
  const [searchParams] = useSearchParams();
  const { loading, handleCallback } = useAuth();
  const navigate = useNavigate();

  useEffect(() => {
    if (loading || exchanged) return; // wait for SMART config to load
    setExchanged(true);

    const code = searchParams.get('code');
    const err = searchParams.get('error');
    if (err) {
      setError(searchParams.get('error_description') || err);
      return;
    }
    if (!code) {
      setError('No authorization code received');
      return;
    }
    handleCallback(code)
      .then(() => {
        const returnPath = getReturnPath();
        clearReturnPath();
        navigate(returnPath, { replace: true });
      })
      .catch(e => setError((e as Error).message));
  }, [loading]); // eslint-disable-line react-hooks/exhaustive-deps

  if (error) {
    return (
      <div className="flex items-center justify-center h-screen bg-gray-50">
        <div className="text-center space-y-3">
          <p className="text-red-600 font-medium">Sign-in failed</p>
          <p className="text-sm text-gray-500">{error}</p>
          <button onClick={() => navigate('/')} className="text-sm text-blue-600 underline">
            Return home
          </button>
        </div>
      </div>
    );
  }

  return (
    <div className="flex items-center justify-center h-screen bg-gray-50">
      <p className="text-gray-400 text-sm">Completing sign-in…</p>
    </div>
  );
}
