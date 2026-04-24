// Suite generation pipeline — frontend helpers and state types

export const ALL_SUITE_GENERATION_CATEGORIES = [
  'reasoning',
  'coding',
  'writing',
  'knowledge-stem',
  'knowledge-humanities',
  'instruction-following',
  'data-analysis',
  'planning',
] as const;

export type SuiteGenerationCategory = (typeof ALL_SUITE_GENERATION_CATEGORIES)[number];

export const SUITE_GENERATION_PHASE_LABELS: Record<string, string> = {
  plan: 'Planning coverage',
  generate: 'Generating questions',
  review: 'Reviewing',
  merge: 'Merging',
  validate: 'Validating coverage',
  dedupe: 'Removing duplicates',
  repair: 'Repairing gaps',
  synthesize: 'Synthesizing rubric',
  save: 'Saving suite',
};

export interface SuiteGenerationLogEntry {
  timestamp: number;
  level: 'info' | 'warning' | 'error';
  message: string;
}

export interface ReviewerActivityStatus {
  model: string;
  status: 'pending' | 'working' | 'done' | 'retry' | 'failed' | 'skipped';
  started_at?: number;
  elapsed_seconds?: number;
}

export interface ActiveGenerationCall {
  task_id: string;
  model: string;
  detail: string;
  started_at: number;
  question_count: number;
  generator_index: number;
  total_generators: number;
  generator_batch_index: number;
  generator_total_batches: number;
  global_batch_index: number;
  total_global_batches: number;
}

export interface ActiveReviewBatch {
  task_id: string;
  batch_index: number;
  total_batches: number;
  started_at: number;
  detail: string;
  reviewers_status: ReviewerActivityStatus[];
}

export interface ActiveMergeBatch {
  task_id: string;
  batch_index: number;
  total_batches: number;
  started_at: number;
  detail: string;
  model: string;
}

export interface SuitePipelineSnapshot {
  session_id: string;
  name: string;
  topic: string;
  phase: string;
  phase_index: number;
  total_phases: number;
  phases: string[];
  batch: number;
  total_batches: number;
  overall_percent: number;
  call_started_at: number | null;
  model: string | null;
  reviewers_status: ReviewerActivityStatus[] | null;
  questions_generated: number;
  questions_reviewed: number;
  questions_merged: number;
  question_count: number;
  completed_generation_batches: number;
  active_generation_batches: number;
  active_generation_calls: ActiveGenerationCall[];
  active_review_batches: ActiveReviewBatch[];
  active_merge_batches: ActiveMergeBatch[];
  coverage_mode?: string;
  required_leaf_count?: number;
  covered_leaf_count?: number;
  missing_leaf_count?: number;
  duplicate_cluster_count?: number;
  replacement_count?: number;
  generator: string;
  generators?: string[];
  editor?: string | null;
  reviewers: string[];
  difficulty?: string;
  categories?: string[];
  generate_answers?: boolean;
  criteria_depth?: string;
  elapsed_seconds: number;
  recent_log: SuiteGenerationLogEntry[];
}

export interface SuiteGenerationMetadata {
  topic?: string;
  requested_question_count?: number;
  difficulty?: string;
  categories?: string[];
  generate_answers?: boolean;
  criteria_depth?: string;
}

export interface SuiteGenerationRequestContext {
  name: string;
  topic: string;
  count: number;
  difficulty: string;
  categories: string[];
  generate_answers: boolean;
  criteria_depth: string;
}

// --- State ---

export type SuiteGenerationStatus =
  | 'idle'
  | 'running'
  | 'complete'
  | 'partial'
  | 'cancelled'
  | 'error'
  | 'disconnected';

