import { useState } from 'react';
import { ChevronLeft, ChevronRight } from 'lucide-react';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import { AnswerCard } from './AnswerCard';
import { buildPromptPreview } from './promptPreview';
import { buildPerQuestionInsightBadges } from './viewModel';
import { WINDOW_SIZE, shouldShowWindowControls, moveModel } from './windowHelpers';
import type { QuestionBrowserDetailResponse } from '@/types/api';

interface QuestionDetailPaneProps {
  detail: QuestionBrowserDetailResponse | null;
  isLoading: boolean;
  errorMessage: string | null;
  emptyMessage: string | null;
  modelOrder: number[];
  windowStart: number;
  onModelOrderChange: (order: number[]) => void;
  onWindowStartChange: (start: number) => void;
  modelIdToLabel: Map<number, string>;
}

function shouldCollapse(content: string | null | undefined): boolean {
  if (!content) {
    return false;
  }

  return content.length > 320 || content.split('\n').length > 6;
}

function PromptPreviewBlock({
  title,
  content,
}: {
  title: string;
  content: string | null | undefined;
}) {
  const [expanded, setExpanded] = useState(false);

  if (!content) {
    return null;
  }

  return (
    <div className="rounded-lg border border-amber-200/70 bg-amber-50/70 p-3 dark:border-amber-900/40 dark:bg-amber-950/10">
      <div className="flex items-start justify-between gap-3">
        <div className="text-sm font-medium text-slate-700 dark:text-gray-200">{title}</div>
        <Button type="button" variant="ghost" size="sm" className="h-auto px-2 py-1 text-xs" onClick={() => setExpanded((value) => !value)}>
          {expanded ? 'Show less' : 'Show full'}
        </Button>
      </div>
      <pre className="mt-2 whitespace-pre-wrap text-sm text-slate-700 dark:text-gray-200">
        {expanded ? content : buildPromptPreview(content)}
      </pre>
    </div>
  );
}

function PromptBlock({
  title,
  content,
  defaultCollapsed = false,
}: {
  title: string;
  content: string | null | undefined;
  defaultCollapsed?: boolean;
}) {
  if (!content) {
    return null;
  }

  if (defaultCollapsed) {
    return (
      <details className="rounded-lg border border-amber-200/70 bg-amber-50/70 p-3 dark:border-amber-900/40 dark:bg-amber-950/10">
        <summary className="cursor-pointer text-sm font-medium text-slate-700 dark:text-gray-200">
          {title}
        </summary>
        <pre className="mt-3 whitespace-pre-wrap text-sm text-slate-700 dark:text-gray-200">
          {content}
        </pre>
      </details>
    );
  }

  return (
    <div className="rounded-lg border border-amber-200/70 bg-amber-50/70 p-3 dark:border-amber-900/40 dark:bg-amber-950/10">
      <div className="text-sm font-medium text-slate-700 dark:text-gray-200">{title}</div>
      <pre className="mt-2 whitespace-pre-wrap text-sm text-slate-700 dark:text-gray-200">
        {content}
      </pre>
    </div>
  );
}

function getCardsGridClass(cardCount: number): string {
  if (cardCount <= 2) {
    return 'md:grid-cols-2';
  }

  if (cardCount === 3) {
    return 'md:grid-cols-2 xl:grid-cols-3';
  }

  return 'md:grid-cols-2 2xl:grid-cols-4';
}

