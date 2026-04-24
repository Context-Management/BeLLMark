export interface QuestionBrowserLaunchOption {
  id: number;
  label: string;
}

export type QuestionBrowserLaunchMatchMode = 'strict' | 'same-label';

export interface QuestionBrowserRunConfigSnapshot {
  models?: Array<{
    id?: number;
    [key: string]: unknown;
  }> | null;
  [key: string]: unknown;
}

const STRICT_SNAPSHOT_FIELDS = [
  'provider',
  'base_url',
  'model_id',
  'is_reasoning',
  'reasoning_level',
  'quantization',
  'model_format',
  'selected_variant',
  'model_architecture',
] as const;

type QuestionBrowserLaunchInput = readonly number[] | readonly QuestionBrowserLaunchOption[];

interface QuestionBrowserLaunchOptions {
  runConfigSnapshot?: QuestionBrowserRunConfigSnapshot | null;
}

interface QuestionBrowserLaunchHiddenState {
  kind: 'hidden';
}

interface QuestionBrowserLaunchNavigateState {
  kind: 'navigate';
  href: string;
  matchMode: QuestionBrowserLaunchMatchMode;
}

interface QuestionBrowserLaunchChooseModelsState {
  kind: 'choose-models';
  options: QuestionBrowserLaunchOption[];
  matchMode: QuestionBrowserLaunchMatchMode;
}

export type QuestionBrowserLaunchState =
  | QuestionBrowserLaunchHiddenState
  | QuestionBrowserLaunchNavigateState
  | QuestionBrowserLaunchChooseModelsState;

function isLaunchOption(value: number | QuestionBrowserLaunchOption): value is QuestionBrowserLaunchOption {
  return typeof value === 'object' && value !== null && 'id' in value && 'label' in value;
}

function normalizeLaunchOptions(input: QuestionBrowserLaunchInput): QuestionBrowserLaunchOption[] {
  const options: QuestionBrowserLaunchOption[] = [];
  const seen = new Set<number>();

  for (const value of input) {
    const option = isLaunchOption(value)
      ? value
      : { id: value, label: String(value) };

    if (!Number.isInteger(option.id) || option.id <= 0 || seen.has(option.id)) {
      continue;
    }

    seen.add(option.id);
    options.push({
      id: option.id,
      label: option.label,
    });
  }

  return options;
}

function normalizeModelIds(modelIds: readonly number[]): number[] {
  return normalizeLaunchOptions(modelIds)
    .map((option) => option.id)
    .sort((left, right) => left - right);
}

function hasFullStrictSnapshotSignature(entry: { [key: string]: unknown }): boolean {
  return STRICT_SNAPSHOT_FIELDS.every((field) => field in entry);
}

export function hasUsableQuestionBrowserStrictSnapshot(
  modelIds: readonly number[],
  runConfigSnapshot: QuestionBrowserRunConfigSnapshot | null | undefined,
): boolean {
  const normalizedModelIds = normalizeModelIds(modelIds);
  if (normalizedModelIds.length === 0) {
    return false;
  }

  const snapshotModelEntries = runConfigSnapshot?.models;
  if (!Array.isArray(snapshotModelEntries) || snapshotModelEntries.length === 0) {
    return false;
  }

  const snapshotModelEntriesById = new Map<number, (typeof snapshotModelEntries)[number]>();
  for (const entry of snapshotModelEntries) {
    const modelId = Number(entry?.id);
    if (Number.isInteger(modelId) && modelId > 0) {
      snapshotModelEntriesById.set(modelId, entry);
    }
  }

  return normalizedModelIds.every((modelId) => {
    const entry = snapshotModelEntriesById.get(modelId);
    return entry !== undefined && hasFullStrictSnapshotSignature(entry);
  });
}

export function getQuestionBrowserLaunchMatchMode(
  modelIds: readonly number[],
  runConfigSnapshot: QuestionBrowserRunConfigSnapshot | null | undefined,
): QuestionBrowserLaunchMatchMode {
  return hasUsableQuestionBrowserStrictSnapshot(modelIds, runConfigSnapshot)
    ? 'strict'
    : 'same-label';
}

import { MAX_QUESTION_BROWSER_MODELS } from './queryState.js';

export function buildQuestionBrowserLaunchHref(
  modelIds: readonly number[],
  sourceRunId: number,
  questionId: number,
  matchMode: QuestionBrowserLaunchMatchMode = 'strict',
): string {
  const normalizedModelIds = normalizeModelIds(modelIds);

  if (normalizedModelIds.length < 2 || normalizedModelIds.length > MAX_QUESTION_BROWSER_MODELS) {
    throw new Error(`question browser launch requires 2 to ${MAX_QUESTION_BROWSER_MODELS} selected models`);
  }

  return `/question-browser?models=${normalizedModelIds.join(',')}&match=${matchMode}&sourceRun=${sourceRunId}&sourceQuestion=${questionId}&question=${questionId}`;
}

export function buildQuestionBrowserLaunchHrefForSelection(
  modelIds: readonly number[],
  sourceRunId: number,
  questionId: number,
  runConfigSnapshot: QuestionBrowserRunConfigSnapshot | null | undefined,
): string {
  return buildQuestionBrowserLaunchHref(
    modelIds,
    sourceRunId,
    questionId,
    getQuestionBrowserLaunchMatchMode(modelIds, runConfigSnapshot),
  );
}

export function getQuestionBrowserLaunchState(
  input: QuestionBrowserLaunchInput,
  sourceRunId: number,
  questionId: number,
  launchOptions: QuestionBrowserLaunchOptions = {},
): QuestionBrowserLaunchState {
  const options = normalizeLaunchOptions(input);
  const matchMode = getQuestionBrowserLaunchMatchMode(
    options.map((option) => option.id),
    launchOptions.runConfigSnapshot,
  );

  if (options.length < 2) {
    return { kind: 'hidden' };
  }

  if (options.length <= MAX_QUESTION_BROWSER_MODELS) {
    return {
      kind: 'navigate',
      href: buildQuestionBrowserLaunchHref(
        options.map((option) => option.id),
        sourceRunId,
        questionId,
        matchMode,
      ),
      matchMode,
    };
  }

  return {
    kind: 'choose-models',
    options,
    matchMode,
  };
}
