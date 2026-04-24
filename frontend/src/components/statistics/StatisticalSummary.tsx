import { useQuery } from '@tanstack/react-query';
import { benchmarksApi } from '@/lib/api';
import type { RunStatistics } from '@/types/statistics';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Alert, AlertDescription } from '@/components/ui/alert';
import { Badge } from '@/components/ui/badge';
import { AlertTriangle } from 'lucide-react';

interface StatisticalSummaryProps {
  runId: number;
}

export function StatisticalSummary({ runId }: StatisticalSummaryProps) {
  const { data, isLoading, error } = useQuery<RunStatistics>({
    queryKey: ['run-statistics', runId],
    queryFn: () => benchmarksApi.statistics(runId),
  });

  if (isLoading) {
    return (
      <Card className="bg-stone-50 dark:bg-gray-800 border-stone-200 dark:border-gray-700">
        <CardContent className="p-6">
          <div className="flex items-center justify-center">
            <div className="animate-spin rounded-full h-8 w-8 border-b-2 border-white"></div>
            <span className="ml-3 text-slate-700 dark:text-gray-300">Loading statistical analysis...</span>
          </div>
        </CardContent>
      </Card>
    );
  }

  if (error) {
    return (
      <Card className="bg-stone-50 dark:bg-gray-800 border-stone-200 dark:border-gray-700">
        <CardContent className="p-6">
          <p className="text-red-600 dark:text-red-500">Error loading statistics: {String(error)}</p>
        </CardContent>
      </Card>
    );
  }

  if (!data) return null;

  return (
    <div className="space-y-6">
      {/* Sample Size Warning */}
      {data.sample_size_warning && (
        <Alert className="bg-amber-100 dark:bg-amber-900/20 border-yellow-600">
          <AlertTriangle className="h-4 w-4 text-amber-600 dark:text-amber-500" />
          <AlertDescription className="text-amber-700 dark:text-amber-200">
            {data.sample_size_warning}
          </AlertDescription>
        </Alert>
      )}

      {/* Confidence Intervals */}
      <Card className="bg-stone-50 dark:bg-gray-800 border-stone-200 dark:border-gray-700">
        <CardHeader>
          <CardTitle className="text-gray-900 dark:text-white">Model Performance (95% Confidence Intervals)</CardTitle>
        </CardHeader>
        <CardContent>
          <div className="overflow-x-auto">
            <table className="w-full text-sm">
              <thead>
                <tr className="border-b border-stone-200 dark:border-gray-700">
                  <th className="text-left py-3 px-4 text-slate-700 dark:text-gray-300 font-medium">Model</th>
                  <th className="text-left py-3 px-4 text-slate-700 dark:text-gray-300 font-medium">Score (95% CI)</th>
                  <th className="text-left py-3 px-4 text-slate-700 dark:text-gray-300 font-medium">Win Rate</th>
                  <th
                    className="text-left py-3 px-4 text-slate-700 dark:text-gray-300 font-medium"
                    title="Length-Controlled win rate adjusts for verbosity bias by discounting wins where the winning response was significantly longer."
                  >
                    LC Win Rate
                    <span className="ml-1 text-slate-400 dark:text-gray-500 text-xs cursor-help" title="Length-Controlled win rate adjusts for verbosity bias by discounting wins where the winning response was significantly longer.">(?)</span>
                  </th>
                </tr>
              </thead>
              <tbody>
                {data.model_statistics.map((stat, idx) => (
                  <tr key={idx} className="border-b border-stone-200 dark:border-gray-700/50">
                    <td className="py-3 px-4 text-gray-900 dark:text-white font-medium">{stat.model_name}</td>
                    <td className="py-3 px-4 text-slate-700 dark:text-gray-300">
                      {stat.weighted_score_ci ? (
                        <span>
                          {stat.weighted_score_ci.mean.toFixed(2)}
                          <span className="text-slate-400 dark:text-gray-500 text-xs ml-2">
                            [{stat.weighted_score_ci.lower.toFixed(2)} – {stat.weighted_score_ci.upper.toFixed(2)}]
                          </span>
                        </span>
                      ) : (
                        <span className="text-slate-400 dark:text-gray-500">N/A</span>
                      )}
                    </td>
                    <td className="py-3 px-4 text-slate-700 dark:text-gray-300">
                      {(stat.win_rate * 100).toFixed(1)}%
                      {stat.win_rate_ci && (
                        <span className="text-slate-400 dark:text-gray-500 text-xs ml-2">
                          ±{((stat.win_rate_ci.upper - stat.win_rate_ci.lower) / 2 * 100).toFixed(1)}%
                        </span>
                      )}
                    </td>
                    <td className="py-3 px-4">
                      {stat.lc_win_rate ? (
                        <span className="flex items-center gap-1.5">
                          <span className="text-slate-700 dark:text-gray-300">{(stat.lc_win_rate.lc_win_rate * 100).toFixed(1)}%</span>
                          {stat.lc_win_rate.bias_magnitude > 0.01 && (
                            <span className="text-xs text-amber-600 dark:text-amber-400">
                              ↓{(stat.lc_win_rate.bias_magnitude * 100).toFixed(1)}pp
                            </span>
                          )}
                          {stat.lc_win_rate.length_bias_detected && (
                            <span
                              className="inline-block w-2 h-2 rounded-full bg-amber-400"
                              title={`Length bias detected: ${stat.lc_win_rate.n_flagged} of ${stat.lc_win_rate.n_total} wins discounted for verbosity`}
                            />
                          )}
                        </span>
                      ) : (
                        <span className="text-slate-400 dark:text-gray-500 text-xs">N/A</span>
                      )}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </CardContent>
      </Card>

      {/* Friedman Omnibus Test (k>=3 models) */}
      {data.friedman && (
        <Card className="bg-stone-50 dark:bg-gray-800 border-stone-200 dark:border-gray-700">
          <CardHeader>
            <CardTitle className="text-gray-900 dark:text-white flex items-center gap-3">
              Friedman Omnibus Test
              {data.friedman.error ? (
                <Badge variant="secondary" className="bg-slate-500 text-white">Unavailable</Badge>
              ) : data.friedman.significant ? (
                <Badge variant="default" className="bg-green-600 hover:bg-green-700 text-white">Significant</Badge>
              ) : (
                <Badge variant="secondary" className="bg-amber-600 hover:bg-amber-700 text-white">Not Significant</Badge>
              )}
            </CardTitle>
          </CardHeader>
          <CardContent>
            {data.friedman.error ? (
              <p className="text-slate-500 dark:text-gray-400 text-sm">{data.friedman.error}</p>
            ) : (
              <div className="space-y-3">
                <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
                  <div>
                    <p className="text-slate-500 dark:text-gray-400 text-sm">Chi-square</p>
                    <p className="text-xl font-semibold text-gray-900 dark:text-white">{data.friedman.chi_square.toFixed(3)}</p>
                  </div>
                  <div>
                    <p className="text-slate-500 dark:text-gray-400 text-sm">p-value</p>
                    <p className="text-xl font-semibold text-gray-900 dark:text-white">{data.friedman.p_value.toFixed(4)}</p>
                  </div>
                  <div>
                    <p className="text-slate-500 dark:text-gray-400 text-sm">Models</p>
                    <p className="text-xl font-semibold text-gray-900 dark:text-white">{data.friedman.n_models}</p>
                  </div>
                  <div>
                    <p className="text-slate-500 dark:text-gray-400 text-sm">Questions</p>
                    <p className="text-xl font-semibold text-gray-900 dark:text-white">{data.friedman.n_questions}</p>
                  </div>
                </div>
                {!data.friedman.significant && (
                  <Alert className="bg-amber-100 dark:bg-amber-900/20 border-amber-600 mt-3">
                    <AlertTriangle className="h-4 w-4 text-amber-600 dark:text-amber-500" />
                    <AlertDescription className="text-amber-700 dark:text-amber-200">
                      Friedman test is not significant (p={data.friedman.p_value.toFixed(4)}). Per Demsar 2006, pairwise comparisons below are exploratory and should be interpreted with caution.
                    </AlertDescription>
                  </Alert>
                )}
                {data.friedman.significant && (
                  <p className="text-slate-500 dark:text-gray-400 text-sm">
                    Global differences detected across models (p={data.friedman.p_value.toFixed(4)}). Pairwise comparisons below are confirmatory.
                  </p>
                )}
              </div>
            )}
          </CardContent>
        </Card>
      )}

      {/* Pairwise Comparisons */}
      <Card className="bg-stone-50 dark:bg-gray-800 border-stone-200 dark:border-gray-700">
        <CardHeader>
          <CardTitle className="text-gray-900 dark:text-white flex items-center gap-3">
            Pairwise Model Comparisons
            {data.pairwise_comparisons.length > 0 && data.pairwise_comparisons[0].exploratory && (
              <Badge variant="secondary" className="bg-amber-600 hover:bg-amber-700 text-white">Exploratory</Badge>
            )}
          </CardTitle>
        </CardHeader>
        <CardContent>
          <div className="overflow-x-auto">
            <table className="w-full text-sm">
              <thead>
                <tr className="border-b border-stone-200 dark:border-gray-700">
                  <th className="text-left py-3 px-4 text-slate-700 dark:text-gray-300 font-medium">Model A</th>
                  <th className="text-left py-3 px-4 text-slate-700 dark:text-gray-300 font-medium">Model B</th>
                  <th className="text-left py-3 px-4 text-slate-700 dark:text-gray-300 font-medium">Score Diff</th>
                  <th className="text-left py-3 px-4 text-slate-700 dark:text-gray-300 font-medium">Cohen's d</th>
                  <th className="text-left py-3 px-4 text-slate-700 dark:text-gray-300 font-medium">Adj. p-value</th>
                  <th className="text-left py-3 px-4 text-slate-700 dark:text-gray-300 font-medium">Significance</th>
                  <th className="text-left py-3 px-4 text-slate-700 dark:text-gray-300 font-medium">Effect Size</th>
                </tr>
              </thead>
              <tbody>
                {data.pairwise_comparisons.map((comp, idx) => (
                  <tr key={idx} className="border-b border-stone-200 dark:border-gray-700/50">
                    <td className="py-3 px-4 text-gray-900 dark:text-white">{comp.model_a}</td>
                    <td className="py-3 px-4 text-gray-900 dark:text-white">{comp.model_b}</td>
                    <td className="py-3 px-4 text-slate-700 dark:text-gray-300">
                      {comp.score_diff > 0 ? '+' : ''}{comp.score_diff.toFixed(2)}
                    </td>
                    <td className="py-3 px-4 text-slate-700 dark:text-gray-300">
                      {comp.cohens_d !== null ? comp.cohens_d.toFixed(2) : 'N/A'}
                    </td>
                    <td className="py-3 px-4 text-slate-700 dark:text-gray-300">
                      {comp.adjusted_p !== null ? comp.adjusted_p.toFixed(3) : 'N/A'}
                    </td>
                    <td className="py-3 px-4">
                      <Badge
                        variant={comp.significant ? "default" : "secondary"}
                        className={comp.significant ? "bg-green-600 hover:bg-green-700 text-white" : "bg-slate-500 hover:bg-slate-600 text-white"}
                      >
                        {comp.significant ? 'Significant' : 'Not significant'}
                      </Badge>
                    </td>
                    <td className="py-3 px-4 text-slate-700 dark:text-gray-300">{comp.effect_label}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </CardContent>
      </Card>

      {/* Power Analysis */}
      <Card className="bg-stone-50 dark:bg-gray-800 border-stone-200 dark:border-gray-700">
        <CardHeader>
          <CardTitle className="text-gray-900 dark:text-white">Statistical Power Analysis</CardTitle>
        </CardHeader>
        <CardContent>
          <div className="space-y-4">
            <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
              <div>
                <p className="text-slate-500 dark:text-gray-400 text-sm">Current Questions</p>
                <p className="text-2xl font-bold text-gray-900 dark:text-white">{data.power_analysis.current_questions}</p>
              </div>
              <div>
                <p className="text-slate-500 dark:text-gray-400 text-sm">Small Effect (d=0.2)</p>
                <p className="text-xl font-semibold text-slate-700 dark:text-gray-300">{data.power_analysis.recommended_small_effect}</p>
              </div>
              <div>
                <p className="text-slate-500 dark:text-gray-400 text-sm">Medium Effect (d=0.5)</p>
                <p className="text-xl font-semibold text-slate-700 dark:text-gray-300">{data.power_analysis.recommended_medium_effect}</p>
              </div>
              <div>
                <p className="text-slate-500 dark:text-gray-400 text-sm">Large Effect (d=0.8)</p>
                <p className="text-xl font-semibold text-slate-700 dark:text-gray-300">{data.power_analysis.recommended_large_effect}</p>
              </div>
            </div>
            <div className="mt-4">
              <Badge
                variant="secondary"
                className={
                  data.power_analysis.adequate_for.includes('large') ? 'bg-green-600' :
                  data.power_analysis.adequate_for.includes('medium') ? 'bg-yellow-600' :
                  'bg-orange-600'
                }
              >
                Adequate for: {data.power_analysis.adequate_for}
              </Badge>
            </div>
          </div>
        </CardContent>
      </Card>
    </div>
  );
}
