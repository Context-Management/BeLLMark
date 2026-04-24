import { useState } from 'react';
import { Link, Outlet, useLocation } from 'react-router-dom';
import { Button } from '@/components/ui/button';
import { ThemeToggle } from '@/components/ThemeToggle';
import { Menu, X, Home, Bot, FileText, Rocket, BarChart3, Trophy, Columns3 } from 'lucide-react';

const DEMO_MODE = import.meta.env.VITE_DEMO_MODE === 'true';

const navItems = [
  { path: '/', label: 'Home', icon: Home, exact: true },
  { path: '/models', label: 'Models', icon: Bot },
  { path: '/suites', label: 'Suites', icon: FileText },
  { path: '/runs/new', label: 'New Run', icon: Rocket },
  { path: '/runs', label: 'Runs', icon: BarChart3 },
  { path: '/question-browser', label: 'Browser', icon: Columns3 },
  { path: '/leaderboard', label: 'Leaderboard', icon: Trophy },
];

export function Layout() {
  const location = useLocation();
  const [mobileMenuOpen, setMobileMenuOpen] = useState(false);

  // In demo mode, strip all app chrome — just render the page content
  if (DEMO_MODE) {
    return (
      <div className="min-h-screen bg-stone-100 dark:bg-gray-900 text-gray-900 dark:text-white">
        <main className="w-full overflow-x-clip">
          <Outlet />
        </main>
      </div>
    );
  }

  return (
    <div className="min-h-screen bg-stone-100 dark:bg-gray-900 text-gray-900 dark:text-white">
      {/* Header */}
      <header className="border-b border-stone-200 dark:border-gray-800 bg-stone-50 dark:bg-gray-950 px-4 md:px-6 py-4 sticky top-0 z-30">
        <div className="flex items-center justify-between">
          <div className="flex items-center gap-4">
            {/* Mobile menu button */}
            <button
              className="md:hidden p-2 hover:bg-stone-100 dark:hover:bg-gray-800 rounded-lg"
              onClick={() => setMobileMenuOpen(!mobileMenuOpen)}
              aria-label={mobileMenuOpen ? "Close navigation menu" : "Open navigation menu"}
              aria-expanded={mobileMenuOpen}
              aria-controls="mobile-navigation"
            >
              {mobileMenuOpen ? <X className="w-6 h-6" /> : <Menu className="w-6 h-6" />}
            </button>
            <Link to="/" className="flex items-center gap-2 text-xl md:text-2xl font-bold text-amber-600 dark:text-amber-400 hover:text-amber-700 dark:hover:text-amber-300 transition-colors">
              <img src="/bellmark-logo.svg" alt="BeLLMark" className="h-7 w-7 md:h-8 md:w-8" />
              BeLLMark
            </Link>
          </div>
          <div className="flex items-center gap-3">
            <span className="hidden sm:block text-slate-500 dark:text-gray-400 text-sm">LLM Benchmark Studio</span>
            <ThemeToggle />
          </div>
        </div>
      </header>

      <div className="flex">
        {/* Mobile menu overlay */}
        {mobileMenuOpen && (
          <div
            className="fixed inset-0 bg-black/50 z-40 md:hidden"
            onClick={() => setMobileMenuOpen(false)}
          />
        )}

        {/* Sidebar - hidden on mobile, slide-in when open */}
        <nav
          id="mobile-navigation"
          aria-label="Main navigation"
          className={`
          fixed md:sticky inset-y-0 left-0 z-50
          md:top-[73px] md:h-[calc(100vh-73px)]
          w-64 border-r border-stone-200 dark:border-gray-800 bg-stone-50 dark:bg-gray-950
          transform transition-transform duration-200 ease-in-out
          ${mobileMenuOpen ? 'translate-x-0' : '-translate-x-full md:translate-x-0'}
          p-4 pt-20 md:pt-4 overflow-y-auto
        `}>
          <div className="space-y-2">
            {(() => {
              // Pick the nav item whose path is the longest prefix-match of the
              // current pathname. Prevents /runs from highlighting when on
              // /runs/new (both would match under a plain startsWith).
              const activePath = navItems
                .filter((item) =>
                  item.exact
                    ? location.pathname === item.path
                    : location.pathname === item.path ||
                      location.pathname.startsWith(item.path + '/'),
                )
                .sort((a, b) => b.path.length - a.path.length)[0]?.path;

              return navItems.map((item) => {
              const isActive = item.path === activePath;
              const Icon = item.icon;

              return (
                <Link key={item.path} to={item.path} onClick={() => setMobileMenuOpen(false)}>
                  <Button
                    variant={isActive ? 'secondary' : 'ghost'}
                    className="w-full justify-start gap-2"
                  >
                    <Icon className="w-4 h-4" />
                    {item.label}
                  </Button>
                </Link>
              );
              });
            })()}
          </div>
        </nav>

        {/* Main content */}
        <main className="flex-1 p-4 md:p-6 w-full overflow-x-clip">
          <Outlet />
        </main>
      </div>
    </div>
  );
}
