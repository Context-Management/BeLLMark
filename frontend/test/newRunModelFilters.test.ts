import assert from 'node:assert/strict';
import test from 'node:test';

import { filterAndSortNewRunModels } from '../src/lib/newRunModelFilters.js';

const models = [
  { id: 1, name: 'Alpha', model_id: 'alpha/model', provider: 'openai', base_url: 'https://api.openai.com', is_reasoning: false, supports_vision: false },
  { id: 2, name: 'Beta', model_id: 'beta/model', provider: 'anthropic', base_url: 'https://api.anthropic.com', is_reasoning: true, supports_vision: false },
  { id: 3, name: 'Gamma', model_id: 'gamma/model', provider: 'google', base_url: 'https://generativelanguage.googleapis.com', is_reasoning: false, supports_vision: true },
];

test('filterAndSortNewRunModels supports selected-only scope', () => {
  const result = filterAndSortNewRunModels(models, {
    searchTerm: '',
    providerFilter: 'all',
    reasoningFilter: 'all',
    selectionFilter: 'selected',
    visionFilter: 'all',
    sortBy: 'provider',
    selectedModelIds: new Set([2, 3]),
  });

  assert.deepEqual(result.map((m) => m.id), [2, 3]);
});

test('filterAndSortNewRunModels supports unselected-only scope', () => {
  const result = filterAndSortNewRunModels(models, {
    searchTerm: '',
    providerFilter: 'all',
    reasoningFilter: 'all',
    selectionFilter: 'unselected',
    visionFilter: 'all',
    sortBy: 'provider',
    selectedModelIds: new Set([2, 3]),
  });

  assert.deepEqual(result.map((m) => m.id), [1]);
});

test('filterAndSortNewRunModels sorts by usage frequency descending', () => {
  const usageCounts = new Map<number, number>([[3, 5], [1, 2]]);
  const result = filterAndSortNewRunModels(models, {
    searchTerm: '',
    providerFilter: 'all',
    reasoningFilter: 'all',
    selectionFilter: 'all',
    visionFilter: 'all',
    sortBy: 'frequency',
    selectedModelIds: new Set(),
    usageCounts,
  });

  // Gamma (5 uses) first, Alpha (2 uses) second, Beta (0 uses) last
  assert.deepEqual(result.map((m) => m.id), [3, 1, 2]);
});

test('filterAndSortNewRunModels keeps vision filter behavior', () => {
  const result = filterAndSortNewRunModels(models, {
    searchTerm: '',
    providerFilter: 'all',
    reasoningFilter: 'all',
    selectionFilter: 'all',
    visionFilter: 'vision',
    sortBy: 'provider',
    selectedModelIds: new Set(),
  });

  assert.deepEqual(result.map((m) => m.id), [3]);
});
