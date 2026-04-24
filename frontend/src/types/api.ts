// Centralized TypeScript types for API responses

// Model Preset
export interface ModelPreset {
  id: number;
  name: string;
  provider: string;
  base_url: string;
  model_id: string;
  has_api_key: boolean;
  price_input: number | null;
  price_output: number | null;
  price_source: string | null;
  price_source_url: string | null;
  price_checked_at: string | null;
  price_currency: string | null;
  supports_vision: boolean | null;
  context_limit: number | null;
  is_reasoning: boolean;
  reasoning_level: 'none' | 'low' | 'medium' | 'high' | 'xhigh' | 'max' | null;
  custom_temperature: number | null;
  quantization: string | null;
  quantization_bits?: number | null;
  model_format: string | null;
  model_source: string | null;
  parameter_count?: string | null;
  selected_variant?: string | null;
  model_architecture?: string | null;
  supported_reasoning_levels?: string[] | null;
  reasoning_detection_source?: string | null;
  created_at: string;
}

export interface ConcurrencySetting {
  provider: string;
  server_key: string | null;
  max_concurrency: number;
  is_override: boolean;
}

export interface DiscoveredModel {
  model?: string;
  name?: string;
  model_id?: string;
  provider_default_url?: string;
  is_reasoning?: boolean;
  reasoning_level?: string;
  supports_vision?: boolean;
  context_limit?: number;
  price_input?: number;
  price_output?: number;
  price_source?: string;
  price_source_url?: string;
  price_checked_at?: string;
  price_currency?: string;
  quantization?: string;
  quantization_bits?: number;
  parameter_count?: string;
  selected_variant?: string;
  model_architecture?: string;
  model_format?: string;
  model_source?: string;
  supported_reasoning_levels?: string[];
  reasoning_detection_source?: string;
}

export interface ValidationResult {
  preset_id: number;
  provider: string;
  base_url: string;
  status: string;
  message: string;
  live_match?: DiscoveredModel | null;
  metadata_drift: string[];
  suggested_action: string | null;
}

export interface ModelTestResult {
  status: string;
  message?: string | null;
  ok: boolean;
  reachable: boolean;
  provider: string;
  base_url: string;
  model_id: string;
  resolved_model_id?: string | null;
  model_info?: Record<string, unknown> | null;
  reasoning_supported_levels?: string[] | null;
  validation_status?: string | null;
  validation_message?: string | null;
  live_match?: DiscoveredModel | null;
  metadata_drift: string[];
  suggested_action?: string | null;
  error?: string | null;
}

// Benchmark Run (list view)
export interface BenchmarkRun {
  id: number;
  name: string;
  status: string;
  created_at: string;
  model_count: number;
  model_ids: number[];
  judge_count: number;
  judge_ids: number[];
  question_count: number;
  top_models: { name: string; weighted_score: number }[];
  total_cost: number | null;
}

// Benchmark Detail (full view)
export interface BenchmarkDetail {
  id: number;
  name: string;
  status: string;
  created_at: string;
  model_ids: number[];
  judge_ids: number[];
  preset_labels?: Record<number, string>;
  questions: QuestionDetail[];
}

export type QuestionBrowserMatchMode = 'strict' | 'same-label';
export type QuestionBrowserMatchFidelity = 'full' | 'degraded';
export type QuestionBrowserEvaluationMode = 'comparison' | 'separate';
export type QuestionBrowserPickerFrequencyBand = 'all' | 'high' | 'medium' | 'low' | 'zero';

export interface QuestionBrowserPickerGuidanceModel {
  model_preset_id: number;
  name: string;
  provider: string;
  model_id: string;
  model_format: string | null;
  quantization: string | null;
  is_archived: boolean;
  is_reasoning: boolean;
  reasoning_level: string | null;
  resolved_label: string;
  host_label: string;
}

export interface QuestionBrowserPickerCandidate extends QuestionBrowserPickerGuidanceModel {
  active_benchmark_count: number;
  selectable: boolean;
}

export interface QuestionBrowserPickerGuidanceResponse {
  selection_state: number;
  max_active_count: number;
  band_counts: Record<QuestionBrowserPickerFrequencyBand, number>;
  selected_models: QuestionBrowserPickerGuidanceModel[];
  candidates: QuestionBrowserPickerCandidate[];
}

export interface QuestionBrowserSelectedModel {
  model_preset_id: number;
  resolved_label: string;
  match_mode: QuestionBrowserMatchMode;
  match_identity: Record<string, unknown>;
  match_fidelity: QuestionBrowserMatchFidelity;
  source_run_id: number | null;
  source_question_id: number | null;
}

export interface QuestionBrowserSearchRow {
  question_id: number;
  run_id: number;
  run_name: string;
  question_order: number;
  prompt_preview: string;
  match_fidelity: QuestionBrowserMatchFidelity;
}

