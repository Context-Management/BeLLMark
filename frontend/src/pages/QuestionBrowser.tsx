import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import axios from 'axios';
import { useQuery } from '@tanstack/react-query';
import { useLocation, useNavigate } from 'react-router-dom';
import { AlertTriangle } from 'lucide-react';
import { benchmarksApi } from '@/lib/api';
import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import { Card, CardContent } from '@/components/ui/card';
import { Checkbox } from '@/components/ui/checkbox';
import { ErrorBanner } from '@/components/ui/error-banner';
import { Input } from '@/components/ui/input';
import {
  MAX_QUESTION_BROWSER_MODELS,
  parseQuestionBrowserSearch,
  serializeQuestionBrowserSearch,
  type QuestionBrowserSearchState,
} from '@/pages/questionBrowser/queryState';
import {
  applyGuidedPickerToggle,
  buildGuidedPickerModeLabel,
  buildGuidedPickerUiState,
  buildStandaloneQuestionBrowserHref,
} from '@/pages/questionBrowser/standaloneEntry';
import { QuestionDetailPane } from '@/pages/questionBrowser/QuestionDetailPane';
import { QuestionRail } from '@/pages/questionBrowser/QuestionRail';
import {
  buildQuestionBrowserExplorerState,
  getAdjacentQuestionId,
  getDefaultExpandedRunIds,
} from '@/pages/questionBrowser/explorerState';
import { buildWindowPersistenceKey } from '@/pages/questionBrowser/windowHelpers';
import type { QuestionBrowserDetailResponse, QuestionBrowserSearchResponse } from '@/types/api';

const SEARCH_BATCH_SIZE = 200;
const MAX_FETCH_ALL_ROWS = 2000;
const STALE_SELECTION_DETAIL = 'does not match the active selection';

interface QuestionBrowserLocationState {
  questionBrowserNotice?: {
    kind: 'auto-fallback';
    fromQuestionId: number;
    toQuestionId: number;
    filterKey: string;
  } | null;
}

function getErrorMessage(error: unknown, fallback: string): string {
  if (axios.isAxiosError(error)) {
    const detail = error.response?.data?.detail;
    if (typeof detail === 'string' && detail.trim() !== '') {
      return detail;
    }
    if (error.message) {
      return error.message;
    }
  }

  if (error instanceof Error && error.message.trim() !== '') {
    return error.message;
  }

  return fallback;
}

function isStaleSelectionError(error: unknown): boolean {
  if (!axios.isAxiosError(error)) {
    return false;
  }

  return (
    error.response?.status === 404 &&
    typeof error.response?.data?.detail === 'string' &&
    error.response.data.detail.includes(STALE_SELECTION_DETAIL)
  );
}

async function fetchAllQuestionBrowserMatches(params: {
  modelIds: number[];
  matchMode: QuestionBrowserSearchState['matchMode'];
  sourceRunId?: number | null;
  sourceQuestionId?: number | null;
}): Promise<QuestionBrowserSearchResponse> {
  const firstPage = await benchmarksApi.questionBrowserSearch({
    ...params,
    limit: SEARCH_BATCH_SIZE,
    offset: 0,
  });

  if (firstPage.total_count <= firstPage.rows.length) {
    return firstPage;
  }

  const offsets: number[] = [];
  const cappedTotalCount = Math.min(firstPage.total_count, MAX_FETCH_ALL_ROWS);
  for (let offset = firstPage.rows.length; offset < cappedTotalCount; offset += SEARCH_BATCH_SIZE) {
    offsets.push(offset);
  }

  const remainingPages = await Promise.all(offsets.map((offset) =>
    benchmarksApi.questionBrowserSearch({
      ...params,
      limit: SEARCH_BATCH_SIZE,
      offset,
    }),
  ));

  const dedupedRows = new Map(firstPage.rows.map((row) => [row.question_id, row]));
  for (const page of remainingPages) {
    for (const row of page.rows) {
      dedupedRows.set(row.question_id, row);
    }
  }

  return {
    ...firstPage,
    rows: [...dedupedRows.values()],
    total_count: dedupedRows.size,
    limit: dedupedRows.size,
    offset: 0,
  };
}

