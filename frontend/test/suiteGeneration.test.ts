import assert from 'node:assert/strict';
import test from 'node:test';

import {
  ALL_SUITE_GENERATION_CATEGORIES,
  INITIAL_GENERATION_STATE,
  buildSuiteGenerationWsUrl,
  getCoverageProgressSummary,
  hydrateSuiteGenerationState,
  reduceSuiteGenerationEvent,
} from '../src/pages/suites/suiteGeneration.js';

test('buildSuiteGenerationWsUrl converts the API base into a websocket URL (no token in URL)', () => {
  assert.equal(
    buildSuiteGenerationWsUrl('http://localhost:8000', 'abc-123'),
    'ws://localhost:8000/ws/suite-generate/abc-123',
  );
});

test('buildSuiteGenerationWsUrl converts https to wss', () => {
  assert.equal(
    buildSuiteGenerationWsUrl('https://bellmark.ai', 'session-456'),
    'wss://bellmark.ai/ws/suite-generate/session-456',
  );
});

test('reduceSuiteGenerationEvent stores progress and completion state', () => {
  const afterProgress = reduceSuiteGenerationEvent(INITIAL_GENERATION_STATE, {
    type: 'suite_progress',
    phase: 'review',
    phase_index: 1,
    total_phases: 5,
    phases: ['generate', 'review', 'merge', 'synthesize', 'save'],
    batch: 2,
    total_batches: 10,
    detail: 'Reviewing with GPT-5.4',
    call_started_at: 1774634000,
    model: 'GPT-5.4 [Reasoning (high)]',
    reviewers_status: [
      { model: 'Claude Opus 4.6', status: 'working', started_at: 1774634000 },
    ],
    overall_percent: 42,
    questions_generated: 10,
    questions_reviewed: 0,
    questions_merged: 0,
    question_count: 50,
    completed_generation_batches: 0,
    active_generation_batches: 0,
    active_generation_calls: [],
    active_review_batches: [
      {
        task_id: 'review-batch-1',
        batch_index: 1,
        total_batches: 10,
        started_at: 1774633990,
        detail: 'Review batch 1/10',
        reviewers_status: [
          { model: 'Claude Opus 4.6', status: 'working', started_at: 1774634000 },
        ],
      },
    ],
    active_merge_batches: [],
  });

  assert.equal(afterProgress.status, 'running');
  assert.equal(afterProgress.phase, 'review');
  assert.equal(afterProgress.phase_index, 1);
  assert.equal(afterProgress.total_phases, 5);
  assert.equal(afterProgress.detail, 'Reviewing with GPT-5.4');
  assert.equal(afterProgress.batch, 2);
  assert.equal(afterProgress.total_batches, 10);
  assert.equal(afterProgress.call_started_at, 1774634000);
  assert.equal(afterProgress.model, 'GPT-5.4 [Reasoning (high)]');
  assert.equal(afterProgress.overall_percent, 42);
  assert.equal(afterProgress.questions_generated, 10);
  assert.deepEqual(afterProgress.phases, ['generate', 'review', 'merge', 'synthesize', 'save']);
  assert.equal(afterProgress.reviewers_status?.[0]?.status, 'working');
  assert.equal(afterProgress.active_review_batches[0]?.batch_index, 1);

  const afterComplete = reduceSuiteGenerationEvent(afterProgress, {
    type: 'suite_complete',
    suite_id: 123,
    question_count: 50,
  });

  assert.equal(afterComplete.status, 'complete');
  assert.equal(afterComplete.suite_id, 123);
  assert.equal(afterComplete.overall_percent, 100);
  assert.equal(afterComplete.detail, null);
});

test('reducer appends suite_log events to the log array', () => {
  const running = {
    ...INITIAL_GENERATION_STATE,
    status: 'running' as const,
  };

  const afterLog = reduceSuiteGenerationEvent(running, {
    type: 'suite_log',
    timestamp: 42,
    level: 'info',
    message: '▶ Generate batch 1/2 — GPT-5.4',
  });

  assert.equal(afterLog.log.length, 1);
  assert.equal(afterLog.log[0]?.message, '▶ Generate batch 1/2 — GPT-5.4');
});

