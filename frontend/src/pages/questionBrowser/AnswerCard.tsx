import { useState } from 'react';
import ReactMarkdown from 'react-markdown';
import remarkGfm from 'remark-gfm';
import { ChevronDown, ChevronLeft, ChevronRight, MessageSquareQuote } from 'lucide-react';
import { useTheme } from '@/lib/theme';
import { getScoreBgColor, getScoreColor } from '@/lib/scoreColors';
import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { buildAnswerCardBadges, buildJudgeDetailContent, buildJudgeScoreTone, formatEstimatedCost, type PerQuestionInsightBadge } from './viewModel';
import type { QuestionBrowserAnswerCard as QuestionBrowserAnswerCardData } from '@/types/api';

interface AnswerCardProps {
  card: QuestionBrowserAnswerCardData;
  defaultJudgeDetailsOpen?: boolean;
  canMoveLeft?: boolean;
  canMoveRight?: boolean;
  onMoveLeft?: () => void;
  onMoveRight?: () => void;
  insightBadges?: PerQuestionInsightBadge[];
}

function rankClass(rank: number | null | undefined): string {
  if (rank == null) return 'text-slate-500 dark:text-gray-400';
  if (rank === 1) return 'text-amber-600 dark:text-amber-400 font-semibold';
  if (rank === 2) return 'text-slate-400 dark:text-slate-300';
  if (rank === 3) return 'text-orange-700 dark:text-orange-400';
  return 'text-slate-500 dark:text-gray-400';
}

function formatGrade(value: number | null): string {
  return value == null ? '—' : value.toFixed(2);
}

function formatLatency(latencyMs: number | null): string | null {
  if (latencyMs == null || !Number.isFinite(latencyMs) || latencyMs <= 0) {
    return null;
  }

  if (latencyMs >= 1000) {
    return `${(latencyMs / 1000).toFixed(1)} s`;
  }

  return `${Math.round(latencyMs)} ms`;
}

