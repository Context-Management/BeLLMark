import assert from 'node:assert/strict';
import test from 'node:test';

import {
  buildCoverageGenerationFields,
  countCoverageLeaves,
  strictCoverageFeasibilityMessage,
  unwrapCoverageSpec,
} from '../src/pages/suites/coverageSpec.js';

test('countCoverageLeaves sums all nested leaves', () => {
  const spec = {
    groups: [
      { leaves: [{ id: 'a.one' }, { id: 'a.two' }] },
      { leaves: [{ id: 'b.one' }] },
    ],
  };

  assert.equal(countCoverageLeaves(spec), 3);
});

test('unwrapCoverageSpec extracts the raw spec from preview response envelopes', () => {
  const wrapped = {
    spec: {
      groups: [
        { leaves: [{ id: 'a.one' }, { id: 'a.two' }] },
        { leaves: [{ id: 'b.one' }] },
      ],
    },
  };

  assert.deepEqual(unwrapCoverageSpec(wrapped), wrapped.spec);
  assert.equal(countCoverageLeaves(wrapped), 3);
});

test('buildCoverageGenerationFields unwraps coverage spec before submit', () => {
  const wrapped = {
    spec: {
      version: '1',
      groups: [
        { id: 'a', label: 'Streaming', leaves: [{ id: 'a.sse', label: 'SSE' }] },
      ],
    },
  };

  assert.deepEqual(
    buildCoverageGenerationFields('strict_leaf_coverage', wrapped, '  A. Streaming\n- SSE  '),
    {
      coverage_mode: 'strict_leaf_coverage',
      coverage_spec: wrapped.spec,
      coverage_outline_text: 'A. Streaming\n- SSE',
    },
  );
});

test('strictCoverageFeasibilityMessage warns when count is too low', () => {
  assert.equal(
    strictCoverageFeasibilityMessage(49, 25),
    'Strict coverage requires at least 49 questions. Current count is 25.',
  );
});

test('strictCoverageFeasibilityMessage returns null when count is sufficient', () => {
  assert.equal(strictCoverageFeasibilityMessage(10, 10), null);
});
