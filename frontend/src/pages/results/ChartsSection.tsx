import { ScatterChart, Scatter, XAxis, YAxis, CartesianGrid, Tooltip, ResponsiveContainer, Cell } from 'recharts';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { PROVIDER_COLORS, PROVIDER_LABELS } from './types';
import type { BenchmarkDetail } from './types';
import type { ComputedResultsData } from './computeResultsData';
import { useTheme } from '@/lib/theme';

interface ChartsSectionProps {
  benchmark: BenchmarkDetail;
  computed: ComputedResultsData;
}

interface ScatterPoint {
  model: string;
  score: number;
  blendedPrice: number;
  tokensPerSec: number | null | undefined;
  costPerAnswer: number | null;
  provider: string;
  color: string;
}

interface TooltipProps {
  active?: boolean;
  payload?: Array<{ payload: ScatterPoint }>;
}

function CustomTooltip({ active, payload }: TooltipProps) {
  if (!active || !payload?.[0]) return null;
  const d = payload[0].payload;
  return (
    <div className="bg-white dark:bg-gray-900 border border-stone-200 dark:border-gray-700 rounded px-3 py-2 text-xs shadow-lg">
      <div className="font-semibold text-gray-900 dark:text-white mb-1">{d.model}</div>
      <div className="text-slate-700 dark:text-gray-300">Score: <span className="text-gray-900 dark:text-white">{d.score.toFixed(1)}/10</span></div>
      <div className="text-slate-700 dark:text-gray-300">Price: <span className="text-gray-900 dark:text-white">{d.blendedPrice > 0 ? `$${d.blendedPrice.toFixed(2)}/1M tok` : 'Free (local)'}</span></div>
      {d.tokensPerSec != null && (
        <div className="text-slate-700 dark:text-gray-300">Speed: <span className="text-gray-900 dark:text-white">{d.tokensPerSec.toFixed(1)} tok/s</span></div>
      )}
      {d.costPerAnswer != null && (
        <div className="text-slate-700 dark:text-gray-300">Cost/Answer: <span className="text-gray-900 dark:text-white">${d.costPerAnswer.toFixed(6)}</span></div>
      )}
      <div className="text-slate-500 dark:text-gray-400 mt-1 capitalize">{PROVIDER_LABELS[d.provider] || d.provider}</div>
    </div>
  );
}

