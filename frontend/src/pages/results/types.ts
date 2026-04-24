export const slugify = (s: string) => s.toLowerCase().replace(/[^a-z0-9]+/g, '-').replace(/^-|-$/g, '');

export const PROVIDER_COLORS: Record<string, string> = {
  anthropic: '#f97316', openai: '#22c55e', google: '#3b82f6',
  mistral: '#a855f7', deepseek: '#06b6d4', grok: '#ef4444',
  glm: '#eab308', kimi: '#ec4899', lmstudio: '#6b7280',
};

export const PROVIDER_LABELS: Record<string, string> = {
  anthropic: 'Anthropic', openai: 'OpenAI', google: 'Google',
  mistral: 'Mistral', deepseek: 'DeepSeek', grok: 'Grok',
  glm: 'GLM', kimi: 'Kimi', lmstudio: 'LM Studio',
};

export interface JudgeSummary {
  agreement_rate: number;
  disagreement_count: number;
  disagreement_questions: number[];
  per_judge_winners: Record<string, Record<string, number>>;
}

export interface ModelPerformanceMetrics {
  total_tokens: number;
  total_latency_ms: number;
  tokens_per_second: number | null;
  estimated_cost: number | null;
  price_input_1m: number | null;
  price_output_1m: number | null;
  provider: string | null;
}

export interface JudgePerformanceMetrics {
  total_tokens: number;
  total_latency_ms: number;
  tokens_per_second: number | null;
  estimated_cost: number | null;
  judgment_count: number;
}

export interface BenchmarkRunConfigSnapshot {
  models?: Array<{
    id?: number;
    [key: string]: unknown;
  }> | null;
  [key: string]: unknown;
}

export interface BenchmarkDetail {
  id: number;
  name: string;
  status: string;
  judge_mode: string;
  criteria: { name: string; description: string; weight: number }[];
  model_ids: number[];
  judge_ids: number[];
  created_at: string;
  completed_at: string | null;
  parent_run_id?: number | null;
  judge_summary?: JudgeSummary;
  performance_metrics?: Record<string, ModelPerformanceMetrics>;
  judge_metrics?: Record<string, JudgePerformanceMetrics>;
  comment_summaries?: Record<string, Record<string, string | { verdict: string; strengths: string[]; weaknesses: string[] }>>;
  total_context_tokens?: number;
  kappa_value?: number | null;
  kappa_type?: string | null;
  run_config_snapshot?: BenchmarkRunConfigSnapshot | null;
  questions: {
    id: number;
    order: number;
    system_prompt: string;
    user_prompt: string;
    expected_answer?: string | null;
    estimated_context_tokens?: number;
    attachments?: Array<{
      id: number;
      filename: string;
      mime_type: string;
      inherited: boolean;
    }>;
    generations: {
      id: number;
      model_preset_id: number;
      model_name: string;
      content: string;
      tokens: number;
      output_tokens?: number | null;
      reasoning_tokens?: number | null;
      raw_chars?: number | null;
      answer_chars?: number | null;
      latency_ms?: number;
      status: string;
      error?: string;
    }[];
    judgments: {
      id: number;
      judge_id: number;
      judge_name: string;
      blind_mapping: Record<string, number>;
      rankings: string[];
      scores: Record<number, Record<string, number>>;
      reasoning: string;
      score_rationales?: Record<number, string> | null;
      comments?: Record<number, { text: string; sentiment: 'positive' | 'negative' }[]>;
      latency_ms?: number;
      status: string;
      error?: string;
    }[];
  }[];
}

export interface JudgeCommentDisplay {
  judgeName: string;
  score: number | null;
  scoreRationale: string;
  hasScoreRationale: boolean;
  comments: { text: string; sentiment: 'positive' | 'negative' }[];
}

function getModelValue<T>(
  data: Record<number, T> | Record<string, T> | null | undefined,
  modelPresetId: number,
): T | undefined {
  if (!data) return undefined;
  return (data as Record<number, T>)[modelPresetId] ?? (data as Record<string, T>)[String(modelPresetId)];
}

export function buildJudgeCommentDisplay(
  judgment: BenchmarkDetail['questions'][0]['judgments'][0],
  modelPresetId: number,
): JudgeCommentDisplay | null {
  if (judgment.status !== 'success') return null;

  const scores = judgment.scores?.[modelPresetId];
  const validScores = scores
    ? Object.values(scores).filter((score): score is number => typeof score === 'number')
    : [];
  const avg = validScores.length > 0
    ? validScores.reduce((sum, score) => sum + score, 0) / validScores.length
    : null;

  const scoreRationale = getModelValue(judgment.score_rationales, modelPresetId)?.trim() ?? '';

  return {
    judgeName: judgment.judge_name,
    score: avg,
    scoreRationale: scoreRationale || 'No score rationale recorded.',
    hasScoreRationale: scoreRationale.length > 0,
    comments: getModelValue(judgment.comments, modelPresetId) ?? [],
  };
}

export function getScore(scores: Record<string, number> | undefined, criterionName: string): number | undefined {
  if (!scores) return undefined;
  if (scores[criterionName] !== undefined) return scores[criterionName];
  const lowerKey = criterionName.toLowerCase();
  for (const [key, value] of Object.entries(scores)) {
    if (key.toLowerCase() === lowerKey) return value;
  }
  return undefined;
}
