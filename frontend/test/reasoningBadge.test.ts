import assert from 'node:assert/strict';
import test from 'node:test';

import { getReasoningBadgeLabel } from '../src/lib/reasoningBadge.js';

test('getReasoningBadgeLabel returns null for non-reasoning models', () => {
  assert.equal(getReasoningBadgeLabel({ is_reasoning: false, reasoning_level: null }), null);
});

test('getReasoningBadgeLabel falls back to on when reasoning is enabled without a level', () => {
  assert.equal(getReasoningBadgeLabel({ is_reasoning: true, reasoning_level: null }), 'on');
});

test('getReasoningBadgeLabel returns explicit reasoning level when present', () => {
  assert.equal(getReasoningBadgeLabel({ is_reasoning: true, reasoning_level: 'high' }), 'high');
});
