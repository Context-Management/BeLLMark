import type {
  QuestionBrowserAnswerCard,
  QuestionBrowserCardJudgeGrade,
  QuestionBrowserEvaluationMode,
} from '@/types/api';

export interface QuestionBrowserAnswerCardBadge {
  kind: 'mode' | 'tokens' | 'speed';
  label: string;
}

export interface BuildAnswerCardBadgesInput {
  evaluationMode: QuestionBrowserEvaluationMode;
  tokens: number | null;
  tokensPerSecond: number | null;
}

function formatEvaluationMode(mode: QuestionBrowserEvaluationMode): string {
  return mode === 'comparison' ? 'Comparison' : 'Separate';
}

function formatQuestionBrowserTokens(tokens: number | null): string | null {
  if (tokens == null || !Number.isFinite(tokens) || tokens <= 0) {
    return null;
  }

  return `${Math.round(tokens)} tok`;
}

export function formatQuestionBrowserSpeed(tokensPerSecond: number | null): string | null {
  if (tokensPerSecond == null || !Number.isFinite(tokensPerSecond) || tokensPerSecond <= 0) {
    return null;
  }

  const roundedToTenth = Number(tokensPerSecond.toFixed(1));
  const rounded =
    roundedToTenth >= 100
      ? String(Math.round(roundedToTenth))
      : roundedToTenth.toFixed(1);

  return `${rounded} tok/s`;
}

export function buildAnswerCardBadges(
  input: BuildAnswerCardBadgesInput,
): QuestionBrowserAnswerCardBadge[] {
  const badges: QuestionBrowserAnswerCardBadge[] = [
    {
      kind: 'mode',
      label: formatEvaluationMode(input.evaluationMode),
    },
  ];

  const tokensLabel = formatQuestionBrowserTokens(input.tokens);
  if (tokensLabel) {
    badges.push({
      kind: 'tokens',
      label: tokensLabel,
    });
  }

  const speedLabel = formatQuestionBrowserSpeed(input.tokensPerSecond);
  if (speedLabel) {
    badges.push({
      kind: 'speed',
      label: speedLabel,
    });
  }

  return badges;
}


export interface QuestionBrowserJudgeScoreTone {
  hasTone: boolean;
  score: number | null;
}

export function buildJudgeScoreTone(score: number | null): QuestionBrowserJudgeScoreTone {
  if (score == null || !Number.isFinite(score)) {
    return { hasTone: false, score: null };
  }

  return { hasTone: true, score };
}



export interface JudgeDetailContent {
  scoreRationaleText: string;
  hasScoreRationale: boolean;
  comments: readonly string[];
}

export function buildJudgeDetailContent(
  judgeGrade: QuestionBrowserCardJudgeGrade,
): JudgeDetailContent {
  const rationale = judgeGrade.score_rationale?.trim();
  return {
    scoreRationaleText: rationale || 'No score rationale recorded.',
    hasScoreRationale: Boolean(rationale),
    comments: judgeGrade.comments,
  };
}

// === Cost formatter (improvement 2) ===

export interface FormattedCost {
  label: string;
  isFree: boolean;
}

export function formatEstimatedCost(cost: number | null | undefined): FormattedCost | null {
  if (cost == null || !Number.isFinite(cost)) return null;
  if (cost === 0) return { label: 'Free', isFree: true };
  if (cost > 0 && cost < 0.0001) return { label: '<$0.0001', isFree: false };
  // Trim trailing zeros after at least 2 decimal places.
  const fixed = cost.toFixed(4);
  // Examples: 0.0023 → "0.0023"; 0.12 → "0.1200" → "0.12"; 1.5 → "1.5000" → "1.50"
  let trimmed = fixed.replace(/0+$/, '').replace(/\.$/, '');
  if (/\.\d$/.test(trimmed)) {
    // Only one decimal digit after trim (e.g. "1.5") — pad to two for currency readability.
    trimmed = `${trimmed}0`;
  } else if (!trimmed.includes('.')) {
    trimmed = `${trimmed}.00`;
  }
  return { label: `$${trimmed}`, isFree: false };
}

// === Per-question insight badges (improvement 7) ===