export interface SuiteGenerationState {
  status: SuiteGenerationStatus;
  phase: string | null;
  phase_index: number;
  total_phases: number;
  phases: string[];
  batch: number;
  total_batches: number;
  detail: string | null;
  call_started_at: number | null;
  model: string | null;
  reviewers_status: ReviewerActivityStatus[] | null;
  overall_percent: number;
  questions_generated: number;
  questions_reviewed: number;
  questions_merged: number;
  question_count: number;
  completed_generation_batches: number;
  active_generation_batches: number;
  active_generation_calls: ActiveGenerationCall[];
  active_review_batches: ActiveReviewBatch[];
  active_merge_batches: ActiveMergeBatch[];
  coverage_mode: string;
  required_leaf_count: number;
  covered_leaf_count: number;
  missing_leaf_count: number;
  duplicate_cluster_count: number;
  replacement_count: number;
  requested_count: number | null;
  generators: string[];
  editor: string | null;
  difficulty: string;
  categories: string[];
  generate_answers: boolean;
  criteria_depth: string;
  log: SuiteGenerationLogEntry[];
  suite_id: number | null;
  error: string | null;
}

export const INITIAL_GENERATION_STATE: SuiteGenerationState = {
  status: 'idle',
  phase: null,
  phase_index: 0,
  total_phases: 0,
  phases: [],
  batch: 0,
  total_batches: 0,
  detail: null,
  call_started_at: null,
  model: null,
  reviewers_status: null,
  overall_percent: 0,
  questions_generated: 0,
  questions_reviewed: 0,
  questions_merged: 0,
  question_count: 0,
  completed_generation_batches: 0,
  active_generation_batches: 0,
  active_generation_calls: [],
  active_review_batches: [],
  active_merge_batches: [],
  coverage_mode: 'none',
  required_leaf_count: 0,
  covered_leaf_count: 0,
  missing_leaf_count: 0,
  duplicate_cluster_count: 0,
  replacement_count: 0,
  requested_count: null,
  generators: [],
  editor: null,
  difficulty: 'balanced',
  categories: [],
  generate_answers: true,
  criteria_depth: 'basic',
  log: [],
  suite_id: null,
  error: null,
};

// --- WebSocket events ---

export interface SuiteProgressEvent {
  type: 'suite_progress';
  snapshot?: boolean;
  session_id?: string;
  name?: string;
  topic?: string;
  phase: string;
  phase_index: number;
  total_phases: number;
  phases: string[];
  batch: number;
  total_batches: number;
  detail?: string;
  call_started_at: number | null;
  model: string | null;
  reviewers_status: ReviewerActivityStatus[] | null;
  overall_percent: number;
  questions_generated: number;
  questions_reviewed: number;
  questions_merged: number;
  question_count: number;
  completed_generation_batches: number;
  active_generation_batches: number;
  active_generation_calls: ActiveGenerationCall[];
  active_review_batches: ActiveReviewBatch[];
  active_merge_batches: ActiveMergeBatch[];
  coverage_mode?: string;
  required_leaf_count?: number;
  covered_leaf_count?: number;
  missing_leaf_count?: number;
  duplicate_cluster_count?: number;
  replacement_count?: number;
  generators?: string[];
  editor?: string | null;
  generator?: string;
  reviewers?: string[];
  difficulty?: string;
  categories?: string[];
  generate_answers?: boolean;
  criteria_depth?: string;
  elapsed_seconds?: number;
  recent_log?: SuiteGenerationLogEntry[];
}

export interface SuiteCompleteEvent {
  type: 'suite_complete';
  suite_id: number;
  question_count: number;
  [key: string]: unknown;
}

export interface SuiteErrorEvent {
  type: 'suite_error';
  phase: string;
  error: string;
}

export interface SuiteLogEvent extends SuiteGenerationLogEntry {
  type: 'suite_log';
}

export interface SuitePartialEvent {
  type: 'suite_partial';
  suite_id: number;
  question_count: number;
  requested_count: number;
  error: string;
  phase: string;
}

export interface SuiteCancelledEvent {
  type: 'suite_cancelled';
  phase: string;
  questions_generated: number;
}

export type SuiteGenerationEvent =
  | SuiteProgressEvent
  | SuiteCompleteEvent
  | SuiteErrorEvent
  | SuiteLogEvent
  | SuitePartialEvent
  | SuiteCancelledEvent;

