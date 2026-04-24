/**
 * CompareParentSection — shows a side-by-side comparison of a spin-off
 * run and its parent run, highlighting judge and criteria changes plus
 * per-model score deltas.
 */
import { useQuery } from '@tanstack/react-query';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Loader2 } from 'lucide-react';
import { benchmarksApi } from '@/lib/api';
import { getScoreColor } from '@/lib/scoreColors';

interface CompareParentSectionProps {
  runId: number;
}

interface RunSummary {
  run_id: number;
  name: string;
  status: string;
  judge_mode: string;
  judges: string[];
  criteria: { name: string; description: string; weight: number }[];
  model_scores: Record<string, number | null>;
  completed_at: string | null;
  created_at: string | null;
}

interface CompareParentResponse {
  spinoff: RunSummary;
  parent: RunSummary;
}

function ScoreCell({ score }: { score: number | null | undefined }) {
  if (score == null) return <span className="text-slate-400 dark:text-gray-500">—</span>;
  const color = getScoreColor(score);
  return (
    <span style={{ color }} className="font-semibold tabular-nums">
      {score.toFixed(2)}
    </span>
  );
}

function DeltaCell({ delta }: { delta: number | null }) {
  if (delta == null) return <span className="text-slate-400 dark:text-gray-500">—</span>;
  const sign = delta > 0 ? '+' : '';
  const colorClass =
    delta > 0.1
      ? 'text-green-600 dark:text-green-400'
      : delta < -0.1
      ? 'text-red-500 dark:text-red-400'
      : 'text-slate-500 dark:text-gray-400';
  return (
    <span className={`font-semibold tabular-nums ${colorClass}`}>
      {sign}{delta.toFixed(2)}
    </span>
  );
}

