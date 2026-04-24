import assert from 'node:assert/strict';
import test from 'node:test';

import { buildJudgeCommentDisplay } from '../src/pages/results/types.js';

test('results judge display keeps score rationale distinct from plus/minus comments', () => {
  const display = buildJudgeCommentDisplay(
    {
      id: 1,
      judge_id: 11,
      judge_name: 'Judge A',
      blind_mapping: {},
      rankings: [],
      scores: { 17: { overall: 8, clarity: 9 } },
      score_rationales: { 17: 'Strong answer with a clear overall fit.' },
      comments: {
        17: [
          { text: 'Clear structure', sentiment: 'positive' },
          { text: 'Missed one nuance', sentiment: 'negative' },
        ],
      },
      reasoning: '',
      status: 'success',
    } as never,
    17,
  );

  assert.ok(display);
  assert.equal(display?.judgeName, 'Judge A');
  assert.equal(display?.scoreRationale, 'Strong answer with a clear overall fit.');
  assert.equal(display?.hasScoreRationale, true);
  assert.deepEqual(display?.comments.map((c) => c.text), ['Clear structure', 'Missed one nuance']);
});

test('results judge display uses a neutral fallback when score rationale is missing', () => {
  const display = buildJudgeCommentDisplay(
    {
      id: 2,
      judge_id: 12,
      judge_name: 'Judge B',
      blind_mapping: {},
      rankings: [],
      scores: { 21: { overall: 7 } },
      comments: { 21: [{ text: 'Needs more detail', sentiment: 'negative' }] },
      reasoning: '',
      status: 'success',
    } as never,
    21,
  );

  assert.ok(display);
  assert.equal(display?.scoreRationale, 'No score rationale recorded.');
  assert.equal(display?.hasScoreRationale, false);
  assert.deepEqual(display?.comments.map((c) => c.text), ['Needs more detail']);
});
