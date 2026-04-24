import { useState } from 'react';
import { useQuery } from '@tanstack/react-query';
import { useSearchParams } from 'react-router-dom';
import { eloApi } from '@/lib/api';
import { formatISODateTime } from '@/lib/utils';
import type { EloLeaderboard as EloLeaderboardType, EloRating, EloHistoryPoint, AggregateLeaderboard, AggregateModelEntry } from '@/types/statistics';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { ChevronDown, ChevronUp, Search } from 'lucide-react';
import { ProviderLogo } from '@/components/ui/provider-logo';
import { LineChart, Line, XAxis, YAxis, CartesianGrid, Tooltip, ResponsiveContainer } from 'recharts';
import { groupByBaseModel } from '@/lib/leaderboardUtils';
import type { GroupedEntry } from '@/lib/leaderboardUtils';

const LOCAL_PROVIDERS = new Set(['lmstudio', 'ollama']);
const TAB_SLUGS = ['elo', 'wins', 'avg-score'] as const;
type TabSlug = typeof TAB_SLUGS[number];
const TAB_LABELS: Record<TabSlug, string> = {
  'elo': 'ELO Ratings',
  'wins': 'Win Record',
  'avg-score': 'Avg Score',
};

type ReasoningFilter = 'all' | 'reasoning' | 'standard';

// ── Variant aggregation helpers ───────────────────────────────────────────
// When the user enables "Group Variants", grouped rows must reflect combined
// stats across all variants — not just whichever variant was first-encountered.
// (Spec: docs/superpowers/specs/2026-04-01-leaderboard-reasoning-toggle-design.md)

function mergeEloVariants(group: GroupedEntry<EloRating>): EloRating {
  if (group.variants.length === 1) return group.representative;
  const variants = group.variants;
  const totalGames = variants.reduce((s, v) => s + v.games_played, 0);
  // Weighted average rating by games played; conservative max uncertainty.
  const rating = totalGames > 0
    ? variants.reduce((s, v) => s + v.rating * v.games_played, 0) / totalGames
    : variants.reduce((s, v) => s + v.rating, 0) / variants.length;
  const uncertainty = Math.max(...variants.map(v => v.uncertainty));
  const updated_at = variants.reduce<string | null>((latest, v) => {
    if (!v.updated_at) return latest;
    if (!latest || v.updated_at > latest) return v.updated_at;
    return latest;
  }, null);
  return {
    ...group.representative,
    model_name: group.baseName,
    rating,
    uncertainty,
    games_played: totalGames,
    updated_at,
  };
}

function mergeAggregateVariants(group: GroupedEntry<AggregateModelEntry>): AggregateModelEntry {
  if (group.variants.length === 1) return group.representative;
  const variants = group.variants;
  const questions_won = variants.reduce((s, v) => s + v.questions_won, 0);
  const questions_lost = variants.reduce((s, v) => s + v.questions_lost, 0);
  const questions_tied = variants.reduce((s, v) => s + v.questions_tied, 0);
  const total_questions = variants.reduce((s, v) => s + v.total_questions, 0);
  const win_rate = total_questions > 0 ? questions_won / total_questions : null;
  const scored_questions = variants.reduce((s, v) => s + v.scored_questions, 0);
  const runs_participated = variants.reduce((s, v) => s + v.runs_participated, 0);
  // Weighted average score by scored question count: a 1-Q variant must not
  // count the same as a 700-Q one.
  let scoreNumerator = 0;
  let scoreDenominator = 0;
  for (const v of variants) {
    if (v.avg_weighted_score == null || v.scored_questions <= 0) continue;
    scoreNumerator += v.avg_weighted_score * v.scored_questions;
    scoreDenominator += v.scored_questions;
  }
  const avg_weighted_score = scoreDenominator > 0 ? scoreNumerator / scoreDenominator : null;
  return {
    ...group.representative,
    model_name: group.baseName,
    questions_won,
    questions_lost,
    questions_tied,
    total_questions,
    win_rate,
    avg_weighted_score,
    scored_questions,
    runs_participated,
  };
}

