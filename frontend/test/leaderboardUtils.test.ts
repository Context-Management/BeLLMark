import assert from 'node:assert/strict';
import test from 'node:test';

import { normalizeModelName, groupByBaseModel } from '../src/lib/leaderboardUtils.js';

// ── normalizeModelName ────────────────────────────────────────────────────────

test('normalizeModelName strips [Reasoning (high)] annotation', () => {
  assert.equal(normalizeModelName('claude-3-7-sonnet [Reasoning (high)]'), 'claude-3-7-sonnet');
});

test('normalizeModelName strips [Reasoning] annotation without level', () => {
  assert.equal(normalizeModelName('o3-mini [Reasoning]'), 'o3-mini');
});

test('normalizeModelName strips [Thinking] annotation', () => {
  assert.equal(normalizeModelName('DeepSeek-R1 [Thinking]'), 'DeepSeek-R1');
});

test('normalizeModelName strips [Thinking (high)] annotation (Gemini-style)', () => {
  // Real cases from production: Gemini 3.x models use [Thinking (high|medium|low)]
  assert.equal(
    normalizeModelName('Gemini 3.1 Pro Preview [Thinking (high)]'),
    'Gemini 3.1 Pro Preview',
  );
  assert.equal(
    normalizeModelName('Gemini 3 Flash Preview [Thinking (medium)]'),
    'Gemini 3 Flash Preview',
  );
});

test('normalizeModelName strips trailing clone-id suffix (#NNN)', () => {
  // LM Studio preset clones: e.g. duplicating a preset appends " #125", " #138"
  assert.equal(
    normalizeModelName('Qwen3.5 27B Heretic [Reasoning] (MLX 8bit @ mini) #125'),
    'Qwen3.5 27B Heretic',
  );
  assert.equal(
    normalizeModelName('Qwen3.5 27B Heretic [Reasoning] (MLX 8bit @ mini) #138'),
    'Qwen3.5 27B Heretic',
  );
});

test('normalizeModelName strips combined format/quant/host parens', () => {
  assert.equal(
    normalizeModelName('Llama-3.3-70B (GGUF Q4_K_M @ cachy)'),
    'Llama-3.3-70B',
  );
});

test('normalizeModelName strips quantization parens', () => {
  assert.equal(normalizeModelName('Qwen2.5-32B (Q4_K_M)'), 'Qwen2.5-32B');
});

test('normalizeModelName strips MLX format parens', () => {
  assert.equal(normalizeModelName('GPT-J-6B (MLX)'), 'GPT-J-6B');
});

test('normalizeModelName strips host-only parens', () => {
  assert.equal(normalizeModelName('Mistral-7B (@ cachy)'), 'Mistral-7B');
});

test('normalizeModelName leaves plain names unchanged', () => {
  assert.equal(normalizeModelName('gpt-4o'), 'gpt-4o');
  assert.equal(normalizeModelName('claude-3-opus-20240229'), 'claude-3-opus-20240229');
});

test('normalizeModelName is case-insensitive for annotations', () => {
  assert.equal(normalizeModelName('Model-X [reasoning (medium)]'), 'Model-X');
});

test('normalizeModelName handles both annotation and quant', () => {
  // e.g. a model name that has both [Reasoning (high)] and a quant suffix
  assert.equal(
    normalizeModelName('DeepSeek-R1 [Reasoning (high)] (GGUF Q4_K_M @ cachy)'),
    'DeepSeek-R1',
  );
});

// ── groupByBaseModel ──────────────────────────────────────────────────────────

interface SimpleEntry {
  id: number;
  name: string;
  provider: string;
  score: number;
}

function makeEntry(id: number, name: string, provider: string, score = 0): SimpleEntry {
  return { id, name, provider, score };
}

const getName = (e: SimpleEntry) => e.name;
const getProvider = (e: SimpleEntry) => e.provider;

test('groupByBaseModel groups reasoning variant with base model', () => {
  const entries = [
    makeEntry(1, 'claude-3-7-sonnet', 'anthropic', 1600),
    makeEntry(2, 'claude-3-7-sonnet [Reasoning (high)]', 'anthropic', 1700),
  ];

  const groups = groupByBaseModel(entries, getName, getProvider, true);
  assert.equal(groups.length, 1);
  assert.equal(groups[0].baseName, 'claude-3-7-sonnet');
  assert.equal(groups[0].variants.length, 2);
  // First entry encountered is the representative
  assert.equal(groups[0].representative.id, 1);
});

test('groupByBaseModel groups quant variants together', () => {
  const entries = [
    makeEntry(1, 'Llama-3.3-70B (GGUF Q4_K_M @ cachy)', 'lmstudio', 1500),
    makeEntry(2, 'Llama-3.3-70B (GGUF Q8_0 @ cachy)', 'lmstudio', 1520),
  ];

  const groups = groupByBaseModel(entries, getName, getProvider, true);
  assert.equal(groups.length, 1);
  assert.equal(groups[0].baseName, 'Llama-3.3-70B');
  assert.equal(groups[0].variants.length, 2);
});

test('groupByBaseModel keeps different providers separate when includeProvider=true', () => {
  const entries = [
    makeEntry(1, 'mistral-7b', 'openrouter', 1500),
    makeEntry(2, 'mistral-7b', 'ollama', 1480),
  ];

  const groups = groupByBaseModel(entries, getName, getProvider, true);
  assert.equal(groups.length, 2);
});

test('groupByBaseModel merges different providers when includeProvider=false (default)', () => {
  const entries = [
    makeEntry(1, 'mistral-7b', 'openrouter', 1500),
    makeEntry(2, 'mistral-7b', 'ollama', 1480),
  ];

  const groups = groupByBaseModel(entries, getName, getProvider);
  assert.equal(groups.length, 1);
  assert.equal(groups[0].variants.length, 2);
});

test('groupByBaseModel preserves ordering: first entry is representative', () => {
  const entries = [
    makeEntry(10, 'GPT-4o', 'openai', 1800),
    makeEntry(11, 'Claude-3', 'anthropic', 1750),
    makeEntry(12, 'GPT-4o [Reasoning]', 'openai', 1820),
  ];

  const groups = groupByBaseModel(entries, getName, getProvider, true);
  // GPT-4o group: representative is id=10 (first encountered), with variant id=12
  const gptGroup = groups.find(g => g.baseName === 'GPT-4o');
  assert.ok(gptGroup);
  assert.equal(gptGroup!.representative.id, 10);
  assert.equal(gptGroup!.variants.length, 2);

  // Claude group is separate
  const claudeGroup = groups.find(g => g.baseName === 'Claude-3');
  assert.ok(claudeGroup);
  assert.equal(claudeGroup!.variants.length, 1);
});

test('groupByBaseModel returns empty array for empty input', () => {
  const groups = groupByBaseModel([], getName, getProvider, true);
  assert.equal(groups.length, 0);
});

test('groupByBaseModel single entry stays in its own group', () => {
  const groups = groupByBaseModel([makeEntry(1, 'gpt-4o', 'openai')], getName, getProvider, true);
  assert.equal(groups.length, 1);
  assert.equal(groups[0].variants.length, 1);
  assert.equal(groups[0].representative.id, 1);
});
