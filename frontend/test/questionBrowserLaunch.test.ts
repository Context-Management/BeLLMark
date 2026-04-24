import assert from 'node:assert/strict';
import test from 'node:test';

import {
  buildQuestionBrowserLaunchHref,
  buildQuestionBrowserLaunchHrefForSelection,
  getQuestionBrowserLaunchState,
  hasUsableQuestionBrowserStrictSnapshot,
} from '../src/pages/questionBrowser/launch.js';

test('launch is hidden when the current run has fewer than 2 models', () => {
  const launch = getQuestionBrowserLaunchState([11], 44, 987);

  assert.equal(launch.kind, 'hidden');
});

test('launch navigates directly when question has 2 to 4 models', () => {
  const launch = getQuestionBrowserLaunchState([13, 11, 12], 44, 987, {
    runConfigSnapshot: {
      models: [
        {
          id: 13,
          provider: 'openai',
          base_url: 'https://api.openai.com/v1',
          model_id: 'gpt-4.1',
          is_reasoning: true,
          reasoning_level: 'high',
          quantization: null,
          model_format: null,
          selected_variant: null,
          model_architecture: null,
        },
        {
          id: 11,
          provider: 'anthropic',
          base_url: 'https://api.anthropic.com/v1',
          model_id: 'claude-sonnet',
          is_reasoning: true,
          reasoning_level: 'high',
          quantization: null,
          model_format: null,
          selected_variant: null,
          model_architecture: null,
        },
        {
          id: 12,
          provider: 'google',
          base_url: 'https://generativelanguage.googleapis.com/v1beta',
          model_id: 'gemini-2.5-pro',
          is_reasoning: true,
          reasoning_level: 'high',
          quantization: null,
          model_format: null,
          selected_variant: null,
          model_architecture: null,
        },
      ],
    },
  });

  assert.equal(launch.kind, 'navigate');
  assert.equal(
    launch.href,
    '/question-browser?models=11,12,13&match=strict&sourceRun=44&sourceQuestion=987&question=987',
  );
});

test('launch navigates directly when question has 5 models', () => {
  const fiveModelIds = [11, 12, 13, 14, 15];
  const launch = getQuestionBrowserLaunchState(fiveModelIds, 44, 987, {
    runConfigSnapshot: {
      models: fiveModelIds.map((id, i) => ({
        id,
        provider: 'openai',
        base_url: 'http://x',
        model_id: `model-${i}`,
        is_reasoning: false,
        reasoning_level: null,
        quantization: null,
        model_format: null,
        selected_variant: null,
        model_architecture: null,
      })),
    },
  });

  assert.equal(launch.kind, 'navigate');
});

test('launch opens chooser when question has more than 15 models', () => {
  const sixteenModels = Array.from({ length: 16 }, (_, i) => ({
    id: i + 1,
    label: `Model ${i + 1}`,
  }));
  const launch = getQuestionBrowserLaunchState(
    sixteenModels,
    44,
    987,
    {
      runConfigSnapshot: {
        models: sixteenModels.map(({ id }, i) => ({
          id,
          provider: 'openai',
          base_url: 'http://x',
          model_id: `model-${i}`,
          is_reasoning: false,
          reasoning_level: null,
          quantization: null,
          model_format: null,
          selected_variant: null,
          model_architecture: null,
        })),
      },
    },
  );

  assert.equal(launch.kind, 'choose-models');
  assert.equal(launch.options.length, 16);
});

test('buildQuestionBrowserLaunchHref uses selected chooser models with current source ids', () => {
  assert.equal(
    buildQuestionBrowserLaunchHref([21, 24, 22], 44, 987, 'strict'),
    '/question-browser?models=21,22,24&match=strict&sourceRun=44&sourceQuestion=987&question=987',
  );
});

test('launch falls back to same-label when run_config_snapshot is missing', () => {
  const launch = getQuestionBrowserLaunchState([18, 144, 143, 116], 117, 2523, {
    runConfigSnapshot: null,
  });

  assert.equal(launch.kind, 'navigate');
  assert.equal(
    launch.href,
    '/question-browser?models=18,116,143,144&match=same-label&sourceRun=117&sourceQuestion=2523&question=2523',
  );
});