export interface QuestionBrowserSearchResponse {
  selected_models: QuestionBrowserSelectedModel[];
  rows: QuestionBrowserSearchRow[];
  total_count: number;
  initial_question_id: number | null;
  strict_excluded_count: number;
  limit: number;
  offset: number;
}

export interface QuestionBrowserCardJudgeGrade {
  judge_preset_id: number;
  judge_label: string;
  score: number | null;
  score_rationale: string | null;
  reasoning: string | null;
  comments: string[];
}

export interface QuestionBrowserAnswerCard {
  model_preset_id: number;
  resolved_label: string;
  source_run_id: number;
  source_run_name: string;
  evaluation_mode: QuestionBrowserEvaluationMode;
  run_grade: number | null;
  question_grade: number | null;
  judge_grades: QuestionBrowserCardJudgeGrade[];
  tokens: number | null;
  latency_ms: number | null;
  speed_tokens_per_second: number | null;
  estimated_cost: number | null;
  run_rank: number | null;
  run_rank_total: number | null;
  question_rank: number | null;
  question_rank_total: number | null;
  answer_text: string | null;
  judge_opinions: string[];
  match_fidelity: QuestionBrowserMatchFidelity;
}

export interface QuestionBrowserDetailResponse {
  question_id: number;
  run_id: number;
  run_name: string;
  question_order: number;
  system_prompt: string;
  user_prompt: string;
  expected_answer: string | null;
  selected_models: QuestionBrowserSelectedModel[];
  cards: QuestionBrowserAnswerCard[];
  source_run_id: number | null;
  source_question_id: number | null;
}

// Question (base type)
export interface Question {
  system_prompt: string;
  user_prompt: string;
  expected_answer?: string | null;
}

// Question with attachments (for NewRun)
export interface QuestionWithAttachments extends Question {
  attachment_ids: number[];
}

// Question Detail (with generations and judgments)
export interface QuestionDetail {
  id: number;
  order: number;
  system_prompt: string;
  user_prompt: string;
  expected_answer?: string | null;
  estimated_context_tokens?: number;
  attachments?: { id: number; filename: string; mime_type: string; inherited: boolean }[];
  generations: Generation[];
  judgments: Judgment[];
}

// Generation
export interface Generation {
  id: number;
  model_preset_id: number;
  model_name: string;
  status: 'pending' | 'running' | 'success' | 'failed';
  response: string | null;
  tokens: number | null;
  error: string | null;
  completed_at: string | null;
}

// Judgment
export interface Judgment {
  id: number;
  judge_preset_id: number;
  judge_name: string;
  status: 'pending' | 'running' | 'success' | 'failed';
  rankings: string[] | null;
  blind_mapping: Record<string, number> | null;
  score_rationales: Record<string, string> | null;
  reasoning: string | null;
  error: string | null;
  completed_at: string | null;
}

// Criterion
export interface Criterion {
  name: string;
  description: string;
  weight: number;
}

export interface SuiteGenerationMetadata {
  topic?: string;
  coverage_mode?: string;
  generator_names?: string[];
  editor_name?: string | null;
  reviewer_names?: string[];
  requested_question_count?: number;
  saved_question_count?: number;
  difficulty?: string;
  categories?: string[];
  generate_answers?: boolean;
  criteria_depth?: string;
  context_attachment_id?: number | null;
}

// Judge Summary
export interface JudgeSummary {
  id: number;
  name: string;
  total_judgments: number;
  avg_latency_ms: number | null;
}

// Prompt Suite
export interface PromptSuite {
  id: number;
  name: string;
  description: string | null;
  items: SuiteItem[];
  default_criteria?: Criterion[] | null;
  generation_metadata?: SuiteGenerationMetadata | null;
  coverage_report?: Record<string, unknown> | null;
  dedupe_report?: Record<string, unknown> | null;
  attachments?: { id: number; attachment_id: number; scope: string; suite_item_order: number | null; attachment: { id: number; filename: string; mime_type: string; size_bytes: number } }[];
  item_count?: number;
  attachment_count?: number;
  answer_count?: number;
  created_at: string;
}

// Suite Item
export interface SuiteItem {
  id: number;
  order: number;
  system_prompt: string;
  user_prompt: string;
  expected_answer?: string | null;
  category?: string | null;
  difficulty?: string | null;
  criteria?: Criterion[] | null;
}

// Suite Import Payload
export interface SuiteImportPayload {
  bellmark_version?: string;
  type?: string;
  name: string;
  description?: string;
  default_criteria?: Criterion[];
  questions: {
    system_prompt?: string;
    user_prompt: string;
    expected_answer?: string;
    category?: string | null;
    difficulty?: string | null;
    criteria?: Criterion[] | null;
  }[];
}

// Compare Data
export interface CompareData {
  runs: {
    id: number;
    name: string;
    model_scores: Record<string, number>;
    weighted_scores: Record<string, number>;
    win_counts: Record<string, number>;
  }[];
}

// Performance Metrics
export interface PerformanceMetrics {
  total_tokens: number;
  total_cost: number;
  avg_latency_ms: number;
}
