import { useState } from 'react';
import { useQuery } from '@tanstack/react-query';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { TokenBar } from '@/components/ui/token-bar';
import { Tooltip, TooltipContent, TooltipProvider, TooltipTrigger } from '@/components/ui/tooltip';
import { Info } from 'lucide-react';
import { getScoreColor, getScoreBgColor } from '@/lib/scoreColors';
import { useTheme } from '@/lib/theme';
import { marginOfErrorDisplay } from '@/lib/statistics';
import { benchmarksApi } from '@/lib/api';
import type { RunStatistics } from '@/types/statistics';
import type { BenchmarkDetail } from './types';
import { slugify } from './types';
import type { ComputedResultsData } from './computeResultsData';
import type { SectionId } from './useResultsNav';

/** Parse "Name (FORMAT QUANT @ host)" into name + tag parts */
function parseModelLabel(label: string): { name: string; format?: string; quant?: string; host?: string } {
  const match = label.match(/^(.+?)\s*\((.+)\)$/);
  if (!match) return { name: label };
  const name = match[1];
  const meta = match[2];
  const atParts = meta.split(' @ ');
  const host = atParts.length > 1 ? atParts[atParts.length - 1] : undefined;
  const fmtQuant = atParts[0].trim();
  const tokens = fmtQuant.split(/\s+/);
  // Known formats
  const formats = new Set(['GGUF', 'MLX', 'GPTQ', 'AWQ', 'EXL2']);
  let format: string | undefined;
  let quant: string | undefined;
  if (tokens.length >= 2 && formats.has(tokens[0])) {
    format = tokens[0];
    quant = tokens.slice(1).join(' ');
  } else if (tokens.length === 1) {
    if (formats.has(tokens[0])) format = tokens[0];
    else quant = tokens[0];
  }
  return { name, format, quant, host };
}

function ModelTags({ label }: { label: string }) {
  const { format, quant, host } = parseModelLabel(label);
  if (!format && !quant && !host) return null;
  return (
    <span className="inline-flex flex-wrap gap-1 ml-2 items-start align-middle">
      {format && (
        <span className="inline-block px-1.5 py-0.5 text-[10px] font-semibold text-white rounded" style={{backgroundColor: '#3b82f6'}}>
          {format}
        </span>
      )}
      {quant && (
        <span className="inline-block px-1.5 py-0.5 text-[10px] font-semibold text-white rounded" style={{backgroundColor: '#f59e0b'}}>
          {quant}
        </span>
      )}
      {host && (
        <span className="inline-block px-1.5 py-0.5 text-[10px] font-semibold text-white rounded" style={{backgroundColor: '#64748b'}}>
          {host}
        </span>
      )}
    </span>
  );
}

function ModelName({ label }: { label: string }) {
  const { name } = parseModelLabel(label);
  return <>{name}<ModelTags label={label} /></>;
}

interface OverviewSectionProps {
  benchmark: BenchmarkDetail;
  computed: ComputedResultsData;
  navigate: (section: SectionId) => void;
}

