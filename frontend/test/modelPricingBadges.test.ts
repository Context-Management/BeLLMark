import assert from 'node:assert/strict';
import test from 'node:test';

import { formatPricingUnitLabel, getModelPricingBadges } from '../src/lib/modelPricingBadges.js';

test('getModelPricingBadges returns compact input/output/source tags', () => {
  assert.deepEqual(
    getModelPricingBadges({
      price_input: 0.75,
      price_output: 4.5,
      price_currency: 'USD',
      price_source: 'catalog',
      price_source_url: 'https://openai.com/api/pricing/',
      price_checked_at: '2026-03-26T00:00:00',
    }),
    [
      { key: 'input', label: 'in $0.75', tone: 'input' },
      { key: 'output', label: 'out $4.50', tone: 'output' },
      {
        key: 'source',
        label: 'catalog',
        tone: 'source',
        href: 'https://openai.com/api/pricing/',
        title: 'catalog · checked 2026-03-26',
      },
    ],
  );
});

test('getModelPricingBadges omits tags when price data is incomplete', () => {
  assert.deepEqual(
    getModelPricingBadges({
      price_input: null,
      price_output: 4.5,
      price_currency: 'USD',
      price_source: 'catalog',
      price_source_url: 'https://openai.com/api/pricing/',
      price_checked_at: '2026-03-26T00:00:00',
    }),
    [],
  );
});

test('getModelPricingBadges omits source tags when numeric pricing is missing', () => {
  assert.deepEqual(
    getModelPricingBadges({
      price_input: 3,
      price_output: null,
      price_currency: 'USD',
      price_source: 'catalog',
      price_source_url: 'https://openai.com/api/pricing/',
      price_checked_at: '2026-03-26T00:00:00',
    }),
    [],
  );
});

test('getModelPricingBadges keeps manual source tags without a link', () => {
  assert.deepEqual(
    getModelPricingBadges({
      price_input: 3,
      price_output: 15,
      price_currency: 'USD',
      price_source: 'manual',
      price_source_url: null,
      price_checked_at: null,
    }),
    [
      { key: 'input', label: 'in $3.00', tone: 'input' },
      { key: 'output', label: 'out $15.00', tone: 'output' },
      { key: 'source', label: 'manual', tone: 'source', title: 'manual' },
    ],
  );
});

test('getModelPricingBadges prefixes non-USD currencies explicitly', () => {
  assert.deepEqual(
    getModelPricingBadges({
      price_input: 2,
      price_output: 12,
      price_currency: 'RMB',
      price_source: 'catalog',
      price_source_url: 'https://example.com/pricing',
      price_checked_at: '2026-03-26',
    })[0],
    { key: 'input', label: 'in RMB 2.00', tone: 'input' },
  );
});

test('formatPricingUnitLabel reflects non-USD currencies explicitly', () => {
  assert.equal(formatPricingUnitLabel('USD'), 'price ($/1M tokens)');
  assert.equal(formatPricingUnitLabel('RMB'), 'price (RMB/1M tokens)');
});