test('reducer handles suite_partial with suite_id and error', () => {
  const running = {
    ...INITIAL_GENERATION_STATE,
    status: 'running' as const,
  };

  const afterPartial = reduceSuiteGenerationEvent(running, {
    type: 'suite_partial',
    suite_id: 99,
    question_count: 35,
    requested_count: 50,
    error: 'Reviewer timed out',
    phase: 'review',
  });

  assert.equal(afterPartial.status, 'partial');
  assert.equal(afterPartial.suite_id, 99);
  assert.equal(afterPartial.question_count, 35);
  assert.equal(afterPartial.requested_count, 50);
  assert.equal(afterPartial.error, 'Reviewer timed out');
});

test('reducer handles suite_cancelled', () => {
  const running = {
    ...INITIAL_GENERATION_STATE,
    status: 'running' as const,
    detail: 'Cancelling...',
  };

  const afterCancelled = reduceSuiteGenerationEvent(running, {
    type: 'suite_cancelled',
    phase: 'review',
    questions_generated: 15,
  });

  assert.equal(afterCancelled.status, 'cancelled');
  assert.equal(afterCancelled.phase, 'review');
  assert.equal(afterCancelled.questions_generated, 15);
  assert.equal(afterCancelled.detail, null);
});

test('category constant contains all eight approved categories', () => {
  assert.deepEqual(ALL_SUITE_GENERATION_CATEGORIES, [
    'reasoning',
    'coding',
    'writing',
    'knowledge-stem',
    'knowledge-humanities',
    'instruction-following',
    'data-analysis',
    'planning',
  ]);
});

test('progress reducer returns error state on suite_error', () => {
  const running = {
    ...INITIAL_GENERATION_STATE,
    status: 'running' as const,
    phase: 'generate',
    overall_percent: 10,
  };

  const afterError = reduceSuiteGenerationEvent(running, {
    type: 'suite_error',
    phase: 'review',
    error: 'Connection timeout',
  });

  assert.equal(afterError.status, 'error');
  assert.equal(afterError.error, 'Connection timeout');
  assert.equal(afterError.phase, 'review');
  assert.equal(afterError.detail, null);
});

test('overall_percent is monotonic — never goes backwards', () => {
  const at60 = {
    ...INITIAL_GENERATION_STATE,
    status: 'running' as const,
    overall_percent: 60,
  };

  // Backend sends a lower percent (e.g., stale event) — should be clamped
  const afterLower = reduceSuiteGenerationEvent(at60, {
    type: 'suite_progress',
    phase: 'review',
    phase_index: 1,
    total_phases: 5,
    phases: ['generate', 'review', 'merge', 'synthesize', 'save'],
    batch: 2,
    total_batches: 5,
    detail: 'Reviewing batch 2/5',
    call_started_at: 1774634000,
    model: 'Reviewer',
    reviewers_status: null,
    overall_percent: 40,
    questions_generated: 20,
    questions_reviewed: 10,
    questions_merged: 0,
    question_count: 50,
    completed_generation_batches: 0,
    active_generation_batches: 0,
    active_generation_calls: [],
    active_review_batches: [],
    active_merge_batches: [],
  });

  assert.equal(afterLower.overall_percent, 60, 'Should clamp to previous value, not go backwards');
});

test('coverage-aware progress event stores coverage and dedupe counters', () => {
  const state = reduceSuiteGenerationEvent(INITIAL_GENERATION_STATE, {
    type: 'suite_progress',
    phase: 'dedupe',
    phase_index: 5,
    total_phases: 9,
    phases: ['plan', 'generate', 'review', 'merge', 'validate', 'dedupe', 'repair', 'synthesize', 'save'],
    batch: 1,
    total_batches: 1,
    detail: 'Removing duplicates',
    call_started_at: null,
    model: 'Editor',
    reviewers_status: null,
    overall_percent: 72,
    questions_generated: 10,
    questions_reviewed: 10,
    questions_merged: 10,
    question_count: 10,
    completed_generation_batches: 0,
    active_generation_batches: 0,
    active_generation_calls: [],
    active_review_batches: [],
    active_merge_batches: [],
    coverage_mode: 'strict_leaf_coverage',
    required_leaf_count: 10,
    covered_leaf_count: 9,
    missing_leaf_count: 1,
    duplicate_cluster_count: 2,
    replacement_count: 1,
  });

  assert.equal(state.phase, 'dedupe');
  assert.equal(state.coverage_mode, 'strict_leaf_coverage');
  assert.equal(state.required_leaf_count, 10);
  assert.equal(state.covered_leaf_count, 9);
  assert.equal(state.missing_leaf_count, 1);
  assert.equal(state.duplicate_cluster_count, 2);
  assert.equal(state.replacement_count, 1);
});

