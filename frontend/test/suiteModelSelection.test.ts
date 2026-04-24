import assert from 'node:assert/strict';
import test from 'node:test';

import type { ModelPreset } from '../src/types/api.js';
import { filterSuiteModels, sortSuiteModels } from '../src/pages/suites/modelSelection.js';

const models = [
  {
    id: 3,
    name: 'Gamma',
    provider: 'openai',
    base_url: 'https://api.openai.com/v1',
    model_id: 'gpt-5.4',
    has_api_key: true,
    price_input: null,
    price_output: null,
    price_source: null,
    price_source_url: null,
    price_checked_at: null,
    price_currency: null,
    supports_vision: false,
    context_limit: null,
    is_reasoning: true,
    reasoning_level: 'high',
    custom_temperature: null,
    quantization: null,
    model_format: null,
    model_source: null,
    created_at: '2026-03-01T00:00:00Z',
  },
  {
    id: 1,
    name: 'Alpha',
    provider: 'anthropic',
    base_url: 'https://api.anthropic.com/v1/messages',
    model_id: 'claude-opus-4-6',
    has_api_key: true,
    price_input: null,
    price_output: null,
    price_source: null,
    price_source_url: null,
    price_checked_at: null,
    price_currency: null,
    supports_vision: false,
    context_limit: null,
    is_reasoning: true,
    reasoning_level: 'high',
    custom_temperature: null,
    quantization: null,
    model_format: null,
    model_source: null,
    created_at: '2026-03-01T00:00:00Z',
  },
  {
    id: 2,
    name: 'Beta',
    provider: 'google',
    base_url: 'https://generativelanguage.googleapis.com',
    model_id: 'gemini-3-pro-preview',
    has_api_key: true,
    price_input: null,
    price_output: null,
    price_source: null,
    price_source_url: null,
    price_checked_at: null,
    price_currency: null,
    supports_vision: true,
    context_limit: null,
    is_reasoning: false,
    reasoning_level: null,
    custom_temperature: null,
    quantization: null,
    model_format: null,
    model_source: null,
    created_at: '2026-03-01T00:00:00Z',
  },
] satisfies ModelPreset[];

test('sortSuiteModels groups by provider then model name', () => {
  const result = sortSuiteModels([...models]);
  assert.deepEqual(result.map((model) => model.id), [1, 2, 3]);
});

test('filterSuiteModels requires every search token to match', () => {
  const openaiMatches = filterSuiteModels([...models], 'openai gpt-5.4');
  assert.deepEqual(openaiMatches.map((model) => model.id), [3]);

  const providerAndNameMatches = filterSuiteModels([...models], 'anthropic alpha');
  assert.deepEqual(providerAndNameMatches.map((model) => model.id), [1]);
});

test('filterSuiteModels falls back to sorted results for blank search', () => {
  const result = filterSuiteModels([...models], '   ');
  assert.deepEqual(result.map((model) => model.id), [1, 2, 3]);
});
