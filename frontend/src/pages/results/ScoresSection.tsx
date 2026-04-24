import { useQuery } from '@tanstack/react-query';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Tooltip, TooltipContent, TooltipProvider, TooltipTrigger } from '@/components/ui/tooltip';
import { Info } from 'lucide-react';
import { getScoreBgColor, getScoreColor } from '@/lib/scoreColors';
import { useTheme } from '@/lib/theme';
import { benchmarksApi } from '@/lib/api';
import type { RunStatistics } from '@/types/statistics';
import type { ComputedResultsData } from './computeResultsData';
import { slugify } from './types';
import type { BenchmarkDetail } from './types';
import type { SectionId } from './useResultsNav';

interface ScoresSectionProps {
  benchmark: BenchmarkDetail;
  computed: ComputedResultsData;
  navigate: (section: SectionId) => void;
}

export function ScoresSection({ benchmark, computed, navigate }: ScoresSectionProps) {
  const { rankedModelData, modelScores, hasWeights } = computed;
  const { theme } = useTheme();
  const isDark = theme === 'dark';

  // Fetch statistics for LC win rate column (non-blocking)
  const { data: statistics } = useQuery<RunStatistics>({
    queryKey: ['run-statistics', benchmark.id],
    queryFn: () => benchmarksApi.statistics(benchmark.id),
    staleTime: 60_000,
  });

  // Build per-model LC win rate lookup
  const lcByModel: Record<string, { lc: number; raw: number; biasDetected: boolean } | null> = {};
  // Build per-model 95% CI lookup for vote share (win rate)
  const ciByModel: Record<string, { winRate: number; lower: number; upper: number } | null> = {};
  if (statistics?.model_statistics) {
    for (const ms of statistics.model_statistics) {
      if (ms.lc_win_rate) {
        lcByModel[ms.model_name] = {
          lc: ms.lc_win_rate.lc_win_rate,
          raw: ms.lc_win_rate.raw_win_rate,
          biasDetected: ms.lc_win_rate.length_bias_detected,
        };
      } else {
        lcByModel[ms.model_name] = null;
      }
      if (ms.win_rate_ci) {
        ciByModel[ms.model_name] = {
          winRate: ms.win_rate,
          lower: ms.win_rate_ci.lower,
          upper: ms.win_rate_ci.upper,
        };
      } else if (typeof ms.win_rate === 'number') {
        ciByModel[ms.model_name] = { winRate: ms.win_rate, lower: ms.win_rate, upper: ms.win_rate };
      } else {
        ciByModel[ms.model_name] = null;
      }
    }
  }
  const hasLcData = Object.keys(lcByModel).length > 0;
  const hasCiData = Object.keys(ciByModel).length > 0;

  return (
    <Card className="bg-stone-50 dark:bg-gray-800 border-stone-200 dark:border-gray-700">
      <CardHeader>
        <CardTitle>📈 Scores by Criterion</CardTitle>
      </CardHeader>
      <CardContent>
        <div className="overflow-x-auto -mx-4 px-4 md:mx-0 md:px-0">
          <table className="w-full text-sm min-w-[600px]">
            <thead>
              <tr className="border-b border-stone-200 dark:border-gray-700">
                <th className="text-left py-2 px-3 text-slate-500 dark:text-gray-400 w-8">#</th>
                <th className="text-left py-2 px-3 text-slate-500 dark:text-gray-400">Model</th>
                {benchmark.criteria.map(c => (
                  <th
                    key={c.name}
                    className="text-center py-2 px-3 text-slate-500 dark:text-gray-400"
                    title={c.description}
                  >
                    <div>{c.name}</div>
                    {c.weight !== 1.0 && (
                      <div className="text-xs text-slate-400 dark:text-gray-500 font-normal">×{c.weight}</div>
                    )}
                  </th>
                ))}
                <th className="text-center py-2 px-3 text-slate-500 dark:text-gray-400 min-w-[70px] border-l border-stone-300 dark:border-gray-600">
                  {hasWeights ? 'Weighted' : 'Avg'}
                </th>
                {hasCiData && (
                  <th className="text-center py-2 px-3 text-slate-500 dark:text-gray-400 min-w-[100px] border-l border-stone-300 dark:border-gray-600">
                    <TooltipProvider>
                      <Tooltip>
                        <TooltipTrigger asChild>
                          <span className="inline-flex items-center gap-1 cursor-help">
                            95% CI
                            <Info className="h-3 w-3 text-slate-400 dark:text-gray-500" />
                          </span>
                        </TooltipTrigger>
                        <TooltipContent>
                          A range that reflects uncertainty due to sample size (number of questions). Wider intervals mean you should add more questions before treating small differences as meaningful.
                        </TooltipContent>
                      </Tooltip>
                    </TooltipProvider>
                  </th>
                )}
                {hasLcData && (
                  <th
                    className="text-center py-2 px-3 text-slate-500 dark:text-gray-400 min-w-[90px] border-l border-stone-300 dark:border-gray-600"
                    title="Length-Controlled win rate adjusts for verbosity bias by discounting wins where the winning response was significantly longer."
                  >
                    LC Win Rate
                    <span className="ml-1 text-slate-400 dark:text-gray-500 text-xs cursor-help" title="Length-Controlled win rate adjusts for verbosity bias by discounting wins where the winning response was significantly longer.">(?)</span>
                  </th>
                )}
              </tr>
            </thead>
            <tbody>
              {rankedModelData.map((item, index) => {
                const model = item.model;
                const scores = modelScores[model] || {};

                return (
                  <tr
                    key={model}
                    className={`border-b border-stone-200 dark:border-gray-700/50 hover:bg-stone-100 dark:hover:bg-gray-700/30 ${index === 0 ? 'bg-amber-50 dark:bg-yellow-900/20' : ''}`}
                  >
                    <td className="py-2 px-3 text-center">
                      {index === 0 ? '🏆' : <span className="text-slate-400 dark:text-gray-500">{index + 1}</span>}
                    </td>
                    <td className={`py-2 px-3 ${index === 0 ? 'text-amber-600 dark:text-yellow-400 font-bold' : 'text-green-600 dark:text-green-400'}`}>
                      <button
                        type="button"
                        className="hover:underline text-left"
                        onClick={() => navigate(`model-${slugify(model)}`)}
                      >
                        {model}
                      </button>
                    </td>
                    {benchmark.criteria.map(c => {
                      const criterionScores = scores[c.name] || [];
                      const avg = criterionScores.length > 0
                        ? criterionScores.reduce((a, b) => a + b, 0) / criterionScores.length
                        : null;

                      return (
                        <td
                          key={c.name}
                          className="py-2 px-3 text-center font-mono"
                          style={{
                            color: avg !== null ? getScoreColor(avg, isDark) : '#6b7280',
                            backgroundColor: avg !== null ? getScoreBgColor(avg, isDark) : 'transparent',
                          }}
                        >
                          {avg !== null ? avg.toFixed(1) : '-'}
                        </td>
                      );
                    })}
                    <td
                      className="py-2 px-3 text-center font-mono font-bold border-l border-stone-300 dark:border-gray-600"
                      style={{
                        color: getScoreColor(item.score, isDark),
                        backgroundColor: getScoreBgColor(item.score, isDark),
                      }}
                    >
                      {item.score.toFixed(2)}
                    </td>
                    {hasCiData && (
                      <td className="py-2 px-3 text-center border-l border-stone-300 dark:border-gray-600">
                        {ciByModel[model] ? (
                          <span className="flex flex-col items-center gap-0.5">
                            <span className="text-slate-700 dark:text-gray-300 font-mono text-sm">
                              {(ciByModel[model]!.winRate * 100).toFixed(0)}%
                            </span>
                            {ciByModel[model]!.lower !== ciByModel[model]!.upper && (
                              <span className="text-slate-400 dark:text-gray-500 font-mono text-xs">
                                [{(ciByModel[model]!.lower * 100).toFixed(0)}–{(ciByModel[model]!.upper * 100).toFixed(0)}%]
                              </span>
                            )}
                          </span>
                        ) : (
                          <span className="text-slate-500 dark:text-gray-600 text-xs">N/A</span>
                        )}
                      </td>
                    )}
                    {hasLcData && (
                      <td className="py-2 px-3 text-center border-l border-stone-300 dark:border-gray-600">
                        {lcByModel[model] ? (
                          <span className="flex flex-col items-center gap-0.5">
                            <span className="text-xs text-slate-400 dark:text-gray-500 font-mono">
                              {(lcByModel[model]!.raw * 100).toFixed(0)}%
                              <span className="text-slate-500 dark:text-gray-600"> raw</span>
                            </span>
                            <span
                              className={`text-sm font-mono font-semibold ${lcByModel[model]!.biasDetected ? 'text-amber-600 dark:text-amber-400' : 'text-slate-700 dark:text-gray-300'}`}
                              title={lcByModel[model]!.biasDetected ? 'Length bias detected' : 'No significant length bias'}
                            >
                              {lcByModel[model]!.biasDetected && <span className="mr-0.5">!</span>}
                              {(lcByModel[model]!.lc * 100).toFixed(0)}%
                              <span className="text-slate-500 dark:text-gray-600 text-xs font-normal ml-0.5">LC</span>
                            </span>
                          </span>
                        ) : (
                          <span className="text-slate-500 dark:text-gray-600 text-xs">N/A</span>
                        )}
                      </td>
                    )}
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
      </CardContent>
    </Card>
  );
}