export interface PerQuestionInsightBadge {
  label: string;
  color: string;
  icon: string;
}

type InsightsByModel = Record<number, PerQuestionInsightBadge[]>;

const BADGE_FREE: PerQuestionInsightBadge = {
  label: 'Free',
  color: 'bg-green-800/60 text-green-300 border-green-600/40',
  icon: '🆓',
};
const BADGE_CHEAPEST: PerQuestionInsightBadge = {
  label: 'Cheapest',
  color: 'bg-emerald-800/60 text-emerald-300 border-emerald-600/40',
  icon: '💰',
};
const BADGE_MOST_EXPENSIVE: PerQuestionInsightBadge = {
  label: 'Most Expensive',
  color: 'bg-red-800/60 text-red-300 border-red-600/40',
  icon: '💸',
};
const BADGE_FASTEST: PerQuestionInsightBadge = {
  label: 'Fastest',
  color: 'bg-blue-800/60 text-blue-300 border-blue-600/40',
  icon: '⚡',
};
const BADGE_SLOWEST: PerQuestionInsightBadge = {
  label: 'Slowest',
  color: 'bg-orange-800/60 text-orange-300 border-orange-600/40',
  icon: '🐢',
};
const BADGE_MOST_VERBOSE: PerQuestionInsightBadge = {
  label: 'Most Verbose',
  color: 'bg-purple-800/60 text-purple-300 border-purple-600/40',
  icon: '📝',
};
const BADGE_MOST_CONCISE: PerQuestionInsightBadge = {
  label: 'Most Concise',
  color: 'bg-cyan-800/60 text-cyan-300 border-cyan-600/40',
  icon: '✂️',
};

function awardAllTiedWinners<K extends string | number>(
  entries: Array<{ key: K; value: number }>,
  mode: 'min' | 'max',
): K[] {
  if (entries.length < 2) return [];
  const values = entries.map((e) => e.value);
  const extreme = mode === 'min' ? Math.min(...values) : Math.max(...values);
  const distinctCount = new Set(values).size;
  if (distinctCount < 2) return []; // all tied → suppress
  return entries.filter((e) => e.value === extreme).map((e) => e.key);
}

export function buildPerQuestionInsightBadges(
  cards: QuestionBrowserAnswerCard[],
): InsightsByModel {
  const result: InsightsByModel = {};
  for (const card of cards) {
    result[card.model_preset_id] = [];
  }
  if (cards.length < 2) return result;

  // Free badge: every model with estimated_cost === 0
  for (const card of cards) {
    if (card.estimated_cost === 0) {
      result[card.model_preset_id].push(BADGE_FREE);
    }
  }

  // Paid cost superlatives
  const paidEntries = cards
    .filter((c) => c.estimated_cost != null && c.estimated_cost > 0)
    .map((c) => ({ key: c.model_preset_id, value: c.estimated_cost as number }));
  for (const id of awardAllTiedWinners(paidEntries, 'min')) {
    result[id].push(BADGE_CHEAPEST);
  }
  for (const id of awardAllTiedWinners(paidEntries, 'max')) {
    result[id].push(BADGE_MOST_EXPENSIVE);
  }

  // Speed superlatives
  const speedEntries = cards
    .filter((c) => c.speed_tokens_per_second != null && c.speed_tokens_per_second > 0)
    .map((c) => ({ key: c.model_preset_id, value: c.speed_tokens_per_second as number }));
  for (const id of awardAllTiedWinners(speedEntries, 'max')) {
    result[id].push(BADGE_FASTEST);
  }
  for (const id of awardAllTiedWinners(speedEntries, 'min')) {
    result[id].push(BADGE_SLOWEST);
  }

  // Verbosity superlatives
  const tokenEntries = cards
    .filter((c) => c.tokens != null && c.tokens > 0)
    .map((c) => ({ key: c.model_preset_id, value: c.tokens as number }));
  for (const id of awardAllTiedWinners(tokenEntries, 'max')) {
    result[id].push(BADGE_MOST_VERBOSE);
  }
  for (const id of awardAllTiedWinners(tokenEntries, 'min')) {
    result[id].push(BADGE_MOST_CONCISE);
  }

  return result;
}
