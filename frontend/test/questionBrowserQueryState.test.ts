import assert from 'node:assert/strict';
import test from 'node:test';

import { buildQuestionBrowserParams } from '../src/lib/api.js';
import {
  clampModelSelection,
  parseQuestionBrowserSearch as parseQuestionBrowserSearchState,
  serializeQuestionBrowserSearch as serializeQuestionBrowserSearchState,
} from '../src/pages/questionBrowser/queryState.js';

test('parseQuestionBrowserSearch extracts models, sourceRun, sourceQuestion, and question id', () => {
  const state = parseQuestionBrowserSearchState(
    '?models=24,12,18&match=strict&sourceRun=44&sourceQuestion=876&question=987',
  );

  assert.deepEqual(state.modelIds, [12, 18, 24]);
  assert.equal(state.matchMode, 'strict');
  assert.equal(state.sourceRunId, 44);
  assert.equal(state.sourceQuestionId, 876);
  assert.equal(state.questionId, 987);
});

test('serializeQuestionBrowserSearch preserves stable parameter ordering', () => {
  assert.equal(
    serializeQuestionBrowserSearchState({
      modelIds: [24, 12],
      matchMode: 'strict',
      sourceRunId: 44,
      sourceQuestionId: 876,
      questionId: 987,
    }),
    '?models=12,24&match=strict&sourceRun=44&sourceQuestion=876&question=987',
  );
});

test('clampModelSelection enforces 2 to 15 normalized model ids', () => {
  assert.deepEqual(clampModelSelection([7]), []);
  assert.deepEqual(clampModelSelection([9, 4, 9, 2, 4, 8]), [2, 4, 8, 9]);
  const sixteenIds = Array.from({ length: 16 }, (_, i) => i + 1);
  assert.equal(clampModelSelection(sixteenIds).length, 15);
});

test('parseQuestionBrowserSearch clamps malformed and oversized model lists', () => {
  const state = parseQuestionBrowserSearchState(
    '?models=9,foo,4,9,2,-1,8,11&match=same-label&question=33',
  );

  assert.deepEqual(state.modelIds, [2, 4, 8, 9, 11]);
  assert.equal(state.matchMode, 'same-label');
  assert.equal(state.questionId, 33);
});

test('parseQuestionBrowserSearch downgrades stale strict URLs without sourceRunId', () => {
  const state = parseQuestionBrowserSearchState('?models=12,18&match=strict&question=987');

  assert.deepEqual(state.modelIds, [12, 18]);
  assert.equal(state.matchMode, 'same-label');
  assert.equal(state.sourceRunId, null);
  assert.equal(state.questionId, 987);
});

test('serializeQuestionBrowserSearch clamps malformed and oversized model lists', () => {
  assert.equal(
    serializeQuestionBrowserSearchState({
      modelIds: [9, 4, 9, 2, -1, 8, 11],
      matchMode: 'same-label',
      questionId: 33,
    }),
    '?models=2,4,8,9,11&match=same-label&question=33',
  );
});

test('serializeQuestionBrowserSearch rejects strict mode without sourceRunId', () => {
  assert.throws(
    () => serializeQuestionBrowserSearchState({
      modelIds: [12, 18],
      matchMode: 'strict',
      questionId: 987,
    }),
    /sourceRunId is required for strict mode/,
  );
});

test('buildQuestionBrowserParams clamps model ids and rejects strict mode without sourceRunId', () => {
  assert.throws(
    () => buildQuestionBrowserParams({
      modelIds: [7],
      matchMode: 'same-label',
      questionId: 33,
    }),
    /question browser requires 2 to 15 models/,
  );

  assert.throws(
    () => buildQuestionBrowserParams({
      modelIds: [9, 4, 9, 2, 8, 11],
      matchMode: 'strict',
      questionId: 33,
    }),
    /sourceRunId is required for strict mode/,
  );

  assert.deepEqual(
    buildQuestionBrowserParams({
      modelIds: [9, 4, 9, 2, 8, 11],
      matchMode: 'same-label',
      questionId: 33,
      limit: 20,
      offset: 40,
    }),
    {
      models: '2,4,8,9,11',
      match: 'same-label',
      question: 33,
      limit: 20,
      offset: 40,
    },
  );
});
