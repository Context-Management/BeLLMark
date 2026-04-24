import assert from 'node:assert/strict';
import test from 'node:test';

import {
  buildVersionReloadUrl,
  shouldForceReloadForVersionMismatch,
} from '../src/lib/api.js';

test('shouldForceReloadForVersionMismatch only reloads when both versions are known and differ', () => {
  assert.equal(shouldForceReloadForVersionMismatch('1.2.3', '1.2.3'), false);
  assert.equal(shouldForceReloadForVersionMismatch('1.2.3', '1.2.4'), true);
  assert.equal(shouldForceReloadForVersionMismatch('1.2.3', null), false);
  assert.equal(shouldForceReloadForVersionMismatch('', '1.2.4'), false);
});

test('buildVersionReloadUrl appends a cache-busting query parameter while preserving existing search', () => {
  const reloaded = buildVersionReloadUrl('http://cachy:8000/question-browser?models=14,99&match=same-label', '1.2.4');
  const parsed = new URL(reloaded, 'http://cachy:8000');

  assert.equal(parsed.pathname, '/question-browser');
  assert.equal(parsed.searchParams.get('models'), '14,99');
  assert.equal(parsed.searchParams.get('match'), 'same-label');
  assert.equal(parsed.searchParams.get('__reload'), '1.2.4');
});
