import assert from 'node:assert/strict';
import test from 'node:test';

import type { EloRating, AggregateModelEntry } from '../src/types/statistics.js';

// These tests verify that the TypeScript types accept the new fields.
// At runtime they act as integration-style shape tests against mock data.

test('EloRating accepts is_reasoning and reasoning_level fields', () => {
  const standardModel: EloRating = {
    model_id: 1,
    model_name: 'GPT-4o',
    provider: 'openai',
    rating: 1520.5,
    uncertainty: 180.0,
    games_played: 42,
    updated_at: '2026-04-01T00:00:00Z',
    is_reasoning: false,
    reasoning_level: null,
  };

  assert.equal(standardModel.is_reasoning, false);
  assert.equal(standardModel.reasoning_level, null);

  const reasoningModel: EloRating = {
    model_id: 2,
    model_name: 'o3-mini',
    provider: 'openai',
    rating: 1600.0,
    uncertainty: 120.0,
    games_played: 30,
    updated_at: '2026-04-01T00:00:00Z',
    is_reasoning: true,
    reasoning_level: 'high',
  };

  assert.equal(reasoningModel.is_reasoning, true);
  assert.equal(reasoningModel.reasoning_level, 'high');
});

test('AggregateModelEntry accepts is_reasoning and reasoning_level fields', () => {
  const entry: AggregateModelEntry = {
    model_preset_id: 10,
    model_name: 'claude-3-7-sonnet',
    provider: 'anthropic',
    questions_won: 15,
    questions_lost: 5,
    questions_tied: 2,
    total_questions: 22,
    win_rate: 0.681,
    avg_weighted_score: 7.4,
    scored_questions: 20,
    runs_participated: 3,
    is_reasoning: false,
    reasoning_level: null,
  };

  assert.equal(entry.is_reasoning, false);
  assert.equal(entry.reasoning_level, null);
  assert.equal(entry.model_preset_id, 10);

  const reasoningEntry: AggregateModelEntry = {
    model_preset_id: 11,
    model_name: 'claude-3-7-sonnet [Reasoning]',
    provider: 'anthropic',
    questions_won: 18,
    questions_lost: 3,
    questions_tied: 1,
    total_questions: 22,
    win_rate: 0.818,
    avg_weighted_score: 8.1,
    scored_questions: 20,
    runs_participated: 3,
    is_reasoning: true,
    reasoning_level: 'medium',
  };

  assert.equal(reasoningEntry.is_reasoning, true);
  assert.equal(reasoningEntry.reasoning_level, 'medium');
});

test('EloRating is_reasoning defaults work for standard models', () => {
  // Verify we can distinguish reasoning from non-reasoning using the boolean field
  const models: EloRating[] = [
    { model_id: 1, model_name: 'Standard', provider: 'openai', rating: 1500, uncertainty: 200, games_played: 10, updated_at: null, is_reasoning: false, reasoning_level: null },
    { model_id: 2, model_name: 'Reasoner', provider: 'openai', rating: 1600, uncertainty: 150, games_played: 20, updated_at: null, is_reasoning: true, reasoning_level: 'low' },
  ];

  const reasoningModels = models.filter(m => m.is_reasoning);
  const standardModels = models.filter(m => !m.is_reasoning);

  assert.equal(reasoningModels.length, 1);
  assert.equal(standardModels.length, 1);
  assert.equal(reasoningModels[0].model_id, 2);
  assert.equal(standardModels[0].model_id, 1);
});