// --- Helpers ---

/**
 * Convert an http/https API base URL into the corresponding ws/wss WebSocket URL
 * for the suite generation endpoint.
 *
 * Note: Auth token is no longer passed as a query parameter (F-003 security).
 * The caller must send an auth frame as the first message after connection opens.
 */
export function buildSuiteGenerationWsUrl(
  apiBase: string,
  sessionId: string,
): string {
  const wsBase = apiBase.replace(/^https:\/\//, 'wss://').replace(/^http:\/\//, 'ws://');
  return `${wsBase}/ws/suite-generate/${sessionId}`;
}

export function formatSuiteElapsed(totalSeconds: number | null | undefined): string {
  const safeSeconds = Math.max(0, Math.floor(totalSeconds ?? 0));
  const minutes = Math.floor(safeSeconds / 60);
  const seconds = safeSeconds % 60;
  return `${minutes.toString().padStart(2, '0')}:${seconds.toString().padStart(2, '0')}`;
}

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === 'object' && value !== null;
}

function toNumber(value: unknown, fallback = 0): number {
  return typeof value === 'number' && Number.isFinite(value) ? value : fallback;
}

function toStringArray(value: unknown): string[] | undefined {
  return Array.isArray(value) ? value.filter((item): item is string => typeof item === 'string') : undefined;
}

function toLogArray(value: unknown): SuiteGenerationLogEntry[] | undefined {
  if (!Array.isArray(value)) {
    return undefined;
  }
  return value.filter((item): item is SuiteGenerationLogEntry => (
    isRecord(item)
    && typeof item.timestamp === 'number'
    && (item.level === 'info' || item.level === 'warning' || item.level === 'error')
    && typeof item.message === 'string'
  ));
}

function toActiveGenerationCalls(value: unknown): ActiveGenerationCall[] | undefined {
  if (!Array.isArray(value)) {
    return undefined;
  }
  return value.filter((item): item is ActiveGenerationCall => (
    isRecord(item)
    && typeof item.task_id === 'string'
    && typeof item.model === 'string'
    && typeof item.detail === 'string'
    && typeof item.started_at === 'number'
    && typeof item.question_count === 'number'
    && typeof item.generator_index === 'number'
    && typeof item.total_generators === 'number'
    && typeof item.generator_batch_index === 'number'
    && typeof item.generator_total_batches === 'number'
    && typeof item.global_batch_index === 'number'
    && typeof item.total_global_batches === 'number'
  ));
}

function toActiveReviewBatches(value: unknown): ActiveReviewBatch[] | undefined {
  if (!Array.isArray(value)) {
    return undefined;
  }
  return value.filter((item): item is ActiveReviewBatch => (
    isRecord(item)
    && typeof item.task_id === 'string'
    && typeof item.batch_index === 'number'
    && typeof item.total_batches === 'number'
    && typeof item.started_at === 'number'
    && typeof item.detail === 'string'
    && Array.isArray(item.reviewers_status)
  ));
}

function toActiveMergeBatches(value: unknown): ActiveMergeBatch[] | undefined {
  if (!Array.isArray(value)) {
    return undefined;
  }
  return value.filter((item): item is ActiveMergeBatch => (
    isRecord(item)
    && typeof item.task_id === 'string'
    && typeof item.batch_index === 'number'
    && typeof item.total_batches === 'number'
    && typeof item.started_at === 'number'
    && typeof item.detail === 'string'
    && typeof item.model === 'string'
  ));
}

function isSnapshotProgressPayload(value: unknown): value is Record<string, unknown> {
  return (
    isRecord(value)
    && (
      'session_id' in value
      || 'recent_log' in value
      || 'elapsed_seconds' in value
      || 'generator' in value
      || 'reviewers' in value
    )
  );
}

