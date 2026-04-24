import assert from 'node:assert/strict';
import test from 'node:test';

import type { QuestionBrowserPickerGuidanceResponse } from '../src/types/api.js';
import {
  buildGuidedPickerFrequencyBandLabel,
  buildGuidedPickerModeLabel,
  buildGuidedPickerUiState,
  buildGuidedPickerVisibleRows,
  sortGuidedPickerCandidates,
} from '../src/pages/questionBrowser/standaloneEntry.js';

const GUIDANCE: QuestionBrowserPickerGuidanceResponse = {
  selection_state: 1,
  max_active_count: 8,
  band_counts: { all: 3, high: 1, medium: 1, low: 0, zero: 1 },
  selected_models: [
    {
      model_preset_id: 11,
      name: 'GPT-5.4',
      provider: 'openai',
      model_id: 'gpt-5.4',
      model_format: null,
      quantization: null,
      is_archived: false,
      is_reasoning: true,
      reasoning_level: 'high',
      resolved_label: 'GPT-5.4',
      host_label: 'openai',
    },
  ],
  candidates: [
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
      resolved_label: 'Claude Opus 4.6',
      host_label: 'anthropic',
      active_benchmark_count: 3,
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
      active_benchmark_count: 8,
      selectable: true,
    },
    {
      model_preset_id: 4,
      name: 'Archived model',
      provider: 'openai',
      model_id: 'archived',
      model_format: null,
      quantization: null,
      is_archived: true,
      is_reasoning: false,
      reasoning_level: null,
      resolved_label: 'Archived model',
      host_label: 'openai',
      active_benchmark_count: 0,
      selectable: false,
    },
  ],
};

test('buildGuidedPickerModeLabel reflects selection state copy', () => {
  assert.equal(buildGuidedPickerModeLabel([]), 'Global benchmark usage');
  assert.equal(buildGuidedPickerModeLabel(['GPT-5.4']), 'Tested with GPT-5.4');
  assert.equal(
    buildGuidedPickerModeLabel(['GPT-5.4', 'Claude Opus 4.6']),
    'Tested with GPT-5.4 + Claude Opus 4.6',
  );
});

test('sortGuidedPickerCandidates sorts by active count then resolved_label', () => {
  const sorted = sortGuidedPickerCandidates(GUIDANCE.candidates);
  assert.deepEqual(sorted.map((row) => row.model_preset_id), [2, 3, 4]);
});

test('buildGuidedPickerVisibleRows filters search without re-deduplicating backend candidates', () => {
  const duplicateGuidance: QuestionBrowserPickerGuidanceResponse = {
    ...GUIDANCE,
    candidates: [
      ...GUIDANCE.candidates,
      {
        ...GUIDANCE.candidates[1],
        model_preset_id: 5,
        active_benchmark_count: 7,
      },
    ],
  };

  const rows = buildGuidedPickerVisibleRows(duplicateGuidance, 'gpt-oss');
  assert.equal(rows.length, 2);
  assert.deepEqual(rows.map((row) => row.model_preset_id), [2, 5]);
});

test('buildGuidedPickerFrequencyBandLabel formats counts', () => {
  assert.equal(buildGuidedPickerFrequencyBandLabel('all', 12), 'All (12)');
  assert.equal(buildGuidedPickerFrequencyBandLabel('high', 5), 'High (5)');
  assert.equal(buildGuidedPickerFrequencyBandLabel('zero', 0), 'Zero (0)');
});

test('buildGuidedPickerUiState mirrors backend guidance and search', () => {
  const state = buildGuidedPickerUiState(GUIDANCE, 'gpt');
  assert.equal(state.modeLabel, 'Tested with GPT-5.4');
  assert.equal(state.canApply, false);
  assert.equal(state.candidateBrowsingLocked, false);
  assert.equal(state.visibleCandidates.length, 1);
  assert.equal(state.visibleCandidates[0]?.resolved_label, 'GPT-OSS 120B');
  assert.deepEqual(state.selectedLabels, ['GPT-5.4']);
});

test('buildGuidedPickerUiState locks browsing at fifteen selected models', () => {
  const extraModels = Array.from({ length: 14 }, (_, i) => ({
    model_preset_id: 12 + i,
    name: `Model ${12 + i}`,
    provider: 'openai' as const,
    model_id: `model-${12 + i}`,
    model_format: null,
    quantization: null,
    is_archived: false,
    is_reasoning: false,
    reasoning_level: null,
    resolved_label: `Model ${12 + i}`,
    host_label: 'openai',
  }));

  const lockedState = buildGuidedPickerUiState({
    ...GUIDANCE,
    selection_state: 15,
    selected_models: [
      ...GUIDANCE.selected_models,
      ...extraModels,
    ],
  }, 'gpt');

  assert.equal(lockedState.canApply, true);
  assert.equal(lockedState.candidateBrowsingLocked, true);
  assert.equal(lockedState.visibleCandidates.length, 1);
});
