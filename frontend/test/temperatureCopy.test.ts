import assert from 'node:assert/strict';
import test from 'node:test';

import {
  getCustomTemperatureHelpText,
  getTemperatureModeDescription,
  getTemperatureModeLabel,
} from '../src/lib/temperatureCopy.js';

test('temperature copy softens normalized wording', () => {
  assert.equal(getTemperatureModeLabel('normalized'), 'Normalized (Best-effort)');
  assert.match(
    getTemperatureModeDescription('normalized'),
    /best-effort provider\/model normalization/i,
  );
  assert.match(
    getTemperatureModeDescription('normalized'),
    /ignore or override temperature/i,
  );
});

test('temperature copy softens provider default wording', () => {
  assert.equal(
    getTemperatureModeLabel('provider_default'),
    'Recommended Defaults (Best-effort)',
  );
  assert.match(
    getTemperatureModeDescription('provider_default'),
    /model-specific recommendations/i,
  );
  assert.match(
    getTemperatureModeDescription('provider_default'),
    /provider defaults/i,
  );
});

test('temperature copy keeps custom temperature help aligned to 2.0', () => {
  assert.equal(
    getCustomTemperatureHelpText(),
    'Used when "Custom per Model" temperature mode is selected (0.0-2.0)',
  );
});
