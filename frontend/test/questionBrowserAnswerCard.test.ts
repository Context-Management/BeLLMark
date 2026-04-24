import assert from 'node:assert/strict';
import test from 'node:test';

import { buildJudgeDetailContent } from '../src/pages/questionBrowser/viewModel.js';

const rationaleGrade = {
  judge_preset_id: 101,
  judge_label: 'Judge One',
  score: 7.5,
  score_rationale: 'The answer directly addressed the criteria and stayed concise.',
  reasoning: null,
  comments: ['Strong structure', 'Clear conclusion'],
};

test('card judge details prefer score rationale over the old summary path', () => {
  const content = buildJudgeDetailContent(rationaleGrade);

  assert.equal(content.scoreRationaleText, 'The answer directly addressed the criteria and stayed concise.');
  assert.equal(content.hasScoreRationale, true);
  assert.deepEqual(content.comments, ['Strong structure', 'Clear conclusion']);
  assert.ok(!content.scoreRationaleText.includes('Question Evaluation'));
});

test('card judge details show the missing score rationale fallback', () => {
  const content = buildJudgeDetailContent({
    ...rationaleGrade,
    score_rationale: null,
    comments: [],
  });

  assert.equal(content.scoreRationaleText, 'No score rationale recorded.');
  assert.deepEqual(content.comments, []);
});
