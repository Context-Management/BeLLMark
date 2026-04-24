import { StatisticalSummary } from '@/components/statistics/StatisticalSummary';
import { BiasDetection } from '@/components/statistics/BiasDetection';

interface StatsSectionProps {
  runId: number;
}

export function StatsSection({ runId }: StatsSectionProps) {
  return (
    <div className="space-y-6">
      <StatisticalSummary runId={runId} />
      <BiasDetection runId={runId} />
    </div>
  );
}
