import { useEffect } from 'react';
import { BrowserRouter, HashRouter, Routes, Route, Navigate } from 'react-router-dom';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { Toaster } from 'sonner';
import { ThemeProvider } from '@/lib/theme';
import { Layout } from '@/components/Layout';
import { Home } from '@/pages/Home';
import { Models } from '@/pages/Models';
import { Runs } from '@/pages/Runs';
import { NewRun } from '@/pages/NewRun';
import { LiveProgress } from '@/pages/LiveProgress';
import { Results } from '@/pages/Results';
import { Compare } from '@/pages/Compare';
import { QuestionBrowser } from '@/pages/QuestionBrowser';
import { Suites } from '@/pages/Suites';
import { EloLeaderboard } from '@/pages/EloLeaderboard';
import { MockupSlide } from '@/pages/export/MockupSlide';
import { ApiKeyGate } from '@/components/ApiKeyGate';
import { buildVersionReloadUrl, fetchServerVersion, shouldForceReloadForVersionMismatch } from '@/lib/api';

// Default staleTime of 30s prevents Home (and other pages) from refetching every
// single query on every navigation. Cached data is considered fresh within the
// window, so revisiting Home is instant instead of waiting on a background refetch
// before the next-frame paint shows up. Individual queries can still override this.
const queryClient = new QueryClient({
  defaultOptions: {
    queries: {
      staleTime: 30_000,
    },
  },
});
const DEMO_MODE = import.meta.env.VITE_DEMO_MODE === 'true';
const CLIENT_APP_VERSION = typeof __APP_VERSION__ === 'string' ? __APP_VERSION__ : '';
const VERSION_CHECK_INTERVAL_MS = 60_000;
const VERSION_RELOAD_SESSION_KEY = 'bellmark-version-reload';


function AppRoutes() {
  return (
    <>
      <Toaster position="top-right" richColors />
      <Routes>
        {/* Export mockup slides — chromeless, 1920×1080, used for design review + screenshot capture. */}
        <Route path="/export/mockup/:slide/:runId" element={<MockupSlide />} />
        <Route path="/" element={<Layout />}>
          {DEMO_MODE ? (
            <Route index element={<Navigate to="/runs/128" replace />} />
          ) : (
            <Route index element={<Home />} />
          )}
          <Route path="models" element={<Models />} />
          <Route path="runs" element={<Runs />} />
          <Route path="runs/new" element={<NewRun />} />
          <Route path="runs/compare" element={<Compare />} />
          <Route path="question-browser" element={<QuestionBrowser />} />
          <Route path="runs/:id/live" element={<LiveProgress />} />
          <Route path="runs/:id" element={<Results />} />
          <Route path="suites" element={<Suites />} />
          <Route path="leaderboard" element={<EloLeaderboard />} />
          <Route path="elo" element={<Navigate to="/leaderboard" replace />} />
        </Route>
      </Routes>
    </>
  );
}

function App() {
  const Router = DEMO_MODE ? HashRouter : BrowserRouter;

  useEffect(() => {
    if (DEMO_MODE) {
      return undefined;
    }

    let cancelled = false;

    const maybeReloadForNewVersion = async () => {
      const serverVersion = await fetchServerVersion();
      if (cancelled || !shouldForceReloadForVersionMismatch(CLIENT_APP_VERSION, serverVersion)) {
        return;
      }

      const currentMarker = sessionStorage.getItem(VERSION_RELOAD_SESSION_KEY);
      if (currentMarker === serverVersion) {
        return;
      }

      sessionStorage.setItem(VERSION_RELOAD_SESSION_KEY, serverVersion ?? '');
      window.location.replace(buildVersionReloadUrl(window.location.href, serverVersion!));
    };

    const handleVisibilityChange = () => {
      if (document.visibilityState === 'visible') {
        void maybeReloadForNewVersion();
      }
    };

    const handleWindowFocus = () => {
      void maybeReloadForNewVersion();
    };

    void maybeReloadForNewVersion();
    window.addEventListener('focus', handleWindowFocus);
    document.addEventListener('visibilitychange', handleVisibilityChange);
    const intervalId = window.setInterval(() => {
      if (document.visibilityState === 'visible') {
        void maybeReloadForNewVersion();
      }
    }, VERSION_CHECK_INTERVAL_MS);

    return () => {
      cancelled = true;
      window.clearInterval(intervalId);
      document.removeEventListener('visibilitychange', handleVisibilityChange);
      window.removeEventListener('focus', handleWindowFocus);
    };
  }, []);

  return (
    <ThemeProvider>
      <QueryClientProvider client={queryClient}>
        <Router>
          {DEMO_MODE ? (
            <AppRoutes />
          ) : (
            <ApiKeyGate>
              <AppRoutes />
            </ApiKeyGate>
          )}
        </Router>
      </QueryClientProvider>
    </ThemeProvider>
  );
}

export default App;
