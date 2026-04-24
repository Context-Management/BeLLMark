import assert from 'node:assert/strict';
import test from 'node:test';

import {
  buildAnswerCardBadges,
  buildJudgeScoreTone,
  formatQuestionBrowserSpeed,
} from '../src/pages/questionBrowser/viewModel.js';

test('buildAnswerCardBadges includes evaluation mode without fidelity wording', () => {
  const badges = buildAnswerCardBadges({
    evaluationMode: 'comparison',
    tokens: 3200,
    tokensPerSecond: 71.9,
  });

  assert.deepEqual(badges[0], { kind: 'mode', label: 'Comparison' });
  assert.equal(badges.length, 3);
  assert.ok(badges.some((badge) => badge.kind === 'tokens' && badge.label === '3200 tok'));
  assert.ok(badges.some((badge) => badge.kind === 'speed' && badge.label === '71.9 tok/s'));
});

test('buildJudgeScoreTone marks scored judges for gradient tinting and leaves empty scores neutral', () => {
  assert.deepEqual(buildJudgeScoreTone(8.2), { hasTone: true, score: 8.2 });
  assert.deepEqual(buildJudgeScoreTone(null), { hasTone: false, score: null });
});

test('formatQuestionBrowserSpeed returns compact token speed labels', () => {
  assert.equal(formatQuestionBrowserSpeed(null), null);
  assert.equal(formatQuestionBrowserSpeed(0), null);
  assert.equal(formatQuestionBrowserSpeed(71.94), '71.9 tok/s');
  assert.equal(formatQuestionBrowserSpeed(99.95), '100 tok/s');
  assert.equal(formatQuestionBrowserSpeed(120.04), '120 tok/s');
});

import {
  buildPerQuestionInsightBadges,
  formatEstimatedCost,
} from '../src/pages/questionBrowser/viewModel.js';
import type { QuestionBrowserAnswerCard } from '../src/types/api.js';

function card(overrides: Partial<QuestionBrowserAnswerCard>): QuestionBrowserAnswerCard {
  return {
    model_preset_id: 1,
    resolved_label: 'Test',
    source_run_id: 1,
    source_run_name: 'r',
    evaluation_mode: 'comparison',
    run_grade: null,
    question_grade: null,
    judge_grades: [],
    tokens: null,
    latency_ms: null,
    speed_tokens_per_second: null,
    answer_text: null,
    judge_opinions: [],
    match_fidelity: 'full',
    estimated_cost: null,
    run_rank: null,
    run_rank_total: null,
    question_rank: null,
    question_rank_total: null,
    ...overrides,
  };
}

test('formatEstimatedCost: null/undefined → null', () => {
  assert.equal(formatEstimatedCost(null), null);
  assert.equal(formatEstimatedCost(undefined), null);
});

test('formatEstimatedCost: 0 → Free', () => {
  assert.deepEqual(formatEstimatedCost(0), { label: 'Free', isFree: true });
});

test('formatEstimatedCost: sub-0.0001 → "<$0.0001"', () => {
  assert.equal(formatEstimatedCost(0.00003)?.label, '<$0.0001');
});

test('formatEstimatedCost: normal values render with ≥2 decimals', () => {
  assert.equal(formatEstimatedCost(0.12)?.label, '$0.12');
  assert.equal(formatEstimatedCost(1.5)?.label, '$1.50');
  assert.equal(formatEstimatedCost(2)?.label, '$2.00');
});

test('formatEstimatedCost: fractional cents up to 4dp, trimmed', () => {
  assert.equal(formatEstimatedCost(0.0023)?.label, '$0.0023');
  assert.equal(formatEstimatedCost(0.00235)?.label, '$0.0024');
});

test('buildPerQuestionInsightBadges: less than 2 cards → empty entries', () => {
  const result = buildPerQuestionInsightBadges([card({ model_preset_id: 1 })]);
  assert.deepEqual(result[1], []);
});

test('buildPerQuestionInsightBadges: all free → Free for each, no paid superlatives', () => {
  const result = buildPerQuestionInsightBadges([
    card({ model_preset_id: 1, estimated_cost: 0 }),
    card({ model_preset_id: 2, estimated_cost: 0 }),
  ]);
  assert.ok(result[1].some((b) => b.label === 'Free'));
  assert.ok(result[2].some((b) => b.label === 'Free'));
  assert.ok(!result[1].some((b) => b.label === 'Cheapest'));
});

