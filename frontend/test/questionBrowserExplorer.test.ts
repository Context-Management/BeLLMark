import assert from 'node:assert/strict';
import test from 'node:test';

import {
  buildQuestionBrowserExplorerState,
  getAdjacentQuestionId,
  getDefaultExpandedRunIds,
} from '../src/pages/questionBrowser/explorerState.js';
import type { QuestionBrowserSearchRow } from '../src/types/api.js';

const ROWS: QuestionBrowserSearchRow[] = [
  {
    question_id: 410,
    run_id: 41,
    run_name: 'Medical & Clinical',
    question_order: 0,
    prompt_preview: 'What does a positive ANA test mean in context?',
    match_fidelity: 'full',
  },
  {
    question_id: 411,
    run_id: 41,
    run_name: 'Medical & Clinical',
    question_order: 1,
    prompt_preview: 'How would you explain sepsis risk to a patient?',
    match_fidelity: 'degraded',
  },
  {
    question_id: 205,
    run_id: 20,
    run_name: 'Legal Drafting',
    question_order: 0,
    prompt_preview: 'Draft a limitation-of-liability clause for an SaaS agreement.',
    match_fidelity: 'full',
  },
  {
    question_id: 206,
    run_id: 20,
    run_name: 'Legal Drafting',
    question_order: 1,
    prompt_preview: 'Rewrite this NDA definition section in plain English.',
    match_fidelity: 'full',
  },
];

test('buildQuestionBrowserExplorerState groups rows by run and surfaces active preview', () => {
  const state = buildQuestionBrowserExplorerState(ROWS, 411);

  assert.equal(state.groups.length, 2);
  assert.equal(state.groups[0].runId, 41);
  assert.equal(state.groups[0].matchCount, 2);
  assert.equal(state.groups[0].previewQuestionId, 411);
  assert.equal(state.groups[0].previewText, 'How would you explain sepsis risk to a patient?');
  assert.equal(state.groups[0].questions[1].isActive, true);
  assert.equal(state.groups[0].hasDegradedMatch, true);
  assert.equal(state.groups[1].runId, 20);
  assert.equal(state.groups[1].previewQuestionId, 205);
  assert.equal(state.groups[1].previewText, 'Draft a limitation-of-liability clause for an SaaS agreement.');
});

test('getDefaultExpandedRunIds opens only the active run when present', () => {
  const state = buildQuestionBrowserExplorerState(ROWS, 206);

  assert.deepEqual(getDefaultExpandedRunIds(state.groups, 206), [20]);
  assert.deepEqual(getDefaultExpandedRunIds(state.groups, null), []);
});

test('getAdjacentQuestionId moves across grouped runs without pagination', () => {
  assert.equal(getAdjacentQuestionId(ROWS, 410, 1), 411);
  assert.equal(getAdjacentQuestionId(ROWS, 411, 1), 205);
  assert.equal(getAdjacentQuestionId(ROWS, 205, -1), 411);
  assert.equal(getAdjacentQuestionId(ROWS, 410, -1), null);
  assert.equal(getAdjacentQuestionId(ROWS, 206, 1), null);
});
