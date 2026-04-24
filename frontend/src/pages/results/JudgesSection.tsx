import { JudgeCalibration } from '@/components/statistics/JudgeCalibration';

interface JudgesSectionProps {
  runId: number;
}

export function JudgesSection({ runId }: JudgesSectionProps) {
  return <JudgeCalibration runId={runId} />;
}
