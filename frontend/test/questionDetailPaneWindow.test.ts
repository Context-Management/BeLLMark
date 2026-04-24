import assert from 'node:assert/strict';
import test from 'node:test';

import {
  WINDOW_SIZE,
  buildWindowPersistenceKey,
  getVisibleModelIds,
  moveModel,
  shouldShowWindowControls,
} from '../src/pages/questionBrowser/windowHelpers.js';

test('WINDOW_SIZE is 4', () => {
  assert.equal(WINDOW_SIZE, 4);
});

test('getVisibleModelIds returns a slice of size WINDOW_SIZE', () => {
  const order = [1, 2, 3, 4, 5, 6, 7, 8];
  assert.deepEqual(getVisibleModelIds(order, 0), [1, 2, 3, 4]);
  assert.deepEqual(getVisibleModelIds(order, 2), [3, 4, 5, 6]);
  assert.deepEqual(getVisibleModelIds(order, 4), [5, 6, 7, 8]);
});

test('getVisibleModelIds clips at end of array', () => {
  const order = [1, 2, 3];
  assert.deepEqual(getVisibleModelIds(order, 1), [2, 3]);
});

test('getVisibleModelIds handles empty array', () => {
  assert.deepEqual(getVisibleModelIds([], 0), []);
});

test('moveModel does nothing for unknown modelId', () => {
  const order = [1, 2, 3];
  const result = moveModel(order, 99, 1, 0);
  assert.deepEqual(result.newOrder, [1, 2, 3]);
  assert.equal(result.newWindowStart, 0);
});

test('moveModel does nothing when moving left beyond start', () => {
  const order = [1, 2, 3];
  const result = moveModel(order, 1, -1, 0);
  assert.deepEqual(result.newOrder, [1, 2, 3]);
  assert.equal(result.newWindowStart, 0);
});

test('moveModel does nothing when moving right beyond end', () => {
  const order = [1, 2, 3];
  const result = moveModel(order, 3, 1, 0);
  assert.deepEqual(result.newOrder, [1, 2, 3]);
  assert.equal(result.newWindowStart, 0);
});

test('moveModel pin-slot: spec example — left click on rightmost visible pins X', () => {
  // modelOrder = [0, 1, 2, 3, X=4, 5, 6, 7], windowStart = 1, visible = [1,2,3,X]
  const result = moveModel([0, 1, 2, 3, 4, 5, 6, 7], 4, -1, 1);
  // After: X swapped with 3 → [0,1,2,X,3,5,6,7] → windowStart=0 → visible=[0,1,2,X]
  assert.deepEqual(result.newOrder, [0, 1, 2, 4, 3, 5, 6, 7]);
  assert.equal(result.newWindowStart, 0);
});

test('moveModel pin-slot: right click scrolls window to keep X at same visual slot', () => {
  // modelOrder=[0,X=1,2,3,4,5], windowStart=0, visible=[0,X,2,3]
  // Click right on X → targetIndex=2, swap → [0,2,X,3,4,5]
  // visualSlot was 1, newWindowStart = 2-1 = 1, visible = [2,X,3,4]
  const result = moveModel([0, 1, 2, 3, 4, 5], 1, 1, 0);
  assert.deepEqual(result.newOrder, [0, 2, 1, 3, 4, 5]);
  assert.equal(result.newWindowStart, 1);
});

test('moveModel pin-slot: clamps window at left edge', () => {
  // modelOrder=[X=0,1,2,3,4], windowStart=0, visible=[X,1,2,3]
  // Click right on X → targetIndex=1, swap → [1,X,2,3,4]
  // visualSlot=0, rawStart=1-0=1, maxStart=max(0,5-4)=1 → newStart=1 → visible=[X,2,3,4]
  const result = moveModel([0, 1, 2, 3, 4], 0, 1, 0);
  assert.deepEqual(result.newOrder, [1, 0, 2, 3, 4]);
  assert.equal(result.newWindowStart, 1);
});

test('moveModel pin-slot: clamps window at right edge', () => {
  // modelOrder=[0,1,2,3,X=4,5], windowStart=2, visible=[2,3,X,5]
  // Click right on X → targetIndex=5, swap → [0,1,2,3,5,X]
  // visualSlot=4-2=2, rawStart=5-2=3, maxStart=max(0,6-4)=2 → clamped to 2 → visible=[2,3,5,X]
  const result = moveModel([0, 1, 2, 3, 4, 5], 4, 1, 2);
  assert.deepEqual(result.newOrder, [0, 1, 2, 3, 5, 4]);
  assert.equal(result.newWindowStart, 2);
});

test('moveModel pin-slot: repeated left clicks keep target pinned at visual slot', () => {
  let order = [0, 1, 2, 3, 4, 5, 6, 7];
  let start = 4; // visible = [4,5,6,7], click target = id 7 at rightmost visible slot (slot 3)
  const target = 7;

  let r = moveModel(order, target, -1, start);
  assert.deepEqual(r.newOrder, [0, 1, 2, 3, 4, 5, 7, 6]);
  assert.equal(r.newWindowStart, 3); // visible = [3,4,5,7]; target stays at slot 3
  order = r.newOrder;
  start = r.newWindowStart;

  r = moveModel(order, target, -1, start);
  assert.deepEqual(r.newOrder, [0, 1, 2, 3, 4, 7, 5, 6]);
  assert.equal(r.newWindowStart, 2); // visible = [2,3,4,7]; target still at slot 3
});

test('buildWindowPersistenceKey sorts model ids for stable keys', () => {
  const key1 = buildWindowPersistenceKey(42, [3, 1, 2]);
  const key2 = buildWindowPersistenceKey(42, [1, 2, 3]);
  assert.equal(key1, key2);
  assert.equal(key1, '42|1,2,3');
});

test('buildWindowPersistenceKey uses empty string for null sourceRunId', () => {
  const key = buildWindowPersistenceKey(null, [1, 2]);
  assert.equal(key, '|1,2');
});

test('buildWindowPersistenceKey distinguishes different run ids', () => {
  const key1 = buildWindowPersistenceKey(1, [1, 2]);
  const key2 = buildWindowPersistenceKey(2, [1, 2]);
  assert.notEqual(key1, key2);
});

test('shouldShowWindowControls returns true when total > WINDOW_SIZE', () => {
  assert.equal(shouldShowWindowControls(5), true);
  assert.equal(shouldShowWindowControls(15), true);
});

test('shouldShowWindowControls returns false when total <= WINDOW_SIZE', () => {
  assert.equal(shouldShowWindowControls(4), false);
  assert.equal(shouldShowWindowControls(3), false);
  assert.equal(shouldShowWindowControls(1), false);
  assert.equal(shouldShowWindowControls(0), false);
});
