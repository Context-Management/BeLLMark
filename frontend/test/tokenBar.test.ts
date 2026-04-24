import assert from 'node:assert/strict';
import test from 'node:test';

import { computeTokenBar } from '../src/lib/tokenBar.js';

test('computeTokenBar clamps fraction to [0, 1]', () => {
  assert.equal(computeTokenBar({ totalTokens: -10, maxTokens: 100 }).fraction, 0);
  assert.equal(computeTokenBar({ totalTokens: 0, maxTokens: 100 }).fraction, 0);
  assert.equal(computeTokenBar({ totalTokens: 40, maxTokens: 100 }).fraction, 0.4);
  assert.equal(computeTokenBar({ totalTokens: 999, maxTokens: 100 }).fraction, 1);
});

test('computeTokenBar returns 0 when maxTokens is 0', () => {
  assert.equal(computeTokenBar({ totalTokens: 50, maxTokens: 0 }).fraction, 0);
});

