import type { BenchmarkDetail } from './types.js';

function sanitizeGenerationCharStats(generation: BenchmarkDetail['questions'][0]['generations'][0]): {
  rawChars: number;
  answerChars: number;
} {
  const rawChars = generation.raw_chars || 0;
  const answerChars = generation.answer_chars || 0;
  const outputTokens = generation.output_tokens || 0;
  const reasoningTokens = generation.reasoning_tokens || 0;

  if (
    rawChars > answerChars &&
    answerChars > 0 &&
    outputTokens > 0 &&
    reasoningTokens > 0
  ) {
    const answerTokens = outputTokens - reasoningTokens;
    if (answerTokens > 0 && (answerChars / answerTokens) > 20) {
      return { rawChars: answerChars, answerChars };
    }
  }

  return { rawChars, answerChars };
}

export interface ComputedResultsData {
  modelScores: Record<string, Record<string, number[]>>;
  weightedScores: Record<string, number>;
  winCounts: Record<string, number>;
  rankedModelData: { model: string; score: number }[];
  overallWinner: [string, number] | null;
  hasWeights: boolean;
  weightMap: Record<string, number>;
  totalWeight: number;
  criteriaNameMap: Map<string, string>;
  validCriteriaNames: Set<string>;
  modelPerformance: Record<string, {
    totalTokens: number;
    rawChars: number;
    answerChars: number;
    latencies: number[];
    totalLatencyMs: number;
    count: number;
  }>;
  maxTotalTokens: number;
  lengthBias: Record<string, { r: number | null; warning: boolean }>;
  perQuestionScores: Record<string, Record<number, number>>;
  perJudgeScores: Record<string, Record<string, number>>; // model -> judgeName -> avgWeightedScore
  heatmapData: Record<string, Record<number, Record<string, number>>>;
  insightBadges: Record<string, { label: string; color: string; icon: string }[]>;
  latencyRange: { minAvg: number; maxAvg: number; minP50: number; maxP50: number; minP95: number; maxP95: number };
  tokPerSecRange: { min: number; max: number };
  costRange: { min: number; max: number };
  calculatePercentile: (arr: number[], percentile: number) => number;
  getLatencyHeatColor: (value: number, min: number, max: number) => string;
  getHigherBetterColor: (value: number, min: number, max: number) => string;
  getLowerBetterColor: (value: number, min: number, max: number) => string;
  bestGenerations: RankedGeneration[];
  worstGenerations: RankedGeneration[];
  mostDisagreeingPair: [string, string] | null;
  pairAvgDelta: number;
  topDisagreements: DisagreementEntry[];
}

export interface RankedGeneration {
  questionOrder: number;
  userPrompt: string;
  modelName: string;
  modelPresetId: number;
  generationId: number;
  weightedAvgScore: number;
  perJudgeScores: Array<{
    judgeName: string;
    criterionScores: Record<string, number>;
    avgScore: number;
  }>;
}

export interface DisagreementEntry {
  questionOrder: number;
  userPrompt: string;
  modelName: string;
  modelPresetId: number;
  judgeA: string;
  judgeB: string;
  judgeAScore: number;
  judgeBScore: number;
  scoreDelta: number;
}

