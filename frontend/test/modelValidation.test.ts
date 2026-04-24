import assert from 'node:assert/strict';
import test from 'node:test';

import {
  buildRetargetPreview,
  describeModelTestResult,
  getBulkArchivePresetIds,
  getValidationBadgeMeta,
} from '../src/lib/modelValidation.js';
import type { ModelPreset, ModelTestResult, ValidationResult } from '../src/types/api.js';

const model = {
  id: 12,
  name: 'Qwen3.5 27B',
  provider: 'lmstudio',
  base_url: 'http://localhost:1234/v1/chat/completions',
  model_id: 'qwen3.5-27b',
  has_api_key: false,
  price_input: null,
  price_output: null,
  price_source: null,
  price_source_url: null,
  price_checked_at: null,
  price_currency: null,
  supports_vision: false,
  context_limit: 32768,
  is_reasoning: false,
  reasoning_level: null,
  custom_temperature: null,
  quantization: 'Q4_K_M',
  model_format: 'gguf',
  model_source: 'lmstudio',
  created_at: '2026-03-30T00:00:00Z',
} satisfies ModelPreset;

test('getValidationBadgeMeta maps validation statuses to UI labels', () => {
  assert.deepEqual(getValidationBadgeMeta('available_metadata_drift'), { label: 'Drifted', tone: 'warning' });
  assert.deepEqual(getValidationBadgeMeta('validation_failed'), { label: 'Validation Failed', tone: 'danger' });
});

test('buildRetargetPreview renders explicit before and after mappings', () => {
  const results: ValidationResult[] = [
    {
      preset_id: 12,
      provider: 'lmstudio',
      base_url: 'http://localhost:1234/v1/chat/completions',
      status: 'available_retarget_suggestion',
      message: 'A likely renamed local model was found.',
      live_match: { model_id: 'qwen3.5-27b-dwq' },
      metadata_drift: [],
      suggested_action: 'Retarget to qwen3.5-27b-dwq',
    },
  ];

  assert.deepEqual(buildRetargetPreview(results, [model]), [
    { presetId: 12, from: 'Qwen3.5 27B', to: 'qwen3.5-27b-dwq' },
  ]);
});

test('getBulkArchivePresetIds supports missing and selected archive flows', () => {
  const results: ValidationResult[] = [
    {
      preset_id: 12,
      provider: 'lmstudio',
      base_url: 'http://localhost:1234/v1/chat/completions',
      status: 'missing',
      message: 'Missing',
      metadata_drift: [],
      suggested_action: null,
    },
    {
      preset_id: 13,
      provider: 'lmstudio',
      base_url: 'http://localhost:1234/v1/chat/completions',
      status: 'missing',
      message: 'Missing',
      metadata_drift: [],
      suggested_action: null,
    },
    {
      preset_id: 14,
      provider: 'lmstudio',
      base_url: 'http://localhost:1234/v1/chat/completions',
      status: 'available_exact',
      message: 'Available',
      metadata_drift: [],
      suggested_action: null,
    },
  ];

  assert.deepEqual(getBulkArchivePresetIds(results, [], 'missing'), [12, 13]);
  assert.deepEqual(getBulkArchivePresetIds(results, [13, 14], 'selected'), [13]);
});

test('describeModelTestResult exposes exact runnable details', () => {
  const result: ModelTestResult = {
    status: 'ok',
    ok: true,
    reachable: true,
    provider: 'lmstudio',
    base_url: 'http://localhost:1234/v1/chat/completions',
    model_id: 'openai/gpt-oss-120b',
    resolved_model_id: 'openai/gpt-oss-120b',
    reasoning_supported_levels: ['low', 'medium', 'high', 'xhigh'],
    validation_status: 'available_exact',
    validation_message: 'Exact local model match is available.',
    metadata_drift: [],
  };

  const summary = describeModelTestResult(result);
  assert.equal(summary.title, 'Exact runnable');
  assert.equal(summary.tone, 'success');
  assert.deepEqual(summary.details, [
    'Exact runnable match confirmed.',
    'Resolved model ID: openai/gpt-oss-120b',
    'Reasoning support: low, medium, high, xhigh',
    'Exact local model match is available.',
  ]);
});

test('describeModelTestResult renders validation_failed distinctly', () => {
  const result: ModelTestResult = {
    status: 'error',
    ok: false,
    reachable: true,
    provider: 'lmstudio',
    base_url: 'http://localhost:1234/v1/chat/completions',
    model_id: 'broken/model',
    validation_status: 'validation_failed',
    validation_message: 'Validation failed: malformed discovery payload',
    metadata_drift: [],
    error: 'Validation failed: malformed discovery payload',
  };

  const summary = describeModelTestResult(result);
  assert.equal(summary.title, 'Validation failed');
  assert.equal(summary.tone, 'danger');
  assert.ok(summary.details.includes('Validation failed: malformed discovery payload'));
});
