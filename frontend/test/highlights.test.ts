import assert from 'node:assert/strict';
import test from 'node:test';

import { computeResultsData } from '../src/pages/results/computeResultsData.js';
import type { BenchmarkDetail } from '../src/pages/results/types.js';

function makeBenchmark(overrides: Partial<BenchmarkDetail> = {}): BenchmarkDetail {
  return {
    id: 1,
    name: 'Test Run',
    status: 'completed',
    judge_mode: 'comparison',
    criteria: [{ name: 'Quality', description: '', weight: 1.0 }],
    model_ids: [1, 2],
    judge_ids: [10, 20],
    created_at: '2026-01-01T00:00:00Z',
    completed_at: '2026-01-01T00:05:00Z',
    questions: [],
    ...overrides,
  };
}

function makeQuestion(
  order: number,
  generations: BenchmarkDetail['questions'][0]['generations'],
  judgments: BenchmarkDetail['questions'][0]['judgments'],
): BenchmarkDetail['questions'][0] {
  return {
    id: order + 100,
    order,
    system_prompt: 'You are helpful.',
    user_prompt: `Question ${order + 1}`,
    generations,
    judgments,
  };
}

function makeGen(
  modelPresetId: number,
  modelName: string,
  tokens = 100,
  overrides: Partial<BenchmarkDetail['questions'][0]['generations'][0]> = {},
) {
  return {
    id: modelPresetId * 1000,
    model_preset_id: modelPresetId,
    model_name: modelName,
    content: `Response from ${modelName}`,
    tokens,
    status: 'success' as const,
    ...overrides,
  };
}

function makeJudgment(
  judgeName: string,
  scores: Record<number, Record<string, number>>,
  opts: { reasoning?: string } = {},
) {
  return {
    id: Math.floor(Math.random() * 100000),
    judge_id: 0,
    judge_name: judgeName,
    blind_mapping: {} as Record<string, number>,
    rankings: [] as string[],
    scores,
    reasoning: opts.reasoning ?? '',
    status: 'success' as const,
  };
}

test('bestGenerations returns top 3 sorted descending', () => {
  const b = makeBenchmark({
    questions: [
      makeQuestion(0,
        [makeGen(1, 'ModelA'), makeGen(2, 'ModelB')],
        [
          makeJudgment('Judge1', { 1: { Quality: 9 }, 2: { Quality: 3 } }),
          makeJudgment('Judge2', { 1: { Quality: 8 }, 2: { Quality: 4 } }),
        ],
      ),
      makeQuestion(1,
        [makeGen(1, 'ModelA'), makeGen(2, 'ModelB')],
        [
          makeJudgment('Judge1', { 1: { Quality: 7 }, 2: { Quality: 6 } }),
          makeJudgment('Judge2', { 1: { Quality: 7 }, 2: { Quality: 5 } }),
        ],
      ),
    ],
  });

  const result = computeResultsData(b);
  assert.equal(result.bestGenerations.length, 3);
  assert.equal(result.bestGenerations[0].modelName, 'ModelA');
  assert.equal(result.bestGenerations[0].questionOrder, 0);
  assert.ok(result.bestGenerations[0].weightedAvgScore > result.bestGenerations[1].weightedAvgScore);
  assert.ok(result.bestGenerations[1].weightedAvgScore > result.bestGenerations[2].weightedAvgScore);
});

test('worstGenerations returns bottom 3 sorted ascending (worst first)', () => {
  const b = makeBenchmark({
    questions: [
      makeQuestion(0,
        [makeGen(1, 'ModelA'), makeGen(2, 'ModelB')],
        [makeJudgment('Judge1', { 1: { Quality: 9 }, 2: { Quality: 2 } })],
      ),
      makeQuestion(1,
        [makeGen(1, 'ModelA'), makeGen(2, 'ModelB')],
        [makeJudgment('Judge1', { 1: { Quality: 7 }, 2: { Quality: 4 } })],
      ),
    ],
  });

  const result = computeResultsData(b);
  assert.equal(result.worstGenerations[0].modelName, 'ModelB');
  assert.equal(result.worstGenerations[0].questionOrder, 0);
  assert.ok(result.worstGenerations[0].weightedAvgScore < result.worstGenerations[1].weightedAvgScore);
});

test('single judge still produces rankings', () => {
  const b = makeBenchmark({
    questions: [
      makeQuestion(0,
        [makeGen(1, 'ModelA')],
        [makeJudgment('Judge1', { 1: { Quality: 5 } })],
      ),
    ],
  });

  const result = computeResultsData(b);
  assert.equal(result.bestGenerations.length, 1);
  assert.equal(result.bestGenerations[0].weightedAvgScore, 5);
  assert.equal(result.worstGenerations.length, 1);
});