export function QuestionDetailPane({
  detail,
  isLoading,
  errorMessage,
  emptyMessage,
  modelOrder,
  windowStart,
  onModelOrderChange,
  onWindowStartChange,
  modelIdToLabel,
}: QuestionDetailPaneProps) {
  if (isLoading) {
    return (
      <Card className="bg-stone-50 dark:bg-gray-800 border-stone-200 dark:border-gray-700">
        <CardContent className="p-6 text-sm text-slate-500 dark:text-gray-400">
          Loading question detail…
        </CardContent>
      </Card>
    );
  }

  if (errorMessage) {
    return (
      <Card className="bg-stone-50 dark:bg-gray-800 border-stone-200 dark:border-gray-700">
        <CardContent className="p-6 text-sm text-red-600 dark:text-red-400">
          {errorMessage}
        </CardContent>
      </Card>
    );
  }

  if (!detail) {
    return (
      <Card className="bg-stone-50 dark:bg-gray-800 border-stone-200 dark:border-gray-700">
        <CardContent className="p-6 text-sm text-slate-500 dark:text-gray-400">
          {emptyMessage ?? 'Select a question from the rail to inspect it here.'}
        </CardContent>
      </Card>
    );
  }

  const visibleModelIds = modelOrder.length > 0
    ? modelOrder.slice(windowStart, windowStart + WINDOW_SIZE)
    : detail.cards.map((c) => c.model_preset_id);
  const visibleCards = visibleModelIds.map((modelId) => {
    const card = detail.cards.find((c) => c.model_preset_id === modelId);
    return { modelId, card: card ?? null };
  });

  const handleMoveModel = (modelId: number, direction: -1 | 1) => {
    const result = moveModel(modelOrder, modelId, direction, windowStart);
    onModelOrderChange(result.newOrder);
    if (result.newWindowStart !== windowStart) {
      onWindowStartChange(result.newWindowStart);
    }
  };

  const insightBadgesByModel = detail ? buildPerQuestionInsightBadges(detail.cards) : {};

  return (
    <div className="space-y-4">
      <Card className="bg-stone-50 dark:bg-gray-800 border-stone-200 dark:border-gray-700">
        <CardHeader className="pb-4">
          <CardTitle className="text-xl">
            {detail.run_name} · Question {detail.question_order + 1}
          </CardTitle>
          <p className="text-sm text-slate-500 dark:text-gray-400">
            {detail.cards.length} selected model{detail.cards.length === 1 ? '' : 's'} on this question instance
          </p>
        </CardHeader>
        <CardContent className="space-y-3">
          <PromptPreviewBlock title="User Prompt" content={detail.user_prompt} />
          <PromptBlock
            title="System Prompt"
            content={detail.system_prompt}
            defaultCollapsed={shouldCollapse(detail.system_prompt) || Boolean(detail.system_prompt)}
          />
          <PromptBlock
            title="Expected Answer"
            content={detail.expected_answer}
            defaultCollapsed={true}
          />
        </CardContent>
      </Card>

      {shouldShowWindowControls(modelOrder.length) && (
        <div className="flex items-center justify-between rounded-lg border border-stone-200 bg-stone-50 px-4 py-2 dark:border-gray-700 dark:bg-gray-800">
          <div className="text-sm text-slate-600 dark:text-gray-300">
            Showing {windowStart + 1}–{Math.min(windowStart + WINDOW_SIZE, modelOrder.length)} of {modelOrder.length} models
          </div>
          <div className="flex items-center gap-2">
            <Button
              type="button"
              variant="outline"
              size="sm"
              disabled={windowStart === 0}
              onClick={() => onWindowStartChange(Math.max(0, windowStart - 1))}
              className="border-stone-300 dark:border-gray-600"
            >
              <ChevronLeft className="h-4 w-4" />
            </Button>
            <Button
              type="button"
              variant="outline"
              size="sm"
              disabled={windowStart + WINDOW_SIZE >= modelOrder.length}
              onClick={() => onWindowStartChange(Math.min(modelOrder.length - WINDOW_SIZE, windowStart + 1))}
              className="border-stone-300 dark:border-gray-600"
            >
              <ChevronRight className="h-4 w-4" />
            </Button>
          </div>
        </div>
      )}

      <div className={`grid grid-cols-1 gap-4 ${getCardsGridClass(visibleCards.length)}`}>
        {visibleCards.map(({ modelId, card }) => (
          card ? (
            <AnswerCard
              key={`${detail.question_id}-${modelId}-${card.source_run_id}-${card.source_run_name}`}
              card={card}
              canMoveLeft={modelOrder.indexOf(modelId) > 0}
              canMoveRight={modelOrder.indexOf(modelId) < modelOrder.length - 1}
              onMoveLeft={() => handleMoveModel(modelId, -1)}
              onMoveRight={() => handleMoveModel(modelId, 1)}
              insightBadges={insightBadgesByModel[modelId] ?? []}
            />
          ) : (
            <Card key={`placeholder-${modelId}`} className="flex h-full flex-col border-stone-200 bg-stone-50 dark:border-gray-700 dark:bg-gray-800">
              <CardHeader className="pb-4">
                <CardTitle className="text-lg leading-tight">
                  {modelIdToLabel.get(modelId) ?? `Model ${modelId}`}
                </CardTitle>
              </CardHeader>
              <CardContent className="flex flex-1 items-center justify-center p-6">
                <p className="text-sm text-slate-500 dark:text-gray-400">No data for this question</p>
              </CardContent>
            </Card>
          )
        ))}
      </div>
    </div>
  );
}
