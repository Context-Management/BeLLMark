import { useSearchParams } from 'react-router-dom';
import { useQuery } from '@tanstack/react-query';
import { benchmarksApi } from '@/lib/api';
import { getScoreColor, getScoreBgColor } from '@/lib/scoreColors';
import { useTheme } from '@/lib/theme';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import type { CompareData } from '@/types/api';

export function Compare() {
  const [searchParams] = useSearchParams();
  const idsParam = searchParams.get('ids');
  const ids = idsParam ? idsParam.split(',').map(Number) : [];
  const { theme } = useTheme();
  const isDark = theme === 'dark';

  const { data, isLoading, error } = useQuery<CompareData>({
    queryKey: ['compare', ids],
    queryFn: async () => (await benchmarksApi.compare(ids)).data,
    enabled: ids.length >= 2,
  });

  if (ids.length < 2) {
    return <div className="text-slate-500 dark:text-gray-400">Select at least 2 runs to compare from the Runs page.</div>;
  }

  if (isLoading) return <div className="text-slate-500 dark:text-gray-400">Loading comparison...</div>;
  if (error || !data) return <div className="text-red-600 dark:text-red-400">Failed to load comparison</div>;

  const runColors = ['#4ade80', '#f59e0b', '#3b82f6', '#ec4899', '#a855f7'];

  // Collect all unique models across all runs
  const allModels = [...new Set(data.runs.flatMap(r => [
    ...Object.keys(r.model_scores),
    ...Object.keys(r.win_counts),
  ]))];

  // Build per-model aggregates
  const modelData = allModels.map(model => {
    const totalWins = data.runs.reduce((sum, run) => sum + (run.win_counts[model] || 0), 0);
    const scores = data.runs
      .map(run => run.model_scores[model])
      .filter((s): s is number => s !== undefined);
    const avgScore = scores.length > 0 ? scores.reduce((a, b) => a + b, 0) / scores.length : 0;
    return { model, totalWins, avgScore };
  });

  // Sort by total wins (desc), then avg score (desc)
  modelData.sort((a, b) => b.totalWins - a.totalWins || b.avgScore - a.avgScore);

  const maxWins = Math.max(...modelData.map(m => m.totalWins), 1);

  // Find the winner (most wins) for each run
  const runWinners = data.runs.map(run => {
    const entries = Object.entries(run.win_counts);
    if (entries.length === 0) return null;
    return entries.sort((a, b) => b[1] - a[1])[0][0];
  });

  const medals = ['\u{1F947}', '\u{1F948}', '\u{1F949}'];

  return (
    <div className="space-y-6">
      {/* Header */}
      <div>
        <h1 className="text-3xl font-bold">Compare Benchmark Runs</h1>
        <p className="text-slate-500 dark:text-gray-400 mt-1">
          {data.runs.length} benchmarks &middot; {allModels.length} models
        </p>
      </div>

      {/* Run Color Legend */}
      <div className="flex flex-wrap gap-x-4 gap-y-1">
        {data.runs.map((run, i) => (
          <div key={run.id} className="flex items-center gap-1.5">
            <div
              className="w-3 h-3 rounded-sm flex-shrink-0"
              style={{ backgroundColor: runColors[i % runColors.length] }}
            />
            <span className="text-sm text-slate-600 dark:text-gray-300">{run.name}</span>
          </div>
        ))}
      </div>

      {/* Overall Rankings with stacked win bars */}
      <Card className="bg-stone-50 dark:bg-gray-800 border-stone-200 dark:border-gray-700">
        <CardHeader className="pb-3">
          <CardTitle className="text-lg">{'\u{1F3C6}'} Model Rankings &mdash; Total Wins</CardTitle>
        </CardHeader>
        <CardContent>
          <div className="space-y-2">
            {modelData.map((m, i) => (
              <div key={m.model} className="flex items-center gap-3">
                <span className="w-6 text-right text-sm flex-shrink-0">
                  {i < 3 ? medals[i] : <span className="text-slate-400 font-mono">{i + 1}.</span>}
                </span>
                <span
                  className="text-sm font-medium w-52 truncate flex-shrink-0"
                  title={m.model}
                >
                  {m.model}
                </span>
                {/* Stacked bar: each segment = wins from one benchmark run */}
                <div className="flex-1 flex h-6 rounded overflow-hidden bg-stone-200 dark:bg-gray-700">
                  {data.runs.map((run, ri) => {
                    const wins = run.win_counts[m.model] || 0;
                    if (wins === 0) return null;
                    return (
                      <div
                        key={run.id}
                        className="h-full transition-all"
                        style={{
                          width: `${(wins / maxWins) * 100}%`,
                          backgroundColor: runColors[ri % runColors.length],
                          opacity: 0.85,
                        }}
                        title={`${run.name}: ${wins} wins`}
                      />
                    );
                  })}
                </div>
                <span className="text-sm font-bold w-16 text-right flex-shrink-0 tabular-nums">
                  {m.totalWins}
                </span>
                <span
                  className="px-2 py-0.5 rounded text-xs font-mono flex-shrink-0"
                  style={{
                    color: getScoreColor(m.avgScore, isDark),
                    backgroundColor: getScoreBgColor(m.avgScore, isDark),
                  }}
                >
                  {m.avgScore.toFixed(1)}
                </span>
              </div>
            ))}
          </div>
        </CardContent>
      </Card>

      {/* Performance Matrix */}
      <Card className="bg-stone-50 dark:bg-gray-800 border-stone-200 dark:border-gray-700">
        <CardHeader className="pb-3">
          <CardTitle className="text-lg">{'\u{1F4CA}'} Performance Matrix</CardTitle>
          <p className="text-xs text-slate-500 dark:text-gray-400">
            Score and wins per model for each benchmark. Run winner highlighted per column.
          </p>
        </CardHeader>
        <CardContent className="overflow-x-auto">
          <table className="w-full text-sm border-collapse">
            <thead>
              <tr className="border-b-2 border-stone-300 dark:border-gray-600">
                <th className="text-left p-2 font-medium sticky left-0 bg-stone-50 dark:bg-gray-800 z-10 min-w-[180px]">
                  Model
                </th>
                {data.runs.map((run, i) => (
                  <th key={run.id} className="p-2 text-center min-w-[120px]">
                    <span
                      className="text-xs font-medium leading-tight block max-w-[140px] truncate mx-auto"
                      style={{ color: runColors[i % runColors.length] }}
                      title={run.name}
                    >
                      {run.name}
                    </span>
                  </th>
                ))}
                <th className="p-2 text-center font-bold min-w-[70px]">Wins</th>
                <th className="p-2 text-center font-bold min-w-[70px]">Avg</th>
              </tr>
            </thead>
            <tbody>
              {modelData.map(({ model, totalWins, avgScore }) => (
                <tr
                  key={model}
                  className="border-b border-stone-200 dark:border-gray-700/50 hover:bg-stone-100 dark:hover:bg-gray-700/30"
                >
                  <td
                    className="p-2 font-medium sticky left-0 bg-stone-50 dark:bg-gray-800 z-10 max-w-[220px] truncate"
                    title={model}
                  >
                    {model}
                  </td>
                  {data.runs.map((run, ri) => {
                    const score = run.model_scores[model];
                    const wins = run.win_counts[model] || 0;
                    const isWinner = runWinners[ri] === model;
                    const hasData = score !== undefined || wins > 0;
                    return (
                      <td key={run.id} className="p-1.5 text-center">
                        {hasData ? (
                          <div
                            className={`inline-flex flex-col items-center gap-0.5 py-1 px-2 rounded ${
                              isWinner ? 'ring-1 ring-yellow-400/60 bg-yellow-400/10' : ''
                            }`}
                          >
                            {score !== undefined && (
                              <span
                                className="px-1.5 py-0.5 rounded text-xs font-mono"
                                style={{
                                  color: getScoreColor(score, isDark),
                                  backgroundColor: getScoreBgColor(score, isDark),
                                }}
                              >
                                {score.toFixed(1)}
                              </span>
                            )}
                            {wins > 0 && (
                              <span className="text-[11px] text-slate-500 dark:text-gray-400 font-medium">
                                {wins}W{isWinner ? ' \u{1F451}' : ''}
                              </span>
                            )}
                          </div>
                        ) : (
                          <span className="text-slate-300 dark:text-gray-600">&mdash;</span>
                        )}
                      </td>
                    );
                  })}
                  <td className="p-2 text-center">
                    <span className="font-bold text-base tabular-nums">{totalWins}</span>
                  </td>
                  <td className="p-2 text-center">
                    <span
                      className="px-2 py-0.5 rounded text-xs font-mono"
                      style={{
                        color: getScoreColor(avgScore, isDark),
                        backgroundColor: getScoreBgColor(avgScore, isDark),
                      }}
                    >
                      {avgScore.toFixed(1)}
                    </span>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </CardContent>
      </Card>
    </div>
  );
}
