export interface ConfidenceInterval {
  lower: number;
  mean: number;
  upper: number;
}

export interface LcWinRate {
  raw_win_rate: number;
  lc_win_rate: number;
  n_flagged: number;
  n_total: number;
  length_bias_detected: boolean;
  bias_magnitude: number;
}

export interface PairwiseComparison {
  model_a: string;
  model_b: string;
  score_diff: number;
  cohens_d: number | null;
  p_value: number | null;
  adjusted_p: number | null;
  significant: boolean;
  exploratory: boolean;
  effect_label: string;
  lc_win_rate: LcWinRate | null;
}

export interface FriedmanResult {
  chi_square: number;
  p_value: number;
  significant: boolean;
  n_models: number;
  n_questions: number;
  error?: string;
}

export interface ModelStatistics {
  model_name: string;
  weighted_score_ci: ConfidenceInterval | null;
  per_criterion_ci: Record<string, ConfidenceInterval>;
  win_rate: number;
  win_rate_ci: ConfidenceInterval | null;
  lc_win_rate: LcWinRate | null;
}

export interface PowerAnalysis {
  current_questions: number;
  recommended_small_effect: number;
  recommended_medium_effect: number;
  recommended_large_effect: number;
  adequate_for: string;
}

export interface RunStatistics {
  model_statistics: ModelStatistics[];
  pairwise_comparisons: PairwiseComparison[];
  friedman: FriedmanResult | null;
  power_analysis: PowerAnalysis;
  sample_size_warning: string | null;
}

export interface BiasIndicator {
  name: string;
  severity: "none" | "low" | "moderate" | "high";
  correlation: number | null;
  p_value: number | null;
  description: string;
  details?: Record<string, unknown>;
}

export interface BiasReport {
  position_bias: BiasIndicator;
  length_bias: BiasIndicator;
  self_preference: BiasIndicator;
  verbosity_bias: BiasIndicator;
  overall_severity: string;
  summary: string;
}

export interface JudgeReliability {
  reliability: number;
  judgment_count: number;
  interpretation: string;
}

export interface KappaPair {
  kappa: number | null;
  interpretation: string;
}

export interface CalibrationReport {
  pairwise_kappa: Record<string, KappaPair>;
  icc: number | null;
  icc_interpretation: string;
  judge_reliability: Record<string, JudgeReliability>;
  recommendations: string[];
}

export interface EloRating {
  model_id: number;
  model_name: string;
  provider: string;
  rating: number;
  uncertainty: number;
  games_played: number;
  updated_at: string | null;
  is_reasoning: boolean;
  reasoning_level: string | null;
}

export interface EloLeaderboard {
  ratings: EloRating[];
  total_models: number;
}

export interface EloHistoryPoint {
  benchmark_run_id: number;
  run_name: string;
  rating_before: number;
  rating_after: number;
  games_in_run: number;
  created_at: string;
}

export interface AggregateModelEntry {
  model_preset_id: number;
  model_name: string;
  provider: string;
  questions_won: number;
  questions_lost: number;
  questions_tied: number;
  total_questions: number;
  win_rate: number | null;
  avg_weighted_score: number | null;
  scored_questions: number;
  runs_participated: number;
  is_reasoning: boolean;
  reasoning_level: string | null;
}

export interface AggregateLeaderboard {
  models: AggregateModelEntry[];
}