export function AnswerCard({
  card,
  defaultJudgeDetailsOpen = true,
  canMoveLeft,
  canMoveRight,
  onMoveLeft,
  onMoveRight,
  insightBadges = [],
}: AnswerCardProps) {
  const [judgeDetailsOpen, setJudgeDetailsOpen] = useState(defaultJudgeDetailsOpen);
  const { theme } = useTheme();
  const isDark = theme === 'dark';
  const badges = buildAnswerCardBadges({
    evaluationMode: card.evaluation_mode,
    tokens: card.tokens,
    tokensPerSecond: card.speed_tokens_per_second,
  });
  const latencyLabel = formatLatency(card.latency_ms);

  return (
    <Card className="flex h-full flex-col border-stone-200 bg-stone-50 dark:border-gray-700 dark:bg-gray-800">
      <CardHeader className="space-y-4 pb-4">
        <div className="space-y-1">
          <div className="flex items-start justify-between gap-2">
            <CardTitle className="text-lg leading-tight">{card.resolved_label}</CardTitle>
            {(onMoveLeft || onMoveRight) && (
              <div className="flex items-center gap-0.5 shrink-0">
                <Button
                  type="button"
                  variant="ghost"
                  size="sm"
                  className="h-6 w-6 p-0"
                  disabled={!canMoveLeft}
                  onClick={onMoveLeft}
                  title="Move left"
                >
                  <ChevronLeft className="h-3.5 w-3.5" />
                </Button>
                <Button
                  type="button"
                  variant="ghost"
                  size="sm"
                  className="h-6 w-6 p-0"
                  disabled={!canMoveRight}
                  onClick={onMoveRight}
                  title="Move right"
                >
                  <ChevronRight className="h-3.5 w-3.5" />
                </Button>
              </div>
            )}
          </div>
          <p className="text-sm text-slate-500 dark:text-gray-400">
            From {card.source_run_name}
          </p>
        </div>

        {(() => {
          const costFormatted = formatEstimatedCost(card.estimated_cost);
          return (
            <div className="flex flex-wrap gap-2">
              {badges.map((badge) => (
                <Badge
                  key={`${badge.kind}-${badge.label}`}
                  variant="secondary"
                  className="bg-stone-200 text-slate-700 dark:bg-gray-700 dark:text-gray-200"
                >
                  {badge.label}
                </Badge>
              ))}
              {latencyLabel && (
                <Badge
                  variant="secondary"
                  className="bg-stone-200 text-slate-700 dark:bg-gray-700 dark:text-gray-200"
                >
                  {latencyLabel}
                </Badge>
              )}
              {costFormatted && (
                <Badge
                  variant="secondary"
                  className={
                    costFormatted.isFree
                      ? 'bg-green-800/60 text-green-300 border-green-600/40'
                      : 'bg-stone-200 text-slate-700 dark:bg-gray-700 dark:text-gray-200'
                  }
                >
                  {costFormatted.isFree ? '🆓 Free' : costFormatted.label}
                </Badge>
              )}
            </div>
          );
        })()}

        {(() => {
          const showFreeFromCost = card.estimated_cost === 0;
          const filteredInsights = showFreeFromCost
            ? insightBadges.filter((b) => b.label !== 'Free')
            : insightBadges;
          if (filteredInsights.length === 0) return null;
          return (
            <div className="flex flex-wrap gap-2">
              {filteredInsights.map((badge) => (
                <span
                  key={badge.label}
                  className={`inline-flex items-center gap-1 rounded border px-2 py-0.5 text-xs font-medium ${badge.color}`}
                >
                  <span>{badge.icon}</span>
                  <span>{badge.label}</span>
                </span>
              ))}
            </div>
          );
        })()}

        <div className="grid gap-2 sm:grid-cols-2">
          <div className="rounded-lg border border-stone-200 bg-white/90 px-3 py-2 dark:border-gray-700 dark:bg-gray-900/70">
            <div className="flex items-baseline justify-between gap-2">
              <div className="text-[11px] uppercase tracking-wide text-slate-500 dark:text-gray-400">
                Run Grade
              </div>
              {card.run_rank != null && card.run_rank_total != null && (
                <div className={`text-[11px] font-mono ${rankClass(card.run_rank)}`}>
                  {card.run_rank}/{card.run_rank_total}
                </div>
              )}
            </div>
            <div
              className="mt-1 inline-flex rounded px-2 py-1 text-sm font-semibold"
              style={
                card.run_grade == null
                  ? undefined
                  : {
                      color: getScoreColor(card.run_grade, isDark),
                      backgroundColor: getScoreBgColor(card.run_grade, isDark),
                    }
              }
            >
              {formatGrade(card.run_grade)}
            </div>
          </div>
          <div className="rounded-lg border border-stone-200 bg-white/90 px-3 py-2 dark:border-gray-700 dark:bg-gray-900/70">
            <div className="flex items-baseline justify-between gap-2">
              <div className="text-[11px] uppercase tracking-wide text-slate-500 dark:text-gray-400">
                Question Grade
              </div>
              {card.question_rank != null && card.question_rank_total != null && (
                <div className={`text-[11px] font-mono ${rankClass(card.question_rank)}`}>
                  {card.question_rank}/{card.question_rank_total}
                </div>
              )}
            </div>
            <div
              className="mt-1 inline-flex rounded px-2 py-1 text-sm font-semibold"
              style={
                card.question_grade == null
                  ? undefined
                  : {
                      color: getScoreColor(card.question_grade, isDark),
                      backgroundColor: getScoreBgColor(card.question_grade, isDark),
                    }
              }
            >
              {formatGrade(card.question_grade)}
            </div>
          </div>
        </div>

      </CardHeader>

      <CardContent className="flex flex-1 flex-col gap-4 pt-0">
        <div className="flex-1 rounded-xl border border-sky-200/70 bg-sky-50/70 dark:border-sky-900/40 dark:bg-sky-950/20">
          <div className="border-b border-sky-200/70 px-4 py-3 text-xs font-medium uppercase tracking-wide text-slate-500 dark:border-sky-900/40 dark:text-gray-400">
            Answer
          </div>
          <div
            className="overflow-x-auto px-4 py-4 text-sm leading-7 text-slate-800 dark:text-gray-100
              [&_p]:my-0 [&_p]:mb-3
              [&_h1]:text-lg [&_h1]:font-bold [&_h1]:text-cyan-500 dark:[&_h1]:text-cyan-400 [&_h1]:mt-3 [&_h1]:mb-2
              [&_h2]:text-base [&_h2]:font-bold [&_h2]:text-cyan-500 dark:[&_h2]:text-cyan-400 [&_h2]:mt-3 [&_h2]:mb-2
              [&_h3]:text-sm [&_h3]:font-bold [&_h3]:text-cyan-400 dark:[&_h3]:text-cyan-300 [&_h3]:mt-2 [&_h3]:mb-1
              [&_strong]:font-semibold [&_em]:italic
              [&_ul]:list-disc [&_ul]:pl-5 [&_ul]:my-2 [&_ol]:list-decimal [&_ol]:pl-5 [&_ol]:my-2 [&_li]:my-1 [&_li>p]:m-0
              [&_a]:text-blue-600 dark:[&_a]:text-blue-400 [&_a]:underline
              [&_code]:rounded [&_code]:bg-white [&_code]:px-1 [&_code]:py-0.5 [&_code]:font-mono [&_code]:text-xs dark:[&_code]:bg-gray-800
              [&_pre]:overflow-x-auto [&_pre]:rounded-xl [&_pre]:bg-white [&_pre]:p-3 dark:[&_pre]:bg-gray-800
              [&_blockquote]:border-l-2 [&_blockquote]:border-cyan-500 [&_blockquote]:pl-3 [&_blockquote]:text-slate-500 dark:[&_blockquote]:text-gray-400 [&_blockquote]:my-2
              [&_table]:w-full [&_table]:my-2 [&_th]:text-cyan-500 dark:[&_th]:text-cyan-400 [&_th]:font-bold [&_th]:text-left [&_th]:pb-1 [&_th]:border-b [&_th]:border-stone-200 dark:[&_th]:border-gray-600
              [&_td]:py-1 [&_td]:pr-2 [&_tr]:border-b [&_tr]:border-stone-200 dark:[&_tr]:border-gray-700/50"
          >
            {card.answer_text ? (
              <ReactMarkdown remarkPlugins={[remarkGfm]}>
                {card.answer_text}
              </ReactMarkdown>
            ) : (
              <p className="text-sm text-slate-500 dark:text-gray-400">No final answer captured.</p>
            )}
          </div>
        </div>

        {card.judge_grades.length > 0 && (
          <div className="rounded-lg border border-violet-200/70 bg-violet-50/70 dark:border-violet-900/40 dark:bg-violet-950/20">
            <Button
              type="button"
              variant="ghost"
              className="flex w-full items-center justify-between rounded-lg px-3 py-2"
              onClick={() => setJudgeDetailsOpen((value) => !value)}
            >
              <span className="flex items-center gap-2 text-sm font-medium">
                <MessageSquareQuote className="h-4 w-4" />
                Judge Details
              </span>
              <span className="flex items-center gap-2 text-xs text-slate-500 dark:text-gray-400">
                {card.judge_grades.length} judge{card.judge_grades.length === 1 ? '' : 's'}
                {judgeDetailsOpen ? <ChevronDown className="h-4 w-4" /> : <ChevronRight className="h-4 w-4" />}
              </span>
            </Button>
            {judgeDetailsOpen && (
              <div className="space-y-3 border-t border-violet-200/70 px-3 py-3 dark:border-violet-900/40">
                {card.judge_grades.map((judgeGrade) => (
                  <div
                    key={`${judgeGrade.judge_preset_id}-${judgeGrade.judge_label}`}
                    className="rounded-lg bg-stone-100 px-3 py-3 text-sm text-slate-700 dark:bg-gray-800 dark:text-gray-200"
                  >
                    <div className="flex items-center justify-between gap-3">
                      <div className="font-medium">{judgeGrade.judge_label}</div>
                      <div
                        className="rounded px-2 py-1 text-xs font-semibold"
                        style={(() => {
                          const tone = buildJudgeScoreTone(judgeGrade.score);
                          return tone.hasTone
                            ? {
                                color: getScoreColor(tone.score!, isDark),
                                backgroundColor: getScoreBgColor(tone.score!, isDark),
                              }
                            : undefined;
                        })()}
                      >
                        Score {formatGrade(judgeGrade.score)}
                      </div>
                    </div>
                    <div className="mt-2 space-y-1">
                      <div className="text-[11px] uppercase tracking-wide text-slate-500 dark:text-gray-400">
                        Score rationale
                      </div>
                      <p className="text-sm leading-6 text-slate-700 dark:text-gray-200">
                        {buildJudgeDetailContent(judgeGrade).scoreRationaleText}
                      </p>
                    </div>
                    <div className="mt-3 space-y-1">
                      <div className="text-[11px] uppercase tracking-wide text-slate-500 dark:text-gray-400">
                        Comments
                      </div>
                      {judgeGrade.comments.length > 0 ? (
                        <ul className="list-disc space-y-1 pl-5 text-sm leading-6">
                          {judgeGrade.comments.map((comment, index) => (
                            <li key={`${judgeGrade.judge_preset_id}-${index}`}>{comment}</li>
                          ))}
                        </ul>
                      ) : (
                        <p className="text-sm text-slate-500 dark:text-gray-400">
                          No question-specific judge comments recorded.
                        </p>
                      )}
                    </div>
                  </div>
                ))}
              </div>
            )}
          </div>
        )}
      </CardContent>
    </Card>
  );
}
