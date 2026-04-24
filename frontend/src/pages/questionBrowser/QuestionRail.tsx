import { useEffect, useRef } from 'react';
import { ChevronDown, ChevronLeft, ChevronRight } from 'lucide-react';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import { cn } from '@/lib/utils';
import type { QuestionBrowserExplorerGroup } from './explorerState';

interface QuestionRailProps {
  groups: QuestionBrowserExplorerGroup[];
  expandedRunIds: number[];
  totalCount: number;
  isLoading: boolean;
  isFetching: boolean;
  onSelectQuestion: (questionId: number) => void;
  onToggleRun: (runId: number) => void;
  previousQuestionId: number | null;
  nextQuestionId: number | null;
}

export function QuestionRail({
  groups,
  expandedRunIds,
  totalCount,
  isLoading,
  isFetching,
  onSelectQuestion,
  onToggleRun,
  previousQuestionId,
  nextQuestionId,
}: QuestionRailProps) {
  const activeQuestionRef = useRef<HTMLButtonElement | null>(null);
  const activeQuestionIds = groups.flatMap((group) => group.questions.filter((question) => question.isActive).map((question) => question.question_id));

  useEffect(() => {
    if (!activeQuestionRef.current) {
      return;
    }

    activeQuestionRef.current.scrollIntoView({
      block: 'nearest',
      behavior: 'smooth',
    });
  }, [activeQuestionIds.join(','), expandedRunIds.join(',')]);

  return (
    <Card className="bg-stone-50 dark:bg-gray-800 border-stone-200 dark:border-gray-700">
      <CardHeader className="pb-3">
        <div className="flex items-center justify-between gap-3">
          <div className="min-w-0">
            <CardTitle className="text-base">Benchmarks</CardTitle>
            <p className="mt-1 text-sm text-slate-500 dark:text-gray-400">
              {totalCount === 0 ? 'No matching questions yet' : `${groups.length} benchmarks • ${totalCount} questions`}
            </p>
          </div>
          {isFetching && !isLoading && (
            <span className="shrink-0 text-xs text-slate-500 dark:text-gray-400">Refreshing…</span>
          )}
        </div>
        {(previousQuestionId != null || nextQuestionId != null) && (
          <div className="mt-3 flex items-center gap-2">
            <Button
              type="button"
              variant="outline"
              size="sm"
              className="flex-1 border-stone-300 dark:border-gray-600"
              disabled={previousQuestionId == null}
              onClick={() => {
                if (previousQuestionId != null) onSelectQuestion(previousQuestionId);
              }}
            >
              <ChevronLeft className="mr-1 h-4 w-4" /> Prev
            </Button>
            <Button
              type="button"
              variant="outline"
              size="sm"
              className="flex-1 border-stone-300 dark:border-gray-600"
              disabled={nextQuestionId == null}
              onClick={() => {
                if (nextQuestionId != null) onSelectQuestion(nextQuestionId);
              }}
            >
              Next <ChevronRight className="ml-1 h-4 w-4" />
            </Button>
          </div>
        )}
      </CardHeader>
      <CardContent className="space-y-3">
        <div className="space-y-2 lg:max-h-[calc(100vh-17rem)] lg:overflow-y-auto lg:pr-1">
          {isLoading && (
            <div className="rounded-lg border border-dashed border-stone-300 bg-white/60 px-3 py-6 text-sm text-slate-500 dark:border-gray-700 dark:bg-gray-900/50 dark:text-gray-400">
              Loading matching benchmarks…
            </div>
          )}

          {!isLoading && groups.length === 0 && (
            <div className="rounded-lg border border-dashed border-stone-300 bg-white/60 px-3 py-6 text-sm text-slate-500 dark:border-gray-700 dark:bg-gray-900/50 dark:text-gray-400">
              No matching question instances for this model set.
            </div>
          )}

          {groups.map((group) => {
            const expanded = expandedRunIds.includes(group.runId);
            const activeQuestion = group.questions.find((question) => question.isActive) ?? null;
            const activeGroup = activeQuestion !== null;

            return (
              <section
                key={group.runId}
                className={cn(
                  'rounded-xl border transition-colors',
                  activeGroup
                    ? 'border-amber-400 bg-amber-50/70 dark:border-amber-600 dark:bg-amber-950/20'
                    : 'border-stone-200 bg-white dark:border-gray-700 dark:bg-gray-900/60',
                )}
              >
                <button
                  type="button"
                  onClick={() => onToggleRun(group.runId)}
                  className="flex w-full items-start gap-3 px-3 py-3 text-left"
                >
                  <span className="mt-0.5 text-slate-500 dark:text-gray-400">
                    {expanded ? <ChevronDown className="h-4 w-4" /> : <ChevronRight className="h-4 w-4" />}
                  </span>
                  <div className="min-w-0 flex-1">
                    <div className="flex items-start justify-between gap-3">
                      <div className="min-w-0">
                        <div className="truncate text-sm font-medium text-slate-900 dark:text-gray-100">
                          {group.runName}
                        </div>
                        <div className="text-xs text-slate-500 dark:text-gray-400">
                          {group.matchCount} matching question{group.matchCount === 1 ? '' : 's'}
                        </div>
                      </div>
                      <div className="flex items-center gap-2">
                      </div>
                    </div>
                    <p className="mt-2 line-clamp-1 text-sm text-slate-600 dark:text-gray-300">
                      {group.previewText}
                    </p>
                  </div>
                </button>

                {expanded && (
                  <div className="border-t border-stone-200 px-3 py-3 dark:border-gray-700">
                    <div className="space-y-1 border-l border-stone-200 pl-3 dark:border-gray-700">
                      {group.questions.map((question) => (
                        <button
                          key={question.question_id}
                          ref={question.isActive ? activeQuestionRef : null}
                          type="button"
                          onClick={() => onSelectQuestion(question.question_id)}
                          data-question-id={question.question_id}
                          data-testid={`qb-question-row-${question.question_id}`}
                          className={cn(
                            'w-full rounded-lg px-3 py-2 text-left transition-colors',
                            question.isActive
                              ? 'bg-amber-100 text-amber-950 dark:bg-amber-900/50 dark:text-amber-100'
                              : 'hover:bg-stone-100 dark:hover:bg-gray-800',
                          )}
                        >
                          <div className="flex items-start justify-between gap-3">
                            <div className="min-w-0">
                              <div className="text-xs font-medium uppercase tracking-wide text-slate-500 dark:text-gray-400">
                                Question {question.question_order + 1}
                              </div>
                              <p className="mt-1 line-clamp-2 text-sm text-slate-700 dark:text-gray-200">
                                {question.prompt_preview}
                              </p>
                            </div>
                          </div>
                        </button>
                      ))}
                    </div>
                  </div>
                )}
              </section>
            );
          })}
        </div>
      </CardContent>
    </Card>
  );
}