export function CompareParentSection({ runId }: CompareParentSectionProps) {
  const { data, isLoading, error } = useQuery<CompareParentResponse>({
    queryKey: ['compare-parent', runId],
    queryFn: async () => {
      const res = await benchmarksApi.compareParent(runId);
      return res.data;
    },
  });

  if (isLoading) {
    return (
      <div className="flex items-center gap-2 text-slate-500 dark:text-gray-400">
        <Loader2 className="w-4 h-4 animate-spin" />
        <span>Loading parent comparison...</span>
      </div>
    );
  }

  if (error || !data) {
    return (
      <div className="text-red-600 dark:text-red-400">
        Failed to load parent comparison.
      </div>
    );
  }

  const { spinoff, parent } = data;

  // Compute delta: spinoff score – parent score, per model
  const allModels = Array.from(
    new Set([...Object.keys(spinoff.model_scores), ...Object.keys(parent.model_scores)])
  ).sort();

  // Detect changes
  const judgeChanged =
    JSON.stringify([...spinoff.judges].sort()) !== JSON.stringify([...parent.judges].sort());
  const criteriaChanged =
    JSON.stringify(spinoff.criteria.map((c) => c.name).sort()) !==
    JSON.stringify(parent.criteria.map((c) => c.name).sort());

  return (
    <div className="space-y-6">
      <div>
        <h2 className="text-xl font-bold mb-1">Comparison with Parent Run</h2>
        <p className="text-sm text-slate-500 dark:text-gray-400">
          This spin-off was re-judged from{' '}
          <span className="font-medium text-slate-700 dark:text-gray-200">
            #{parent.run_id} — {parent.name}
          </span>
          . The same model responses were re-evaluated with different judges or criteria.
        </p>
      </div>

      {/* Change summary badges */}
      <div className="flex flex-wrap gap-2">
        {judgeChanged && (
          <span className="px-2 py-1 text-xs font-medium bg-amber-100 dark:bg-amber-900/40 text-amber-800 dark:text-amber-300 rounded-full border border-amber-200 dark:border-amber-700">
            Judges changed
          </span>
        )}
        {criteriaChanged && (
          <span className="px-2 py-1 text-xs font-medium bg-purple-100 dark:bg-purple-900/40 text-purple-800 dark:text-purple-300 rounded-full border border-purple-200 dark:border-purple-700">
            Criteria changed
          </span>
        )}
        {!judgeChanged && !criteriaChanged && (
          <span className="px-2 py-1 text-xs font-medium bg-stone-100 dark:bg-gray-700 text-slate-600 dark:text-gray-300 rounded-full border border-stone-200 dark:border-gray-600">
            Same judges and criteria
          </span>
        )}
      </div>

      {/* Side-by-side metadata */}
      <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
        <Card className="bg-stone-50 dark:bg-gray-800 border-stone-200 dark:border-gray-700">
          <CardHeader className="pb-2">
            <CardTitle className="text-sm font-semibold text-slate-500 dark:text-gray-400 uppercase tracking-wide">
              Parent Run #{parent.run_id}
            </CardTitle>
            <p className="text-base font-medium">{parent.name}</p>
          </CardHeader>
          <CardContent className="space-y-2 text-sm">
            <div>
              <span className="text-slate-500 dark:text-gray-400">Judges: </span>
              {parent.judges.length > 0 ? parent.judges.join(', ') : '—'}
            </div>
            <div>
              <span className="text-slate-500 dark:text-gray-400">Criteria: </span>
              {parent.criteria.map((c) => c.name).join(', ') || '—'}
            </div>
          </CardContent>
        </Card>

        <Card className="bg-blue-50 dark:bg-blue-900/20 border-blue-200 dark:border-blue-800">
          <CardHeader className="pb-2">
            <CardTitle className="text-sm font-semibold text-blue-500 dark:text-blue-400 uppercase tracking-wide">
              This Spin-off #{spinoff.run_id}
            </CardTitle>
            <p className="text-base font-medium">{spinoff.name}</p>
          </CardHeader>
          <CardContent className="space-y-2 text-sm">
            <div>
              <span className="text-slate-500 dark:text-gray-400">Judges: </span>
              <span className={judgeChanged ? 'text-amber-700 dark:text-amber-400 font-medium' : ''}>
                {spinoff.judges.length > 0 ? spinoff.judges.join(', ') : '—'}
              </span>
            </div>
            <div>
              <span className="text-slate-500 dark:text-gray-400">Criteria: </span>
              <span className={criteriaChanged ? 'text-purple-700 dark:text-purple-400 font-medium' : ''}>
                {spinoff.criteria.map((c) => c.name).join(', ') || '—'}
              </span>
            </div>
          </CardContent>
        </Card>
      </div>

      {/* Score delta table */}
      {allModels.length > 0 && (
        <Card className="bg-stone-50 dark:bg-gray-800 border-stone-200 dark:border-gray-700">
          <CardHeader>
            <CardTitle className="text-base">Avg. Weighted Score Comparison</CardTitle>
          </CardHeader>
          <CardContent>
            <div className="overflow-x-auto">
              <table className="w-full text-sm">
                <thead>
                  <tr className="border-b border-stone-200 dark:border-gray-700">
                    <th className="text-left py-2 pr-4 font-medium text-slate-600 dark:text-gray-300">
                      Model
                    </th>
                    <th className="text-right py-2 px-3 font-medium text-slate-600 dark:text-gray-300">
                      Parent
                    </th>
                    <th className="text-right py-2 px-3 font-medium text-slate-600 dark:text-gray-300">
                      Spin-off
                    </th>
                    <th className="text-right py-2 pl-3 font-medium text-slate-600 dark:text-gray-300">
                      Delta
                    </th>
                  </tr>
                </thead>
                <tbody>
                  {allModels.map((model) => {
                    const parentScore = parent.model_scores[model] ?? null;
                    const spinoffScore = spinoff.model_scores[model] ?? null;
                    const delta =
                      spinoffScore != null && parentScore != null
                        ? spinoffScore - parentScore
                        : null;
                    return (
                      <tr
                        key={model}
                        className="border-b border-stone-100 dark:border-gray-700/50 last:border-0"
                      >
                        <td className="py-2 pr-4 font-medium">{model}</td>
                        <td className="py-2 px-3 text-right">
                          <ScoreCell score={parentScore} />
                        </td>
                        <td className="py-2 px-3 text-right">
                          <ScoreCell score={spinoffScore} />
                        </td>
                        <td className="py-2 pl-3 text-right">
                          <DeltaCell delta={delta} />
                        </td>
                      </tr>
                    );
                  })}
                </tbody>
              </table>
            </div>
          </CardContent>
        </Card>
      )}
    </div>
  );
}