export function normalizeSuiteGenerationEvent(value: unknown): SuiteGenerationEvent | null {
  if (!isRecord(value)) {
    return null;
  }

  const eventType = typeof value.type === 'string' ? value.type : null;

  if (eventType === 'suite_progress' || (eventType == null && isSnapshotProgressPayload(value))) {
    const progressValue = value as Record<string, unknown>;
    if (isSnapshotProgressPayload(value)) {
      return {
        type: 'suite_progress',
        snapshot: true,
        session_id: typeof progressValue.session_id === 'string' ? progressValue.session_id : undefined,
        name: typeof progressValue.name === 'string' ? progressValue.name : undefined,
        topic: typeof progressValue.topic === 'string' ? progressValue.topic : undefined,
        phase: typeof progressValue.phase === 'string' ? progressValue.phase : 'generate',
        phase_index: toNumber(progressValue.phase_index),
        total_phases: toNumber(progressValue.total_phases),
        phases: toStringArray(progressValue.phases) ?? [],
        batch: toNumber(progressValue.batch),
        total_batches: toNumber(progressValue.total_batches),
        detail: typeof progressValue.detail === 'string' ? progressValue.detail : undefined,
        call_started_at: typeof progressValue.call_started_at === 'number' ? progressValue.call_started_at : null,
        model: typeof progressValue.model === 'string' ? progressValue.model : null,
        reviewers_status: Array.isArray(progressValue.reviewers_status) ? progressValue.reviewers_status as ReviewerActivityStatus[] : null,
        overall_percent: toNumber(progressValue.overall_percent),
        questions_generated: toNumber(progressValue.questions_generated),
        questions_reviewed: toNumber(progressValue.questions_reviewed),
        questions_merged: toNumber(progressValue.questions_merged),
        question_count: toNumber(progressValue.question_count),
        completed_generation_batches: toNumber(progressValue.completed_generation_batches),
        active_generation_batches: toNumber(progressValue.active_generation_batches),
        active_generation_calls: toActiveGenerationCalls(progressValue.active_generation_calls) ?? [],
        active_review_batches: toActiveReviewBatches(progressValue.active_review_batches) ?? [],
        active_merge_batches: toActiveMergeBatches(progressValue.active_merge_batches) ?? [],
        coverage_mode: typeof progressValue.coverage_mode === 'string' ? progressValue.coverage_mode : undefined,
        required_leaf_count: typeof progressValue.required_leaf_count === 'number' ? progressValue.required_leaf_count : undefined,
        covered_leaf_count: typeof progressValue.covered_leaf_count === 'number' ? progressValue.covered_leaf_count : undefined,
        missing_leaf_count: typeof progressValue.missing_leaf_count === 'number' ? progressValue.missing_leaf_count : undefined,
        duplicate_cluster_count: typeof progressValue.duplicate_cluster_count === 'number' ? progressValue.duplicate_cluster_count : undefined,
        replacement_count: typeof progressValue.replacement_count === 'number' ? progressValue.replacement_count : undefined,
        generators: toStringArray(progressValue.generators),
        editor: typeof progressValue.editor === 'string' || progressValue.editor === null ? progressValue.editor : undefined,
        generator: typeof progressValue.generator === 'string' ? progressValue.generator : undefined,
        reviewers: toStringArray(progressValue.reviewers),
        difficulty: typeof progressValue.difficulty === 'string' ? progressValue.difficulty : undefined,
        categories: toStringArray(progressValue.categories),
        generate_answers: typeof progressValue.generate_answers === 'boolean' ? progressValue.generate_answers : undefined,
        criteria_depth: typeof progressValue.criteria_depth === 'string' ? progressValue.criteria_depth : undefined,
        elapsed_seconds: typeof progressValue.elapsed_seconds === 'number' ? progressValue.elapsed_seconds : undefined,
        recent_log: toLogArray(progressValue.recent_log),
      };
    }
    return {
      type: 'suite_progress',
      phase: typeof progressValue.phase === 'string' ? progressValue.phase : 'generate',
      phase_index: toNumber(progressValue.phase_index),
      total_phases: toNumber(progressValue.total_phases),
      phases: toStringArray(progressValue.phases) ?? [],
      batch: toNumber(progressValue.batch),
      total_batches: toNumber(progressValue.total_batches),
      detail: typeof progressValue.detail === 'string' ? progressValue.detail : undefined,
      call_started_at: typeof progressValue.call_started_at === 'number' ? progressValue.call_started_at : null,
      model: typeof progressValue.model === 'string' ? progressValue.model : null,
      reviewers_status: Array.isArray(progressValue.reviewers_status) ? progressValue.reviewers_status as ReviewerActivityStatus[] : null,
      overall_percent: toNumber(progressValue.overall_percent),
      questions_generated: toNumber(progressValue.questions_generated),
      questions_reviewed: toNumber(progressValue.questions_reviewed),
      questions_merged: toNumber(progressValue.questions_merged),
      question_count: toNumber(progressValue.question_count),
      completed_generation_batches: toNumber(progressValue.completed_generation_batches),
      active_generation_batches: toNumber(progressValue.active_generation_batches),
      active_generation_calls: toActiveGenerationCalls(progressValue.active_generation_calls) ?? [],
      active_review_batches: toActiveReviewBatches(progressValue.active_review_batches) ?? [],
      active_merge_batches: toActiveMergeBatches(progressValue.active_merge_batches) ?? [],
      coverage_mode: typeof progressValue.coverage_mode === 'string' ? progressValue.coverage_mode : undefined,
      required_leaf_count: typeof progressValue.required_leaf_count === 'number' ? progressValue.required_leaf_count : undefined,
      covered_leaf_count: typeof progressValue.covered_leaf_count === 'number' ? progressValue.covered_leaf_count : undefined,
      missing_leaf_count: typeof progressValue.missing_leaf_count === 'number' ? progressValue.missing_leaf_count : undefined,
      duplicate_cluster_count: typeof progressValue.duplicate_cluster_count === 'number' ? progressValue.duplicate_cluster_count : undefined,
      replacement_count: typeof progressValue.replacement_count === 'number' ? progressValue.replacement_count : undefined,
      generators: toStringArray(progressValue.generators),
      editor: typeof progressValue.editor === 'string' || progressValue.editor === null ? progressValue.editor : undefined,
      difficulty: typeof progressValue.difficulty === 'string' ? progressValue.difficulty : undefined,
      categories: toStringArray(progressValue.categories),
      generate_answers: typeof progressValue.generate_answers === 'boolean' ? progressValue.generate_answers : undefined,
      criteria_depth: typeof progressValue.criteria_depth === 'string' ? progressValue.criteria_depth : undefined,
    };
  }

  switch (eventType) {
    case 'suite_complete':
    case 'suite_error':
    case 'suite_log':
    case 'suite_partial':
    case 'suite_cancelled':
      return value as SuiteGenerationEvent;
    default:
      return null;
  }
}

