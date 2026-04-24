import assert from 'node:assert/strict';
import test from 'node:test';

import { filterDiscoveredModels } from '../src/lib/discoverModels.js';

const models = [
  { model: 'm-a', name: 'Alpha', model_id: 'alpha/model', supports_vision: false, is_reasoning: false, parameter_count: '7B', selected_variant: 'alpha/model@q4', model_architecture: 'llama' },
  { model: 'm-b', name: 'Beta', model_id: 'beta/model', supports_vision: true, is_reasoning: false, quantization_bits: 4.0 },
  { model: 'm-c', name: 'Gamma', model_id: 'gamma/model', supports_vision: false, is_reasoning: true, reasoning_level: 'high', parameter_count: '120B', selected_variant: 'gamma/model@mxfp4', model_architecture: 'gpt-oss' },
];

test('filterDiscoveredModels can show only selected models', () => {
  const result = filterDiscoveredModels(models, {
    searchTerm: '',
    sort: 'default',
    capability: 'all',
    selectedOnly: true,
    selectedIndices: new Set([1, 2]),
  });

  assert.deepEqual(result.map((m) => m._origIndex), [1, 2]);
});

test('filterDiscoveredModels search matches capability keywords: vision', () => {
  const result = filterDiscoveredModels(models, {
    searchTerm: 'vision',
    sort: 'default',
    capability: 'all',
    selectedOnly: false,
    selectedIndices: new Set(),
  });

  assert.deepEqual(result.map((m) => m.model_id), ['beta/model']);
});

test('filterDiscoveredModels search matches capability keywords: reasoning', () => {
  const result = filterDiscoveredModels(models, {
    searchTerm: 'reasoning',
    sort: 'default',
    capability: 'all',
    selectedOnly: false,
    selectedIndices: new Set(),
  });

  assert.deepEqual(result.map((m) => m.model_id), ['gamma/model']);
});

test('filterDiscoveredModels search matches richer local metadata', () => {
  const result = filterDiscoveredModels(models, {
    searchTerm: 'gpt-oss',
    sort: 'default',
    capability: 'all',
    selectedOnly: false,
    selectedIndices: new Set(),
  });

  assert.deepEqual(result.map((m) => m.model_id), ['gamma/model']);
});

test('filterDiscoveredModels search matches parameter count and selected variant', () => {
  const byParameterCount = filterDiscoveredModels(models, {
    searchTerm: '7B',
    sort: 'default',
    capability: 'all',
    selectedOnly: false,
    selectedIndices: new Set(),
  });
  const byVariant = filterDiscoveredModels(models, {
    searchTerm: 'gamma/model@mxfp4',
    sort: 'default',
    capability: 'all',
    selectedOnly: false,
    selectedIndices: new Set(),
  });

  assert.deepEqual(byParameterCount.map((m) => m.model_id), ['alpha/model']);
  assert.deepEqual(byVariant.map((m) => m.model_id), ['gamma/model']);
});

test('filterDiscoveredModels applies capability filter before sorting', () => {
  const result = filterDiscoveredModels(models, {
    searchTerm: '',
    sort: 'za',
    capability: 'vision',
    selectedOnly: false,
    selectedIndices: new Set(),
  });

  assert.equal(result.length, 1);
  assert.equal(result[0].model_id, 'beta/model');
});