test('hydrateSuiteGenerationState preserves active review batches from snapshot', () => {
  const state = hydrateSuiteGenerationState({
    session_id: 'session-1',
    name: 'Suite',
    topic: 'Topic',
    phase: 'review',
    phase_index: 2,
    total_phases: 5,
    phases: ['generate', 'review', 'merge', 'synthesize', 'save'],
    batch: 3,
    total_batches: 10,
    overall_percent: 48,
    call_started_at: 1774634000,
    model: 'Claude Sonnet 4.6',
    reviewers_status: null,
    questions_generated: 20,
    questions_reviewed: 5,
    questions_merged: 0,
    question_count: 50,
    completed_generation_batches: 4,
    active_generation_batches: 2,
    active_generation_calls: [],
    active_review_batches: [
      {
        task_id: 'review-batch-2',
        batch_index: 2,
        total_batches: 10,
        started_at: 1774634010,
        detail: 'Review batch 2/10',
        reviewers_status: [
          { model: 'GPT-5.2', status: 'working', started_at: 1774634011 },
        ],
      },
      {
        task_id: 'review-batch-3',
        batch_index: 3,
        total_batches: 10,
        started_at: 1774634012,
        detail: 'Review batch 3/10',
        reviewers_status: [
          { model: 'Claude Sonnet 4.6', status: 'working', started_at: 1774634013 },
        ],
      },
    ],
    active_merge_batches: [],
    generator: 'GPT-5.4',
    generators: ['GPT-5.4', 'Claude Opus 4.6'],
    editor: 'GPT-5.4-mini',
    reviewers: ['GPT-5.2', 'Claude Sonnet 4.6'],
    difficulty: 'hard',
    categories: ['reasoning'],
    generate_answers: true,
    criteria_depth: 'detailed',
    elapsed_seconds: 120,
    recent_log: [],
  });

  assert.equal(state.active_review_batches.length, 2);
  assert.equal(state.active_review_batches[0]?.task_id, 'review-batch-2');
  assert.equal(state.active_review_batches[1]?.reviewers_status[0]?.model, 'Claude Sonnet 4.6');
});

test('getCoverageProgressSummary returns compact coverage and dedupe lines', () => {
  assert.deepEqual(
    getCoverageProgressSummary({
      required_leaf_count: 10,
      covered_leaf_count: 9,
      missing_leaf_count: 1,
      duplicate_cluster_count: 2,
      replacement_count: 1,
    } as typeof INITIAL_GENERATION_STATE),
    [
      'Coverage: 9/10',
      'Missing leaves: 1',
      'Duplicate clusters: 2',
      'Replacements: 1',
    ],
  );
  assert.deepEqual(
    getCoverageProgressSummary({
      required_leaf_count: 0,
      covered_leaf_count: 0,
      missing_leaf_count: 0,
      duplicate_cluster_count: 0,
      replacement_count: 0,
    } as typeof INITIAL_GENERATION_STATE),
    [],
  );
});

test('suite_complete forces overall_percent to 100', () => {
  const at90 = {
    ...INITIAL_GENERATION_STATE,
    status: 'running' as const,
    overall_percent: 90,
  };

  const afterComplete = reduceSuiteGenerationEvent(at90, {
    type: 'suite_complete',
    suite_id: 42,
    question_count: 10,
  });

  assert.equal(afterComplete.status, 'complete');
  assert.equal(afterComplete.suite_id, 42);
  assert.equal(afterComplete.overall_percent, 100);
});

