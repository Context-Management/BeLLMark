import assert from 'node:assert/strict';
import test from 'node:test';

import { buildPromptPreview } from '../src/pages/questionBrowser/promptPreview.js';

test('buildPromptPreview trims long prompts to three lines with ellipsis', () => {
  assert.equal(
    buildPromptPreview('line 1\nline 2\nline 3\nline 4'),
    'line 1\nline 2\nline 3…',
  );
});

test('buildPromptPreview leaves short prompts untouched', () => {
  assert.equal(buildPromptPreview('line 1\nline 2'), 'line 1\nline 2');
});
