import assert from 'node:assert/strict';
import test from 'node:test';

import {
  PROGRESS_MATRIX_META_COLUMNS,
  getProgressMatrixTemplate,
  parseModelLabel,
} from '../src/pages/liveProgress/progressMatrix.js';

test('parseModelLabel splits model name, format, quant, and host into separate slots', () => {
  assert.deepEqual(
    parseModelLabel('GPT-OSS 120B (GGUF MXFP4 @ cachy)'),
    {
      name: 'GPT-OSS 120B',
      format: 'GGUF',
      quant: 'MXFP4',
      host: 'cachy',
    },
  );

  assert.deepEqual(
    parseModelLabel('Qwen3.5 27B (MLX 4bit @ mini)'),
    {
      name: 'Qwen3.5 27B',
      format: 'MLX',
      quant: '4bit',
      host: 'mini',
    },
  );

  assert.deepEqual(
    parseModelLabel('GPT-OSS 120B [Reasoning (high)] (GGUF MXFP4 @ cachy)'),
    {
      name: 'GPT-OSS 120B [Reasoning (high)]',
      format: 'GGUF',
      quant: 'MXFP4',
      host: 'cachy',
    },
  );
});

test('getProgressMatrixTemplate reserves aligned metadata columns before question dots', () => {
  assert.equal(PROGRESS_MATRIX_META_COLUMNS, 3);
  assert.equal(
    getProgressMatrixTemplate(4),
    '1rem minmax(18rem, max-content) max-content repeat(4, 0.875rem)',
  );
});