export function EloLeaderboard() {
  const [searchParams, setSearchParams] = useSearchParams();
  const [expandedModel, setExpandedModel] = useState<number | null>(null);

  // Read filter state from URL
  const activeTab = (searchParams.get('tab') as TabSlug) || 'elo';
  const searchQuery = searchParams.get('q') || '';
  const typeFilter = searchParams.get('type') || 'all';
  const providerFilter = searchParams.get('providers')?.split(',').filter(Boolean) || [];
  const reasoningFilterRaw = searchParams.get('reasoning') || '';
  const reasoningFilter: ReasoningFilter =
    reasoningFilterRaw === 'reasoning' || reasoningFilterRaw === 'standard'
      ? reasoningFilterRaw
      : 'all';
  const groupVariants = searchParams.get('group') === 'true';

  const setFilter = (key: string, value: string) => {
    const params = new URLSearchParams(searchParams);
    if (value) params.set(key, value);
    else params.delete(key);
    setSearchParams(params, { replace: true });
  };

  // Data queries
  const { data: eloData, isLoading: eloLoading } = useQuery<EloLeaderboardType>({
    queryKey: ['elo-leaderboard'],
    queryFn: () => eloApi.leaderboard(),
  });

  const { data: aggregateData, isLoading: aggLoading } = useQuery<AggregateLeaderboard>({
    queryKey: ['aggregate-leaderboard'],
    queryFn: () => eloApi.aggregateLeaderboard(),
    staleTime: 60_000,
  });

  // Build provider list from union of both datasets
  const allProviders = (() => {
    const providers = new Set<string>();
    eloData?.ratings.forEach(r => providers.add(r.provider));
    aggregateData?.models.forEach(m => providers.add(m.provider));
    return [...providers].sort();
  })();

  // Base filter function (no reasoning filter — applied separately below)
  const matchesBaseFilters = (name: string, provider: string) => {
    if (searchQuery && !name.toLowerCase().includes(searchQuery.toLowerCase())) return false;
    if (typeFilter === 'cloud' && LOCAL_PROVIDERS.has(provider)) return false;
    if (typeFilter === 'local' && !LOCAL_PROVIDERS.has(provider)) return false;
    if (providerFilter.length > 0 && !providerFilter.includes(provider)) return false;
    return true;
  };

  const isLoading = eloLoading || aggLoading;

  // ── ELO pipeline: group FIRST (on full set), THEN filter ──────────────────
  const processedElo = (() => {
    if (!eloData) return [];
    const sorted = [...eloData.ratings].sort((a, b) => b.rating - a.rating);

    if (groupVariants) {
      // Group across full dataset, then apply base filters to groups
      const groups = groupByBaseModel(
        sorted,
        r => r.model_name,
        r => r.provider,
        true, // include provider to prevent cross-provider merging
      );
      return groups
        .filter(g => matchesBaseFilters(g.representative.model_name, g.representative.provider))
        .map(g => ({ ...g, representative: mergeEloVariants(g) }))
        .sort((a, b) => b.representative.rating - a.representative.rating);
    } else {
      // No grouping: apply base + reasoning filters to flat list
      return sorted
        .filter(r => {
          if (!matchesBaseFilters(r.model_name, r.provider)) return false;
          if (reasoningFilter === 'reasoning' && !r.is_reasoning) return false;
          if (reasoningFilter === 'standard' && r.is_reasoning) return false;
          return true;
        })
        .map(r => ({
          representative: r,
          variants: [r],
          baseName: r.model_name,
        } as GroupedEntry<typeof r>));
    }
  })();

  // ── Aggregate pipeline ─────────────────────────────────────────────────────
  const processedAggregate = (() => {
    if (!aggregateData) return [];
    const sorted = [...aggregateData.models];

    if (groupVariants) {
      const groups = groupByBaseModel(
        sorted,
        m => m.model_name,
        m => m.provider,
        true,
      );
      // Aggregate variant stats into a synthetic representative so display & sort
      // reflect the full group, not whichever variant was first in the input.
      return groups
        .filter(g => matchesBaseFilters(g.representative.model_name, g.representative.provider))
        .map(g => ({ ...g, representative: mergeAggregateVariants(g) }));
    } else {
      return sorted
        .filter(m => {
          if (!matchesBaseFilters(m.model_name, m.provider)) return false;
          if (reasoningFilter === 'reasoning' && !m.is_reasoning) return false;
          if (reasoningFilter === 'standard' && m.is_reasoning) return false;
          return true;
        })
        .map(m => ({
          representative: m,
          variants: [m],
          baseName: m.model_name,
        } as GroupedEntry<typeof m>));
    }
  })();

  const processedWins = [...processedAggregate].sort((a, b) => {
    const rateA = a.representative.win_rate ?? -1;
    const rateB = b.representative.win_rate ?? -1;
    if (rateB !== rateA) return rateB - rateA;
    return b.representative.questions_won - a.representative.questions_won;
  });

  const processedAvgScore = [...processedAggregate].sort((a, b) => {
    const scoreA = a.representative.avg_weighted_score ?? -1;
    const scoreB = b.representative.avg_weighted_score ?? -1;
    if (scoreB !== scoreA) return scoreB - scoreA;
    return b.representative.scored_questions - a.representative.scored_questions;
  });

  if (isLoading) {
    return (
      <div className="container mx-auto p-6">
        <div className="flex items-center justify-center min-h-[400px]">
          <div className="animate-spin rounded-full h-12 w-12 border-b-2 border-white"></div>
          <span className="ml-3 text-slate-800 dark:text-gray-200 text-lg">Loading leaderboard...</span>
        </div>
      </div>
    );
  }

  return (
    <div className="container mx-auto p-6">
      <Card className="bg-stone-50 dark:bg-gray-800 border-stone-200 dark:border-gray-700">
        <CardHeader>
          <CardTitle className="text-gray-900 dark:text-white text-2xl">Leaderboard</CardTitle>
          <p className="text-slate-500 dark:text-gray-400 text-sm mt-1">
            Tracking model performance across all benchmark runs
          </p>
        </CardHeader>
        <CardContent>
          {/* Tabs */}
          <div className="flex gap-1 mb-4 border-b border-stone-200 dark:border-gray-700">
            {TAB_SLUGS.map(slug => (
              <button
                key={slug}
                data-testid={slug === 'elo' ? 'lb-tab-elo' : slug === 'wins' ? 'lb-tab-wins' : 'lb-tab-avg'}
                onClick={() => setFilter('tab', slug === 'elo' ? '' : slug)}
                className={`px-4 py-2 text-sm font-medium border-b-2 transition-colors ${
                  activeTab === slug
                    ? 'border-amber-500 text-amber-700 dark:text-amber-300'
                    : 'border-transparent text-slate-500 dark:text-gray-400 hover:text-slate-700 dark:hover:text-gray-300'
                }`}
              >
                {TAB_LABELS[slug]}
              </button>
            ))}
          </div>

          {/* Filter Bar */}
          <div className="flex flex-wrap gap-3 mb-4">
            {/* Search */}
            <div className="relative flex-1 min-w-[200px]">
              <Search className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-slate-400" />
              <Input
                placeholder="Search models..."
                value={searchQuery}
                onChange={e => setFilter('q', e.target.value)}
                className="pl-9 bg-stone-100 dark:bg-gray-900 border-stone-200 dark:border-gray-700"
              />
            </div>

            {/* Provider dropdown */}
            <ProviderFilter
              providers={allProviders}
              selected={providerFilter}
              onChange={selected => setFilter('providers', selected.join(','))}
            />

            {/* Cloud/Local toggle */}
            <div className="flex rounded-lg border border-stone-200 dark:border-gray-700 overflow-hidden">
              {(['all', 'cloud', 'local'] as const).map(t => (
                <button
                  key={t}
                  onClick={() => setFilter('type', t === 'all' ? '' : t)}
                  className={`px-3 py-1.5 text-xs font-medium transition-colors ${
                    typeFilter === t || (t === 'all' && typeFilter === '')
                      ? 'bg-amber-500/20 text-amber-700 dark:text-amber-300'
                      : 'text-slate-500 dark:text-gray-400 hover:bg-stone-100 dark:hover:bg-gray-700/50'
                  }`}
                >
                  {t === 'all' ? 'All' : t === 'cloud' ? 'Cloud' : 'Local'}
                </button>
              ))}
            </div>

            {/* Reasoning filter pill toggle */}
            <div className="relative group flex rounded-lg border border-stone-200 dark:border-gray-700 overflow-hidden">
              {(['all', 'reasoning', 'standard'] as const).map(r => (
                <button
                  key={r}
                  onClick={() => {
                    if (!groupVariants) setFilter('reasoning', r === 'all' ? '' : r);
                  }}
                  disabled={groupVariants}
                  title={groupVariants ? 'Disable "Group Variants" to filter by reasoning type' : undefined}
                  className={`px-3 py-1.5 text-xs font-medium transition-colors ${
                    groupVariants
                      ? 'opacity-40 cursor-not-allowed text-slate-400 dark:text-gray-500'
                      : reasoningFilter === r
                        ? 'bg-amber-500/20 text-amber-700 dark:text-amber-300'
                        : 'text-slate-500 dark:text-gray-400 hover:bg-stone-100 dark:hover:bg-gray-700/50'
                  }`}
                >
                  {r === 'all' ? 'All Types' : r === 'reasoning' ? 'Reasoning' : 'Standard'}
                </button>
              ))}
            </div>

            {/* Group variants checkbox */}
            <label
              className="flex items-center gap-1.5 px-3 py-1.5 rounded-lg border border-stone-200 dark:border-gray-700 text-xs font-medium text-slate-600 dark:text-gray-300 cursor-pointer hover:bg-stone-100 dark:hover:bg-gray-700/50 transition-colors select-none"
              title="Merge reasoning and standard variants of the same base model into a single row"
            >
              <input
                type="checkbox"
                checked={groupVariants}
                onChange={e => {
                  // Mutate both params in one update — calling setFilter twice
                  // would clone the same stale searchParams closure, and the
                  // second call would overwrite the first.
                  const params = new URLSearchParams(searchParams);
                  if (e.target.checked) {
                    params.set('group', 'true');
                    params.delete('reasoning'); // grouped rows mix reasoning + standard
                  } else {
                    params.delete('group');
                  }
                  setSearchParams(params, { replace: true });
                }}
                data-testid="lb-group-variants"
                className="rounded border-stone-300 dark:border-gray-600 w-3.5 h-3.5"
              />
              Group Variants
            </label>
          </div>

          {/* Tab Content */}
          {activeTab === 'elo' && (
            <EloTable
              groups={processedElo}
              expandedModel={expandedModel}
              onToggle={id => setExpandedModel(expandedModel === id ? null : id)}
              groupVariants={groupVariants}
            />
          )}
          {activeTab === 'wins' && <WinRecordTable groups={processedWins} groupVariants={groupVariants} />}
          {activeTab === 'avg-score' && <AvgScoreTable groups={processedAvgScore} groupVariants={groupVariants} />}
        </CardContent>
      </Card>
    </div>
  );
}

