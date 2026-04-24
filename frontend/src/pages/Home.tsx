import { useState } from 'react';
import { Link } from 'react-router-dom';
import { useQuery } from '@tanstack/react-query';
import { Button } from '@/components/ui/button';
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card';
import { modelsApi, benchmarksApi, suitesApi, eloApi } from '@/lib/api';
import type { AggregateLeaderboard, AggregateModelEntry } from '@/types/statistics';
import { formatISODateTime } from '@/lib/utils';
import {
  ArrowRight,
  Zap,
  BarChart3,
  Bot,
  FileText,
  TrendingUp,
  Clock,
  CheckCircle2,
  AlertCircle
} from 'lucide-react';
import { ProviderLogo } from '@/components/ui/provider-logo';
import { groupByBaseModel } from '@/lib/leaderboardUtils';

export function Home() {
  const [showLicenseBanner, setShowLicenseBanner] = useState(
    () => localStorage.getItem('bellmark-license-dismissed') !== 'true'
  );

  const dismissBanner = () => {
    localStorage.setItem('bellmark-license-dismissed', 'true');
    setShowLicenseBanner(false);
  };

  // Fetch real stats
  const { data: models = [], isLoading: modelsLoading } = useQuery({
    queryKey: ['models'],
    queryFn: async () => (await modelsApi.list()).data,
  });

  const { data: runs = [], isLoading: runsLoading } = useQuery({
    queryKey: ['runs'],
    queryFn: async () => (await benchmarksApi.list()).data,
  });

  const { data: suites = [], isLoading: suitesLoading } = useQuery({
    queryKey: ['suites'],
    queryFn: async () => (await suitesApi.list()).data,
  });

  const { data: aggregateData, isLoading: aggregateLoading } = useQuery<AggregateLeaderboard>({
    queryKey: ['aggregate-leaderboard'],
    queryFn: () => eloApi.aggregateLeaderboard(),
    staleTime: 60_000,
  });

  const isLoading = modelsLoading || runsLoading || suitesLoading || aggregateLoading;

  // Calculate stats
  const completedRuns = runs.filter((r) => r.status === 'completed').length;
  const runningRuns = runs.filter((r) => r.status === 'running').length;

  // Get unique providers
  const providers = new Set(models.map((m) => m.provider));

  // Get recent runs (last 5)
  const recentRuns = [...runs]
    .sort((a, b) => new Date(b.created_at).getTime() - new Date(a.created_at).getTime())
    .slice(0, 5);

  const LOCAL_PROVIDERS = new Set(['lmstudio', 'ollama']);

  const aggregateModels = aggregateData?.models || [];

  // Group variants and flatten back to AggregateModelEntry-shaped objects for LeaderboardCard
  const flattenGroups = (entries: AggregateModelEntry[]) =>
    groupByBaseModel(entries, e => e.model_name, e => e.provider).map(g => {
      const totalWon = g.variants.reduce((s, v) => s + v.questions_won, 0);
      const totalLost = g.variants.reduce((s, v) => s + v.questions_lost, 0);
      const totalTied = g.variants.reduce((s, v) => s + v.questions_tied, 0);
      const totalQ = totalWon + totalLost + totalTied;
      return {
        ...g.representative,
        model_name: g.baseName,
        questions_won: totalWon,
        questions_lost: totalLost,
        questions_tied: totalTied,
        total_questions: totalQ,
        win_rate: totalQ > 0 ? totalWon / totalQ : null,
      };
    }).sort((a, b) => (b.win_rate ?? -1) - (a.win_rate ?? -1));

  const cloudLeaderboard = flattenGroups(
    aggregateModels.filter(m => !LOCAL_PROVIDERS.has(m.provider))
  ).slice(0, 10);
  const localLeaderboard = flattenGroups(
    aggregateModels.filter(m => LOCAL_PROVIDERS.has(m.provider))
  ).slice(0, 10);

  const topModelEntry = cloudLeaderboard[0] || localLeaderboard[0];
  const topModelName = topModelEntry?.model_name;

  return (
    <div className="space-y-8">
      {showLicenseBanner && (
        <div className="rounded-lg border border-amber-200 dark:border-amber-500/30 bg-amber-100 dark:bg-amber-500/10 p-4 flex items-start justify-between mb-6">
          <div>
            <p className="text-sm font-medium text-amber-800 dark:text-amber-200">
              Using BeLLMark in an organization? A commercial license (€799/entity) is required under the PolyForm NC terms.
            </p>
            <div className="mt-2 flex gap-3">
              <a href="https://bellmark.ai/pricing" target="_blank" rel="noopener noreferrer"
                 className="text-sm font-medium text-amber-600 dark:text-amber-400 hover:text-amber-700 dark:hover:text-amber-300">Buy License</a>
              <button onClick={dismissBanner}
                      className="text-sm text-slate-500 dark:text-gray-400 hover:text-slate-700 dark:hover:text-gray-300">I'm using this non-commercially</button>
            </div>
          </div>
          <button onClick={dismissBanner} className="text-slate-400 dark:text-gray-500 hover:text-slate-500 dark:hover:text-gray-400 ml-4 text-lg">&times;</button>
        </div>
      )}

      {/* Hero Section */}
      <div className="relative overflow-hidden rounded-2xl bg-gradient-to-br from-stone-50 via-stone-50 to-stone-100 dark:from-gray-800 dark:via-gray-800 dark:to-gray-900 border border-stone-200 dark:border-gray-700/50 p-8">
        {/* Background decoration */}
        <div className="absolute top-0 right-0 w-96 h-96 bg-amber-500/5 rounded-full blur-3xl -translate-y-1/2 translate-x-1/2" />
        <div className="absolute bottom-0 left-0 w-64 h-64 bg-amber-500/5 rounded-full blur-3xl translate-y-1/2 -translate-x-1/2" />

        <div className="relative flex flex-col md:flex-row items-start md:items-center gap-6">
          <div className="relative">
            <div className="absolute inset-0 bg-amber-400/20 rounded-2xl blur-xl" />
            <img
              src="/bellmark-logo.svg"
              alt="BeLLMark"
              className="relative h-20 w-20 md:h-24 md:w-24 drop-shadow-lg"
            />
          </div>
          <div className="flex-1">
            <h1 className="text-3xl md:text-4xl font-bold bg-gradient-to-r from-amber-600 via-amber-700 to-orange-600 dark:from-amber-300 dark:via-amber-400 dark:to-orange-400 bg-clip-text text-transparent">
              Welcome to BeLLMark
            </h1>
            <p className="mt-2 text-slate-500 dark:text-gray-400 text-lg max-w-2xl">
              Your LLM benchmarking studio. Compare models, configure judges, and discover which AI performs best for your use cases.
            </p>
          </div>
          <Link to="/runs/new" className="shrink-0">
            <Button size="lg" className="bg-amber-600 dark:bg-amber-500 hover:bg-amber-700 dark:hover:bg-amber-400 text-white font-semibold gap-2 shadow-lg shadow-amber-600/20 dark:shadow-amber-500/20">
              <Zap className="w-5 h-5" />
              New Benchmark
              <ArrowRight className="w-4 h-4" />
            </Button>
          </Link>
        </div>
      </div>

      {/* Stats Grid */}
      {isLoading ? (
        <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
          {[1, 2, 3, 4].map(i => (
            <Card key={i} className="bg-stone-50 dark:bg-gray-800 border-stone-200 dark:border-gray-700">
              <CardContent className="p-4">
                <div className="animate-pulse space-y-2">
                  <div className="h-3 bg-stone-200 dark:bg-gray-700 rounded w-20" />
                  <div className="h-8 bg-stone-200 dark:bg-gray-700 rounded w-16" />
                  <div className="h-3 bg-stone-200 dark:bg-gray-700 rounded w-24" />
                </div>
              </CardContent>
            </Card>
          ))}
        </div>
      ) : (
        <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
          <StatsCard
            icon={<Bot className="w-5 h-5" />}
            label="Models"
            value={models.length}
            subtext={`${providers.size} providers`}
            color="blue"
          />
          <StatsCard
            icon={<BarChart3 className="w-5 h-5" />}
            label="Benchmarks"
            value={runs.length}
            subtext={`${completedRuns} completed`}
            color="green"
          />
          <StatsCard
            icon={<FileText className="w-5 h-5" />}
            label="Prompt Suites"
            value={suites.length}
            subtext="Reusable sets"
            color="purple"
          />
          <StatsCard
            icon={<TrendingUp className="w-5 h-5" />}
            label="Top Model"
            value={topModelName || '—'}
            subtext={topModelEntry ? `${((topModelEntry.win_rate ?? 0) * 100).toFixed(0)}% win rate` : 'No data yet'}
            color="amber"
          />
        </div>
      )}

      {/* Leaderboards */}
      {(cloudLeaderboard.length > 0 || localLeaderboard.length > 0) && (
        <div className="grid gap-4 md:grid-cols-2">
          <LeaderboardCard title="Top Cloud Models" entries={cloudLeaderboard} icon="☁️" />
          <LeaderboardCard title="Top Local Models" entries={localLeaderboard} icon="🖥️" />
        </div>
      )}


      {/* Quick Actions + Recent Activity */}
      <div className="grid gap-6 lg:grid-cols-3">
        {/* Quick Actions */}
        <div className="lg:col-span-2 space-y-4">
          <h2 className="text-lg font-semibold text-slate-800 dark:text-gray-200 flex items-center gap-2">
            <Zap className="w-5 h-5 text-amber-600 dark:text-amber-400" />
            Quick Actions
          </h2>
          <div className="grid gap-4 sm:grid-cols-3">
            <ActionCard
              icon="🤖"
              title="Configure Models"
              description="Set up API keys and model presets"
              href="/models"
              stats={isLoading ? '...' : `${models.length} models`}
            />
            <ActionCard
              icon="🚀"
              title="Start Benchmark"
              description="Compare models head-to-head"
              href="/runs/new"
              stats="New run"
              highlight
            />
            <ActionCard
              icon="📝"
              title="Manage Suites"
              description="Create reusable prompt sets"
              href="/suites"
              stats={isLoading ? '...' : `${suites.length} suites`}
            />
          </div>
        </div>

        {/* Recent Activity */}
        <div className="space-y-4">
          <h2 className="text-lg font-semibold text-slate-800 dark:text-gray-200 flex items-center gap-2">
            <Clock className="w-5 h-5 text-slate-500 dark:text-gray-400" />
            Recent Runs
          </h2>
          <Card className="bg-stone-100 dark:bg-gray-800/50 border-stone-200 dark:border-gray-700/50">
            <CardContent className="p-0">
              {recentRuns.length > 0 ? (
                <div className="divide-y divide-stone-200 dark:divide-gray-700/50">
                  {recentRuns.map((run) => (
                    <Link
                      key={run.id}
                      to={`/runs/${run.id}`}
                      className="flex items-center gap-3 p-3 hover:bg-stone-100 dark:hover:bg-gray-700/30 transition-colors"
                    >
                      <StatusIcon status={run.status} />
                      <div className="flex-1 min-w-0">
                        <p className="text-sm font-medium text-slate-800 dark:text-gray-200 truncate">
                          {run.name || `Run #${run.id}`}
                        </p>
                        <p className="text-xs text-slate-500 dark:text-gray-400">
                          {formatISODateTime(run.created_at)}
                        </p>
                      </div>
                      <ArrowRight className="w-4 h-4 text-slate-400 dark:text-gray-500" />
                    </Link>
                  ))}
                </div>
              ) : (
                <div className="p-6 text-center text-slate-500 dark:text-gray-400">
                  <p>No benchmarks yet</p>
                  <Link to="/runs/new" className="text-amber-600 dark:text-amber-400 hover:text-amber-700 dark:hover:text-amber-300 text-sm">
                    Start your first run →
                  </Link>
                </div>
              )}
            </CardContent>
          </Card>

          {recentRuns.length > 0 && (
            <Link to="/runs" className="block text-center text-sm text-slate-500 dark:text-gray-400 hover:text-amber-600 dark:hover:text-amber-400 transition-colors">
              View all runs →
            </Link>
          )}
        </div>
      </div>

      {/* Running benchmarks alert */}
      {runningRuns > 0 && (
        <div className="flex items-center gap-3 p-4 rounded-xl bg-blue-100 dark:bg-blue-500/10 border border-blue-200 dark:border-blue-500/20">
          <div className="flex items-center justify-center w-10 h-10 rounded-full bg-blue-500/20">
            <div className="w-3 h-3 rounded-full bg-blue-400 animate-pulse" />
          </div>
          <div className="flex-1">
            <p className="font-medium text-blue-700 dark:text-blue-300">
              {runningRuns} benchmark{runningRuns > 1 ? 's' : ''} in progress
            </p>
            <p className="text-sm text-blue-400/70">
              Models are being evaluated...
            </p>
          </div>
          <Link to="/runs">
            <Button variant="ghost" size="sm" className="text-blue-600 dark:text-blue-400 hover:text-blue-700 dark:hover:text-blue-300 hover:bg-blue-100 dark:hover:bg-blue-500/10">
              View Progress
            </Button>
          </Link>
        </div>
      )}
    </div>
  );
}