export function OverviewSection({ benchmark, computed, navigate }: OverviewSectionProps) {
  const [questionsExpanded, setQuestionsExpanded] = useState(false);
  const { theme } = useTheme();
  const isDark = theme === 'dark';

  // Fetch statistics for LC win rate display (non-blocking)
  const { data: statistics } = useQuery<RunStatistics>({
    queryKey: ['run-statistics', benchmark.id],
    queryFn: () => benchmarksApi.statistics(benchmark.id),
    staleTime: 60_000,
  });

  // Build per-model LC win rate lookup from statistics
  const lcByModel: Record<string, { lc: number; raw: number; biasDetected: boolean; nFlagged: number; nTotal: number } | null> = {};
  if (statistics?.model_statistics) {
    for (const ms of statistics.model_statistics) {
      if (ms.lc_win_rate) {
        lcByModel[ms.model_name] = {
          lc: ms.lc_win_rate.lc_win_rate,
          raw: ms.lc_win_rate.raw_win_rate,
          biasDetected: ms.lc_win_rate.length_bias_detected,
          nFlagged: ms.lc_win_rate.n_flagged,
          nTotal: ms.lc_win_rate.n_total,
        };
      } else {
        lcByModel[ms.model_name] = null;
      }
    }
  }

  const {
    overallWinner,
    hasWeights,
    winCounts,
    rankedModelData,
    modelPerformance,
    maxTotalTokens,
    insightBadges,
    perQuestionScores,
    perJudgeScores,
    modelScores,
    latencyRange,
    tokPerSecRange,
    costRange,
    calculatePercentile,
    getLatencyHeatColor,
    getHigherBetterColor,
    getLowerBetterColor,
  } = computed;

  const {
    minAvg: minAvgLatency,
    maxAvg: maxAvgLatency,
    minP50: minP50Latency,
    maxP50: maxP50Latency,
    minP95: minP95Latency,
    maxP95: maxP95Latency,
  } = latencyRange;

  const { min: minTokPerSec, max: maxTokPerSec } = tokPerSecRange;
  const { min: minCost, max: maxCost } = costRange;

  return (
    <div className="space-y-6">
      {/* Winner Card with Questions Preview */}
      {overallWinner && (
        <Card className="bg-gradient-to-r from-amber-50 to-yellow-50 dark:from-yellow-900/30 dark:to-amber-900/30 border-amber-300 dark:border-yellow-500/50">
          <CardContent className="py-4 flex flex-col sm:flex-row items-start sm:items-center gap-4 sm:gap-6">
            {/* Winner Badge - Left */}
            <div className="flex items-center gap-3 flex-shrink-0">
              <div className="text-3xl">🏆</div>
              <div>
                <div className="text-xl font-bold text-amber-600 dark:text-yellow-400">{overallWinner[0]}</div>
                <div className="text-slate-500 dark:text-gray-400 text-sm">
                  {overallWinner[1].toFixed(2)}{hasWeights ? ' weighted' : ''} · {winCounts[overallWinner[0]] || 0} wins{' '}
                  <span className="text-xs text-muted-foreground">
                    {marginOfErrorDisplay(
                      winCounts[overallWinner[0]] || 0,
                      benchmark.questions.length * (benchmark.judge_ids?.length || 1)
                    )}
                  </span>
                </div>
              </div>
            </div>

            {/* Divider */}
            <div className="hidden sm:block h-10 w-px bg-yellow-500/30 flex-shrink-0" />

            {/* Benchmark Info - Right */}
            <div className="flex-1 min-w-0 space-y-2">
              {/* Questions */}
              <div>
                <div className="text-xs text-yellow-600/70 mb-1 uppercase tracking-wide">Questions</div>
                <div className="flex flex-wrap gap-1.5">
                  {(questionsExpanded ? benchmark.questions : benchmark.questions.slice(0, 4)).map((q) => (
                    <span
                      key={q.id}
                      className="text-xs text-slate-700 dark:text-gray-300 bg-stone-50 dark:bg-gray-900/60 px-2 py-1 rounded-md border border-stone-200 dark:border-gray-700/50 truncate max-w-[240px]"
                      title={q.user_prompt}
                    >
                      {q.user_prompt.length > 50 ? q.user_prompt.substring(0, 50) + '…' : q.user_prompt}
                    </span>
                  ))}
                  {benchmark.questions.length > 4 && (
                    <button
                      onClick={() => setQuestionsExpanded(!questionsExpanded)}
                      className="text-xs text-amber-600 hover:text-amber-700 hover:bg-amber-100 dark:text-yellow-500/80 dark:hover:text-yellow-400 dark:hover:bg-yellow-900/20 px-2 py-1 rounded transition-colors"
                    >
                      {questionsExpanded ? '− show less' : `+${benchmark.questions.length - 4} more`}
                    </button>
                  )}
                </div>
              </div>

              {/* Criteria & Judges Row */}
              <div className="flex gap-6">
                {/* Criteria */}
                <div>
                  <div className="text-xs text-yellow-600/70 mb-1 uppercase tracking-wide">Criteria</div>
                  <div className="flex flex-wrap gap-1">
                    {benchmark.criteria.map((c) => (
                      <span
                        key={c.name}
                        className="text-xs text-amber-700 bg-amber-100 border-amber-300 dark:text-amber-300/90 dark:bg-amber-900/30 dark:border-amber-700/30 px-1.5 py-0.5 rounded border"
                        title={c.description}
                      >
                        {c.name}{c.weight !== 1.0 && <span className="text-amber-500/70 ml-0.5">×{c.weight}</span>}
                      </span>
                    ))}
                  </div>
                </div>

                {/* Judges */}
                <div>
                  <div className="text-xs text-yellow-600/70 mb-1 uppercase tracking-wide">Judges</div>
                  <div className="flex flex-wrap gap-1">
                    {(() => {
                      const judgeNames = [...new Set(benchmark.questions.flatMap(q => q.judgments.map(j => j.judge_name)))];
                      return judgeNames.map((judge) => (
                        <span
                          key={judge}
                          className="text-xs text-purple-700 bg-purple-100 border-purple-300 dark:text-purple-300/90 dark:bg-purple-900/30 dark:border-purple-700/30 px-1.5 py-0.5 rounded border"
                        >
                          {judge}
                        </span>
                      ));
                    })()}
                  </div>
                </div>
              </div>
            </div>
          </CardContent>
        </Card>
      )}

      {/* Combined Performance & Rankings Card */}
      <Card className="bg-stone-50 dark:bg-gray-800 border-stone-200 dark:border-gray-700">
        <CardHeader>
          <CardTitle>📊 Model Performance & Rankings</CardTitle>
        </CardHeader>
        <CardContent>
          {/* Mobile card layout */}
          <div className="md:hidden space-y-3">
            {rankedModelData.map((item, index) => {
              const model = item.model;
              const perf = modelPerformance[model];
              const tokPerSec = perf?.totalLatencyMs > 0
                ? perf.totalTokens / (perf.totalLatencyMs / 1000)
                : 0;
              const avgLatency = perf?.latencies.length > 0
                ? perf.latencies.reduce((a, b) => a + b, 0) / perf.latencies.length
                : 0;
              const backendMetrics = benchmark.performance_metrics?.[model];
              const estimatedCost = backendMetrics?.estimated_cost;

              return (
                <div
                  key={model}
                  className={`rounded-lg border p-3 cursor-pointer transition-colors ${
                    index === 0
                      ? 'bg-amber-50 dark:bg-yellow-900/20 border-amber-300 dark:border-yellow-500/40'
                      : 'bg-stone-50 dark:bg-gray-900/50 border-stone-200 dark:border-gray-700/50 active:bg-stone-200 dark:active:bg-gray-700/40'
                  }`}
                  onClick={() => navigate(`model-${slugify(model)}`)}
                >
                  {/* Rank + Model name */}
                  <div className="flex items-center gap-2 mb-2">
                    <span className={`text-lg font-bold shrink-0 w-8 ${
                      index === 0 ? 'text-amber-600 dark:text-yellow-400' :
                      index === 1 ? 'text-slate-700 dark:text-gray-300' :
                      index === 2 ? 'text-orange-600 dark:text-orange-400' :
                      'text-slate-400 dark:text-gray-500'
                    }`}>
                      {index === 0 ? '🏆' : `${index + 1}`}
                    </span>
                    <span className={`font-semibold ${index === 0 ? 'text-amber-600 dark:text-yellow-400' : 'text-green-600 dark:text-green-400'}`}>
                      <ModelName label={model} />
                    </span>
                  </div>

                  {/* Score bar */}
                  <div className="flex items-center gap-2 mb-2">
                    <div className="flex-1 h-5 bg-stone-200 dark:bg-gray-700 rounded overflow-hidden">
                      <div
                        className="h-full rounded transition-all"
                        style={{
                          width: `${(item.score / 10) * 100}%`,
                          backgroundColor: getScoreColor(item.score, isDark)
                        }}
                      />
                    </div>
                    <span
                      className="w-10 text-right font-mono font-bold text-sm shrink-0"
                      style={{ color: getScoreColor(item.score, isDark) }}
                    >
                      {item.score.toFixed(1)}
                    </span>
                  </div>

                  {/* Token bar */}
                  {perf && (
                    <div className="mb-2">
                      <TokenBar
                        totalTokens={perf.totalTokens}
                        maxTokens={maxTotalTokens}
                        rawChars={perf.rawChars > 0 ? perf.rawChars : null}
                        answerChars={perf.answerChars > 0 ? perf.answerChars : null}
                      />
                    </div>
                  )}

                  {/* Stats row */}
                  <div className="flex flex-wrap gap-x-4 gap-y-1 text-xs text-slate-500 dark:text-gray-400">
                    {tokPerSec > 0 && (
                      <span>
                        <span className="text-slate-400 dark:text-gray-500">Tok/s:</span>{' '}
                        <span className="text-slate-700 dark:text-gray-300 font-mono">{tokPerSec.toFixed(0)}</span>
                      </span>
                    )}
                    {estimatedCost != null && (
                      <span>
                        <span className="text-slate-400 dark:text-gray-500">Cost:</span>{' '}
                        <span className="text-slate-700 dark:text-gray-300 font-mono">
                          {estimatedCost === 0
                            ? '$0'
                            : `$${estimatedCost < 0.01 ? estimatedCost.toFixed(3) : estimatedCost.toFixed(2)}`}
                        </span>
                      </span>
                    )}
                    {avgLatency > 0 && (
                      <span>
                        <span className="text-slate-400 dark:text-gray-500">Avg:</span>{' '}
                        <span className="text-slate-700 dark:text-gray-300 font-mono">{(avgLatency / 1000).toFixed(1)}s</span>
                      </span>
                    )}
                  </div>
                </div>
              );
            })}
          </div>

          {/* Desktop table layout */}
          <div className="hidden md:block overflow-x-auto">
            <table className="w-full text-sm min-w-[700px]">
              <thead>
                <tr className="border-b border-stone-200 dark:border-gray-700">
                  <th className="text-left py-2 text-slate-500 dark:text-gray-400 w-8">#</th>
                  <th className="text-left py-2 text-slate-500 dark:text-gray-400 w-40">Model</th>
                  <th className="text-left py-2 text-slate-500 dark:text-gray-400 w-48">Score</th>
                  <th className="text-left py-2 text-slate-500 dark:text-gray-400">Tokens</th>
                  <th className="text-right py-2 text-slate-500 dark:text-gray-400 w-16">Tok/s</th>
                  <th className="text-right py-2 text-slate-500 dark:text-gray-400 w-16">Cost</th>
                  <th
                    className="text-right py-2 text-slate-500 dark:text-gray-400 w-28"
                    title="Raw win rate / Length-Controlled win rate. LC adjusts for verbosity bias by discounting wins where the winner was significantly longer."
                  >
                    Win / LC
                  </th>
                  <th className="text-right py-2 text-slate-500 dark:text-gray-400 w-20">Avg</th>
                  <th className="text-right py-2 text-slate-500 dark:text-gray-400 w-20">P50</th>
                  <th className="text-right py-2 text-slate-500 dark:text-gray-400 w-20">P95</th>
                </tr>
              </thead>
              {rankedModelData.map((item, index) => {
                const model = item.model;
                const perf = modelPerformance[model];
                const avgLatency = perf?.latencies.length > 0
                  ? perf.latencies.reduce((a, b) => a + b, 0) / perf.latencies.length
                  : 0;
                const p50 = perf ? calculatePercentile(perf.latencies, 50) : 0;
                const p95 = perf ? calculatePercentile(perf.latencies, 95) : 0;
                const tokPerSec = perf?.totalLatencyMs > 0
                  ? perf.totalTokens / (perf.totalLatencyMs / 1000)
                  : 0;
                const backendMetrics = benchmark.performance_metrics?.[model];
                const estimatedCost = backendMetrics?.estimated_cost;

                const verdicts = benchmark.comment_summaries ? Object.entries(benchmark.comment_summaries)
                  .map(([, models]) => {
                    const s = (models as Record<string, string | { verdict?: string }>)?.[model];
                    return s ? (typeof s === 'object' && s.verdict ? s.verdict : String(s)) : null;
                  })
                  .filter(Boolean) : [];

                return (
                  <tbody key={model} className="group">
                  <tr
                    className={`border-b border-stone-200 dark:border-gray-700/50 group-hover:bg-stone-200 dark:group-hover:bg-gray-700/40 cursor-pointer ${index === 0 ? 'bg-amber-50 dark:bg-yellow-900/20' : ''}`}
                    onClick={() => navigate(`model-${slugify(model)}`)}
                    title={`Click to view ${model} details`}
                  >
                    <td className="py-3 text-center">
                      {index === 0 ? '🏆' : <span className="text-slate-400 dark:text-gray-500">{index + 1}</span>}
                    </td>
                    <td className={`py-3 ${index === 0 ? 'text-amber-600 dark:text-yellow-400 font-bold' : 'text-green-600 dark:text-green-400'}`}>
                      <ModelName label={model} />
                    </td>
                    <td className="py-3 pr-2">
                      <div className="flex items-center gap-2">
                        <div className="flex-1 h-5 bg-stone-200 dark:bg-gray-700 rounded overflow-hidden">
                          <div
                            className="h-full rounded transition-all"
                            style={{
                              width: `${(item.score / 10) * 100}%`,
                              backgroundColor: getScoreColor(item.score, isDark)
                            }}
                          />
                        </div>
                        <span
                          className="w-10 text-right font-mono font-bold"
                          style={{ color: getScoreColor(item.score, isDark) }}
                        >
                          {item.score.toFixed(1)}
                        </span>
                      </div>
                    </td>
                    <td className="py-3 pr-2">
                      {perf && (
                        <TokenBar
                          totalTokens={perf.totalTokens}
                          maxTokens={maxTotalTokens}
                          rawChars={perf.rawChars > 0 ? perf.rawChars : null}
                          answerChars={perf.answerChars > 0 ? perf.answerChars : null}
                        />
                      )}
                    </td>
                    <td
                      className="text-right text-slate-700 dark:text-gray-300 px-1 font-mono text-xs rounded"
                      style={{ backgroundColor: getHigherBetterColor(tokPerSec, minTokPerSec, maxTokPerSec) }}
                    >
                      {tokPerSec > 0 ? tokPerSec.toFixed(0) : '-'}
                    </td>
                    <td
                      className="text-right text-slate-700 dark:text-gray-300 px-1 font-mono text-xs rounded"
                      style={{
                        backgroundColor: estimatedCost === 0
                          ? 'hsla(120, 70%, 35%, 0.4)'
                          : getLowerBetterColor(estimatedCost ?? 0, minCost, maxCost)
                      }}
                    >
                      {estimatedCost != null
                        ? estimatedCost === 0
                          ? '$0'
                          : `$${estimatedCost < 0.01 ? estimatedCost.toFixed(3) : estimatedCost.toFixed(2)}`
                        : '-'}
                    </td>
                    <td className="text-right px-1 text-xs">
                      {lcByModel[model] ? (
                        <span className="flex flex-col items-end gap-0.5">
                          <span className="text-slate-500 dark:text-gray-400 font-mono">{(lcByModel[model]!.raw * 100).toFixed(0)}%</span>
                          <span
                            className={`font-mono flex items-center gap-0.5 ${lcByModel[model]!.biasDetected ? 'text-amber-600 dark:text-amber-400' : 'text-slate-700 dark:text-gray-300'}`}
                            title={
                              lcByModel[model]!.biasDetected
                                ? `Length bias detected: ${lcByModel[model]!.nFlagged} of ${lcByModel[model]!.nTotal} wins discounted for verbosity`
                                : 'Length-Controlled win rate — no significant verbosity bias detected'
                            }
                          >
                            {lcByModel[model]!.biasDetected && <span className="text-amber-600 dark:text-amber-400 mr-0.5">!</span>}
                            {(lcByModel[model]!.lc * 100).toFixed(0)}%<span className="text-gray-600 text-[9px] ml-0.5">LC</span>
                          </span>
                        </span>
                      ) : Object.keys(lcByModel).length > 0 ? (
                        <span className="text-gray-600 font-mono">-</span>
                      ) : null}
                    </td>
                    <td
                      className="text-right text-slate-700 dark:text-gray-300 px-1 rounded text-xs"
                      style={{ backgroundColor: getLatencyHeatColor(avgLatency, minAvgLatency, maxAvgLatency) }}
                    >
                      {avgLatency > 0 ? `${(avgLatency / 1000).toFixed(1)}s` : '-'}
                    </td>
                    <td
                      className="text-right text-slate-700 dark:text-gray-300 px-1 rounded text-xs"
                      style={{ backgroundColor: getLatencyHeatColor(p50, minP50Latency, maxP50Latency) }}
                    >
                      {p50 > 0 ? `${(p50 / 1000).toFixed(1)}s` : '-'}
                    </td>
                    <td
                      className="text-right text-slate-700 dark:text-gray-300 px-1 rounded text-xs"
                      style={{ backgroundColor: getLatencyHeatColor(p95, minP95Latency, maxP95Latency) }}
                    >
                      {p95 > 0 ? `${(p95 / 1000).toFixed(1)}s` : '-'}
                    </td>
                  </tr>
                  {(verdicts.length > 0 || (insightBadges[model]?.length ?? 0) > 0 || perQuestionScores[model]) && (
                    <tr className="hidden group-hover:table-row border-b border-stone-200 dark:border-gray-700/50">
                      <td colSpan={10} className="px-3 py-3">
                        <div className="flex gap-4">
                          {/* Left: Score tables */}
                          <div className="flex-1 min-w-0 space-y-2">
                            {/* Per-question scores */}
                            {perQuestionScores[model] && Object.keys(perQuestionScores[model]).length > 0 && (
                              <div>
                                <div className="text-[10px] text-slate-400 dark:text-gray-500 uppercase tracking-wider mb-1">Per Question</div>
                                <div className="flex flex-wrap gap-1">
                                  {benchmark.questions.map((q) => {
                                    const qs = perQuestionScores[model]?.[q.order];
                                    return (
                                      <div
                                        key={q.order}
                                        className="text-[10px] font-mono px-1.5 py-0.5 rounded"
                                        style={{
                                          color: qs != null ? getScoreColor(qs, isDark) : '#6b7280',
                                          backgroundColor: qs != null ? getScoreBgColor(qs, isDark) : 'transparent'
                                        }}
                                        title={`Q${q.order + 1}: ${q.user_prompt.substring(0, 60)}...`}
                                      >
                                        Q{q.order + 1}: {qs != null ? qs.toFixed(1) : '-'}
                                      </div>
                                    );
                                  })}
                                </div>
                              </div>
                            )}
                            {/* Per-criteria scores */}
                            {modelScores[model] && Object.keys(modelScores[model]).length > 0 && (
                              <div>
                                <div className="text-[10px] text-slate-400 dark:text-gray-500 uppercase tracking-wider mb-1">Per Criterion</div>
                                <div className="flex flex-wrap gap-1">
                                  {benchmark.criteria.map(c => {
                                    const scores = modelScores[model]?.[c.name] || [];
                                    const avg = scores.length > 0 ? scores.reduce((a, b) => a + b, 0) / scores.length : null;
                                    return (
                                      <div
                                        key={c.name}
                                        className="text-[10px] font-mono px-1.5 py-0.5 rounded"
                                        style={{
                                          color: avg != null ? getScoreColor(avg, isDark) : '#6b7280',
                                          backgroundColor: avg != null ? getScoreBgColor(avg, isDark) : 'transparent'
                                        }}
                                        title={c.description}
                                      >
                                        {c.name}: {avg != null ? avg.toFixed(1) : '-'}
                                      </div>
                                    );
                                  })}
                                </div>
                              </div>
                            )}
                            {/* Per-judge average scores */}
                            {perJudgeScores[model] && Object.keys(perJudgeScores[model]).length > 1 && (
                              <div>
                                <div className="text-[10px] text-slate-400 dark:text-gray-500 uppercase tracking-wider mb-1">Per Judge</div>
                                <div className="flex flex-wrap gap-1">
                                  {Object.entries(perJudgeScores[model]).sort(([, a], [, b]) => b - a).map(([judge, avg]) => (
                                    <div
                                      key={judge}
                                      className="text-[10px] font-mono px-1.5 py-0.5 rounded"
                                      style={{
                                        color: getScoreColor(avg, isDark),
                                        backgroundColor: getScoreBgColor(avg, isDark)
                                      }}
                                    >
                                      {judge.replace(/^(OpenAI |Anthropic |Google |Mistral |Meta )/i, '')}: {avg.toFixed(1)}
                                    </div>
                                  ))}
                                </div>
                              </div>
                            )}
                          </div>
                          {/* Right: Badges + Quotes */}
                          <div className="flex-1 min-w-0 space-y-2">
                            {/* Insight badges */}
                            {insightBadges[model]?.length > 0 && (
                              <div className="flex flex-wrap gap-1.5">
                                {insightBadges[model].map((badge, bi) => (
                                  <span
                                    key={bi}
                                    className={`text-[10px] font-semibold px-2 py-0.5 rounded-full border ${badge.color}`}
                                  >
                                    {badge.icon} {badge.label}
                                  </span>
                                ))}
                              </div>
                            )}
                            {/* Verdict quotes */}
                            {verdicts.length > 0 && (
                              <ul className="space-y-1">
                                {verdicts.map((v, vi) => (
                                  <li key={vi} className="text-xs text-slate-700 dark:text-gray-300 italic leading-snug flex gap-1.5">
                                    <span className="text-gray-600 select-none shrink-0">&bull;</span>
                                    <span>"{v}"</span>
                                  </li>
                                ))}
                              </ul>
                            )}
                          </div>
                        </div>
                      </td>
                    </tr>
                  )}
                  </tbody>
                );
              })}
            </table>
          </div>
        </CardContent>
      </Card>

      {/* Judge Analysis Card */}
      {benchmark.judge_summary && (
        <Card className="bg-stone-50 dark:bg-gray-800 border-stone-200 dark:border-gray-700">
          <CardHeader>
            <CardTitle>⚖️ Judge Analysis</CardTitle>
          </CardHeader>
          <CardContent>
            <div className="space-y-4">
              <div className="flex items-center gap-4">
                <div className="text-2xl font-bold text-green-600 dark:text-green-400">
                  {(benchmark.judge_summary.agreement_rate * 100).toFixed(0)}%
                </div>
                <div className="text-slate-500 dark:text-gray-400">
                  <TooltipProvider>
                    <Tooltip>
                      <TooltipTrigger asChild>
                        <span className="inline-flex items-center gap-1 cursor-help">
                          Judge Agreement
                          <Info className="h-3 w-3 text-slate-400 dark:text-gray-500" />
                        </span>
                      </TooltipTrigger>
                      <TooltipContent>
                        How often judges selected the same winner for the same question. Higher agreement means more consistent judging; lower agreement means results depend more on which judge you use.
                      </TooltipContent>
                    </Tooltip>
                  </TooltipProvider>
                  {benchmark.judge_summary.disagreement_count > 0 && (
                    <span className="ml-2 text-amber-600 dark:text-amber-400">
                      ({benchmark.judge_summary.disagreement_count} question{benchmark.judge_summary.disagreement_count !== 1 ? 's' : ''} with disagreement)
                    </span>
                  )}
                </div>
              </div>

              {benchmark.judge_summary.disagreement_questions.length > 0 && (
                <div className="text-sm text-slate-500 dark:text-gray-400">
                  Disagreement on question{benchmark.judge_summary.disagreement_questions.length !== 1 ? 's' : ''}:{' '}
                  <span className="text-amber-600 dark:text-amber-400">
                    {benchmark.judge_summary.disagreement_questions.map(q => q + 1).join(', ')}
                  </span>
                </div>
              )}

              {benchmark.kappa_value !== null && benchmark.kappa_value !== undefined && (
                <div className="text-sm">
                  <span className="text-slate-500 dark:text-gray-400">
                    {benchmark.kappa_type === "cohen" ? "Cohen's" : "Fleiss'"} κ:
                  </span>{" "}
                  <span className={benchmark.kappa_value > 0.6 ? "text-green-500" : benchmark.kappa_value > 0.2 ? "text-amber-500" : "text-red-500"}>
                    {benchmark.kappa_value.toFixed(2)}
                  </span>
                  <span className="text-xs text-slate-500 dark:text-gray-400 ml-1">
                    ({benchmark.kappa_value > 0.8 ? "almost perfect" :
                      benchmark.kappa_value > 0.6 ? "substantial" :
                      benchmark.kappa_value > 0.4 ? "moderate" :
                      benchmark.kappa_value > 0.2 ? "fair" : "slight"} agreement)
                  </span>
                </div>
              )}

              <div className="overflow-x-auto -mx-4 px-4 md:mx-0 md:px-0">
                <table className="w-full text-sm min-w-[400px]">
                  <thead>
                    <tr className="border-b border-stone-200 dark:border-gray-700">
                      <th className="text-left py-2 text-slate-500 dark:text-gray-400">Judge</th>
                      {Object.keys(benchmark.judge_summary.per_judge_winners).length > 0 && (
                        <>
                          {Object.keys(
                            Object.values(benchmark.judge_summary.per_judge_winners)[0] || {}
                          ).map(model => (
                            <th key={model} className="text-center py-2 text-slate-500 dark:text-gray-400 px-2">
                              {model}
                            </th>
                          ))}
                        </>
                      )}
                      <th className="text-right py-2 text-slate-500 dark:text-gray-400">Total</th>
                    </tr>
                  </thead>
                  <tbody>
                    {Object.entries(benchmark.judge_summary?.per_judge_winners || {}).map(([judge, winners]) => {
                      const total = Object.values(winners).reduce((a, b) => a + b, 0);
                      const modelNames = Object.keys(benchmark.judge_summary?.per_judge_winners || {}).length > 0
                        ? Object.keys(Object.values(benchmark.judge_summary?.per_judge_winners || {})[0] || {})
                        : [];

                      return (
                        <tr key={judge} className="border-b border-stone-200 dark:border-gray-700/50">
                          <td className="py-2 text-amber-600 dark:text-amber-400">{judge}</td>
                          {modelNames.map(model => (
                            <td key={model} className="text-center text-slate-700 dark:text-gray-300 px-2">
                              {winners[model] || 0}
                            </td>
                          ))}
                          <td className="text-right text-slate-700 dark:text-gray-300 font-medium">{total}</td>
                        </tr>
                      );
                    })}
                  </tbody>
                </table>
              </div>
            </div>
          </CardContent>
        </Card>
      )}
    </div>
  );
}
