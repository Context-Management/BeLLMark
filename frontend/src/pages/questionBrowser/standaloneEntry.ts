import type {
  QuestionBrowserPickerCandidate,
  QuestionBrowserPickerFrequencyBand,
  QuestionBrowserPickerGuidanceModel,
  QuestionBrowserPickerGuidanceResponse,
} from '@/types/api';
import { clampModelSelection, MAX_QUESTION_BROWSER_MODELS, serializeQuestionBrowserSearch } from './queryState.js';

function normalizeDraftSelection(modelIds: readonly number[]): number[] {
  return [...new Set(
    modelIds
      .map((value) => Number(value))
      .filter((value) => Number.isInteger(value) && value > 0),
  )].sort((left, right) => left - right).slice(0, MAX_QUESTION_BROWSER_MODELS);
}

function normalizeGuidedSearchQuery(query: string): string {
  return query.trim().toLocaleLowerCase();
}

function candidateSearchText(candidate: QuestionBrowserPickerGuidanceModel): string {
  return [
    candidate.resolved_label,
    candidate.name,
    candidate.provider,
    candidate.model_id,
    candidate.host_label,
    candidate.model_format ?? '',
    candidate.quantization ?? '',
  ].join(' ').toLocaleLowerCase();
}

function buildSelectedLabelSummary(selectedLabels: readonly string[]): string {
  const labels = selectedLabels.map((label) => label.trim()).filter(Boolean);
  if (labels.length === 0) {
    return 'Global benchmark usage';
  }
  if (labels.length === 1) {
    return `Tested with ${labels[0]}`;
  }

  const [lastLabel] = labels.slice(-1);
  return `Tested with ${labels.slice(0, -1).join(', ')} + ${lastLabel}`;
}

export function buildGuidedPickerModeLabel(selectedLabels: readonly string[]): string {
  return buildSelectedLabelSummary(selectedLabels);
}

export function buildGuidedPickerFrequencyBandLabel(
  band: QuestionBrowserPickerFrequencyBand,
  count?: number,
): string {
  const labels: Record<QuestionBrowserPickerFrequencyBand, string> = {
    all: 'All',
    high: 'High',
    medium: 'Medium',
    low: 'Low',
    zero: 'Zero',
  };
  const label = labels[band];
  return count == null ? label : `${label} (${count})`;
}

export interface GuidedPickerUiState {
  modeLabel: string;
  selectedLabels: string[];
  visibleCandidates: QuestionBrowserPickerCandidate[];
  canApply: boolean;
  candidateBrowsingLocked: boolean;
}

export function buildGuidedPickerUiState(
  guidance: QuestionBrowserPickerGuidanceResponse,
  query: string,
): GuidedPickerUiState {
  return {
    modeLabel: buildGuidedPickerModeLabel(guidance.selected_models.map((model) => model.resolved_label)),
    selectedLabels: guidance.selected_models.map((model) => model.resolved_label),
    visibleCandidates: buildGuidedPickerVisibleRows(guidance, query),
    canApply: guidance.selection_state >= 2 && guidance.selection_state <= MAX_QUESTION_BROWSER_MODELS,
    candidateBrowsingLocked: guidance.selection_state >= MAX_QUESTION_BROWSER_MODELS,
  };
}

export function sortGuidedPickerCandidates(
  candidates: readonly QuestionBrowserPickerCandidate[],
): QuestionBrowserPickerCandidate[] {
  return [...candidates].sort((left, right) => {
    const countDelta = right.active_benchmark_count - left.active_benchmark_count;
    if (countDelta !== 0) {
      return countDelta;
    }
    const labelDelta = left.resolved_label.localeCompare(right.resolved_label);
    if (labelDelta !== 0) {
      return labelDelta;
    }
    return left.model_preset_id - right.model_preset_id;
  });
}

export function buildGuidedPickerVisibleRows(
  guidance: Pick<QuestionBrowserPickerGuidanceResponse, 'candidates'>,
  query: string,
): QuestionBrowserPickerCandidate[] {
  const normalizedQuery = normalizeGuidedSearchQuery(query);
  const sortedCandidates = sortGuidedPickerCandidates(guidance.candidates);
  if (normalizedQuery === '') {
    return sortedCandidates;
  }
  return sortedCandidates.filter((candidate) => candidateSearchText(candidate).includes(normalizedQuery));
}

export function buildStandaloneQuestionBrowserHref(modelIds: readonly number[]): string {
  return `/question-browser${serializeQuestionBrowserSearch({
    modelIds: clampModelSelection(modelIds),
    matchMode: 'same-label',
    sourceRunId: null,
    sourceQuestionId: null,
    questionId: null,
  })}`;
}

export function toggleStandaloneQuestionBrowserModel(
  modelIds: readonly number[],
  modelId: number,
): number[] {
  const current = normalizeDraftSelection(modelIds);
  if (current.includes(modelId)) {
    return current.filter((id) => id !== modelId);
  }
  if (current.length >= MAX_QUESTION_BROWSER_MODELS) {
    return current;
  }
  return normalizeDraftSelection([...current, modelId]);
}

export function applyGuidedPickerToggle(
  modelIds: readonly number[],
  modelId: number,
  currentSearch: string,
): { nextModelIds: number[]; nextSearch: string } {
  const nextModelIds = toggleStandaloneQuestionBrowserModel(modelIds, modelId);
  const selectionChanged =
    nextModelIds.length !== modelIds.length ||
    nextModelIds.some((value, index) => value !== modelIds[index]);

  return {
    nextModelIds,
    nextSearch: selectionChanged ? '' : currentSearch,
  };
}