// Stats Card Component
function StatsCard({
  icon,
  label,
  value,
  subtext,
  color
}: {
  icon: React.ReactNode;
  label: string;
  value: string | number;
  subtext: string;
  color: 'blue' | 'green' | 'purple' | 'amber';
}) {
  const colorClasses = {
    blue: 'bg-blue-100 dark:bg-blue-500/10 text-blue-600 dark:text-blue-400 border-blue-200 dark:border-blue-500/20',
    green: 'bg-green-100 dark:bg-green-500/10 text-green-600 dark:text-green-400 border-green-200 dark:border-green-500/20',
    purple: 'bg-purple-100 dark:bg-purple-500/10 text-purple-600 dark:text-purple-400 border-purple-200 dark:border-purple-500/20',
    amber: 'bg-amber-100 dark:bg-amber-500/10 text-amber-600 dark:text-amber-400 border-amber-200 dark:border-amber-500/20',
  };

  return (
    <div className={`p-4 rounded-xl border ${colorClasses[color]}`}>
      <div className="flex items-center gap-2 mb-2">
        {icon}
        <span className="text-xs font-medium uppercase tracking-wide">{label}</span>
      </div>
      <p className="text-2xl font-bold text-gray-900 dark:text-white">{value}</p>
      <p className="text-xs text-slate-500 dark:text-gray-400 mt-1">{subtext}</p>
    </div>
  );
}