// Provider filter dropdown
function ProviderFilter({ providers, selected, onChange }: {
  providers: string[];
  selected: string[];
  onChange: (selected: string[]) => void;
}) {
  const [open, setOpen] = useState(false);

  const toggle = (provider: string) => {
    if (selected.includes(provider)) {
      onChange(selected.filter(p => p !== provider));
    } else {
      onChange([...selected, provider]);
    }
  };

  return (
    <div className="relative">
      <Button
        variant="outline"
        size="sm"
        onClick={() => setOpen(!open)}
        className="border-stone-200 dark:border-gray-700 text-slate-600 dark:text-gray-300"
      >
        Provider {selected.length > 0 && `(${selected.length})`}
        <ChevronDown className="w-3 h-3 ml-1" />
      </Button>
      {open && (
        <>
          <div className="fixed inset-0 z-40" onClick={() => setOpen(false)} />
          <div className="absolute right-0 top-full mt-1 z-50 bg-white dark:bg-gray-800 border border-stone-200 dark:border-gray-700 rounded-lg shadow-lg p-2 min-w-[160px]">
            {providers.map(p => (
              <label key={p} className="flex items-center gap-2 px-2 py-1.5 hover:bg-stone-50 dark:hover:bg-gray-700/50 rounded cursor-pointer">
                <input
                  type="checkbox"
                  checked={selected.includes(p)}
                  onChange={() => toggle(p)}
                  className="rounded border-stone-300 dark:border-gray-600"
                />
                <ProviderLogo provider={p} size="sm" />
                <span className="text-sm text-slate-700 dark:text-gray-300">{p}</span>
              </label>
            ))}
            {selected.length > 0 && (
              <button
                onClick={() => onChange([])}
                className="w-full text-left text-xs text-slate-400 hover:text-slate-600 dark:hover:text-gray-300 px-2 py-1.5 mt-1 border-t border-stone-100 dark:border-gray-700"
              >
                Clear all
              </button>
            )}
          </div>
        </>
      )}
    </div>
  );
}

