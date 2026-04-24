import { useState, useEffect, type ReactNode } from 'react';
import { checkAuthRequired, validateApiKey, getStoredApiKey, setStoredApiKey } from '@/lib/api';

export function ApiKeyGate({ children }: { children: ReactNode }) {
  const [state, setState] = useState<'loading' | 'open' | 'prompt' | 'error'>('loading');
  const [key, setKey] = useState('');
  const [error, setError] = useState('');
  const [checking, setChecking] = useState(false);

  const check = async () => {
    const required = await checkAuthRequired();
    if (required === null) {
      // Server unreachable — fail closed
      setState('error');
      return;
    }
    if (!required) {
      setState('open');
      return;
    }
    // Auth required — check if we have a stored key that works
    const stored = getStoredApiKey();
    if (stored) {
      const valid = await validateApiKey(stored);
      if (valid) {
        setState('open');
        return;
      }
    }
    setState('prompt');
  };

  const retry = () => {
    setState('loading');
    check();
  };

  useEffect(() => {
    check(); // eslint-disable-line react-hooks/set-state-in-effect -- initial auth check on mount
    const handler = () => setState('prompt');
    window.addEventListener('bellmark-auth-required', handler);
    return () => window.removeEventListener('bellmark-auth-required', handler);
  }, []);

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setChecking(true);
    setError('');
    const valid = await validateApiKey(key);
    if (valid) {
      setStoredApiKey(key);
      setState('open');
    } else {
      setError('Invalid API key');
    }
    setChecking(false);
  };

  if (state === 'loading') {
    return (
      <div className="min-h-screen flex items-center justify-center bg-white dark:bg-gray-950">
        <div className="text-gray-500 dark:text-gray-400">Loading...</div>
      </div>
    );
  }

  if (state === 'open') {
    return <>{children}</>;
  }

  if (state === 'error') {
    return (
      <div className="min-h-screen flex items-center justify-center bg-white dark:bg-gray-950 px-4">
        <div className="w-full max-w-sm">
          <div className="text-center mb-8">
            <h1 className="text-2xl font-bold text-gray-900 dark:text-gray-100">BeLLMark</h1>
            <p className="text-sm text-gray-500 dark:text-gray-400 mt-2">
              Could not connect to server
            </p>
          </div>
          <button
            onClick={retry}
            className="w-full px-3 py-2 bg-blue-600 text-white rounded-md hover:bg-blue-700"
          >
            Retry
          </button>
        </div>
      </div>
    );
  }

  return (
    <div className="min-h-screen flex items-center justify-center bg-white dark:bg-gray-950 px-4">
      <div className="w-full max-w-sm">
        <div className="text-center mb-8">
          <h1 className="text-2xl font-bold text-gray-900 dark:text-gray-100">BeLLMark</h1>
          <p className="text-sm text-gray-500 dark:text-gray-400 mt-2">
            This instance requires an API key
          </p>
        </div>
        <form onSubmit={handleSubmit} className="space-y-4">
          <input
            type="password"
            value={key}
            onChange={(e) => setKey(e.target.value)}
            placeholder="Enter API key"
            autoFocus
            className="w-full px-3 py-2 border rounded-md bg-white dark:bg-gray-900 border-gray-300 dark:border-gray-700 text-gray-900 dark:text-gray-100 focus:outline-none focus:ring-2 focus:ring-blue-500"
          />
          {error && <p className="text-sm text-red-500">{error}</p>}
          <button
            type="submit"
            disabled={!key || checking}
            className="w-full px-3 py-2 bg-blue-600 text-white rounded-md hover:bg-blue-700 disabled:opacity-50 disabled:cursor-not-allowed"
          >
            {checking ? 'Checking...' : 'Authenticate'}
          </button>
        </form>
      </div>
    </div>
  );
}