// Action Card Component
function ActionCard({
  icon,
  title,
  description,
  href,
  stats,
  highlight = false
}: {
  icon: string;
  title: string;
  description: string;
  href: string;
  stats: string;
  highlight?: boolean;
}) {
  return (
    <Link to={href}>
      <Card className={`
        h-full transition-all duration-200 hover:scale-[1.02] hover:shadow-lg
        ${highlight
          ? 'bg-gradient-to-br from-amber-100 to-orange-50 dark:from-amber-500/20 dark:to-orange-500/10 border-amber-200 dark:border-amber-500/30 hover:border-amber-400/50'
          : 'bg-stone-100 dark:bg-gray-800/50 border-stone-200 dark:border-gray-700/50 hover:border-stone-300 dark:hover:border-gray-600/50 hover:bg-white dark:hover:bg-gray-800/70'
        }
      `}>
        <CardHeader className="pb-2">
          <div className="flex items-start justify-between">
            <span className="text-2xl">{icon}</span>
            <span className={`text-xs px-2 py-1 rounded-full ${
              highlight ? 'bg-amber-100 dark:bg-amber-500/20 text-amber-700 dark:text-amber-300' : 'bg-stone-200/50 dark:bg-gray-700/50 text-slate-500 dark:text-gray-400'
            }`}>
              {stats}
            </span>
          </div>
          <CardTitle className={`text-base ${highlight ? 'text-amber-800 dark:text-amber-200' : 'text-slate-800 dark:text-gray-200'}`}>
            {title}
          </CardTitle>
          <CardDescription className="text-sm">
            {description}
          </CardDescription>
        </CardHeader>
      </Card>
    </Link>
  );
}

