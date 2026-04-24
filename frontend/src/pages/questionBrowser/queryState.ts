export type QuestionBrowserMatchMode = 'strict' | 'same-label';

export interface QuestionBrowserSearchState {
  modelIds: number[];
  matchMode: QuestionBrowserMatchMode;
  sourceRunId: number | null;
  sourceQuestionId: number | null;
  questionId: number | null;
}

function assertStrictSourceRunInvariant(
  matchMode: QuestionBrowserMatchMode,
  sourceRunId: number | null | undefined,
): void {
  if (matchMode === 'strict' && sourceRunId == null) {
    throw new Error('sourceRunId is required for strict mode');
  }
}

function normalizeModelIds(modelIds: readonly number[]): number[] {
  return [...new Set(
    modelIds
      .map((value) => Number(value))
      .filter((value) => Number.isInteger(value) && value > 0),
  )].sort((left, right) => left - right);
}

function parseNumericParam(rawValue: string | null): number | null {
  if (rawValue == null || rawValue.trim() === '') {
    return null;
  }

  const value = Number(rawValue);
  return Number.isInteger(value) && value > 0 ? value : null;
}

function parseMatchMode(rawValue: string | null | undefined): QuestionBrowserMatchMode {
  return rawValue === 'same-label' ? 'same-label' : 'strict';
}

function normalizeParsedMatchMode(
  matchMode: QuestionBrowserMatchMode,
  sourceRunId: number | null,
): QuestionBrowserMatchMode {
  if (matchMode === 'strict' && sourceRunId == null) {
    return 'same-label';
  }
  return matchMode;
}

export const MAX_QUESTION_BROWSER_MODELS = 15;

export function clampModelSelection(modelIds: readonly number[]): number[] {
  const normalized = normalizeModelIds(modelIds);
  if (normalized.length < 2) {
    return [];
  }
  return normalized.slice(0, MAX_QUESTION_BROWSER_MODELS);
}

export function parseQuestionBrowserSearch(search: string): QuestionBrowserSearchState {
  const params = new URLSearchParams(search.startsWith('?') ? search.slice(1) : search);
  const sourceRunId = parseNumericParam(params.get('sourceRun'));
  const matchMode = normalizeParsedMatchMode(parseMatchMode(params.get('match')), sourceRunId);

  return {
    modelIds: clampModelSelection(
      (params.get('models') ?? '')
        .split(',')
        .map((value) => Number(value.trim())),
    ),
    matchMode,
    sourceRunId,
    sourceQuestionId: parseNumericParam(params.get('sourceQuestion')),
    questionId: parseNumericParam(params.get('question')),
  };
}

export function serializeQuestionBrowserSearch(
  state: Partial<QuestionBrowserSearchState> & Pick<QuestionBrowserSearchState, 'modelIds'>,
): string {
  const pairs: [string, string][] = [];
  const matchMode = parseMatchMode(state.matchMode);
  const modelIds = clampModelSelection(state.modelIds);

  assertStrictSourceRunInvariant(matchMode, state.sourceRunId);

  if (modelIds.length > 0) {
    pairs.push(['models', modelIds.join(',')]);
  }

  pairs.push(['match', matchMode]);

  if (state.sourceRunId != null) {
    pairs.push(['sourceRun', String(state.sourceRunId)]);
  }

  if (state.sourceQuestionId != null) {
    pairs.push(['sourceQuestion', String(state.sourceQuestionId)]);
  }

  if (state.questionId != null) {
    pairs.push(['question', String(state.questionId)]);
  }

  if (pairs.length === 0) {
    return '';
  }

  return `?${pairs.map(([key, value]) => `${key}=${value}`).join('&')}`;
}