test('hydrateSuiteGenerationState converts REST snapshot into reducer state', () => {
  const hydrated = hydrateSuiteGenerationState({
    session_id: 'pipeline-123',
    name: 'Reconnect Test',
    topic: 'Testing',
    phase: 'review',
    phase_index: 1,
    total_phases: 5,
    phases: ['generate', 'review', 'merge', 'synthesize', 'save'],
    batch: 3,
    total_batches: 10,
    overall_percent: 52,
    call_started_at: 1774640100,
    model: 'Claude Opus 4.6 [Reasoning (high)]',
    reviewers_status: [
      { model: 'Claude Opus 4.6', status: 'working', started_at: 1774640100 },
      { model: 'MiMo-V2-Pro', status: 'done', elapsed_seconds: 142 },
    ],
    questions_generated: 35,
    questions_reviewed: 30,
    questions_merged: 30,
    question_count: 50,
    completed_generation_batches: 6,
    active_generation_batches: 1,
    active_generation_calls: [
      {
        task_id: 'generator-2-batch-1-global-7',
        model: 'Claude Opus 4.6 [Reasoning (high)]',
        detail: 'Generating batch 1/3 (5 questions) — Claude Opus 4.6 [Reasoning (high)]',
        started_at: 1774640100,
        question_count: 5,
        generator_index: 2,
        total_generators: 2,
        generator_batch_index: 1,
        generator_total_batches: 3,
        global_batch_index: 7,
        total_global_batches: 10,
      },
    ],
    active_review_batches: [
      {
        task_id: 'review-batch-7',
        batch_index: 7,
        total_batches: 10,
        started_at: 1774640090,
        detail: 'Review batch 7/10',
        reviewers_status: [
          { model: 'Claude Opus 4.6', status: 'working', started_at: 1774640100 },
          { model: 'MiMo-V2-Pro', status: 'done', elapsed_seconds: 142 },
        ],
      },
    ],
    active_merge_batches: [
      {
        task_id: 'merge-batch-6',
        batch_index: 6,
        total_batches: 10,
        started_at: 1774640110,
        detail: 'Merging batch 6/10',
        model: 'GPT-5.4 [Reasoning (high)]',
      },
    ],
    coverage_mode: 'strict_leaf_coverage',
    required_leaf_count: 50,
    covered_leaf_count: 47,
    missing_leaf_count: 3,
    duplicate_cluster_count: 2,
    replacement_count: 1,
    generator: 'GPT-5.4 [Reasoning (high)]',
    generators: ['GPT-5.4 [Reasoning (high)]', 'Claude Opus 4.6 [Reasoning (high)]'],
    editor: 'GPT-5.4 [Reasoning (high)]',
    reviewers: ['Claude Opus 4.6 [Reasoning (high)]', 'MiMo-V2-Pro [Reasoning]'],
    elapsed_seconds: 6700,
    recent_log: [
      { timestamp: 6650, level: 'info', message: '▶ Review batch 7/10 — Claude Opus 4.6' },
    ],
  });

  assert.equal(hydrated.status, 'running');
  assert.equal(hydrated.phase, 'review');
  assert.equal(hydrated.batch, 3);
  assert.equal(hydrated.total_batches, 10);
  assert.equal(hydrated.call_started_at, 1774640100);
  assert.equal(hydrated.model, 'Claude Opus 4.6 [Reasoning (high)]');
  assert.equal(hydrated.coverage_mode, 'strict_leaf_coverage');
  assert.equal(hydrated.required_leaf_count, 50);
  assert.equal(hydrated.covered_leaf_count, 47);
  assert.equal(hydrated.missing_leaf_count, 3);
  assert.equal(hydrated.duplicate_cluster_count, 2);
  assert.equal(hydrated.replacement_count, 1);
  assert.deepEqual(hydrated.generators, ['GPT-5.4 [Reasoning (high)]', 'Claude Opus 4.6 [Reasoning (high)]']);
  assert.equal(hydrated.editor, 'GPT-5.4 [Reasoning (high)]');
  assert.equal(hydrated.log.length, 1);
  assert.equal(hydrated.log[0]?.timestamp, 6650);
  assert.equal(hydrated.active_merge_batches[0]?.task_id, 'merge-batch-6');
});