test('buildQuestionBrowserLaunchHref can preserve source ids in same-label mode', () => {
  assert.equal(
    buildQuestionBrowserLaunchHref([18, 144, 143, 116], 117, 2523, 'same-label'),
    '/question-browser?models=18,116,143,144&match=same-label&sourceRun=117&sourceQuestion=2523&question=2523',
  );
});

test('strict snapshot usability requires snapshot model entries for all run models', () => {
  assert.equal(hasUsableQuestionBrowserStrictSnapshot([11, 12], null), false);
  assert.equal(
    hasUsableQuestionBrowserStrictSnapshot([11, 12], {
      models: [{
        id: 11,
        provider: 'openai',
        base_url: 'http://x',
        model_id: 'a',
        is_reasoning: false,
        reasoning_level: null,
        quantization: null,
        model_format: null,
        selected_variant: null,
        model_architecture: null,
      }],
    }),
    false,
  );
  assert.equal(
    hasUsableQuestionBrowserStrictSnapshot([11, 12], {
      models: [
        {
          id: 11,
          provider: 'openai',
          base_url: 'http://x',
          model_id: 'a',
          is_reasoning: false,
          reasoning_level: null,
          quantization: null,
          model_format: null,
          selected_variant: null,
          model_architecture: null,
        },
        {
          id: 12,
          provider: 'openai',
          base_url: 'http://x',
          model_id: 'b',
          is_reasoning: false,
          reasoning_level: null,
          quantization: null,
          model_format: null,
          selected_variant: null,
          model_architecture: null,
        },
      ],
    }),
    true,
  );
});

test('strict snapshot usability falls back when a selected model snapshot is missing strict-signature keys', () => {
  const launch = getQuestionBrowserLaunchState([11, 12], 44, 987, {
    runConfigSnapshot: {
      models: [
        {
          id: 11,
          provider: 'openai',
          base_url: 'http://x',
          model_id: 'a',
          is_reasoning: false,
          reasoning_level: null,
          quantization: null,
          model_format: null,
          selected_variant: null,
          model_architecture: null,
        },
        {
          id: 12,
          provider: 'openai',
          base_url: 'http://x',
          model_id: 'b',
        },
      ],
    },
  });

  assert.equal(launch.kind, 'navigate');
  assert.equal(
    launch.href,
    '/question-browser?models=11,12&match=same-label&sourceRun=44&sourceQuestion=987&question=987',
  );
});

test('chooser subset launch can still use strict when an unselected model has a partial snapshot', () => {
  // Build 16 models — last one has a partial snapshot (no strict fields)
  const fullModels = Array.from({ length: 15 }, (_, i) => ({
    id: i + 11,
    provider: 'openai' as const,
    base_url: 'http://x',
    model_id: `model-${i}`,
    is_reasoning: false,
    reasoning_level: null,
    quantization: null,
    model_format: null,
    selected_variant: null,
    model_architecture: null,
  }));
  const partialModel = { id: 26, provider: 'openai', base_url: 'http://x', model_id: 'partial' };
  const runConfigSnapshot = { models: [...fullModels, partialModel] };
  const allOptions = [...fullModels.map((m, i) => ({ id: m.id, label: `Model ${i}` })), { id: 26, label: 'Partial' }];

  const fullRunLaunch = getQuestionBrowserLaunchState(allOptions, 44, 987, { runConfigSnapshot });

  assert.equal(fullRunLaunch.kind, 'choose-models');
  assert.equal(fullRunLaunch.matchMode, 'same-label');
  assert.equal(
    buildQuestionBrowserLaunchHrefForSelection([11, 12, 13, 14], 44, 987, runConfigSnapshot),
    '/question-browser?models=11,12,13,14&match=strict&sourceRun=44&sourceQuestion=987&question=987',
  );
});

test('buildQuestionBrowserLaunchHref works with 15 models', () => {
  const fifteenIds = Array.from({ length: 15 }, (_, i) => i + 1);
  const href = buildQuestionBrowserLaunchHref(fifteenIds, 44, 987, 'same-label');
  assert.ok(href.startsWith('/question-browser?models=1,2,3,4,5,6,7,8,9,10,11,12,13,14,15'));
});
