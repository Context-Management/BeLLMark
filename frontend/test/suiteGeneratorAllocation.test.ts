import assert from 'node:assert/strict';
import test from 'node:test';

import { allocatePromptCounts } from '../src/pages/suites/modelSelection.js';

test('allocatePromptCounts balances counts across selected generators', () => {
  assert.deepEqual(allocatePromptCounts(25, [11, 22, 33]), [9, 8, 8]);
});

test('allocatePromptCounts returns zeroes when generators outnumber prompts', () => {
  assert.deepEqual(allocatePromptCounts(2, [11, 22, 33]), [1, 1, 0]);
});