test('buildPerQuestionInsightBadges: partial Cheapest tie', () => {
  const result = buildPerQuestionInsightBadges([
    card({ model_preset_id: 1, estimated_cost: 0.01 }),
    card({ model_preset_id: 2, estimated_cost: 0.01 }),
    card({ model_preset_id: 3, estimated_cost: 0.05 }),
  ]);
  assert.ok(result[1].some((b) => b.label === 'Cheapest'));
  assert.ok(result[2].some((b) => b.label === 'Cheapest'));
  assert.ok(result[3].some((b) => b.label === 'Most Expensive'));
  assert.ok(!result[3].some((b) => b.label === 'Cheapest'));
});

test('buildPerQuestionInsightBadges: everyone tied → superlatives suppressed', () => {
  const result = buildPerQuestionInsightBadges([
    card({ model_preset_id: 1, estimated_cost: 0.05 }),
    card({ model_preset_id: 2, estimated_cost: 0.05 }),
  ]);
  assert.ok(!result[1].some((b) => b.label === 'Cheapest'));
  assert.ok(!result[1].some((b) => b.label === 'Most Expensive'));
});

test('buildPerQuestionInsightBadges: mix of free and paid', () => {
  const result = buildPerQuestionInsightBadges([
    card({ model_preset_id: 1, estimated_cost: 0 }),
    card({ model_preset_id: 2, estimated_cost: 0.01 }),
    card({ model_preset_id: 3, estimated_cost: 0.05 }),
  ]);
  assert.deepEqual(
    result[1].map((b) => b.label),
    ['Free'],
  );
  assert.ok(result[2].some((b) => b.label === 'Cheapest'));
  assert.ok(result[3].some((b) => b.label === 'Most Expensive'));
});

test('buildPerQuestionInsightBadges: single paid model among free → no paid superlatives', () => {
  const result = buildPerQuestionInsightBadges([
    card({ model_preset_id: 1, estimated_cost: 0 }),
    card({ model_preset_id: 2, estimated_cost: 0 }),
    card({ model_preset_id: 3, estimated_cost: 0.01 }),
  ]);
  assert.ok(!result[3].some((b) => b.label === 'Cheapest'));
  assert.ok(!result[3].some((b) => b.label === 'Most Expensive'));
});

test('buildPerQuestionInsightBadges: two tied Fastest', () => {
  const result = buildPerQuestionInsightBadges([
    card({ model_preset_id: 1, speed_tokens_per_second: 100 }),
    card({ model_preset_id: 2, speed_tokens_per_second: 100 }),
    card({ model_preset_id: 3, speed_tokens_per_second: 50 }),
  ]);
  assert.ok(result[1].some((b) => b.label === 'Fastest'));
  assert.ok(result[2].some((b) => b.label === 'Fastest'));
  assert.ok(result[3].some((b) => b.label === 'Slowest'));
});

test('buildPerQuestionInsightBadges: two tied Most Verbose', () => {
  const result = buildPerQuestionInsightBadges([
    card({ model_preset_id: 1, tokens: 500 }),
    card({ model_preset_id: 2, tokens: 500 }),
    card({ model_preset_id: 3, tokens: 100 }),
  ]);
  assert.ok(result[1].some((b) => b.label === 'Most Verbose'));
  assert.ok(result[2].some((b) => b.label === 'Most Verbose'));
  assert.ok(result[3].some((b) => b.label === 'Most Concise'));
});

test('buildPerQuestionInsightBadges: null values excluded', () => {
  const result = buildPerQuestionInsightBadges([
    card({ model_preset_id: 1, speed_tokens_per_second: null }),
    card({ model_preset_id: 2, speed_tokens_per_second: 100 }),
    card({ model_preset_id: 3, speed_tokens_per_second: 50 }),
  ]);
  assert.ok(!result[1].some((b) => b.label === 'Fastest'));
  assert.ok(!result[1].some((b) => b.label === 'Slowest'));
  assert.ok(result[2].some((b) => b.label === 'Fastest'));
  assert.ok(result[3].some((b) => b.label === 'Slowest'));
});