// ELO ratings table
type EloGroup = GroupedEntry<EloLeaderboardType['ratings'][0]>;

function EloTable({ groups, expandedModel, onToggle, groupVariants }: {
  groups: EloGroup[];
  expandedModel: number | null;
  onToggle: (id: number) => void;
  groupVariants: boolean;
}) {
  if (groups.length === 0) {
    return <p className="text-slate-500 dark:text-gray-400 text-center py-8">No ELO ratings match your filters.</p>;
  }

  return (
    <div className="overflow-x-auto">
      <table className="w-full text-sm">
        <thead>
          <tr className="border-b border-stone-200 dark:border-gray-700">
            <th className="text-left py-3 px-2 sm:px-4 text-slate-700 dark:text-gray-300 font-medium">Rank</th>
            <th className="text-left py-3 px-2 sm:px-4 text-slate-700 dark:text-gray-300 font-medium">Model</th>
            <th className="text-left py-3 px-2 sm:px-4 text-slate-700 dark:text-gray-300 font-medium">Provider</th>
            <th className="text-left py-3 px-2 sm:px-4 text-slate-700 dark:text-gray-300 font-medium">Rating</th>
            <th className="text-left py-3 px-4 text-slate-700 dark:text-gray-300 font-medium hidden md:table-cell">Games</th>
            <th className="text-left py-3 px-4 text-slate-700 dark:text-gray-300 font-medium hidden md:table-cell">Last Updated</th>
            <th className="py-3 px-2 sm:px-4"></th>
          </tr>
        </thead>
        <tbody>
          {groups.map((group, idx) => (
            <ModelRow
              key={group.representative.model_id}
              group={group}
              rank={idx + 1}
              isExpanded={expandedModel === group.representative.model_id}
              onToggle={() => onToggle(group.representative.model_id)}
              groupVariants={groupVariants}
            />
          ))}
        </tbody>
      </table>
    </div>
  );
}

