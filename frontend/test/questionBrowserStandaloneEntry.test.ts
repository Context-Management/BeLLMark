import assert from 'node:assert/strict';
import test from 'node:test';

import {
  applyGuidedPickerToggle,
  buildGuidedPickerFrequencyBandLabel,
  buildGuidedPickerModeLabel,
  buildGuidedPickerVisibleRows,
  buildStandaloneQuestionBrowserHref,
  sortGuidedPickerCandidates,
  toggleStandaloneQuestionBrowserModel,
} from '../src/pages/questionBrowser/standaloneEntry.js';

test('buildStandaloneQuestionBrowserHref creates canonical same-label URLs', () => {
  assert.equal(
    buildStandaloneQuestionBrowserHref([144, 18, 116]),
    '/question-browser?models=18,116,144&match=same-label',
  );
});

test('toggleStandaloneQuestionBrowserModel adds, removes, and caps selections at fifteen', () => {
  assert.deepEqual(toggleStandaloneQuestionBrowserModel([], 18), [18]);
  assert.deepEqual(toggleStandaloneQuestionBrowserModel([18, 144], 116), [18, 116, 144]);
  assert.deepEqual(toggleStandaloneQuestionBrowserModel([18, 144, 116], 144), [18, 116]);
  const fifteenIds = Array.from({ length: 15 }, (_, i) => i + 1);
  assert.deepEqual(toggleStandaloneQuestionBrowserModel(fifteenIds, 99), fifteenIds);
  assert.deepEqual(toggleStandaloneQuestionBrowserModel([18, 19, 20, 21], 22), [18, 19, 20, 21, 22]);
});

test('applyGuidedPickerToggle clears stale search after a successful selection change', () => {
  assert.deepEqual(
    applyGuidedPickerToggle([99], 14, 'gpt-oss 120b'),
    { nextModelIds: [14, 99], nextSearch: '' },
  );

  const fifteenIds = Array.from({ length: 15 }, (_, i) => i + 1);
  assert.deepEqual(
    applyGuidedPickerToggle(fifteenIds, 99, 'gpt'),
    { nextModelIds: fifteenIds, nextSearch: 'gpt' },
  );
});

test('buildGuidedPickerModeLabel reflects selection state copy', () => {
  assert.equal(buildGuidedPickerModeLabel([]), 'Global benchmark usage');
  assert.equal(buildGuidedPickerModeLabel(['GPT-5.4']), 'Tested with GPT-5.4');
  assert.equal(
    buildGuidedPickerModeLabel(['GPT-5.4', 'Claude Opus 4.6']),
    'Tested with GPT-5.4 + Claude Opus 4.6',
  );
});

test('sortGuidedPickerCandidates sorts by active count then resolved label', () => {
  const sorted = sortGuidedPickerCandidates([
    {
      model_preset_id: 3,
      name: 'Model C',
      provider: 'provider',
      model_id: 'c',
      model_format: null,
      quantization: null,
      is_archived: false,
      is_reasoning: false,
      reasoning_level: null,
      resolved_label: 'B',
      host_label: 'host',
      active_benchmark_count: 3,
      selectable: true,
    },
    {
      model_preset_id: 2,
      name: 'Model B',
      provider: 'provider',
      model_id: 'b',
      model_format: null,
      quantization: null,
      is_archived: false,
      is_reasoning: false,
      reasoning_level: null,
      resolved_label: 'A',
      host_label: 'host',
      active_benchmark_count: 3,
      selectable: true,
    },
    {
      model_preset_id: 1,
      name: 'Model A',
      provider: 'provider',
      model_id: 'a',
      model_format: null,
      quantization: null,
      is_archived: false,
      is_reasoning: false,
      reasoning_level: null,
      resolved_label: 'C',
      host_label: 'host',
      active_benchmark_count: 1,
      selectable: true,
    },
  ]);

  assert.deepEqual(sorted.map((row) => row.resolved_label), ['A', 'B', 'C']);
});

test('buildGuidedPickerVisibleRows filters search without re-deduplicating backend candidates', () => {
  const rows = buildGuidedPickerVisibleRows(
    {
      candidates: [
        {
          model_preset_id: 1,
          name: 'GPT-OSS 120B',
          provider: 'lmstudio',
          model_id: 'openai/gpt-oss-120b',
          model_format: 'gguf',
          quantization: 'MXFP4',
          is_archived: false,
          is_reasoning: true,
          reasoning_level: null,
          resolved_label: 'GPT-OSS 120B',
          host_label: 'cachy:1234',
          active_benchmark_count: 8,
          selectable: true,
        },
        {
          model_preset_id: 2,
          name: 'GPT-OSS 120B',
          provider: 'lmstudio',
          model_id: 'openai/gpt-oss-120b',
          model_format: 'gguf',
          quantization: 'MXFP4',
          is_archived: false,
          is_reasoning: true,
          reasoning_level: null,
          resolved_label: 'GPT-OSS 120B',
          host_label: 'cachy:1234',
          active_benchmark_count: 7,
          selectable: true,
        },
        {
          model_preset_id: 3,
          name: 'Claude Opus 4.6',
          provider: 'anthropic',
          model_id: 'claude-opus-4-6',
          model_format: null,
          quantization: null,
          is_archived: false,
          is_reasoning: true,
          reasoning_level: 'high',
          resolved_label: 'Claude Opus 4.6 [Reasoning (high)]',
          host_label: 'anthropic.com',
          active_benchmark_count: 4,
          selectable: true,
        },
      ],
    },
    'gpt-oss',
  );

  assert.equal(rows.length, 2);
  assert.deepEqual(rows.map((row) => row.model_preset_id), [1, 2]);
});

test('buildGuidedPickerFrequencyBandLabel formats counts', () => {
  assert.equal(buildGuidedPickerFrequencyBandLabel('all', 12), 'All (12)');
  assert.equal(buildGuidedPickerFrequencyBandLabel('high', 5), 'High (5)');
  assert.equal(buildGuidedPickerFrequencyBandLabel('zero', 0), 'Zero (0)');
});