/**
 * Pure reducer for suite generation WebSocket events.
 * Returns a new state object; never mutates the input.
 *
 * Key invariant: overall_percent is MONOTONIC — never goes backwards.
 */
export function reduceSuiteGenerationEvent(
  state: SuiteGenerationState,
  event: SuiteGenerationEvent,
): SuiteGenerationState {
  switch (event.type) {
    case 'suite_progress':
      if (event.snapshot) {
        return hydrateSuiteGenerationState({
          session_id: event.session_id ?? '',
          name: event.name ?? '',
          topic: event.topic ?? '',
          phase: event.phase,
          phase_index: event.phase_index,
          total_phases: event.total_phases,
          phases: event.phases,
          batch: event.batch,
          total_batches: event.total_batches,
          overall_percent: event.overall_percent,
          call_started_at: event.call_started_at,
          model: event.model,
          reviewers_status: event.reviewers_status,
          questions_generated: event.questions_generated,
          questions_reviewed: event.questions_reviewed,
          questions_merged: event.questions_merged,
          question_count: event.question_count,
          completed_generation_batches: event.completed_generation_batches,
          active_generation_batches: event.active_generation_batches,
          active_generation_calls: event.active_generation_calls,
          active_review_batches: event.active_review_batches,
          active_merge_batches: event.active_merge_batches,
          coverage_mode: event.coverage_mode ?? 'none',
          required_leaf_count: event.required_leaf_count ?? 0,
          covered_leaf_count: event.covered_leaf_count ?? 0,
          missing_leaf_count: event.missing_leaf_count ?? 0,
          duplicate_cluster_count: event.duplicate_cluster_count ?? 0,
          replacement_count: event.replacement_count ?? 0,
          generator: event.generator ?? event.generators?.[0] ?? '',
          generators: event.generators,
          editor: event.editor ?? null,
          reviewers: event.reviewers ?? [],
          difficulty: event.difficulty ?? 'balanced',
          categories: event.categories ?? [],
          generate_answers: event.generate_answers ?? true,
          criteria_depth: event.criteria_depth ?? 'basic',
          elapsed_seconds: event.elapsed_seconds ?? 0,
          recent_log: event.recent_log ?? [],
        });
      }
      return {
        ...state,
        status: 'running',
        phase: event.phase,
        phase_index: event.phase_index,
        total_phases: event.total_phases,
        phases: event.phases ?? state.phases,
        batch: event.batch,
        total_batches: event.total_batches,
        detail: event.detail ?? null,
        call_started_at: event.call_started_at,
        model: event.model,
        reviewers_status: event.reviewers_status,
        // Monotonic clamp: never go backwards
        overall_percent: Math.max(state.overall_percent, event.overall_percent),
        questions_generated: event.questions_generated,
        questions_reviewed: event.questions_reviewed,
        questions_merged: event.questions_merged,
        question_count: event.question_count,
        completed_generation_batches: event.completed_generation_batches,
        active_generation_batches: event.active_generation_batches,
        active_generation_calls: event.active_generation_calls,
        active_review_batches: event.active_review_batches,
        active_merge_batches: event.active_merge_batches,
        coverage_mode: event.coverage_mode ?? state.coverage_mode,
        required_leaf_count: event.required_leaf_count ?? state.required_leaf_count,
        covered_leaf_count: event.covered_leaf_count ?? state.covered_leaf_count,
        missing_leaf_count: event.missing_leaf_count ?? state.missing_leaf_count,
        duplicate_cluster_count: event.duplicate_cluster_count ?? state.duplicate_cluster_count,
        replacement_count: event.replacement_count ?? state.replacement_count,
        generators: event.generators ?? state.generators,
        editor: event.editor ?? state.editor,
        difficulty: event.difficulty ?? state.difficulty,
        categories: event.categories ?? state.categories,
        generate_answers: event.generate_answers ?? state.generate_answers,
        criteria_depth: event.criteria_depth ?? state.criteria_depth,
      };

    case 'suite_complete':
      return {
        ...state,
        status: 'complete',
        overall_percent: 100,
        suite_id: event.suite_id,
        question_count: event.question_count ?? state.question_count,
        detail: null,
        call_started_at: null,
        active_generation_calls: [],
        active_review_batches: [],
        active_merge_batches: [],
        error: null,
      };

    case 'suite_log':
      return {
        ...state,
        log: [...state.log, {
          timestamp: event.timestamp,
          level: event.level,
          message: event.message,
        }],
      };

    case 'suite_partial':
      return {
        ...state,
        status: 'partial',
        phase: event.phase,
        suite_id: event.suite_id,
        question_count: event.question_count,
        requested_count: event.requested_count,
        error: event.error,
        detail: null,
        call_started_at: null,
        active_generation_calls: [],
        active_review_batches: [],
        active_merge_batches: [],
      };

    case 'suite_cancelled':
      return {
        ...state,
        status: 'cancelled',
        phase: event.phase,
        questions_generated: event.questions_generated,
        detail: null,
        call_started_at: null,
        active_generation_calls: [],
        active_review_batches: [],
        active_merge_batches: [],
      };

    case 'suite_error':
      return {
        ...state,
        status: 'error',
        phase: event.phase,
        error: event.error,
        detail: null,
        call_started_at: null,
        active_generation_calls: [],
        active_review_batches: [],
        active_merge_batches: [],
      };

    default:
      return state;
  }
}