// Win Record table
type AggGroup = GroupedEntry<AggregateModelEntry>;

function WinRecordTable({ groups, groupVariants }: { groups: AggGroup[]; groupVariants: boolean }) {
  if (groups.length === 0) {
    return <p className="text-slate-500 dark:text-gray-400 text-center py-8">No win data matches your filters.</p>;
  }

  return (
    <div className="overflow-x-auto">
      <table className="w-full text-sm">
        <thead>
          <tr className="border-b border-stone-200 dark:border-gray-700">
            <th className="text-left py-3 px-2 sm:px-4 text-slate-700 dark:text-gray-300 font-medium">Rank</th>
            <th className="text-left py-3 px-2 sm:px-4 text-slate-700 dark:text-gray-300 font-medium">Model</th>
            <th className="text-left py-3 px-2 sm:px-4 text-slate-700 dark:text-gray-300 font-medium">Provider</th>
            <th className="text-left py-3 px-2 sm:px-4 text-slate-700 dark:text-gray-300 font-medium">Record</th>
            <th className="text-left py-3 px-2 sm:px-4 text-slate-700 dark:text-gray-300 font-medium">Win Rate</th>
            <th className="text-left py-3 px-4 text-slate-700 dark:text-gray-300 font-medium hidden md:table-cell">Questions</th>
            <th className="text-left py-3 px-4 text-slate-700 dark:text-gray-300 font-medium hidden md:table-cell">Runs</th>
            {groupVariants && <th className="py-3 px-2 sm:px-4"></th>}
          </tr>
        </thead>
        <tbody>
          {groups.map((group, idx) => (
            <AggregateGroupRow
              key={group.representative.model_preset_id}
              group={group}
              rank={idx + 1}
              mode="wins"
              groupVariants={groupVariants}
            />
          ))}
        </tbody>
      </table>
    </div>
  );
}

// Avg Score table
function AvgScoreTable({ groups, groupVariants }: { groups: AggGroup[]; groupVariants: boolean }) {
  if (groups.length === 0) {
    return <p className="text-slate-500 dark:text-gray-400 text-center py-8">No score data matches your filters.</p>;
  }

  return (
    <div className="overflow-x-auto">
      <table className="w-full text-sm">
        <thead>
          <tr className="border-b border-stone-200 dark:border-gray-700">
            <th className="text-left py-3 px-2 sm:px-4 text-slate-700 dark:text-gray-300 font-medium">Rank</th>
            <th className="text-left py-3 px-2 sm:px-4 text-slate-700 dark:text-gray-300 font-medium">Model</th>
            <th className="text-left py-3 px-2 sm:px-4 text-slate-700 dark:text-gray-300 font-medium">Provider</th>
            <th className="text-left py-3 px-2 sm:px-4 text-slate-700 dark:text-gray-300 font-medium">Avg Score</th>
            <th className="text-left py-3 px-4 text-slate-700 dark:text-gray-300 font-medium hidden md:table-cell">Scored Questions</th>
            <th className="text-left py-3 px-4 text-slate-700 dark:text-gray-300 font-medium hidden md:table-cell">Runs</th>
            {groupVariants && <th className="py-3 px-2 sm:px-4"></th>}
          </tr>
        </thead>
        <tbody>
          {groups.map((group, idx) => (
            <AggregateGroupRow
              key={group.representative.model_preset_id}
              group={group}
              rank={idx + 1}
              mode="avg-score"
              groupVariants={groupVariants}
            />
          ))}
        </tbody>
      </table>
    </div>
  );
}

