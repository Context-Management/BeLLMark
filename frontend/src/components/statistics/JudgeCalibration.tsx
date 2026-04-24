import { useQuery } from '@tanstack/react-query';
import { benchmarksApi } from '@/lib/api';
import type { CalibrationReport } from '@/types/statistics';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Alert, AlertDescription } from '@/components/ui/alert';
import { Badge } from '@/components/ui/badge';
import { Progress } from '@/components/ui/progress';
import { Info } from 'lucide-react';

interface JudgeCalibrationProps {
  runId: number;
}

function getIccColor(icc: number | null): string {
  if (icc === null) return 'text-slate-400 dark:text-gray-500';
  if (icc >= 0.75) return 'text-green-600 dark:text-green-500';
  if (icc >= 0.60) return 'text-yellow-500';
  if (icc >= 0.40) return 'text-orange-500';
  return 'text-red-600 dark:text-red-500';
}

function getKappaColor(kappa: number | null): string {
  if (kappa === null) return 'bg-gray-500';
  if (kappa >= 0.80) return 'bg-green-500';
  if (kappa >= 0.60) return 'bg-yellow-500';
  if (kappa >= 0.40) return 'bg-orange-500';
  return 'bg-red-500';
}

function getReliabilityColor(reliability: number): string {
  if (reliability >= 0.80) return 'bg-green-600';
  if (reliability >= 0.60) return 'bg-yellow-600';
  if (reliability >= 0.40) return 'bg-orange-600';
  return 'bg-red-600';
}

export function JudgeCalibration({ runId }: JudgeCalibrationProps) {
  const { data, isLoading, error } = useQuery<CalibrationReport>({
    queryKey: ['run-calibration', runId],
    queryFn: () => benchmarksApi.calibration(runId),
  });

  if (isLoading) {
    return (
      <Card className="bg-stone-50 dark:bg-gray-800 border-stone-200 dark:border-gray-700">
        <CardContent className="p-6">
          <div className="flex items-center justify-center">
            <div className="animate-spin rounded-full h-8 w-8 border-b-2 border-white"></div>
            <span className="ml-3 text-slate-700 dark:text-gray-300">Loading judge calibration analysis...</span>
          </div>
        </CardContent>
      </Card>
    );
  }

  if (error) {
    return (
      <Card className="bg-stone-50 dark:bg-gray-800 border-stone-200 dark:border-gray-700">
        <CardContent className="p-6">
          <p className="text-red-600 dark:text-red-500">Error loading calibration analysis: {String(error)}</p>
        </CardContent>
      </Card>
    );
  }

  if (!data) return null;

  return (
    <div className="space-y-6">
      {/* ICC Score */}
      <Card className="bg-stone-50 dark:bg-gray-800 border-stone-200 dark:border-gray-700">
        <CardHeader>
          <CardTitle className="text-gray-900 dark:text-white">Inter-Rater Reliability (ICC)</CardTitle>
        </CardHeader>
        <CardContent>
          <div className="flex items-center gap-4">
            <div className="flex-1">
              <p className={`text-4xl font-bold ${getIccColor(data.icc)}`}>
                {data.icc !== null ? data.icc.toFixed(3) : 'N/A'}
              </p>
              <p className="text-slate-500 dark:text-gray-400 mt-1">{data.icc_interpretation}</p>
            </div>
            {data.icc !== null && (
              <div className="flex-1">
                <Progress
                  value={data.icc * 100}
                  className="h-4"
                />
              </div>
            )}
          </div>
        </CardContent>
      </Card>

      {/* Pairwise Kappa */}
      <Card className="bg-stone-50 dark:bg-gray-800 border-stone-200 dark:border-gray-700">
        <CardHeader>
          <CardTitle className="text-gray-900 dark:text-white">Pairwise Judge Agreement (Cohen's Kappa)</CardTitle>
        </CardHeader>
        <CardContent>
          <div className="overflow-x-auto">
            <table className="w-full text-sm">
              <thead>
                <tr className="border-b border-stone-200 dark:border-gray-700">
                  <th className="text-left py-3 px-4 text-slate-700 dark:text-gray-300 font-medium">Judge Pair</th>
                  <th className="text-left py-3 px-4 text-slate-700 dark:text-gray-300 font-medium">Kappa</th>
                  <th className="text-left py-3 px-4 text-slate-700 dark:text-gray-300 font-medium">Interpretation</th>
                </tr>
              </thead>
              <tbody>
                {Object.entries(data.pairwise_kappa).map(([pair, kappaPair]) => (
                  <tr key={pair} className="border-b border-stone-200 dark:border-gray-700/50">
                    <td className="py-3 px-4 text-gray-900 dark:text-white">{pair}</td>
                    <td className="py-3 px-4">
                      {kappaPair.kappa !== null ? (
                        <div className="flex items-center gap-2">
                          <div className="w-24 h-4 bg-stone-200 dark:bg-gray-700 rounded-full overflow-hidden">
                            <div
                              className={`h-full ${getKappaColor(kappaPair.kappa)}`}
                              style={{ width: `${Math.max(0, Math.min(100, kappaPair.kappa * 100))}%` }}
                            />
                          </div>
                          <span className="text-slate-700 dark:text-gray-300">{kappaPair.kappa.toFixed(3)}</span>
                        </div>
                      ) : (
                        <span className="text-slate-400 dark:text-gray-500">N/A</span>
                      )}
                    </td>
                    <td className="py-3 px-4 text-slate-700 dark:text-gray-300">{kappaPair.interpretation}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </CardContent>
      </Card>

      {/* Per-Judge Reliability */}
      <Card className="bg-stone-50 dark:bg-gray-800 border-stone-200 dark:border-gray-700">
        <CardHeader>
          <CardTitle className="text-gray-900 dark:text-white">Individual Judge Reliability</CardTitle>
        </CardHeader>
        <CardContent>
          <div className="space-y-4">
            {Object.entries(data.judge_reliability).map(([judge, reliability]) => (
              <div key={judge} className="space-y-2">
                <div className="flex justify-between items-center">
                  <span className="text-gray-900 dark:text-white font-medium">{judge}</span>
                  <div className="flex items-center gap-2">
                    <Badge
                      variant="secondary"
                      className={getReliabilityColor(reliability.reliability)}
                    >
                      {reliability.interpretation}
                    </Badge>
                    <span className="text-slate-500 dark:text-gray-400 text-sm">
                      {reliability.judgment_count} judgments
                    </span>
                  </div>
                </div>
                <Progress
                  value={reliability.reliability * 100}
                  className="h-2"
                />
                <p className="text-xs text-slate-500 dark:text-gray-400">
                  Reliability score: {reliability.reliability.toFixed(3)}
                </p>
              </div>
            ))}
          </div>
        </CardContent>
      </Card>

      {/* Recommendations */}
      {data.recommendations.length > 0 && (
        <Alert className="bg-blue-100 dark:bg-blue-900/20 border-blue-600">
          <Info className="h-4 w-4 text-blue-600 dark:text-blue-400" />
          <AlertDescription className="text-blue-700 dark:text-blue-200">
            <p className="font-semibold mb-2">Recommendations:</p>
            <ul className="list-disc list-inside space-y-1">
              {data.recommendations.map((rec, idx) => (
                <li key={idx}>{rec}</li>
              ))}
            </ul>
          </AlertDescription>
        </Alert>
      )}
    </div>
  );
}