export function hydrateSuiteGenerationState(
  snapshot: SuitePipelineSnapshot,
): SuiteGenerationState {
  return {
    ...INITIAL_GENERATION_STATE,
    status: 'running',
    phase: snapshot.phase,
    phase_index: snapshot.phase_index,
    total_phases: snapshot.total_phases,
    phases: snapshot.phases,
    batch: snapshot.batch,
    total_batches: snapshot.total_batches,
    detail: null,
    call_started_at: snapshot.call_started_at,
    model: snapshot.model,
    reviewers_status: snapshot.reviewers_status,
    overall_percent: snapshot.overall_percent,
    questions_generated: snapshot.questions_generated,
    questions_reviewed: snapshot.questions_reviewed,
    questions_merged: snapshot.questions_merged,
    question_count: snapshot.question_count,
    completed_generation_batches: snapshot.completed_generation_batches,
    active_generation_batches: snapshot.active_generation_batches,
    active_generation_calls: snapshot.active_generation_calls,
    active_review_batches: snapshot.active_review_batches,
    active_merge_batches: snapshot.active_merge_batches,
    coverage_mode: snapshot.coverage_mode ?? 'none',
    required_leaf_count: snapshot.required_leaf_count ?? 0,
    covered_leaf_count: snapshot.covered_leaf_count ?? 0,
    missing_leaf_count: snapshot.missing_leaf_count ?? 0,
    duplicate_cluster_count: snapshot.duplicate_cluster_count ?? 0,
    replacement_count: snapshot.replacement_count ?? 0,
    requested_count: snapshot.question_count,
    generators: snapshot.generators ?? (snapshot.generator ? [snapshot.generator] : []),
    editor: snapshot.editor ?? null,
    difficulty: snapshot.difficulty ?? 'balanced',
    categories: snapshot.categories ?? [],
    generate_answers: snapshot.generate_answers ?? true,
    criteria_depth: snapshot.criteria_depth ?? 'basic',
    log: snapshot.recent_log,
  };
}