// Shared rank badge
function RankBadge({ rank }: { rank: number }) {
  return (
    <span className={`font-bold text-lg ${
      rank === 1 ? 'text-amber-600 dark:text-yellow-400' :
      rank === 2 ? 'text-slate-700 dark:text-gray-300' :
      rank === 3 ? 'text-orange-500 dark:text-orange-400' :
      'text-slate-500 dark:text-gray-400'
    }`}>
      #{rank}
    </span>
  );
}

// Aggregate grouped row (wins + avg-score tables)
function AggregateGroupRow({ group, rank, mode, groupVariants }: {
  group: AggGroup;
  rank: number;
  mode: 'wins' | 'avg-score';
  groupVariants: boolean;
}) {
  const [expanded, setExpanded] = useState(false);
  const m = group.representative;
  const hasVariants = group.variants.length > 1;

  const displayName = groupVariants && hasVariants ? group.baseName : m.model_name;

  return (
    <>
      <tr className="border-b border-stone-200 dark:border-gray-700/50 hover:bg-stone-100 dark:hover:bg-gray-700/30 transition-colors">
        <td className="py-3 px-2 sm:px-4">
          <RankBadge rank={rank} />
        </td>
        <td className="py-3 px-2 sm:px-4 text-gray-900 dark:text-white font-medium">
          <span>{displayName}</span>
          {groupVariants && hasVariants && (
            <span className="ml-1.5 text-xs text-slate-400 dark:text-gray-500">
              ({group.variants.length} variants)
            </span>
          )}
        </td>
        <td className="py-3 px-2 sm:px-4 text-slate-700 dark:text-gray-300">
          <div className="flex items-center gap-2">
            <ProviderLogo provider={m.provider} size="sm" />
            <span>{m.provider}</span>
          </div>
        </td>
        {mode === 'wins' ? (
          <>
            <td className="py-3 px-2 sm:px-4">
              <span className="text-green-600 dark:text-green-400 font-medium">{m.questions_won}W</span>
              {' '}
              <span className="text-red-500 dark:text-red-400">{m.questions_lost}L</span>
              {m.questions_tied > 0 && (
                <> <span className="text-slate-500 dark:text-gray-400">{m.questions_tied}T</span></>
              )}
            </td>
            <td className="py-3 px-2 sm:px-4">
              <span className="text-gray-900 dark:text-white font-semibold">
                {m.win_rate != null ? `${(m.win_rate * 100).toFixed(1)}%` : '—'}
              </span>
            </td>
            <td className="py-3 px-4 text-slate-700 dark:text-gray-300 hidden md:table-cell">{m.total_questions}</td>
            <td className="py-3 px-4 text-slate-700 dark:text-gray-300 hidden md:table-cell">{m.runs_participated}</td>
          </>
        ) : (
          <>
            <td className="py-3 px-2 sm:px-4">
              <span className="text-gray-900 dark:text-white font-semibold text-lg">
                {m.avg_weighted_score != null ? m.avg_weighted_score.toFixed(2) : '—'}
              </span>
              <span className="text-slate-500 dark:text-gray-400 text-xs ml-1">/10</span>
            </td>
            <td className="py-3 px-4 text-slate-700 dark:text-gray-300 hidden md:table-cell">{m.scored_questions}</td>
            <td className="py-3 px-4 text-slate-700 dark:text-gray-300 hidden md:table-cell">{m.runs_participated}</td>
          </>
        )}
        {groupVariants && (
          <td className="py-3 px-2 sm:px-4">
            {hasVariants && (
              <Button
                variant="ghost"
                size="sm"
                onClick={() => setExpanded(!expanded)}
                className="text-slate-500 dark:text-gray-400 hover:text-gray-900 dark:hover:text-white"
                aria-label={expanded ? 'Collapse variants' : 'Expand variants'}
              >
                {expanded ? <ChevronUp className="h-4 w-4" /> : <ChevronDown className="h-4 w-4" />}
              </Button>
            )}
          </td>
        )}
      </tr>
      {expanded && hasVariants && (
        <tr className="bg-stone-50 dark:bg-gray-900/50">
          <td colSpan={groupVariants ? 8 : 7} className="p-3 sm:p-4">
            <div className="text-xs text-slate-500 dark:text-gray-400 mb-2 font-medium">Variants</div>
            <table className="w-full text-xs">
              <tbody>
                {group.variants.map(v => (
                  <tr key={v.model_preset_id} className="border-b border-stone-200 dark:border-gray-700/30 last:border-0">
                    <td className="py-2 px-2 text-gray-800 dark:text-gray-200">{v.model_name}</td>
                    {mode === 'wins' ? (
                      <>
                        <td className="py-2 px-2">
                          <span className="text-green-600 dark:text-green-400">{v.questions_won}W</span>
                          {' '}
                          <span className="text-red-500 dark:text-red-400">{v.questions_lost}L</span>
                        </td>
                        <td className="py-2 px-2 text-slate-600 dark:text-gray-400">
                          {v.win_rate != null ? `${(v.win_rate * 100).toFixed(1)}%` : '—'}
                        </td>
                      </>
                    ) : (
                      <td className="py-2 px-2 text-slate-600 dark:text-gray-400">
                        {v.avg_weighted_score != null ? `${v.avg_weighted_score.toFixed(2)}/10` : '—'}
                      </td>
                    )}
                  </tr>
                ))}
              </tbody>
            </table>
          </td>
        </tr>
      )}
    </>
  );
}

