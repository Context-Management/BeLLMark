// Sample-size thresholds for benchmark statistical reliability messaging.
// Tier 0.2.3 from docs/plans/2026-02-15-bellmark-activity-plan.md.
//
// Rationale:
//   <3 questions  : results are illustrative only, no statistical meaning
//   3–4 questions : usable but margins of error dominate any signal
//   5–9 questions : limited; effect sizes need to be large to detect
//   10+ questions : recommended floor for credible per-model conclusions
//
// Single source of truth — keep aligned with backend export warnings if/when
// added (see backend/app/core/exports/common.py).
export const MIN_MEANINGFUL_QUESTIONS = 3;
export const MIN_USABLE_QUESTIONS = 5;
export const MIN_RECOMMENDED_QUESTIONS = 10;

export type SampleSizeSeverity = 'critical' | 'warning' | 'info' | 'ok';

export interface SampleSizeAssessment {
  severity: SampleSizeSeverity;
  questionCount: number;
  message: string;
}

export function assessSampleSize(questionCount: number): SampleSizeAssessment {
  const plural = questionCount === 1 ? '' : 's';
  if (questionCount === 0) {
    return {
      severity: 'critical',
      questionCount,
      message: `No questions were recorded for this benchmark, so these results cannot support any conclusion. Recommend ${MIN_RECOMMENDED_QUESTIONS}+ questions for a credible run.`,
    };
  }
  if (questionCount < MIN_MEANINGFUL_QUESTIONS) {
    return {
      severity: 'critical',
      questionCount,
      message: `Insufficient sample (${questionCount} question${plural}). Results are illustrative only — not statistically meaningful. Recommend ${MIN_RECOMMENDED_QUESTIONS}+ for credible conclusions.`,
    };
  }
  if (questionCount < MIN_USABLE_QUESTIONS) {
    return {
      severity: 'warning',
      questionCount,
      message: `Small sample (${questionCount} questions). Confidence intervals will be wide; only large effect sizes are detectable. Recommend ${MIN_RECOMMENDED_QUESTIONS}+ for robust conclusions.`,
    };
  }
  if (questionCount < MIN_RECOMMENDED_QUESTIONS) {
    return {
      severity: 'info',
      questionCount,
      message: `Limited sample (${questionCount} questions). Conclusions are usable but increase to ${MIN_RECOMMENDED_QUESTIONS}+ for higher statistical confidence.`,
    };
  }
  return { severity: 'ok', questionCount, message: '' };
}