export function ChartsSection({ benchmark, computed }: ChartsSectionProps) {
  const { theme } = useTheme();
  const { weightedScores, modelPerformance } = computed;

  if (!benchmark.performance_metrics || Object.keys(weightedScores).length === 0) {
    return null;
  }

  const isDark = theme === 'dark';
  const gridColor = isDark ? '#374151' : '#e7e5e4'; // gray-700 / stone-200
  const tickColor = isDark ? '#9ca3af' : '#64748b'; // gray-400 / slate-500

  // Build scatter data from weighted scores + performance metrics
  const scatterData: ScatterPoint[] = Object.entries(weightedScores).flatMap(([model, score]) => {
    const metrics = benchmark.performance_metrics?.[model];
    if (!metrics) return [];
    const priceIn = metrics.price_input_1m ?? 0;
    const priceOut = metrics.price_output_1m ?? 0;
    const blendedPrice = priceIn * 0.2 + priceOut * 0.8;

    // Cost per answer: (totalTokens / questionCount) * priceOutput / 1_000_000
    const perf = modelPerformance[model];
    let costPerAnswer: number | null = null;
    if (perf && perf.count > 0 && metrics.price_output_1m != null) {
      const avgTokens = perf.totalTokens / perf.count;
      costPerAnswer = (avgTokens * metrics.price_output_1m) / 1_000_000;
    }

    return [{
      model,
      score: Number(score.toFixed(2)),
      blendedPrice: Number(blendedPrice.toFixed(4)),
      tokensPerSec: metrics.tokens_per_second,
      costPerAnswer: costPerAnswer !== null ? Number(costPerAnswer.toFixed(8)) : null,
      provider: metrics.provider || 'unknown',
      color: PROVIDER_COLORS[metrics.provider || ''] || '#6b7280',
    }];
  });

  const hasPriceData = scatterData.some(d => d.blendedPrice > 0);
  const hasSpeedData = scatterData.some(d => d.tokensPerSec != null && d.tokensPerSec > 0);
  const hasCostPerAnswerData = scatterData.some(d => d.costPerAnswer != null && d.costPerAnswer > 0);

  if (!hasPriceData && !hasSpeedData && !hasCostPerAnswerData) {
    return null;
  }

  // Unique providers for legend
  const providers = [...new Set(scatterData.map(d => d.provider))].sort();

  const visibleChartCount = [hasPriceData, hasSpeedData, hasCostPerAnswerData].filter(Boolean).length;
  const gridClass = visibleChartCount === 1
    ? 'grid-cols-1'
    : visibleChartCount === 2
    ? 'grid-cols-1 lg:grid-cols-2'
    : 'grid-cols-1 lg:grid-cols-3';

  return (
    <div className={`grid gap-4 ${gridClass}`}>
      {hasPriceData && (() => {
        const priceProviders = [...new Set(scatterData.map(d => d.provider))].sort();
        return (
          <Card key="price" className="bg-stone-50 dark:bg-gray-800 border-stone-200 dark:border-gray-700">
            <CardHeader className="pb-2">
              <CardTitle className="text-base">Score vs Price ($/1M tokens)</CardTitle>
            </CardHeader>
            <CardContent>
              <div className="flex flex-wrap gap-x-4 gap-y-1 mb-3">
                {priceProviders.map(p => (
                  <div key={p} className="flex items-center gap-1.5 text-xs text-slate-500 dark:text-gray-400">
                    <div className="w-2.5 h-2.5 rounded-full" style={{ backgroundColor: PROVIDER_COLORS[p] || '#6b7280' }} />
                    {PROVIDER_LABELS[p] || p}
                  </div>
                ))}
              </div>
              <ResponsiveContainer width="100%" height={300}>
                <ScatterChart margin={{ top: 10, right: 20, bottom: 20, left: 10 }}>
                  <CartesianGrid strokeDasharray="3 3" stroke={gridColor} />
                  <XAxis
                    type="number"
                    dataKey="blendedPrice"
                    name="Price"
                    domain={[0, 'auto']}
                    tick={{ fill: tickColor, fontSize: 11 }}
                    label={{ value: '$/1M tokens (blended)', position: 'bottom', offset: 5, fill: tickColor, fontSize: 11 }}
                  />
                  <YAxis
                    type="number"
                    dataKey="score"
                    name="Score"
                    domain={[0, 10]}
                    tick={{ fill: tickColor, fontSize: 11 }}
                    label={{ value: 'Score', angle: -90, position: 'insideLeft', offset: 5, fill: tickColor, fontSize: 11 }}
                  />
                  <Tooltip content={<CustomTooltip />} />
                  <Scatter data={scatterData} fill="#8884d8">
                    {scatterData.map((entry, i) => (
                      <Cell key={i} fill={entry.color} r={7} />
                    ))}
                  </Scatter>
                </ScatterChart>
              </ResponsiveContainer>
            </CardContent>
          </Card>
        );
      })()}

      {hasSpeedData && (
        <Card className="bg-stone-50 dark:bg-gray-800 border-stone-200 dark:border-gray-700">
          <CardHeader className="pb-2">
            <CardTitle className="text-base">Score vs Speed (tokens/sec)</CardTitle>
          </CardHeader>
          <CardContent>
            <div className="flex flex-wrap gap-x-4 gap-y-1 mb-3">
              {providers.map(p => (
                <div key={p} className="flex items-center gap-1.5 text-xs text-slate-500 dark:text-gray-400">
                  <div className="w-2.5 h-2.5 rounded-full" style={{ backgroundColor: PROVIDER_COLORS[p] || '#6b7280' }} />
                  {PROVIDER_LABELS[p] || p}
                </div>
              ))}
            </div>
            <ResponsiveContainer width="100%" height={300}>
              <ScatterChart margin={{ top: 10, right: 20, bottom: 20, left: 10 }}>
                <CartesianGrid strokeDasharray="3 3" stroke={gridColor} />
                <XAxis
                  type="number"
                  dataKey="tokensPerSec"
                  name="Speed"
                  tick={{ fill: tickColor, fontSize: 11 }}
                  label={{ value: 'tokens/sec', position: 'bottom', offset: 5, fill: tickColor, fontSize: 11 }}
                />
                <YAxis
                  type="number"
                  dataKey="score"
                  name="Score"
                  domain={[0, 10]}
                  tick={{ fill: tickColor, fontSize: 11 }}
                  label={{ value: 'Score', angle: -90, position: 'insideLeft', offset: 5, fill: tickColor, fontSize: 11 }}
                />
                <Tooltip content={<CustomTooltip />} />
                <Scatter data={scatterData.filter(d => d.tokensPerSec != null)} fill="#8884d8">
                  {scatterData.filter(d => d.tokensPerSec != null).map((entry, i) => (
                    <Cell key={i} fill={entry.color} r={7} />
                  ))}
                </Scatter>
              </ScatterChart>
            </ResponsiveContainer>
          </CardContent>
        </Card>
      )}

      {hasCostPerAnswerData && (() => {
        const costData = scatterData.filter(d => d.costPerAnswer != null);
        const costProviders = [...new Set(costData.map(d => d.provider))].sort();
        return (
          <Card key="costPerAnswer" className="bg-stone-50 dark:bg-gray-800 border-stone-200 dark:border-gray-700">
            <CardHeader className="pb-2">
              <CardTitle className="text-base">Score vs Cost per Answer</CardTitle>
            </CardHeader>
            <CardContent>
              <div className="flex flex-wrap gap-x-4 gap-y-1 mb-3">
                {costProviders.map(p => (
                  <div key={p} className="flex items-center gap-1.5 text-xs text-slate-500 dark:text-gray-400">
                    <div className="w-2.5 h-2.5 rounded-full" style={{ backgroundColor: PROVIDER_COLORS[p] || '#6b7280' }} />
                    {PROVIDER_LABELS[p] || p}
                  </div>
                ))}
              </div>
              <ResponsiveContainer width="100%" height={300}>
                <ScatterChart margin={{ top: 10, right: 20, bottom: 20, left: 10 }}>
                  <CartesianGrid strokeDasharray="3 3" stroke={gridColor} />
                  <XAxis
                    type="number"
                    dataKey="costPerAnswer"
                    name="Cost/Answer"
                    tick={{ fill: tickColor, fontSize: 11 }}
                    label={{ value: '$/answer', position: 'bottom', offset: 5, fill: tickColor, fontSize: 11 }}
                    tickFormatter={(v: number) => `$${v.toFixed(4)}`}
                  />
                  <YAxis
                    type="number"
                    dataKey="score"
                    name="Score"
                    domain={[0, 10]}
                    tick={{ fill: tickColor, fontSize: 11 }}
                    label={{ value: 'Score', angle: -90, position: 'insideLeft', offset: 5, fill: tickColor, fontSize: 11 }}
                  />
                  <Tooltip content={<CustomTooltip />} />
                  <Scatter data={costData} fill="#8884d8">
                    {costData.map((entry, i) => (
                      <Cell key={i} fill={entry.color} r={7} />
                    ))}
                  </Scatter>
                </ScatterChart>
              </ResponsiveContainer>
            </CardContent>
          </Card>
        );
      })()}
    </div>
  );
}