// ModelRow with expandable ELO history chart (or variants sub-table when grouped)
interface ModelRowProps {
  group: EloGroup;
  rank: number;
  isExpanded: boolean;
  onToggle: () => void;
  groupVariants: boolean;
}

function ModelRow({ group, rank, isExpanded, onToggle, groupVariants }: ModelRowProps) {
  const rating = group.representative;
  const hasVariants = group.variants.length > 1;

  const { data: history } = useQuery<EloHistoryPoint[]>({
    queryKey: ['elo-history', rating.model_id],
    queryFn: () => eloApi.history(rating.model_id),
    // Only fetch history when expanded AND not in group-variants mode (we show sub-table instead)
    enabled: isExpanded && !(groupVariants && hasVariants),
  });

  const displayName = groupVariants && hasVariants ? group.baseName : rating.model_name;

  return (
    <>
      <tr className="border-b border-stone-200 dark:border-gray-700/50 hover:bg-stone-100 dark:hover:bg-gray-700/30 transition-colors">
        <td className="py-3 px-2 sm:px-4">
          <span className={`font-bold text-lg ${
            rank === 1 ? 'text-amber-600 dark:text-yellow-400' :
            rank === 2 ? 'text-slate-700 dark:text-gray-300' :
            rank === 3 ? 'text-orange-500 dark:text-orange-400' :
            'text-slate-500 dark:text-gray-400'
          }`}>
            #{rank}
          </span>
        </td>
        <td className="py-3 px-2 sm:px-4 text-gray-900 dark:text-white font-medium">
          <span>{displayName}</span>
          {groupVariants && hasVariants && (
            <span className="ml-1.5 text-xs text-slate-400 dark:text-gray-500">
              ({group.variants.length} variants)
            </span>
          )}
        </td>
        <td className="py-3 px-2 sm:px-4 text-slate-700 dark:text-gray-300">
          <div className="flex items-center gap-2">
            <ProviderLogo provider={rating.provider} size="sm" />
            <span>{rating.provider}</span>
          </div>
        </td>
        <td className="py-3 px-2 sm:px-4">
          <span className="text-gray-900 dark:text-white font-semibold text-lg">{Math.round(rating.rating)}</span>
          <span className="text-slate-500 dark:text-gray-400 text-xs ml-2">±{Math.round(rating.uncertainty)}</span>
        </td>
        <td className="py-3 px-4 text-slate-700 dark:text-gray-300 hidden md:table-cell">{rating.games_played}</td>
        <td className="py-3 px-4 text-slate-500 dark:text-gray-400 text-xs hidden md:table-cell">
          {rating.updated_at ? formatISODateTime(rating.updated_at) : 'Never'}
        </td>
        <td className="py-3 px-2 sm:px-4">
          <Button
            variant="ghost"
            size="sm"
            onClick={onToggle}
            data-testid={`lb-row-expand-${group.representative.model_id}`}
            className="text-slate-500 dark:text-gray-400 hover:text-gray-900 dark:hover:text-white"
            aria-label={isExpanded ? `Collapse ${displayName}` : `Expand ${displayName}`}
          >
            {isExpanded ? <ChevronUp className="h-4 w-4" /> : <ChevronDown className="h-4 w-4" />}
          </Button>
        </td>
      </tr>
      {isExpanded && (
        <tr className="bg-stone-50 dark:bg-gray-900/50">
          <td colSpan={7} className="p-3 sm:p-6">
            {/* When group-variants is ON and this group has multiple variants, show sub-table */}
            {groupVariants && hasVariants ? (
              <div className="space-y-3">
                <h4 className="text-gray-900 dark:text-white font-semibold text-sm">Variants</h4>
                <table className="w-full text-xs">
                  <thead>
                    <tr className="border-b border-stone-200 dark:border-gray-700/50">
                      <th className="text-left py-2 px-2 text-slate-600 dark:text-gray-400 font-medium">Model</th>
                      <th className="text-left py-2 px-2 text-slate-600 dark:text-gray-400 font-medium">Rating</th>
                      <th className="text-left py-2 px-2 text-slate-600 dark:text-gray-400 font-medium hidden sm:table-cell">Games</th>
                      <th className="text-left py-2 px-2 text-slate-600 dark:text-gray-400 font-medium hidden sm:table-cell">Type</th>
                    </tr>
                  </thead>
                  <tbody>
                    {group.variants.map(v => (
                      <tr key={v.model_id} className="border-b border-stone-100 dark:border-gray-800/50 last:border-0">
                        <td className="py-2 px-2 text-gray-800 dark:text-gray-200">{v.model_name}</td>
                        <td className="py-2 px-2 text-gray-800 dark:text-gray-200 font-medium">
                          {Math.round(v.rating)}
                          <span className="text-slate-400 dark:text-gray-500 ml-1">±{Math.round(v.uncertainty)}</span>
                        </td>
                        <td className="py-2 px-2 text-slate-500 dark:text-gray-400 hidden sm:table-cell">{v.games_played}</td>
                        <td className="py-2 px-2 hidden sm:table-cell">
                          {v.is_reasoning ? (
                            <span className="px-1.5 py-0.5 rounded text-xs bg-purple-100 dark:bg-purple-500/20 text-purple-700 dark:text-purple-300">
                              Reasoning
                            </span>
                          ) : (
                            <span className="px-1.5 py-0.5 rounded text-xs bg-stone-100 dark:bg-gray-700/50 text-slate-500 dark:text-gray-400">
                              Standard
                            </span>
                          )}
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            ) : (
              /* Normal mode: show ELO history chart */
              history && history.length > 0 ? (
                <div className="space-y-4">
                  <h4 className="text-gray-900 dark:text-white font-semibold">ELO Rating History</h4>
                  <ResponsiveContainer width="100%" height={250}>
                    <LineChart data={history}>
                      <CartesianGrid strokeDasharray="3 3" stroke="#374151" />
                      <XAxis
                        dataKey="run_name"
                        stroke="#9CA3AF"
                        tick={{ fill: '#9CA3AF' }}
                      />
                      <YAxis
                        stroke="#9CA3AF"
                        tick={{ fill: '#9CA3AF' }}
                        domain={['auto', 'auto']}
                      />
                      <Tooltip
                        contentStyle={{
                          backgroundColor: '#1F2937',
                          border: '1px solid #374151',
                          borderRadius: '0.375rem',
                        }}
                        labelStyle={{ color: '#F3F4F6' }}
                        itemStyle={{ color: '#F3F4F6' }}
                      />
                      <Line
                        type="monotone"
                        dataKey="rating_after"
                        stroke="#3B82F6"
                        strokeWidth={2}
                        dot={{ fill: '#3B82F6', r: 4 }}
                        name="Rating"
                      />
                    </LineChart>
                  </ResponsiveContainer>
                </div>
              ) : (
                <p className="text-slate-500 dark:text-gray-400 text-center py-4">Loading history...</p>
              )
            )}
          </td>
        </tr>
      )}
    </>
  );
}