export function QuestionBrowser() {
  const location = useLocation() as ReturnType<typeof useLocation> & { state: QuestionBrowserLocationState | null };
  const navigate = useNavigate();
  const locationState = location.state ?? null;
  const [selectorOpen, setSelectorOpen] = useState(() => location.search.trim() === '');
  const [draftModelIds, setDraftModelIds] = useState<number[]>(() => []);
  const [modelSearch, setModelSearch] = useState('');
  const [expandedRunIds, setExpandedRunIds] = useState<number[]>([]);
  const searchState = useMemo(
    () => parseQuestionBrowserSearch(location.search),
    [location.search],
  );
  const filterKey = [
    searchState.modelIds.join(','),
    searchState.matchMode,
    searchState.sourceRunId ?? '',
    searchState.sourceQuestionId ?? '',
  ].join('|');
  const hasValidSelection = searchState.modelIds.length >= 2;
  const selectedModelKey = searchState.modelIds.join(',');
  const autoFallbackNotice = useMemo(() => {
    const notice = locationState?.questionBrowserNotice;
    if (!notice || notice.kind !== 'auto-fallback' || notice.filterKey !== filterKey) {
      return null;
    }
    return notice;
  }, [locationState, filterKey]);

  const updateSearchState = useCallback((
    nextState: Partial<QuestionBrowserSearchState>,
    options?: { replace?: boolean; state?: QuestionBrowserLocationState | null },
  ) => {
    const nextSearch = serializeQuestionBrowserSearch({
      ...searchState,
      ...nextState,
      modelIds: nextState.modelIds ?? searchState.modelIds,
    });
    const hasExplicitState = Object.prototype.hasOwnProperty.call(options ?? {}, 'state');
    const nextNavigationState = options?.state ?? null;

    if (
      nextSearch === location.search &&
      (!hasExplicitState || nextNavigationState === locationState)
    ) {
      return;
    }

    navigate(
      {
        pathname: location.pathname,
        search: nextSearch,
      },
      { replace: options?.replace ?? false, state: nextNavigationState },
    );
  }, [location.pathname, location.search, locationState, navigate, searchState]);

  const railQuery = useQuery({
    queryKey: [
      'question-browser',
      'search-all',
      searchState.modelIds,
      searchState.matchMode,
      searchState.sourceRunId,
      searchState.sourceQuestionId,
    ],
    queryFn: () => fetchAllQuestionBrowserMatches({
      modelIds: searchState.modelIds,
      matchMode: searchState.matchMode,
      sourceRunId: searchState.sourceRunId,
      sourceQuestionId: searchState.sourceQuestionId,
    }),
    enabled: hasValidSelection,
  });

  const guidedPickerLocked = draftModelIds.length >= MAX_QUESTION_BROWSER_MODELS;
  const guidanceQuery = useQuery({
    queryKey: ['question-browser', 'picker-guidance', draftModelIds],
    queryFn: () => benchmarksApi.questionBrowserPickerGuidance({
      selectedModelIds: draftModelIds,
    }),
    enabled: !guidedPickerLocked && (!hasValidSelection || selectorOpen),
    staleTime: 60_000,
  });

  const guidedPickerState = useMemo(
    () => (guidanceQuery.data ? buildGuidedPickerUiState(guidanceQuery.data, modelSearch) : null),
    [guidanceQuery.data, modelSearch],
  );
  const selectedDraftLabels = useMemo(() => {
    const infoById = new Map<number, { resolvedLabel: string; provider: string; modelId: string; hostLabel: string }>();
    for (const model of guidanceQuery.data?.selected_models ?? []) {
      infoById.set(model.model_preset_id, {
        resolvedLabel: model.resolved_label,
        provider: model.provider,
        modelId: model.model_id,
        hostLabel: model.host_label,
      });
    }
    for (const candidate of guidanceQuery.data?.candidates ?? []) {
      if (!infoById.has(candidate.model_preset_id)) {
        infoById.set(candidate.model_preset_id, {
          resolvedLabel: candidate.resolved_label,
          provider: candidate.provider,
          modelId: candidate.model_id,
          hostLabel: candidate.host_label,
        });
      }
    }
    for (const selectedModel of railQuery.data?.selected_models ?? []) {
      if (!infoById.has(selectedModel.model_preset_id)) {
        infoById.set(selectedModel.model_preset_id, {
          resolvedLabel: selectedModel.resolved_label,
          provider: '',
          modelId: '',
          hostLabel: '',
        });
      }
    }

    const selectedInfos = draftModelIds.map((modelId) => ({
      id: modelId,
      ...infoById.get(modelId),
    }));
    const duplicateCounts = new Map<string, number>();
    for (const selected of selectedInfos) {
      const resolvedLabel = selected.resolvedLabel ?? `Model ${selected.id}`;
      duplicateCounts.set(resolvedLabel, (duplicateCounts.get(resolvedLabel) ?? 0) + 1);
    }

    return selectedInfos.map((selected) => {
      const resolvedLabel = selected.resolvedLabel ?? `Model ${selected.id}`;
      const hasDuplicateLabel = (duplicateCounts.get(resolvedLabel) ?? 0) > 1;
      const disambiguator = selected.hostLabel || selected.provider || selected.modelId || '';
      const label = hasDuplicateLabel && disambiguator ? `${resolvedLabel} @ ${disambiguator}` : resolvedLabel;
      const titleParts = [resolvedLabel, selected.provider, selected.modelId, selected.hostLabel].filter(Boolean);
      return {
        id: selected.id,
        label,
        title: titleParts.join(' · '),
      };
    });
  }, [draftModelIds, guidanceQuery.data, railQuery.data?.selected_models]);

  const [modelOrder, setModelOrder] = useState<number[]>([]);
  const [windowStart, setWindowStart] = useState(0);
  const windowPersistenceKeyRef = useRef('');
  const windowPersistenceKey = buildWindowPersistenceKey(searchState.sourceRunId, searchState.modelIds);

  useEffect(() => {
    if (windowPersistenceKey !== windowPersistenceKeyRef.current) {
      windowPersistenceKeyRef.current = windowPersistenceKey;
      // eslint-disable-next-line react-hooks/set-state-in-effect
      setModelOrder(searchState.modelIds);
      // eslint-disable-next-line react-hooks/set-state-in-effect
      setWindowStart(0);
    }
  }, [windowPersistenceKey, searchState.modelIds]);

  const modelIdToLabel = useMemo(() => {
    const map = new Map<number, string>();
    for (const model of railQuery.data?.selected_models ?? []) {
      map.set(model.model_preset_id, model.resolved_label);
    }
    return map;
  }, [railQuery.data?.selected_models]);

  useEffect(() => {
    // eslint-disable-next-line react-hooks/set-state-in-effect
    setDraftModelIds(searchState.modelIds);
    if (searchState.modelIds.length < 2) {
      setSelectorOpen(true);
    }
  }, [selectedModelKey, searchState.modelIds.length]);

  useEffect(() => {
    // eslint-disable-next-line react-hooks/set-state-in-effect
    setExpandedRunIds([]);
  }, [filterKey]);

  const activeQuestionId = searchState.questionId ?? railQuery.data?.initial_question_id ?? null;
  const explorerState = useMemo(
    () => buildQuestionBrowserExplorerState(railQuery.data?.rows ?? [], activeQuestionId),
    [railQuery.data?.rows, activeQuestionId],
  );

  useEffect(() => {
    if (searchState.questionId == null && railQuery.data?.initial_question_id != null) {
      updateSearchState({ questionId: railQuery.data.initial_question_id }, { replace: true });
    }
  }, [railQuery.data?.initial_question_id, searchState.questionId, updateSearchState]);

  useEffect(() => {
    const defaultExpandedRunIds = getDefaultExpandedRunIds(explorerState.groups, activeQuestionId);
    if (defaultExpandedRunIds.length === 0) {
      return;
    }

    // eslint-disable-next-line react-hooks/set-state-in-effect
    setExpandedRunIds((current) => {
      const [activeRunId] = defaultExpandedRunIds;
      if (current.length === 0) {
        return [activeRunId];
      }
      if (current.includes(activeRunId)) {
        return current;
      }
      return [...current, activeRunId];
    });
  }, [explorerState.groups, activeQuestionId]);

  const detailQuery = useQuery<QuestionBrowserDetailResponse>({
    queryKey: [
      'question-browser',
      'detail',
      activeQuestionId,
      searchState.modelIds,
      searchState.matchMode,
      searchState.sourceRunId,
      searchState.sourceQuestionId,
    ],
    queryFn: () => benchmarksApi.questionBrowserDetail(activeQuestionId!, {
      modelIds: searchState.modelIds,
      matchMode: searchState.matchMode,
      sourceRunId: searchState.sourceRunId,
      sourceQuestionId: searchState.sourceQuestionId,
    }),
    enabled: hasValidSelection && activeQuestionId != null && railQuery.isSuccess && railQuery.data.total_count > 0,
  });

  const fallbackQuestionId = railQuery.data?.initial_question_id ?? null;

  let detailErrorMessage: string | null = null;
  if (detailQuery.error) {
    detailErrorMessage = getErrorMessage(detailQuery.error, 'Failed to load question detail.');
  }
  const staleSelectionCanAutoRecover =
    isStaleSelectionError(detailQuery.error) &&
    activeQuestionId != null &&
    fallbackQuestionId != null &&
    fallbackQuestionId !== activeQuestionId;

  useEffect(() => {
    if (!staleSelectionCanAutoRecover || activeQuestionId == null || fallbackQuestionId == null) {
      return;
    }

    if (
      autoFallbackNotice?.fromQuestionId === activeQuestionId &&
      autoFallbackNotice.toQuestionId === fallbackQuestionId
    ) {
      return;
    }

    updateSearchState(
      { questionId: fallbackQuestionId },
      {
        replace: true,
        state: {
          questionBrowserNotice: {
            kind: 'auto-fallback',
            fromQuestionId: activeQuestionId,
            toQuestionId: fallbackQuestionId,
            filterKey,
          },
        },
      },
    );
  }, [staleSelectionCanAutoRecover, activeQuestionId, fallbackQuestionId, autoFallbackNotice, filterKey, updateSearchState]);

  const canApplyStandaloneSelection = draftModelIds.length >= 2 && draftModelIds.length <= MAX_QUESTION_BROWSER_MODELS;

  const applyStandaloneSelection = useCallback(() => {
    if (!canApplyStandaloneSelection) {
      return;
    }

    setSelectorOpen(false);
    navigate(buildStandaloneQuestionBrowserHref(draftModelIds), { state: null });
  }, [canApplyStandaloneSelection, draftModelIds, navigate]);

  const previousQuestionId = useMemo(
    () => getAdjacentQuestionId(railQuery.data?.rows ?? [], activeQuestionId, -1),
    [railQuery.data?.rows, activeQuestionId],
  );
  const nextQuestionId = useMemo(
    () => getAdjacentQuestionId(railQuery.data?.rows ?? [], activeQuestionId, 1),
    [railQuery.data?.rows, activeQuestionId],
  );

  const toggleRunExpansion = useCallback((runId: number) => {
    setExpandedRunIds((current) => (
      current.includes(runId)
        ? current.filter((candidate) => candidate !== runId)
        : [...current, runId]
    ));
  }, []);

  useEffect(() => {
    const handler = (event: KeyboardEvent) => {
      if (event.metaKey || event.ctrlKey || event.altKey) return;
      const target = event.target as HTMLElement | null;
      if (target) {
        const tag = target.tagName;
        if (tag === 'INPUT' || tag === 'TEXTAREA' || tag === 'SELECT') return;
        if (target.isContentEditable) return;
      }
      if (event.key === 'ArrowLeft' || event.key === 'j') {
        if (previousQuestionId != null) {
          event.preventDefault();
          updateSearchState({ questionId: previousQuestionId }, { state: null });
        }
      } else if (event.key === 'ArrowRight' || event.key === 'k') {
        if (nextQuestionId != null) {
          event.preventDefault();
          updateSearchState({ questionId: nextQuestionId }, { state: null });
        }
      }
    };
    window.addEventListener('keydown', handler);
    return () => window.removeEventListener('keydown', handler);
  }, [previousQuestionId, nextQuestionId, updateSearchState]);

  return (
    <div data-testid="qb-root" className="space-y-4">
      <div>
        <h1 className="text-3xl font-bold">Question Browser</h1>
        <p className="mt-1 text-slate-500 dark:text-gray-400">
          Browse benchmarks as grouped question explorers instead of paging through a flat stream.
        </p>
      </div>

      {(!hasValidSelection || selectorOpen) && (
        <Card className="bg-stone-50 dark:bg-gray-800 border-stone-200 dark:border-gray-700">
          <CardContent className="space-y-4 p-4">
            <div className="flex flex-wrap items-start justify-between gap-3">
              <div className="space-y-1">
                <div className="text-sm font-semibold text-slate-900 dark:text-white">
                  Guided model picker
                </div>
                <p className="text-sm text-slate-500 dark:text-gray-400">
                  Pick models that have actually been benchmarked together before. Search stays local to the guided candidates.
                </p>
              </div>
              {hasValidSelection && (
                <Button
                  type="button"
                  variant="outline"
                  className="border-stone-300 dark:border-gray-600"
                  onClick={() => {
                    setDraftModelIds(searchState.modelIds);
                    setSelectorOpen(false);
                  }}
                >
                  Cancel
                </Button>
              )}
            </div>

            <div className="flex flex-wrap items-center gap-3">
              <Input
                value={modelSearch}
                onChange={(event) => setModelSearch(event.target.value)}
                placeholder="Filter guided candidates by name, provider, or model ID"
                className="min-w-[220px] flex-1 bg-white dark:bg-gray-900"
                disabled={guidedPickerLocked}
              />
              <Badge
                variant="outline"
                className="border-stone-300 text-slate-700 dark:border-gray-600 dark:text-gray-200"
              >
                {draftModelIds.length}/{MAX_QUESTION_BROWSER_MODELS} selected
              </Badge>
              <Badge
                variant="outline"
                className="border-stone-300 text-slate-700 dark:border-gray-600 dark:text-gray-200"
              >
                {guidedPickerState?.modeLabel ?? buildGuidedPickerModeLabel(selectedDraftLabels.map((selectedModel) => selectedModel.label))}
              </Badge>
            </div>

            {guidedPickerLocked && (
              <div className="rounded-lg border border-stone-200 bg-stone-100 px-4 py-3 text-sm text-slate-600 dark:border-gray-700 dark:bg-gray-900/70 dark:text-gray-300">
                {MAX_QUESTION_BROWSER_MODELS} selected. Remove one to explore more candidates.
              </div>
            )}


            <div className="flex flex-wrap gap-2">
              {selectedDraftLabels.map((selectedModel) => (
                <Button
                  key={`guided-${selectedModel.id}`}
                  type="button"
                  variant="secondary"
                  title={selectedModel.title || selectedModel.label}
                  className="h-auto bg-stone-200 px-3 py-1 text-slate-700 hover:bg-stone-300 dark:bg-gray-700 dark:text-gray-200 dark:hover:bg-gray-600"
                  onClick={() => {
                    const nextState = applyGuidedPickerToggle(draftModelIds, selectedModel.id, modelSearch);
                    setDraftModelIds(nextState.nextModelIds);
                    if (nextState.nextSearch !== modelSearch) {
                      setModelSearch(nextState.nextSearch);
                    }
                  }}
                >
                  {selectedModel.label} ×
                </Button>
              ))}
            </div>

            {!guidedPickerLocked && guidanceQuery.error && (
              <ErrorBanner
                message={getErrorMessage(guidanceQuery.error, 'Failed to load guided candidates for the browser picker.')}
                onRetry={() => {
                  void guidanceQuery.refetch();
                }}
              />
            )}

            {!guidedPickerLocked && !guidanceQuery.error && guidanceQuery.isLoading && (
              <div className="rounded-lg border border-dashed border-stone-300 px-4 py-6 text-sm text-slate-500 dark:border-gray-700 dark:text-gray-400">
                Loading guided model picker…
              </div>
            )}

            {!guidedPickerLocked && !guidanceQuery.error && !guidanceQuery.isLoading && guidedPickerState && (
              <div className="grid gap-2 md:grid-cols-2">
                {guidedPickerState.visibleCandidates.map((candidate) => {
                  const checked = draftModelIds.includes(candidate.model_preset_id);
                  const disabled = !checked && !candidate.selectable;
                  return (
                    <label
                      key={candidate.model_preset_id}
                      className={`flex items-start gap-3 rounded-xl border px-3 py-3 transition-colors ${
                        checked
                          ? 'border-cyan-500 bg-cyan-50 dark:border-cyan-500/80 dark:bg-cyan-950/30'
                          : 'border-stone-200 bg-white hover:border-stone-300 dark:border-gray-700 dark:bg-gray-900/70 dark:hover:border-gray-600'
                      } ${disabled ? 'cursor-not-allowed opacity-60' : 'cursor-pointer'}`}
                    >
                      <Checkbox
                        checked={checked}
                        disabled={disabled}
                        onCheckedChange={() => {
                          const nextState = applyGuidedPickerToggle(
                            draftModelIds,
                            candidate.model_preset_id,
                            modelSearch,
                          );
                          setDraftModelIds(nextState.nextModelIds);
                          if (nextState.nextSearch !== modelSearch) {
                            setModelSearch(nextState.nextSearch);
                          }
                        }}
                        className="mt-0.5"
                      />
                      <div className="min-w-0 flex-1 space-y-1">
                        <div className="flex items-start justify-between gap-3">
                          <div className="min-w-0">
                            <div className="truncate text-sm font-medium text-slate-900 dark:text-white">
                              {candidate.resolved_label}
                            </div>
                            <div className="truncate text-xs text-slate-500 dark:text-gray-400">
                              {candidate.provider} · {candidate.model_id}
                            </div>
                            <div className="truncate text-xs text-slate-500 dark:text-gray-400">
                              {candidate.host_label}
                            </div>
                          </div>
                          <Badge variant="outline" className="border-stone-300 text-slate-700 dark:border-gray-600 dark:text-gray-200">
                            {candidate.active_benchmark_count} benchmark{candidate.active_benchmark_count === 1 ? '' : 's'}
                          </Badge>
                        </div>
                        <div className="flex flex-wrap gap-2">
                          <Badge variant="secondary" className="bg-stone-200 text-slate-700 dark:bg-gray-700 dark:text-gray-200">
                            {candidate.is_archived ? 'Archived' : 'Active'}
                          </Badge>
                          {!candidate.selectable && (
                            <Badge variant="outline" className="border-amber-300 text-amber-700 dark:border-amber-700 dark:text-amber-300">
                              Zero match
                            </Badge>
                          )}
                        </div>
                      </div>
                    </label>
                  );
                })}
              </div>
            )}

            {!guidedPickerLocked && !guidanceQuery.error && !guidanceQuery.isLoading && guidedPickerState && guidedPickerState.visibleCandidates.length === 0 && (
              <div className="rounded-lg border border-dashed border-stone-300 px-4 py-6 text-sm text-slate-500 dark:border-gray-700 dark:text-gray-400">
                No guided candidates matched that filter.
              </div>
            )}

            <div className="flex flex-wrap items-center justify-between gap-3 border-t border-stone-200 pt-3 dark:border-gray-700">
              <p className="text-sm text-slate-500 dark:text-gray-400">
                Pick 2 to {MAX_QUESTION_BROWSER_MODELS} models, then open the browser. You can come back here anytime to change the set.
              </p>
              <Button
                type="button"
                onClick={applyStandaloneSelection}
                disabled={!canApplyStandaloneSelection}
                className="bg-cyan-600 text-white hover:bg-cyan-700 dark:bg-cyan-500 dark:hover:bg-cyan-400"
              >
                {hasValidSelection ? 'Apply Models' : 'Open Browser'}
              </Button>
            </div>
          </CardContent>
        </Card>
      )}

      {hasValidSelection && (
        <Card className="bg-stone-50 dark:bg-gray-800 border-stone-200 dark:border-gray-700">
          <CardContent className="flex flex-col gap-4 p-4">
            <div className="flex flex-wrap items-start justify-between gap-4">
              <div className="space-y-2">
                <div className="text-sm font-medium text-slate-700 dark:text-gray-200">Selected models</div>
                <div className="flex flex-wrap gap-2">
                  {(railQuery.data?.selected_models ?? searchState.modelIds.map((modelId) => ({
                    model_preset_id: modelId,
                    resolved_label: `Model ${modelId}`,
                    match_mode: searchState.matchMode,
                    match_identity: {},
                    match_fidelity: 'full' as const,
                    source_run_id: searchState.sourceRunId,
                    source_question_id: searchState.sourceQuestionId,
                  }))).map((selectedModel) => (
                    <Badge
                      key={`${selectedModel.model_preset_id}-${selectedModel.resolved_label}`}
                      variant="secondary"
                      className="bg-stone-200 text-slate-700 dark:bg-gray-700 dark:text-gray-200"
                    >
                      {selectedModel.resolved_label}
                    </Badge>
                  ))}
                </div>
              </div>

              <div className="flex flex-wrap items-center gap-2 text-sm">
                <Badge
                  variant="outline"
                  className="border-stone-300 text-slate-700 dark:border-gray-600 dark:text-gray-200"
                >
                  Match: {searchState.matchMode === 'strict' ? 'Strict' : 'Same label'}
                </Badge>
                <Badge
                  variant="outline"
                  className="border-stone-300 text-slate-700 dark:border-gray-600 dark:text-gray-200"
                >
                  Benchmarks: {explorerState.groups.length}
                </Badge>
                <Badge
                  variant="outline"
                  className="border-stone-300 text-slate-700 dark:border-gray-600 dark:text-gray-200"
                >
                  Questions: {railQuery.data?.total_count ?? 0}
                </Badge>
                {searchState.sourceRunId != null && (
                  <Badge
                    variant="outline"
                    className="border-stone-300 text-slate-700 dark:border-gray-600 dark:text-gray-200"
                  >
                    Source run #{searchState.sourceRunId}
                  </Badge>
                )}
                <Button
                  type="button"
                  variant="outline"
                  className="border-stone-300 dark:border-gray-600"
                  onClick={() => setSelectorOpen(true)}
                >
                  Edit Models
                </Button>
              </div>
            </div>

            {railQuery.data && railQuery.data.strict_excluded_count > 0 && (
              <div className="flex items-start gap-3 rounded-lg border border-amber-200 bg-amber-50 px-4 py-3 text-sm text-amber-800 dark:border-amber-800 dark:bg-amber-950/30 dark:text-amber-200">
                <AlertTriangle className="mt-0.5 h-4 w-4 shrink-0" />
                <span>
                  Strict matching excluded {railQuery.data.strict_excluded_count} run
                  {railQuery.data.strict_excluded_count === 1 ? '' : 's'} because historical model signatures were too incomplete to trust.
                </span>
              </div>
            )}

          </CardContent>
        </Card>
      )}

      {hasValidSelection && railQuery.error && (
        <ErrorBanner
          message={getErrorMessage(railQuery.error, 'Failed to load matching questions.')}
          onRetry={() => {
            void railQuery.refetch();
          }}
        />
      )}

      {hasValidSelection && !railQuery.error && (
        <div className="grid gap-4 lg:grid-cols-[360px_minmax(0,1fr)] xl:grid-cols-[380px_minmax(0,1fr)]">
          <div className="lg:sticky lg:top-[89px] lg:self-start">
            <QuestionRail
              groups={explorerState.groups}
              expandedRunIds={expandedRunIds}
              totalCount={railQuery.data?.total_count ?? 0}
              isLoading={railQuery.isLoading}
              isFetching={railQuery.isFetching}
              onSelectQuestion={(questionId) => updateSearchState({ questionId }, { state: null })}
              onToggleRun={toggleRunExpansion}
              previousQuestionId={previousQuestionId}
              nextQuestionId={nextQuestionId}
            />
          </div>

          <div className="min-w-0">
            {autoFallbackNotice && (
              <div className="mb-4 flex flex-wrap items-center gap-3 rounded-lg border border-amber-200 bg-amber-50 px-4 py-3 text-sm text-amber-800 dark:border-amber-800 dark:bg-amber-950/30 dark:text-amber-200">
                <span>
                  The requested question no longer matched these filters. Switched to the first available match automatically.
                </span>
              </div>
            )}

            <QuestionDetailPane
              detail={detailQuery.data ?? null}
              isLoading={detailQuery.isLoading}
              errorMessage={staleSelectionCanAutoRecover ? null : detailErrorMessage}
              emptyMessage={
                railQuery.isLoading
                  ? 'Loading matching questions…'
                  : 'No matching question selected yet.'
              }
              modelOrder={modelOrder}
              windowStart={windowStart}
              onModelOrderChange={setModelOrder}
              onWindowStartChange={setWindowStart}
              modelIdToLabel={modelIdToLabel}
            />
          </div>
        </div>
      )}
    </div>
  );
}
