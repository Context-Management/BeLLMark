import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import { getScoreColor, getScoreBgColor } from '@/lib/scoreColors';
import { useTheme } from '@/lib/theme';
import { slugify } from './types';
import type { BenchmarkDetail } from './types';
import type { ComputedResultsData } from './computeResultsData';
import type { SectionId } from './useResultsNav';

interface ModelDetailProps {
  benchmark: BenchmarkDetail;
  computed: ComputedResultsData;
  modelSlug: string;
  navigate: (section: SectionId) => void;
}

export function ModelDetail({ benchmark, computed, modelSlug, navigate }: ModelDetailProps) {
  const { theme } = useTheme();
  const isDark = theme === 'dark';

  // Find the model entry matching the slug
  const modelEntry = computed.rankedModelData.find(
    ({ model }) => slugify(model) === modelSlug
  );

  if (!modelEntry) {
    return (
      <Card className="bg-stone-50 dark:bg-gray-800 border-stone-200 dark:border-gray-700">
        <CardContent className="pt-6">
          <div className="text-center py-8">
            <p className="text-slate-500 dark:text-gray-400 mb-4">Model not found</p>
            <Button variant="outline" onClick={() => navigate('overview')}>
              Back to Overview
            </Button>
          </div>
        </CardContent>
      </Card>
    );
  }

  const { model, score } = modelEntry;
  const index = computed.rankedModelData.findIndex(d => d.model === model);
  const modelHeatmap = computed.heatmapData[model];
  const bias = computed.lengthBias[model];
  const summaries = benchmark.comment_summaries;
  const judgeNames = summaries ? Object.keys(summaries) : [];

  // Build a generation lookup: question_order -> generation
  const genLookup: Record<number, BenchmarkDetail['questions'][0]['generations'][0]> = {};
  benchmark.questions.forEach(q => {
    q.generations.forEach(g => {
      if (g.status !== 'success') return;
      if (g.model_name === model) {
        genLookup[q.order] = g;
      }
    });
  });

  // Derive cost_per_token for this model from aggregate metrics
  let costPerToken: number | null = null;
  const metrics = benchmark.performance_metrics?.[model];
  if (metrics && metrics.estimated_cost != null && metrics.total_tokens > 0) {
    costPerToken = metrics.estimated_cost / metrics.total_tokens;
  }

  return (
    <Card className="bg-stone-50 dark:bg-gray-800 border-stone-200 dark:border-gray-700">
      <CardHeader>
        <CardTitle>Model Detail</CardTitle>
      </CardHeader>
      <CardContent>
        <div className="bg-white dark:bg-gray-900 rounded-lg p-4">
          {/* Model header */}
          <div className="flex items-center gap-2 mb-3 flex-wrap">
            {index === 0 && <span>🏆</span>}
            <span className={`font-medium text-lg ${index === 0 ? 'text-yellow-400' : 'text-green-600 dark:text-green-400'}`}>
              {model}
            </span>
            <span className="text-slate-400 dark:text-gray-500 text-xs bg-stone-200 dark:bg-gray-700 rounded px-1.5 py-0.5">
              #{index + 1}
            </span>
            <span className="text-slate-400 dark:text-gray-500 text-sm font-mono ml-2">{score.toFixed(2)} avg</span>
            {bias?.warning && (
              <span className="inline-flex items-center gap-1 text-xs text-amber-600 dark:text-amber-500 bg-amber-100 dark:bg-amber-500/10 rounded px-1.5 py-0.5 ml-2">
                May favor {bias.r && bias.r > 0 ? 'longer' : 'shorter'} responses
                (r={bias.r?.toFixed(2)})
              </span>
            )}
          </div>

          {/* Score heatmap table with per-question metrics */}
          {modelHeatmap && (
            <div className="overflow-x-auto mb-4">
              <table className="w-full text-xs">
                <thead>
                  <tr className="border-b border-stone-200 dark:border-gray-700">
                    <th className="text-left py-1.5 px-2 text-slate-400 dark:text-gray-500 w-12">Q</th>
                    {benchmark.criteria.map(c => (
                      <th key={c.name} className="text-center py-1.5 px-2 text-slate-400 dark:text-gray-500" title={c.description}>
                        {c.name}
                      </th>
                    ))}
                    <th className="text-center py-1.5 px-2 text-slate-400 dark:text-gray-500 border-l border-gray-600">Avg</th>
                    <th className="text-right py-1.5 px-2 text-slate-400 dark:text-gray-500 border-l border-gray-600">Tokens</th>
                    <th className="text-right py-1.5 px-2 text-slate-400 dark:text-gray-500">Think/Ans</th>
                    <th className="text-right py-1.5 px-2 text-slate-400 dark:text-gray-500">Speed</th>
                    <th className="text-right py-1.5 px-2 text-slate-400 dark:text-gray-500">Cost</th>
                    <th className="text-right py-1.5 px-2 text-slate-400 dark:text-gray-500">Time</th>
                  </tr>
                </thead>
                <tbody>
                  {benchmark.questions.map(q => {
                    const qScores = modelHeatmap[q.order];
                    if (!qScores) return null;
                    const values = benchmark.criteria
                      .map(c => qScores[c.name])
                      .filter((v): v is number => v != null);
                    const avg = values.length > 0 ? values.reduce((a, b) => a + b, 0) / values.length : null;

                    // Per-question generation data
                    const gen = genLookup[q.order];
                    const tokens = gen?.tokens || 0;
                    const rawChars = gen?.raw_chars || 0;
                    const answerChars = gen?.answer_chars || 0;
                    const latencyMs = gen?.latency_ms || 0;
                    // Only show thinking split if >= 50 estimated tokens AND >= 5% of total
                    const rawHasThinking = rawChars > 0 && answerChars > 0 && rawChars > answerChars;
                    const rawAnswerRatio = rawHasThinking ? answerChars / rawChars : 1;
                    const rawThinkingEst = rawHasThinking ? tokens - Math.round(tokens * rawAnswerRatio) : 0;
                    const hasThinking = rawHasThinking && rawThinkingEst >= 50 && tokens > 0 && rawThinkingEst / tokens >= 0.05;
                    const answerRatio = hasThinking ? rawAnswerRatio : 1;
                    const answerTokens = Math.round(tokens * answerRatio);
                    const thinkingTokens = tokens - answerTokens;
                    const tokPerSec = latencyMs > 0 ? tokens / (latencyMs / 1000) : 0;
                    const cost = costPerToken != null ? costPerToken * tokens : null;

                    return (
                      <tr
                        key={q.order}
                        className="border-b border-stone-100 dark:border-gray-700/30 hover:bg-stone-50 dark:hover:bg-gray-800/50 cursor-pointer"
                        onClick={() => navigate(`question-${q.order}` as SectionId)}
                        title={`Click to view Q${q.order + 1}: ${q.user_prompt.substring(0, 80)}`}
                      >
                        <td className="py-1 px-2 text-slate-500 dark:text-gray-400" title={q.user_prompt.substring(0, 80)}>
                          Q{q.order + 1}
                        </td>
                        {benchmark.criteria.map(c => {
                          const s = qScores[c.name];
                          return (
                            <td
                              key={c.name}
                              className="py-1 px-2 text-center font-mono"
                              style={{
                                color: s != null ? getScoreColor(s, isDark) : '#6b7280',
                                backgroundColor: s != null ? getScoreBgColor(s, isDark) : 'transparent',
                              }}
                            >
                              {s != null ? s.toFixed(1) : '-'}
                            </td>
                          );
                        })}
                        <td
                          className="py-1 px-2 text-center font-mono font-bold border-l border-gray-600"
                          style={{
                            color: avg != null ? getScoreColor(avg, isDark) : '#6b7280',
                            backgroundColor: avg != null ? getScoreBgColor(avg, isDark) : 'transparent',
                          }}
                        >
                          {avg != null ? avg.toFixed(1) : '-'}
                        </td>
                        <td className="py-1 px-2 text-right font-mono text-slate-700 dark:text-gray-300 border-l border-gray-600">
                          {tokens > 0 ? tokens.toLocaleString() : '-'}
                        </td>
                        <td className="py-1 px-2 text-right font-mono text-slate-500 dark:text-gray-400">
                          {hasThinking ? (
                            <span title={`${thinkingTokens.toLocaleString()} thinking + ${answerTokens.toLocaleString()} answer tokens (estimated from char ratio)`}>
                              <span className="text-purple-600 dark:text-purple-400">{thinkingTokens.toLocaleString()}</span>
                              <span className="text-gray-600">/</span>
                              <span className="text-blue-600 dark:text-blue-400">{answerTokens.toLocaleString()}</span>
                            </span>
                          ) : (
                            <span className="text-gray-600">-</span>
                          )}
                        </td>
                        <td className="py-1 px-2 text-right font-mono text-slate-700 dark:text-gray-300">
                          {tokPerSec > 0 ? `${tokPerSec.toFixed(0)} t/s` : '-'}
                        </td>
                        <td className="py-1 px-2 text-right font-mono text-slate-700 dark:text-gray-300">
                          {cost != null && cost > 0
                            ? `$${cost < 0.001 ? cost.toFixed(4) : cost < 0.01 ? cost.toFixed(3) : cost.toFixed(2)}`
                            : cost === 0 ? '$0' : '-'}
                        </td>
                        <td className="py-1 px-2 text-right font-mono text-slate-500 dark:text-gray-400">
                          {latencyMs > 0 ? `${(latencyMs / 1000).toFixed(1)}s` : '-'}
                        </td>
                      </tr>
                    );
                  })}

                  {/* Totals row */}
                  {(() => {
                    const totalTokens = benchmark.questions.reduce((sum, q) => {
                      return sum + (genLookup[q.order]?.tokens || 0);
                    }, 0);
                    const totalLatency = benchmark.questions.reduce((sum, q) => {
                      return sum + (genLookup[q.order]?.latency_ms || 0);
                    }, 0);
                    const totalCost = metrics?.estimated_cost;
                    const avgTokPerSec = totalLatency > 0 ? totalTokens / (totalLatency / 1000) : 0;

                    return (
                      <tr className="border-t-2 border-stone-300 dark:border-gray-600 font-medium">
                        <td className="py-1.5 px-2 text-slate-700 dark:text-gray-300" colSpan={benchmark.criteria.length + 2}>
                          Total
                        </td>
                        <td className="py-1.5 px-2 text-right font-mono text-slate-800 dark:text-gray-200 border-l border-gray-600">
                          {totalTokens > 0 ? totalTokens.toLocaleString() : '-'}
                        </td>
                        <td className="py-1.5 px-2 text-right font-mono text-slate-500 dark:text-gray-400"></td>
                        <td className="py-1.5 px-2 text-right font-mono text-slate-800 dark:text-gray-200">
                          {avgTokPerSec > 0 ? `${avgTokPerSec.toFixed(0)} t/s` : '-'}
                        </td>
                        <td className="py-1.5 px-2 text-right font-mono text-slate-800 dark:text-gray-200">
                          {totalCost != null
                            ? totalCost === 0 ? '$0' : `$${totalCost < 0.01 ? totalCost.toFixed(3) : totalCost.toFixed(2)}`
                            : '-'}
                        </td>
                        <td className="py-1.5 px-2 text-right font-mono text-slate-800 dark:text-gray-200">
                          {totalLatency > 0 ? `${(totalLatency / 1000).toFixed(1)}s` : '-'}
                        </td>
                      </tr>
                    );
                  })()}
                </tbody>
              </table>
            </div>
          )}

          {/* Judge Feedback Summary */}
          {summaries && judgeNames.length > 0 && (
            <div className="space-y-3">
              <div className="text-xs text-slate-400 dark:text-gray-500 uppercase tracking-wider font-medium">Judge Feedback</div>
              {judgeNames.map(judge => {
                const summary = summaries[judge]?.[model];
                if (!summary) return null;

                if (typeof summary === 'object' && summary.verdict) {
                  return (
                    <div key={judge} className="text-sm">
                      <span className="text-purple-600 dark:text-purple-400 text-xs uppercase tracking-wide font-medium">{judge}:</span>
                      <p className="text-slate-800 dark:text-gray-200 mt-1 font-medium">{summary.verdict}</p>
                      <div className="flex gap-6 mt-1.5">
                        {summary.strengths?.length > 0 && (
                          <ul className="space-y-0.5">
                            {summary.strengths.map((s, i) => (
                              <li key={i} className="text-green-600 dark:text-green-400/80 text-xs">+ {s}</li>
                            ))}
                          </ul>
                        )}
                        {summary.weaknesses?.length > 0 && (
                          <ul className="space-y-0.5">
                            {summary.weaknesses.map((w, i) => (
                              <li key={i} className="text-amber-700 dark:text-amber-400/80 text-xs">- {w}</li>
                            ))}
                          </ul>
                        )}
                      </div>
                    </div>
                  );
                }

                return (
                  <div key={judge} className="text-sm">
                    <span className="text-purple-600 dark:text-purple-400 text-xs uppercase tracking-wide font-medium">{judge}:</span>
                    <p className="text-slate-700 dark:text-gray-300 mt-0.5 leading-relaxed">{String(summary)}</p>
                  </div>
                );
              })}
            </div>
          )}
        </div>
      </CardContent>
    </Card>
  );
}
