import { useQuery } from '@tanstack/react-query';
import { benchmarksApi } from '@/lib/api';
import type { BiasReport } from '@/types/statistics';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Alert, AlertDescription } from '@/components/ui/alert';
import { AlertCircle } from 'lucide-react';

interface BiasDetectionProps {
  runId: number;
}

const severityColors = {
  none: 'text-green-600 dark:text-green-500',
  low: 'text-yellow-500',
  moderate: 'text-orange-500',
  high: 'text-red-600 dark:text-red-500',
};

const severityBgColors = {
  none: 'bg-green-100 dark:bg-green-900/20 border-green-600',
  low: 'bg-amber-100 dark:bg-yellow-900/20 border-yellow-600',
  moderate: 'bg-amber-100 dark:bg-orange-900/20 border-orange-600',
  high: 'bg-red-100 dark:bg-red-900/20 border-red-600',
};

export function BiasDetection({ runId }: BiasDetectionProps) {
  const { data, isLoading, error } = useQuery<BiasReport>({
    queryKey: ['run-bias', runId],
    queryFn: () => benchmarksApi.bias(runId),
  });

  if (isLoading) {
    return (
      <Card className="bg-stone-50 dark:bg-gray-800 border-stone-200 dark:border-gray-700">
        <CardContent className="p-6">
          <div className="flex items-center justify-center">
            <div className="animate-spin rounded-full h-8 w-8 border-b-2 border-white"></div>
            <span className="ml-3 text-slate-700 dark:text-gray-300">Loading bias detection analysis...</span>
          </div>
        </CardContent>
      </Card>
    );
  }

  if (error) {
    return (
      <Card className="bg-stone-50 dark:bg-gray-800 border-stone-200 dark:border-gray-700">
        <CardContent className="p-6">
          <p className="text-red-600 dark:text-red-500">Error loading bias analysis: {String(error)}</p>
        </CardContent>
      </Card>
    );
  }

  if (!data) return null;

  const biasIndicators = [
    { key: 'position_bias', label: 'Position Bias', indicator: data.position_bias },
    { key: 'length_bias', label: 'Length Bias', indicator: data.length_bias },
    { key: 'self_preference', label: 'Self-Preference', indicator: data.self_preference },
    { key: 'verbosity_bias', label: 'Verbosity Bias', indicator: data.verbosity_bias },
  ];

  return (
    <div className="space-y-6">
      {/* Overall Summary */}
      <Alert className={severityBgColors[data.overall_severity as keyof typeof severityBgColors] || 'bg-stone-50 dark:bg-gray-800 border-stone-200 dark:border-gray-700'}>
        <AlertCircle className={`h-4 w-4 ${severityColors[data.overall_severity as keyof typeof severityColors] || 'text-slate-500 dark:text-gray-400'}`} />
        <AlertDescription className="text-gray-900 dark:text-gray-100">
          <strong className="font-semibold">Overall Bias Severity: {data.overall_severity}</strong>
          <br />
          {data.summary}
        </AlertDescription>
      </Alert>

      {/* Bias Indicator Cards */}
      <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
        {biasIndicators.map(({ key, label, indicator }) => (
          <Card key={key} className="bg-stone-50 dark:bg-gray-800 border-stone-200 dark:border-gray-700">
            <CardHeader>
              <CardTitle className="text-gray-900 dark:text-white flex items-center gap-3">
                <div className={`w-4 h-4 rounded-full ${severityColors[indicator.severity]}`} style={{ backgroundColor: 'currentColor' }} />
                {label}
              </CardTitle>
            </CardHeader>
            <CardContent>
              <div className="space-y-2">
                <p className="text-slate-700 dark:text-gray-300 text-sm">{indicator.description}</p>
                <div className="flex gap-4 mt-3">
                  {indicator.correlation !== null && (
                    <div>
                      <p className="text-slate-500 dark:text-gray-400 text-xs">Correlation</p>
                      <p className="text-gray-900 dark:text-white font-medium">{indicator.correlation.toFixed(3)}</p>
                    </div>
                  )}
                  {indicator.p_value !== null && (
                    <div>
                      <p className="text-slate-500 dark:text-gray-400 text-xs">p-value</p>
                      <p className="text-gray-900 dark:text-white font-medium">{indicator.p_value.toFixed(3)}</p>
                    </div>
                  )}
                </div>
                <div className="mt-2">
                  <span className={`text-sm font-semibold ${severityColors[indicator.severity]}`}>
                    Severity: {indicator.severity}
                  </span>
                </div>
              </div>
            </CardContent>
          </Card>
        ))}
      </div>
    </div>
  );
}