export function computeResultsData(benchmark: BenchmarkDetail): ComputedResultsData {
  // Calculate aggregate scores per model
  const modelScores: Record<string, Record<string, number[]>> = {};
  const winCounts: Record<string, number> = {};

  // Valid criteria names for filtering unknown keys (case-insensitive lookup)
  const criteriaNameMap = new Map(benchmark.criteria.map(c => [c.name.toLowerCase(), c.name]));
  const validCriteriaNames = new Set(benchmark.criteria.map(c => c.name));

  // Build weight map
  const weightMap = benchmark.criteria.reduce((acc, c) => {
    acc[c.name] = c.weight || 1.0;
    return acc;
  }, {} as Record<string, number>);
  const totalWeight = Object.values(weightMap).reduce((a, b) => a + b, 0);

  benchmark.questions.forEach((q) => {
    q.judgments.forEach((j) => {
      if (j.status !== 'success') return;

      // Count wins
      if (j.rankings?.length > 0 && j.blind_mapping) {
        const winnerLabel = j.rankings[0];
        const winnerId = j.blind_mapping[winnerLabel];
        const gen = q.generations.find((g) => g.model_preset_id === winnerId);
        if (gen) {
          winCounts[gen.model_name] = (winCounts[gen.model_name] || 0) + 1;
        }
      }

      // Aggregate scores
      if (j.scores) {
        Object.entries(j.scores).forEach(([modelId, criterionScores]) => {
          const gen = q.generations.find((g) => g.model_preset_id === Number(modelId));
          if (!gen) return;

          if (!modelScores[gen.model_name]) {
            modelScores[gen.model_name] = {};
          }

          Object.entries(criterionScores).forEach(([criterion, score]) => {
            // Normalize criterion key (case-insensitive match)
            let normalizedCriterion = criterion;
            if (!validCriteriaNames.has(criterion)) {
              // Try case-insensitive lookup
              const mapped = criteriaNameMap.get(criterion.toLowerCase());
              if (mapped) {
                normalizedCriterion = mapped;
              } else {
                console.warn(`Ignoring unknown criterion key: ${criterion}`);
                return;
              }
            }
            if (!modelScores[gen.model_name][normalizedCriterion]) {
              modelScores[gen.model_name][normalizedCriterion] = [];
            }
            modelScores[gen.model_name][normalizedCriterion].push(score as number);
          });
        });
      }
    });
  });

  // Calculate weighted scores
  const weightedScores: Record<string, number> = {};
  Object.entries(modelScores).forEach(([model, criterionScores]) => {
    let weightedSum = 0;
    Object.entries(criterionScores).forEach(([criterion, scores]) => {
      const weight = weightMap[criterion] || 1.0;
      const avg = scores.reduce((a, b) => a + b, 0) / scores.length;
      weightedSum += avg * weight;
    });
    weightedScores[model] = totalWeight > 0 ? weightedSum / totalWeight : 0;
  });

  // Compute length bias for each model (Pearson correlation between tokens and scores)
  const lengthBias: Record<string, { r: number | null; warning: boolean }> = {};
  Object.keys(modelScores).forEach(model => {
    const tokenScorePairs: Array<[number, number]> = [];

    // For each question, get token count and weighted score for this model
    benchmark.questions.forEach(q => {
      const gen = q.generations.find(g => g.model_name === model && g.status === 'success');
      if (!gen || !gen.tokens) return;

      // Calculate weighted score for this question from per-question judgments
      let questionWeightedSum = 0;
      let questionHasScores = false;

      Object.entries(weightMap).forEach(([criterion, weight]) => {
        const qScores: number[] = [];
        q.judgments.forEach(j => {
          if (j.status !== 'success' || !j.scores) return;
          Object.entries(j.scores).forEach(([modelId, critScores]) => {
            const jGen = q.generations.find(g => g.model_preset_id === Number(modelId));
            if (jGen?.model_name === model && (critScores as Record<string, number>)[criterion] !== undefined) {
              qScores.push((critScores as Record<string, number>)[criterion]);
            }
          });
        });
        if (qScores.length > 0) {
          const avg = qScores.reduce((a, b) => a + b, 0) / qScores.length;
          questionWeightedSum += avg * weight;
          questionHasScores = true;
        }
      });

      if (questionHasScores) {
        const questionScore = totalWeight > 0 ? questionWeightedSum / totalWeight : 0;
        tokenScorePairs.push([gen.tokens, questionScore]);
      }
    });

    // Calculate Pearson correlation
    let r: number | null = null;
    if (tokenScorePairs.length >= 3) {
      const tokens = tokenScorePairs.map(p => p[0]);
      const scores = tokenScorePairs.map(p => p[1]);
      const n = tokens.length;
      const meanTokens = tokens.reduce((a, b) => a + b, 0) / n;
      const meanScores = scores.reduce((a, b) => a + b, 0) / n;
      const varTokens = tokens.reduce((sum, t) => sum + Math.pow(t - meanTokens, 2), 0);
      const varScores = scores.reduce((sum, s) => sum + Math.pow(s - meanScores, 2), 0);

      if (varTokens > 0 && varScores > 0) {
        const cov = tokenScorePairs.reduce((sum, [t, s]) => sum + (t - meanTokens) * (s - meanScores), 0);
        r = cov / Math.sqrt(varTokens * varScores);
      }
    }

    lengthBias[model] = {
      r: r !== null ? Number(r.toFixed(2)) : null,
      warning: r !== null && Math.abs(r) > 0.5
    };
  });

  // Create ranked model data for heatmap table
  const rankedModelData = Object.entries(weightedScores)
    .map(([model, score]) => ({ model, score }))
    .sort((a, b) => b.score - a.score);

  // Find overall winner based on weighted scores
  const hasWeights = benchmark.criteria.some(c => c.weight !== 1.0);
  const winnerEntry = Object.entries(weightedScores).sort((a, b) => b[1] - a[1])[0];
  const overallWinner: [string, number] | null = winnerEntry ? [winnerEntry[0], winnerEntry[1]] : null;

  // Calculate performance metrics per model
  const modelPerformance: Record<string, {
    totalTokens: number;
    rawChars: number;
    answerChars: number;
    latencies: number[];
    totalLatencyMs: number;
    count: number;
  }> = {};
  benchmark.questions.forEach((q) => {
    q.generations.forEach((g) => {
      if (g.status !== 'success') return;
      if (!modelPerformance[g.model_name]) {
        modelPerformance[g.model_name] = { totalTokens: 0, rawChars: 0, answerChars: 0, latencies: [], totalLatencyMs: 0, count: 0 };
      }
      const sanitizedChars = sanitizeGenerationCharStats(g);
      modelPerformance[g.model_name].totalTokens += g.tokens || 0;
      modelPerformance[g.model_name].rawChars += sanitizedChars.rawChars;
      modelPerformance[g.model_name].answerChars += sanitizedChars.answerChars;
      if (g.latency_ms) {
        modelPerformance[g.model_name].latencies.push(g.latency_ms);
        modelPerformance[g.model_name].totalLatencyMs += g.latency_ms;
      }
      modelPerformance[g.model_name].count += 1;
    });
  });

  const maxTotalTokens = Math.max(0, ...Object.values(modelPerformance).map((p) => p.totalTokens));

  // Calculate percentiles
  const calculatePercentile = (arr: number[], percentile: number): number => {
    if (arr.length === 0) return 0;
    const sorted = [...arr].sort((a, b) => a - b);
    const index = Math.ceil((percentile / 100) * sorted.length) - 1;
    return sorted[Math.max(0, index)];
  };

  // Pre-calculate latency stats for heat map coloring
  const latencyStats = Object.values(modelPerformance).map((perf) => {
    const avg = perf.latencies.length > 0
      ? perf.latencies.reduce((a, b) => a + b, 0) / perf.latencies.length
      : 0;
    return {
      avg,
      p50: calculatePercentile(perf.latencies, 50),
      p95: calculatePercentile(perf.latencies, 95),
    };
  });
  const maxAvgLatency = Math.max(0, ...latencyStats.map((s) => s.avg));
  const minAvgLatency = Math.min(...latencyStats.filter((s) => s.avg > 0).map((s) => s.avg)) || 0;
  const maxP50Latency = Math.max(0, ...latencyStats.map((s) => s.p50));
  const minP50Latency = Math.min(...latencyStats.filter((s) => s.p50 > 0).map((s) => s.p50)) || 0;
  const maxP95Latency = Math.max(0, ...latencyStats.map((s) => s.p95));
  const minP95Latency = Math.min(...latencyStats.filter((s) => s.p95 > 0).map((s) => s.p95)) || 0;

  const latencyRange = {
    minAvg: minAvgLatency,
    maxAvg: maxAvgLatency,
    minP50: minP50Latency,
    maxP50: maxP50Latency,
    minP95: minP95Latency,
    maxP95: maxP95Latency,
  };

  // Heat map color: green (fast) -> yellow -> red (slow)
  const getLatencyHeatColor = (value: number, min: number, max: number): string => {
    if (value <= 0 || max <= min) return 'transparent';
    const ratio = (value - min) / (max - min); // 0 = fastest, 1 = slowest
    // Green (120) -> Yellow (60) -> Red (0)
    const hue = 120 - ratio * 120;
    return `hsla(${hue}, 70%, 35%, 0.4)`;
  };

  // Pre-calculate tok/s and cost stats for coloring
  const tokPerSecValues = Object.values(modelPerformance)
    .map((perf) => perf.totalLatencyMs > 0 ? perf.totalTokens / (perf.totalLatencyMs / 1000) : 0)
    .filter(v => v > 0);
  const maxTokPerSec = Math.max(0, ...tokPerSecValues);
  const minTokPerSec = Math.min(...tokPerSecValues) || 0;

  const tokPerSecRange = { min: minTokPerSec, max: maxTokPerSec };

  const costValues = Object.keys(modelPerformance)
    .map(model => benchmark.performance_metrics?.[model]?.estimated_cost)
    .filter((v): v is number => v != null && v > 0);
  const maxCost = Math.max(0, ...costValues);
  const minCost = Math.min(...costValues) || 0;

  const costRange = { min: minCost, max: maxCost };

  // Higher is better (green = high, red = low)
  const getHigherBetterColor = (value: number, min: number, max: number): string => {
    if (value <= 0 || max <= min) return 'transparent';
    const ratio = (value - min) / (max - min); // 0 = lowest, 1 = highest
    const hue = ratio * 120; // Red (0) -> Green (120)
    return `hsla(${hue}, 70%, 35%, 0.4)`;
  };

  // Lower is better (green = low, red = high)
  const getLowerBetterColor = (value: number, min: number, max: number): string => {
    if (value <= 0 || max <= min) return 'transparent';
    const ratio = (value - min) / (max - min); // 0 = lowest, 1 = highest
    const hue = 120 - ratio * 120; // Green (120) -> Red (0)
    return `hsla(${hue}, 70%, 35%, 0.4)`;
  };

  // Insight badges: compute superlatives across models
  const modelNames = rankedModelData.map(d => d.model);
  const insightBadges: Record<string, { label: string; color: string; icon: string }[]> = {};
  modelNames.forEach(m => { insightBadges[m] = []; });

  if (modelNames.length > 1) {
    // Cost badges
    const costByModel = modelNames.map(m => ({
      model: m,
      cost: benchmark.performance_metrics?.[m]?.estimated_cost ?? null
    }));
    const paidModels = costByModel.filter(c => c.cost !== null && c.cost > 0);
    const freeModels = costByModel.filter(c => c.cost === 0);
    freeModels.forEach(f => insightBadges[f.model].push({ label: 'Free', color: 'bg-green-800/60 text-green-300 border-green-600/40', icon: '\uD83C\uDD93' }));
    if (paidModels.length > 1) {
      const cheapest = paidModels.reduce((a, b) => (a.cost! < b.cost!) ? a : b);
      const expensive = paidModels.reduce((a, b) => (a.cost! > b.cost!) ? a : b);
      if (cheapest.model !== expensive.model) {
        insightBadges[cheapest.model].push({ label: 'Cheapest', color: 'bg-emerald-800/60 text-emerald-300 border-emerald-600/40', icon: '\uD83D\uDCB0' });
        insightBadges[expensive.model].push({ label: 'Most Expensive', color: 'bg-red-800/60 text-red-300 border-red-600/40', icon: '\uD83D\uDCB8' });
      }
    }

    // Speed badges (tok/s)
    const speedByModel = modelNames.map(m => {
      const p = modelPerformance[m];
      return { model: m, tps: p?.totalLatencyMs > 0 ? p.totalTokens / (p.totalLatencyMs / 1000) : 0 };
    }).filter(s => s.tps > 0);
    if (speedByModel.length > 1) {
      const fastest = speedByModel.reduce((a, b) => a.tps > b.tps ? a : b);
      const slowest = speedByModel.reduce((a, b) => a.tps < b.tps ? a : b);
      if (fastest.model !== slowest.model) {
        insightBadges[fastest.model].push({ label: 'Fastest', color: 'bg-blue-800/60 text-blue-300 border-blue-600/40', icon: '\u26A1' });
        insightBadges[slowest.model].push({ label: 'Slowest', color: 'bg-orange-800/60 text-orange-300 border-orange-600/40', icon: '\uD83D\uDC22' });
      }
    }

    // Token badges
    const tokenByModel = modelNames.map(m => ({
      model: m,
      tokens: modelPerformance[m]?.totalTokens ?? 0
    })).filter(t => t.tokens > 0);
    if (tokenByModel.length > 1) {
      const most = tokenByModel.reduce((a, b) => a.tokens > b.tokens ? a : b);
      const fewest = tokenByModel.reduce((a, b) => a.tokens < b.tokens ? a : b);
      if (most.model !== fewest.model) {
        insightBadges[most.model].push({ label: 'Most Verbose', color: 'bg-purple-800/60 text-purple-300 border-purple-600/40', icon: '\uD83D\uDCDD' });
        insightBadges[fewest.model].push({ label: 'Most Concise', color: 'bg-cyan-800/60 text-cyan-300 border-cyan-600/40', icon: '\u2702\uFE0F' });
      }
    }
  }

  // Per-question weighted scores per model
  const perQuestionScores: Record<string, Record<number, number>> = {}; // model -> { questionOrder -> weightedScore }
  benchmark.questions.forEach((q) => {
    const questionScores: Record<string, Record<string, number[]>> = {}; // model -> { criterion -> scores[] }
    q.judgments.forEach((j) => {
      if (j.status !== 'success' || !j.scores) return;
      Object.entries(j.scores).forEach(([modelId, criterionScores]) => {
        const gen = q.generations.find(g => g.model_preset_id === Number(modelId));
        if (!gen) return;
        if (!questionScores[gen.model_name]) questionScores[gen.model_name] = {};
        Object.entries(criterionScores).forEach(([criterion, score]) => {
          let nc = criterion;
          if (!validCriteriaNames.has(criterion)) {
            const mapped = criteriaNameMap.get(criterion.toLowerCase());
            if (mapped) nc = mapped; else return;
          }
          if (!questionScores[gen.model_name][nc]) questionScores[gen.model_name][nc] = [];
          questionScores[gen.model_name][nc].push(score as number);
        });
      });
    });
    // Calculate weighted average per model for this question
    Object.entries(questionScores).forEach(([model, critScores]) => {
      let ws = 0;
      Object.entries(critScores).forEach(([crit, scores]) => {
        const w = weightMap[crit] || 1.0;
        const avg = scores.reduce((a, b) => a + b, 0) / scores.length;
        ws += avg * w;
      });
      if (!perQuestionScores[model]) perQuestionScores[model] = {};
      perQuestionScores[model][q.order] = totalWeight > 0 ? ws / totalWeight : 0;
    });
  });

  // Per-judge weighted average scores per model
  // Accumulate: model -> judgeName -> { sum, count }
  const perJudgeAcc: Record<string, Record<string, { sum: number; count: number }>> = {};
  benchmark.questions.forEach((q) => {
    q.judgments.forEach((j) => {
      if (j.status !== 'success' || !j.scores) return;
      Object.entries(j.scores).forEach(([modelId, criterionScores]) => {
        const gen = q.generations.find(g => g.model_preset_id === Number(modelId));
        if (!gen) return;
        const model = gen.model_name;
        const judge = j.judge_name;
        // Compute weighted score for this model from this judgment
        let ws = 0;
        let tw = 0;
        Object.entries(criterionScores).forEach(([criterion, score]) => {
          let nc = criterion;
          if (!validCriteriaNames.has(criterion)) {
            const mapped = criteriaNameMap.get(criterion.toLowerCase());
            if (mapped) nc = mapped; else return;
          }
          const w = weightMap[nc] || 1.0;
          ws += (score as number) * w;
          tw += w;
        });
        const weighted = tw > 0 ? ws / tw : 0;
        if (!perJudgeAcc[model]) perJudgeAcc[model] = {};
        if (!perJudgeAcc[model][judge]) perJudgeAcc[model][judge] = { sum: 0, count: 0 };
        perJudgeAcc[model][judge].sum += weighted;
        perJudgeAcc[model][judge].count += 1;
      });
    });
  });
  const perJudgeScores: Record<string, Record<string, number>> = {};
  Object.entries(perJudgeAcc).forEach(([model, judges]) => {
    perJudgeScores[model] = {};
    Object.entries(judges).forEach(([judge, { sum, count }]) => {
      perJudgeScores[model][judge] = count > 0 ? sum / count : 0;
    });
  });

  // Per-question x per-criterion scores per model (for heatmap)
  const heatmapData: Record<string, Record<number, Record<string, number>>> = {};
  benchmark.questions.forEach((q) => {
    const raw: Record<string, Record<string, number[]>> = {};
    q.judgments.forEach((j) => {
      if (j.status !== 'success' || !j.scores) return;
      Object.entries(j.scores).forEach(([modelId, critScores]) => {
        const gen = q.generations.find(g => g.model_preset_id === Number(modelId));
        if (!gen) return;
        if (!raw[gen.model_name]) raw[gen.model_name] = {};
        Object.entries(critScores).forEach(([crit, score]) => {
          let nc = crit;
          if (!validCriteriaNames.has(crit)) {
            const mapped = criteriaNameMap.get(crit.toLowerCase());
            if (mapped) nc = mapped; else return;
          }
          if (!raw[gen.model_name][nc]) raw[gen.model_name][nc] = [];
          raw[gen.model_name][nc].push(score as number);
        });
      });
    });
    Object.entries(raw).forEach(([model, critMap]) => {
      if (!heatmapData[model]) heatmapData[model] = {};
      heatmapData[model][q.order] = {};
      Object.entries(critMap).forEach(([crit, scores]) => {
        heatmapData[model][q.order][crit] = scores.reduce((a, b) => a + b, 0) / scores.length;
      });
    });
  });

  // ── Highlights: Best/Worst generations ──
  const allGenerationScores: RankedGeneration[] = [];
  benchmark.questions.forEach((q) => {
    q.generations.forEach((g) => {
      if (g.status !== 'success') return;

      const perJudge: RankedGeneration['perJudgeScores'] = [];
      q.judgments.forEach((j) => {
        if (j.status !== 'success' || !j.scores?.[g.model_preset_id]) return;
        const rawScores = j.scores[g.model_preset_id];
        const criterionScores: Record<string, number> = {};
        let ws = 0;
        let tw = 0;
        Object.entries(rawScores).forEach(([crit, score]) => {
          let nc = crit;
          if (!validCriteriaNames.has(crit)) {
            const mapped = criteriaNameMap.get(crit.toLowerCase());
            if (mapped) nc = mapped; else return;
          }
          criterionScores[nc] = score as number;
          const w = weightMap[nc] || 1.0;
          ws += (score as number) * w;
          tw += w;
        });
        perJudge.push({
          judgeName: j.judge_name,
          criterionScores,
          avgScore: tw > 0 ? ws / tw : 0,
        });
      });

      if (perJudge.length === 0) return;

      const avgAcrossJudges = perJudge.reduce((s, j) => s + j.avgScore, 0) / perJudge.length;
      allGenerationScores.push({
        questionOrder: q.order,
        userPrompt: q.user_prompt,
        modelName: g.model_name,
        modelPresetId: g.model_preset_id,
        generationId: g.id,
        weightedAvgScore: avgAcrossJudges,
        perJudgeScores: perJudge,
      });
    });
  });

  allGenerationScores.sort((a, b) => b.weightedAvgScore - a.weightedAvgScore);
  const bestGenerations = allGenerationScores.slice(0, 3);
  const worstGenerations = allGenerationScores.length > 3
    ? allGenerationScores.slice(-3).reverse()
    : [...allGenerationScores].reverse().slice(0, 3);

  // ── Highlights: Judge disagreement ──
  const judgeScoreMap: Record<string, Record<string, number>> = {};
  benchmark.questions.forEach((q) => {
    q.judgments.forEach((j) => {
      if (j.status !== 'success' || !j.scores) return;
      Object.entries(j.scores).forEach(([modelId, critScores]) => {
        const key = `${q.order}:${modelId}`;
        let ws = 0;
        let tw = 0;
        Object.entries(critScores).forEach(([crit, score]) => {
          let nc = crit;
          if (!validCriteriaNames.has(crit)) {
            const mapped = criteriaNameMap.get(crit.toLowerCase());
            if (mapped) nc = mapped; else return;
          }
          const w = weightMap[nc] || 1.0;
          ws += (score as number) * w;
          tw += w;
        });
        if (!judgeScoreMap[key]) judgeScoreMap[key] = {};
        judgeScoreMap[key][j.judge_name] = tw > 0 ? ws / tw : 0;
      });
    });
  });

  const judgeNames = [...new Set(benchmark.questions.flatMap(q =>
    q.judgments.filter(j => j.status === 'success').map(j => j.judge_name)
  ))];

  let mostDisagreeingPair: [string, string] | null = null;
  let pairAvgDelta = 0;
  let topDisagreements: DisagreementEntry[] = [];

  if (judgeNames.length >= 2) {
    let maxAvgDelta = -1;
    let bestPair: [string, string] | null = null;

    for (let i = 0; i < judgeNames.length; i++) {
      for (let k = i + 1; k < judgeNames.length; k++) {
        let sumDelta = 0;
        let overlapCount = 0;
        Object.values(judgeScoreMap).forEach((judges) => {
          if (judges[judgeNames[i]] !== undefined && judges[judgeNames[k]] !== undefined) {
            sumDelta += Math.abs(judges[judgeNames[i]] - judges[judgeNames[k]]);
            overlapCount += 1;
          }
        });
        const avgDelta = overlapCount > 0 ? sumDelta / overlapCount : 0;
        if (avgDelta > maxAvgDelta) {
          maxAvgDelta = avgDelta;
          bestPair = [judgeNames[i], judgeNames[k]];
        }
      }
    }

    if (bestPair) {
      mostDisagreeingPair = bestPair;
      const [jA, jB] = bestPair;

      const entries: DisagreementEntry[] = [];
      Object.entries(judgeScoreMap).forEach(([key, judges]) => {
        if (judges[jA] === undefined || judges[jB] === undefined) return;
        const [qOrderStr, modelIdStr] = key.split(':');
        const qOrder = Number(qOrderStr);
        const modelPresetId = Number(modelIdStr);
        const q = benchmark.questions.find(qq => qq.order === qOrder);
        if (!q) return;
        const gen = q.generations.find(g => g.model_preset_id === modelPresetId);
        if (!gen) return;
        entries.push({
          questionOrder: qOrder,
          userPrompt: q.user_prompt,
          modelName: gen.model_name,
          modelPresetId,
          judgeA: jA,
          judgeB: jB,
          judgeAScore: judges[jA],
          judgeBScore: judges[jB],
          scoreDelta: Math.abs(judges[jA] - judges[jB]),
        });
      });

      pairAvgDelta = entries.length > 0
        ? entries.reduce((s, e) => s + e.scoreDelta, 0) / entries.length
        : 0;

      entries.sort((a, b) => b.scoreDelta - a.scoreDelta);
      topDisagreements = entries.slice(0, 3);
    }
  }

  return {
    modelScores,
    weightedScores,
    winCounts,
    rankedModelData,
    overallWinner,
    hasWeights,
    weightMap,
    totalWeight,
    criteriaNameMap,
    validCriteriaNames,
    modelPerformance,
    maxTotalTokens,
    lengthBias,
    perQuestionScores,
    perJudgeScores,
    heatmapData,
    insightBadges,
    latencyRange,
    tokPerSecRange,
    costRange,
    calculatePercentile,
    getLatencyHeatColor,
    getHigherBetterColor,
    getLowerBetterColor,
    bestGenerations,
    worstGenerations,
    mostDisagreeingPair,
    pairAvgDelta,
    topDisagreements,
  };
}