export function getRequestContextFromSnapshot(
  snapshot: SuitePipelineSnapshot,
): SuiteGenerationRequestContext {
  return {
    name: snapshot.name,
    topic: snapshot.topic,
    count: snapshot.question_count,
    difficulty: snapshot.difficulty ?? 'balanced',
    categories: snapshot.categories ?? [],
    generate_answers: snapshot.generate_answers ?? true,
    criteria_depth: snapshot.criteria_depth ?? 'basic',
  };
}

export function getRequestContextFromMetadata(
  name: string,
  metadata: SuiteGenerationMetadata | null | undefined,
  fallbackCount: number,
): SuiteGenerationRequestContext | null {
  if (!metadata?.topic) {
    return null;
  }

  return {
    name,
    topic: metadata.topic,
    count: metadata.requested_question_count ?? fallbackCount,
    difficulty: metadata.difficulty ?? 'balanced',
    categories: metadata.categories ?? [],
    generate_answers: metadata.generate_answers ?? true,
    criteria_depth: metadata.criteria_depth ?? 'basic',
  };
}

export function getCoverageProgressSummary(
  state: Pick<
    SuiteGenerationState,
    | 'required_leaf_count'
    | 'covered_leaf_count'
    | 'missing_leaf_count'
    | 'duplicate_cluster_count'
    | 'replacement_count'
  >,
): string[] {
  if (!state.required_leaf_count) {
    return [];
  }
  return [
    `Coverage: ${state.covered_leaf_count}/${state.required_leaf_count}`,
    `Missing leaves: ${state.missing_leaf_count}`,
    `Duplicate clusters: ${state.duplicate_cluster_count}`,
    `Replacements: ${state.replacement_count}`,
  ];
}