// Leaderboard Card Component
function LeaderboardCard({ title, entries, icon }: {
  title: string;
  entries: AggregateModelEntry[];
  icon: string;
}) {
  const medals = ['🥇', '🥈', '🥉'];
  const maxRate = entries[0]?.win_rate ?? 1;

  return (
    <Card className="bg-stone-100 dark:bg-gray-800/50 border-stone-200 dark:border-gray-700/50">
      <CardHeader className="pb-2">
        <CardTitle className="text-sm font-medium text-slate-700 dark:text-gray-300 flex items-center gap-2">
          <span>{icon}</span> {title}
        </CardTitle>
      </CardHeader>
      <CardContent>
        {entries.length > 0 ? (
          <div className="space-y-1.5">
            {entries.map((entry, i) => (
              <div key={entry.model_preset_id} className={`flex items-center gap-2 ${i >= 3 ? 'pl-1' : ''}`}>
                {i < 3 ? (
                  <span className="w-5 text-center text-sm">{medals[i]}</span>
                ) : (
                  <span className="w-5 text-center text-xs text-slate-400 dark:text-gray-500">{i + 1}</span>
                )}
                <ProviderLogo provider={entry.provider} size="sm" />
                <span className={`text-sm truncate flex-1 ${
                  i === 0 ? 'text-amber-700 dark:text-amber-300 font-medium'
                  : i === 1 ? 'text-slate-500 dark:text-gray-400'
                  : i === 2 ? 'text-amber-500'
                  : 'text-slate-400 dark:text-gray-500 text-xs'
                }`} title={entry.model_name}>
                  {entry.model_name}
                </span>
                <div className="w-16 h-3 bg-stone-200 dark:bg-gray-700/40 rounded overflow-hidden">
                  <div
                    className={`h-full rounded ${i === 0 ? 'bg-amber-500/60' : i === 1 ? 'bg-gray-500/40' : i === 2 ? 'bg-amber-800/50' : 'bg-gray-500/30'}`}
                    style={{ width: `${Math.max(12, ((entry.win_rate ?? 0) / (maxRate || 1)) * 100)}%` }}
                  />
                </div>
                <span className="text-xs text-slate-500 dark:text-gray-400 w-10 text-right tabular-nums">
                  {entry.win_rate != null ? `${(entry.win_rate * 100).toFixed(0)}%` : '—'}
                </span>
              </div>
            ))}
          </div>
        ) : (
          <p className="text-sm text-slate-500 dark:text-gray-400">No data yet</p>
        )}
      </CardContent>
    </Card>
  );
}

// Status Icon Component
function StatusIcon({ status }: { status: string }) {
  switch (status) {
    case 'completed':
      return <CheckCircle2 className="w-4 h-4 text-green-600 dark:text-green-400" />;
    case 'running':
      return <div className="w-4 h-4 rounded-full border-2 border-blue-400 border-t-transparent animate-spin" />;
    case 'failed':
      return <AlertCircle className="w-4 h-4 text-red-600 dark:text-red-400" />;
    default:
      return <Clock className="w-4 h-4 text-slate-500 dark:text-gray-400" />;
  }
}