test('disagreement uses average delta, not total (coverage-independent)', () => {
  const b = makeBenchmark({
    criteria: [{ name: 'Quality', description: '', weight: 1.0 }],
    questions: [
      makeQuestion(0,
        [makeGen(1, 'M1'), makeGen(2, 'M2')],
        [
          makeJudgment('JudgeA', { 1: { Quality: 5 }, 2: { Quality: 5 } }),
          makeJudgment('JudgeB', { 1: { Quality: 6 }, 2: { Quality: 6 } }),
          makeJudgment('JudgeC', { 1: { Quality: 10 } }),
        ],
      ),
      makeQuestion(1,
        [makeGen(1, 'M1'), makeGen(2, 'M2')],
        [
          makeJudgment('JudgeA', { 1: { Quality: 5 }, 2: { Quality: 5 } }),
          makeJudgment('JudgeB', { 1: { Quality: 6 }, 2: { Quality: 6 } }),
        ],
      ),
    ],
  });

  const result = computeResultsData(b);
  assert.ok(result.mostDisagreeingPair !== null);
  assert.ok(result.mostDisagreeingPair!.includes('JudgeA'));
  assert.ok(result.mostDisagreeingPair!.includes('JudgeC'));
});

test('pairAvgDelta reflects all comparable items, not just top 3', () => {
  const b = makeBenchmark({
    questions: Array.from({ length: 5 }, (_, i) =>
      makeQuestion(i,
        [makeGen(1, 'M1')],
        [
          makeJudgment('JA', { 1: { Quality: 5 } }),
          makeJudgment('JB', { 1: { Quality: 5 + (i + 1) } }),
        ],
      ),
    ),
  });

  const result = computeResultsData(b);
  assert.equal(result.topDisagreements.length, 3);
  assert.equal(result.pairAvgDelta, 3.0);
});

test('no judges returns null pair and empty disagreements', () => {
  const b = makeBenchmark({
    questions: [
      makeQuestion(0, [makeGen(1, 'M1')], []),
    ],
  });

  const result = computeResultsData(b);
  assert.equal(result.mostDisagreeingPair, null);
  assert.equal(result.topDisagreements.length, 0);
  assert.equal(result.pairAvgDelta, 0);
});

test('single judge returns null pair', () => {
  const b = makeBenchmark({
    questions: [
      makeQuestion(0,
        [makeGen(1, 'M1')],
        [makeJudgment('OnlyJudge', { 1: { Quality: 7 } })],
      ),
    ],
  });

  const result = computeResultsData(b);
  assert.equal(result.mostDisagreeingPair, null);
  assert.equal(result.topDisagreements.length, 0);
});

test('tied scores produce zero delta', () => {
  const b = makeBenchmark({
    questions: [
      makeQuestion(0,
        [makeGen(1, 'M1')],
        [
          makeJudgment('JA', { 1: { Quality: 7 } }),
          makeJudgment('JB', { 1: { Quality: 7 } }),
        ],
      ),
    ],
  });

  const result = computeResultsData(b);
  assert.ok(result.mostDisagreeingPair !== null);
  assert.equal(result.pairAvgDelta, 0);
  assert.equal(result.topDisagreements[0].scoreDelta, 0);
});

test('case-insensitive criterion matching works for highlights', () => {
  const b = makeBenchmark({
    criteria: [{ name: 'Quality', description: '', weight: 1.0 }],
    questions: [
      makeQuestion(0,
        [makeGen(1, 'M1')],
        [makeJudgment('J1', { 1: { quality: 8 } })],
      ),
    ],
  });

  const result = computeResultsData(b);
  assert.equal(result.bestGenerations.length, 1);
  assert.equal(result.bestGenerations[0].weightedAvgScore, 8);
});

test('modelPerformance ignores impossible reasoning-token inflation for existing rows', () => {
  const b = makeBenchmark({
    questions: [
      makeQuestion(0,
        [
          makeGen(1, 'MiMo', 65536, {
            raw_chars: 9178906624,
            answer_chars: 140059,
            output_tokens: 65536,
            reasoning_tokens: 65535,
          }),
        ],
        [makeJudgment('J1', { 1: { Quality: 8 } })],
      ),
      makeQuestion(1,
        [
          makeGen(1, 'MiMo', 200, {
            raw_chars: 4000,
            answer_chars: 1000,
            output_tokens: 200,
            reasoning_tokens: 150,
          }),
        ],
        [makeJudgment('J1', { 1: { Quality: 7 } })],
      ),
    ],
  });

  const result = computeResultsData(b);
  assert.equal(result.modelPerformance.MiMo.answerChars, 141059);
  assert.equal(result.modelPerformance.MiMo.rawChars, 144059);
});
