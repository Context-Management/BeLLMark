import { useState } from 'react';
import ReactMarkdown from 'react-markdown';
import remarkGfm from 'remark-gfm';
import { Loader2, ChevronDown, ChevronRight, AlertTriangle } from 'lucide-react';
import { useNavigate } from 'react-router-dom';
import { Button } from '@/components/ui/button';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Checkbox } from '@/components/ui/checkbox';
import { ContextUsageBar } from '@/components/ui/context-usage-bar';
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/dialog';
import { Label } from '@/components/ui/label';
import { AttachmentList } from '@/components/ui/attachment-list';
import { getScoreColor, getScoreBgColor } from '@/lib/scoreColors';
import { useTheme } from '@/lib/theme';
import {
  buildQuestionBrowserLaunchHrefForSelection,
  getQuestionBrowserLaunchState,
} from '@/pages/questionBrowser/launch';
import { MAX_QUESTION_BROWSER_MODELS } from '@/pages/questionBrowser/queryState';
import { slugify, getScore, buildJudgeCommentDisplay } from './types';
import type { BenchmarkDetail } from './types';
import type { ComputedResultsData } from './computeResultsData';
import type { SectionId } from './useResultsNav';

interface QuestionDetailProps {
  benchmark: BenchmarkDetail;
  computed: ComputedResultsData;
  questionOrder: number;
  navigate: (section: SectionId) => void;
  onRetry?: (itemType: 'generation' | 'judgment', itemId: number) => void;
  retryingItem?: { type: string; id: number } | null;
  /** If set, auto-expand this model's generation (from deep-link) */
  expandedModel?: string;
}

function getFirstLine(content: string | null, tokens?: number): string {
  if (!content) {
    if (tokens && tokens > 100) {
      return `\u26a0 Thinking only (${tokens.toLocaleString()} tokens, no answer)`;
    }
    return 'No content';
  }
  // Strip markdown formatting for a clean preview
  const stripped = content.replace(/^#{1,6}\s+/gm, '').replace(/[*_`~]/g, '');
  const firstLine = stripped.split('\n').find(line => line.trim().length > 0) || 'No content';
  return firstLine.length > 120 ? firstLine.slice(0, 120) + '...' : firstLine;
}

function JudgeComments({
  judgments,
  modelPresetId,
}: {
  judgments: BenchmarkDetail['questions'][0]['judgments'];
  modelPresetId: number;
}) {
  const commentsData = judgments
    .map((j) => buildJudgeCommentDisplay(j, modelPresetId))
    .filter((display): display is NonNullable<typeof display> => display !== null)
    .filter((display) => display.comments.length > 0 || display.hasScoreRationale);

  if (commentsData.length === 0) return null;

  return (
    <div className="p-3 bg-stone-50 dark:bg-gray-800 rounded mt-2 text-xs">
      <div className="text-purple-600 dark:text-purple-400 font-medium mb-2">Judge Details:</div>
      <div className="space-y-3">
        {commentsData.map(({ judgeName, score, scoreRationale, comments }) => (
          <div key={judgeName} className="space-y-2">
            <div className="flex items-center gap-2">
              <div className="text-slate-400 dark:text-gray-500 text-[10px] uppercase tracking-wide">{judgeName}</div>
              <span className="px-1.5 py-0.5 rounded text-[10px] font-mono bg-stone-200 dark:bg-gray-700 text-slate-700 dark:text-gray-200">
                {score !== null ? score.toFixed(1) : '-'}
              </span>
            </div>
            <div className="space-y-1">
              <div className="text-[10px] uppercase tracking-wide text-slate-500 dark:text-gray-400">
                Score Rationale:
              </div>
              <div className="rounded border border-stone-200 dark:border-gray-700 bg-white dark:bg-gray-900 px-2 py-1 text-slate-700 dark:text-gray-200">
                {scoreRationale}
              </div>
            </div>
            <div className="space-y-1">
              {(comments || []).map((c, i) => (
                <div
                  key={i}
                  className={`flex items-start gap-1.5 px-2 py-1 rounded text-xs ${
                    c.sentiment === 'positive'
                      ? 'bg-green-100 dark:bg-green-900/30 text-green-700 dark:text-green-300 border border-green-700/30'
                      : 'bg-red-100 dark:bg-red-900/30 text-red-600 dark:text-red-300 border border-red-700/30'
                  }`}
                >
                  <span className="font-bold shrink-0 mt-px">
                    {c.sentiment === 'positive' ? '+' : '−'}
                  </span>
                  <span>{c.text}</span>
                </div>
              ))}
            </div>
          </div>
        ))}
      </div>
    </div>
  );
}

export function QuestionDetail({
  benchmark,
  // eslint-disable-next-line @typescript-eslint/no-unused-vars
  computed: _computed,
  questionOrder,
  navigate,
  onRetry,
  retryingItem,
  expandedModel,
}: QuestionDetailProps) {
  const q = benchmark.questions.find((question) => question.order === questionOrder);
  const routerNavigate = useNavigate();
  const { theme } = useTheme();
  const isDark = theme === 'dark';

  // Hooks must be called before any conditional return (React Rules of Hooks)
  const [expandedGens, setExpandedGens] = useState<Set<number>>(() => {
    if (!q || !expandedModel) return new Set();
    const gen = q.generations.find(g => slugify(g.model_name) === expandedModel);
    return gen ? new Set([gen.model_preset_id]) : new Set();
  });
  const [chooserQuestionId, setChooserQuestionId] = useState<number | null>(null);
  const [selectedModelIds, setSelectedModelIds] = useState<number[]>([]);

  if (!q) {
    return (
      <Card className="bg-stone-50 dark:bg-gray-800 border-stone-200 dark:border-gray-700">
        <CardContent className="p-6 text-center">
          <p className="text-slate-500 dark:text-gray-400 mb-4">Question not found.</p>
          <Button variant="outline" onClick={() => navigate('overview')}>
            Back to Overview
          </Button>
        </CardContent>
      </Card>
    );
  }

  const toggleGen = (modelPresetId: number) => {
    setExpandedGens(prev => {
      const next = new Set(prev);
      if (next.has(modelPresetId)) next.delete(modelPresetId);
      else next.add(modelPresetId);
      return next;
    });
  };

  const questionBrowserModelOptions = benchmark.model_ids
    .map((modelId) => ({
      id: modelId,
      label:
        q.generations.find((generation) => generation.model_preset_id === modelId)?.model_name ??
        `Model ${modelId}`,
    }))
    .filter((option, index, options) => options.findIndex((candidate) => candidate.id === option.id) === index);

  const questionBrowserLaunch = getQuestionBrowserLaunchState(
    questionBrowserModelOptions,
    benchmark.id,
    q.id,
    {
      runConfigSnapshot: benchmark.run_config_snapshot,
    },
  );
  const isModelChooserOpen = chooserQuestionId === q.id;

  const chooserSelectionCount = selectedModelIds.length;
  const canConfirmModelSelection = chooserSelectionCount >= 2 && chooserSelectionCount <= MAX_QUESTION_BROWSER_MODELS;

  const handleToggleChooserModel = (modelId: number, checked: boolean | 'indeterminate') => {
    setSelectedModelIds((current) => {
      const next = new Set(current);
      if (checked === true) {
        next.add(modelId);
      } else {
        next.delete(modelId);
      }

      return questionBrowserModelOptions
        .filter((option) => next.has(option.id))
        .map((option) => option.id);
    });
  };

  const handleLaunchQuestionBrowser = () => {
    if (questionBrowserLaunch.kind === 'navigate') {
      routerNavigate(questionBrowserLaunch.href);
      return;
    }

    if (questionBrowserLaunch.kind === 'choose-models') {
      setSelectedModelIds([]);
      setChooserQuestionId(q.id);
    }
  };

  const handleModelChooserOpenChange = (open: boolean) => {
    setChooserQuestionId(open ? q.id : null);
    if (!open) {
      setSelectedModelIds([]);
    }
  };

  const handleConfirmQuestionBrowserLaunch = () => {
    if (!canConfirmModelSelection) {
      return;
    }

    if (questionBrowserLaunch.kind !== 'choose-models') {
      return;
    }

    routerNavigate(
      buildQuestionBrowserLaunchHrefForSelection(
        selectedModelIds,
        benchmark.id,
        q.id,
        benchmark.run_config_snapshot,
      ),
    );
    setChooserQuestionId(null);
    setSelectedModelIds([]);
  };

  // Calculate min/max for this question's generations
  const successGens = q.generations.filter((g) => g.status === 'success');
  const tokenValues = successGens.map((g) => g.tokens).filter((t) => t > 0);
  const latencyValues = successGens.map((g) => g.latency_ms || 0).filter((l) => l > 0);
  const speedValues = successGens
    .filter((g) => g.latency_ms && g.latency_ms > 0)
    .map((g) => g.tokens / (g.latency_ms! / 1000));

  const minTokens = Math.min(...tokenValues) || 0;
  const maxTokens = Math.max(...tokenValues) || 1;
  const minLatency = Math.min(...latencyValues) || 0;
  const maxLatency = Math.max(...latencyValues) || 1;
  const minSpeed = Math.min(...speedValues) || 0;
  const maxSpeed = Math.max(...speedValues) || 1;

  const getTokenBadgeColor = (tokens: number) => {
    if (maxTokens === minTokens) return 'bg-gray-600';
    const ratio = (tokens - minTokens) / (maxTokens - minTokens);
    if (ratio > 0.7) return 'bg-amber-600/70 text-amber-200';
    if (ratio > 0.3) return 'bg-gray-600/70 text-gray-200';
    return 'bg-blue-600/70 text-blue-200';
  };

  const getLatencyBadgeColor = (latency: number) => {
    if (maxLatency === minLatency) return 'bg-gray-600';
    const ratio = (latency - minLatency) / (maxLatency - minLatency);
    if (ratio > 0.7) return 'bg-red-600/70 text-red-200';
    if (ratio > 0.3) return 'bg-yellow-600/70 text-yellow-200';
    return 'bg-green-600/70 text-green-200';
  };

  const getSpeedBadgeColor = (speed: number) => {
    if (maxSpeed === minSpeed) return 'bg-gray-600';
    const ratio = (speed - minSpeed) / (maxSpeed - minSpeed);
    if (ratio > 0.7) return 'bg-green-600/70 text-green-200';
    if (ratio > 0.3) return 'bg-yellow-600/70 text-yellow-200';
    return 'bg-red-600/70 text-red-200';
  };

  return (
    <Card className="bg-stone-50 dark:bg-gray-800 border-stone-200 dark:border-gray-700">
      <CardHeader>
        <div className="flex flex-col gap-3 md:flex-row md:items-start md:justify-between">
          <CardTitle>
            <span className="font-medium">Question {q.order + 1}:</span>{' '}
            <span className="text-slate-500 dark:text-gray-400 font-normal text-base">
              {q.user_prompt.substring(0, 100)}...
            </span>
          </CardTitle>
          {questionBrowserLaunch.kind !== 'hidden' && (
            <Button
              size="sm"
              variant="outline"
              onClick={handleLaunchQuestionBrowser}
              className="shrink-0 border-cyan-300 bg-cyan-50 text-cyan-900 hover:bg-cyan-100 dark:border-cyan-800 dark:bg-cyan-950/40 dark:text-cyan-100 dark:hover:bg-cyan-950/70"
            >
              Open Browser
            </Button>
          )}
        </div>
      </CardHeader>
      <CardContent className="space-y-4">
        {/* System Prompt */}
        <div>
          <div className="text-sm text-slate-500 dark:text-gray-400 mb-1">System Prompt:</div>
          <pre className="bg-white dark:bg-gray-900 p-2 rounded text-sm font-mono whitespace-pre-wrap overflow-x-auto m-0">
            {q.system_prompt}
          </pre>
        </div>

        {/* User Prompt */}
        <div>
          <div className="text-sm text-slate-500 dark:text-gray-400 mb-1">User Prompt:</div>
          <pre className="bg-white dark:bg-gray-900 p-2 rounded text-sm font-mono whitespace-pre-wrap overflow-x-auto m-0">
            {q.user_prompt}
          </pre>
        </div>

        {/* Context Usage */}
        {q.estimated_context_tokens && (
          <div>
            <ContextUsageBar used={q.estimated_context_tokens} />
          </div>
        )}

        {/* Attachments */}
        {q.attachments && q.attachments.length > 0 && (
          <div>
            <h5 className="text-sm font-medium text-slate-500 dark:text-gray-400 mb-2">Attachments</h5>
            <AttachmentList
              attachments={q.attachments.map((a) => ({
                id: a.id,
                filename: a.filename,
                mime_type: a.mime_type,
                size_bytes: 0,
                inherited: a.inherited,
              }))}
              showInherited={true}
            />
          </div>
        )}

        {/* Generations */}
        <div>
          <div className="text-sm text-green-600 dark:text-green-400 mb-2">Generations:</div>
          {q.generations.map((g) => {
            const speed =
              g.latency_ms && g.latency_ms > 0 ? g.tokens / (g.latency_ms / 1000) : null;
            const isExpanded = expandedGens.has(g.model_preset_id);

            return (
              <div
                key={`${q.id}-${g.model_preset_id}`}
                id={`gen-q${q.order}-${slugify(g.model_name)}`}
                className="mb-4 border border-stone-200 dark:border-gray-700 rounded-lg overflow-hidden"
              >
                {/* Generation header — always visible, clickable to expand/collapse */}
                <div
                  role="button"
                  tabIndex={0}
                  onClick={() => toggleGen(g.model_preset_id)}
                  onKeyDown={(e) => { if (e.key === 'Enter' || e.key === ' ') { e.preventDefault(); toggleGen(g.model_preset_id); } }}
                  className="w-full p-2 bg-stone-50 dark:bg-gray-800 flex justify-between items-center text-left cursor-pointer hover:bg-stone-100 dark:hover:bg-gray-750 transition-colors border-0"
                >
                  <div className="flex items-center gap-2 flex-wrap">
                    {isExpanded ? (
                      <ChevronDown className="w-4 h-4 text-slate-400 dark:text-gray-500 shrink-0" />
                    ) : (
                      <ChevronRight className="w-4 h-4 text-slate-400 dark:text-gray-500 shrink-0" />
                    )}
                    <span
                      className="text-green-600 dark:text-green-400 font-medium hover:text-green-700 dark:hover:text-green-300 cursor-pointer"
                      onClick={(e) => {
                        e.stopPropagation();
                        navigate(`model-${slugify(g.model_name)}` as SectionId);
                      }}
                    >
                      {g.model_name}
                    </span>
                    {g.status === 'success' ? (
                      <div className="flex items-center gap-1.5 flex-wrap">
                        <span
                          className={`px-2 py-0.5 rounded text-xs font-mono ${getTokenBadgeColor(g.tokens)}`}
                        >
                          {g.tokens.toLocaleString()} tok
                        </span>
                        {g.latency_ms && (
                          <span
                            className={`px-2 py-0.5 rounded text-xs font-mono ${getLatencyBadgeColor(g.latency_ms)}`}
                          >
                            {(g.latency_ms / 1000).toFixed(1)}s
                          </span>
                        )}
                        {speed !== null && (
                          <span
                            className={`px-2 py-0.5 rounded text-xs font-mono ${getSpeedBadgeColor(speed)}`}
                          >
                            {speed.toFixed(0)} t/s
                          </span>
                        )}
                        <span className="text-slate-400 dark:text-gray-500 mx-1">|</span>
                        {q.judgments
                          .filter(
                            (j) => j.status === 'success' && j.scores?.[g.model_preset_id]
                          )
                          .map((j) => {
                            const scores = j.scores[g.model_preset_id];
                            const validScores = Object.values(scores).filter(
                              (s): s is number => typeof s === 'number'
                            );
                            const avg =
                              validScores.length > 0
                                ? validScores.reduce((a, b) => a + b, 0) / validScores.length
                                : null;
                            if (avg === null) return null;
                            return (
                              <span
                                key={j.id}
                                className="px-2 py-0.5 rounded text-xs font-mono"
                                style={{
                                  color: getScoreColor(avg, isDark),
                                  backgroundColor: getScoreBgColor(avg, isDark),
                                }}
                                title={`${j.judge_name}: ${avg.toFixed(1)}`}
                              >
                                {avg.toFixed(1)}
                              </span>
                            );
                          })}
                        {/* Collapsed preview — first line of content */}
                        {!isExpanded && (
                          <span className="text-slate-400 dark:text-gray-500 text-xs ml-1 truncate max-w-[300px]">
                            {getFirstLine(g.content, g.tokens)}
                          </span>
                        )}
                      </div>
                    ) : (
                      <span className="text-red-600 dark:text-red-400 text-sm">
                        {g.status}: {g.error}
                      </span>
                    )}
                  </div>
                  {g.status === 'failed' && onRetry && (
                    <Button
                      size="sm"
                      variant="outline"
                      onClick={(e) => {
                        e.stopPropagation();
                        onRetry('generation', g.id);
                      }}
                      disabled={retryingItem !== null}
                    >
                      {retryingItem?.type === 'generation' && retryingItem?.id === g.id ? (
                        <>
                          <Loader2 className="h-4 w-4 animate-spin mr-1" /> Retrying...
                        </>
                      ) : (
                        'Retry'
                      )}
                    </Button>
                  )}
                </div>

                {/* Expandable content */}
                {isExpanded && (
                  <>
                    {/* Generation content */}
                    <div
                      className="p-3 bg-stone-200 dark:bg-gray-700 text-sm overflow-x-auto whitespace-pre-wrap text-slate-800 dark:text-gray-200 leading-tight
                        [&_p]:m-0 [&_p]:mb-1
                        [&_strong]:text-amber-700 dark:[&_strong]:text-amber-300 [&_strong]:font-bold
                        [&_em]:text-blue-600 dark:[&_em]:text-blue-300
                        [&_code]:text-green-600 dark:[&_code]:text-green-400 [&_code]:bg-stone-50 dark:[&_code]:bg-gray-800 [&_code]:px-1 [&_code]:rounded [&_code]:font-mono [&_code]:text-xs
                        [&_pre]:bg-stone-50 dark:[&_pre]:bg-gray-800 [&_pre]:p-2 [&_pre]:rounded [&_pre]:border [&_pre]:border-stone-200 dark:[&_pre]:border-gray-600 [&_pre]:my-1 [&_pre]:font-mono
                        [&_h1]:text-lg [&_h1]:font-bold [&_h1]:text-cyan-400 [&_h1]:mt-2 [&_h1]:mb-0
                        [&_h2]:text-base [&_h2]:font-bold [&_h2]:text-cyan-400 [&_h2]:mt-2 [&_h2]:mb-0
                        [&_h3]:text-sm [&_h3]:font-bold [&_h3]:text-cyan-300 [&_h3]:mt-1 [&_h3]:mb-0
                        [&_ul]:list-disc [&_ul]:pl-5 [&_ul]:my-0 [&_ol]:list-decimal [&_ol]:pl-5 [&_ol]:my-0 [&_li]:my-0 [&_li>p]:m-0
                        [&_a]:text-blue-600 dark:[&_a]:text-blue-400 [&_a]:underline
                        [&_blockquote]:border-l-2 [&_blockquote]:border-cyan-500 [&_blockquote]:pl-3 [&_blockquote]:text-slate-500 dark:[&_blockquote]:text-gray-400 [&_blockquote]:my-1
                        [&_table]:w-full [&_table]:my-1 [&_th]:text-cyan-400 [&_th]:font-bold [&_th]:text-left [&_th]:pb-1 [&_th]:border-b [&_th]:border-stone-200 dark:[&_th]:border-gray-600
                        [&_td]:py-0.5 [&_td]:pr-2 [&_tr]:border-b [&_tr]:border-stone-200 dark:[&_tr]:border-gray-700/50"
                    >
                      {!g.content && g.tokens > 100 ? (
                        <div className="flex items-center gap-2 text-amber-600 dark:text-amber-400 py-2">
                          <AlertTriangle className="w-4 h-4 shrink-0" />
                          <span>
                            Model used {g.tokens.toLocaleString()} tokens on reasoning but produced no final answer.
                            This typically happens when a reasoning model exhausts its output token budget on thinking.
                          </span>
                        </div>
                      ) : (
                        <ReactMarkdown remarkPlugins={[remarkGfm]}>
                          {g.content || 'No content'}
                        </ReactMarkdown>
                      )}
                    </div>

                    {/* Per-judge score breakdown for this generation */}
                    {q.judgments.filter(
                      (j) => j.status === 'success' && j.scores?.[g.model_preset_id]
                    ).length > 0 && (
                      <div className="p-3 bg-stone-50 dark:bg-gray-800 mt-2 text-xs">
                        <div className="text-amber-600 dark:text-amber-400 font-medium mb-2">Judge Scores:</div>
                        <table className="w-full">
                          <thead>
                            <tr className="text-slate-400 dark:text-gray-500">
                              <th className="text-left pb-1">Judge</th>
                              {benchmark.criteria.map((c) => (
                                <th key={c.name} className="text-center pb-1 px-1">
                                  {c.name}
                                </th>
                              ))}
                              <th className="text-center pb-1">Avg</th>
                            </tr>
                          </thead>
                          <tbody>
                            {q.judgments
                              .filter(
                                (j) => j.status === 'success' && j.scores?.[g.model_preset_id]
                              )
                              .map((j) => {
                                const scores = j.scores[g.model_preset_id] || {};
                                const validScores = benchmark.criteria
                                  .map((c) => getScore(scores, c.name))
                                  .filter((s): s is number => typeof s === 'number');
                                const avg =
                                  validScores.length > 0
                                    ? validScores.reduce((a, b) => a + b, 0) / validScores.length
                                    : null;
                                return (
                                  <tr key={j.id} className="border-t border-stone-200 dark:border-gray-700">
                                    <td className="text-slate-500 dark:text-gray-400 py-1">{j.judge_name}</td>
                                    {benchmark.criteria.map((c) => {
                                      const score = getScore(scores, c.name);
                                      return (
                                        <td
                                          key={c.name}
                                          className="text-center px-1 rounded"
                                          style={{
                                            color:
                                              score !== undefined ? getScoreColor(score, isDark) : undefined,
                                            backgroundColor:
                                              score !== undefined ? getScoreBgColor(score, isDark) : undefined,
                                          }}
                                        >
                                          {score ?? '-'}
                                        </td>
                                      );
                                    })}
                                    <td
                                      className="text-center font-medium rounded"
                                      style={{
                                        color: avg !== null ? getScoreColor(avg, isDark) : undefined,
                                        backgroundColor:
                                          avg !== null ? getScoreBgColor(avg, isDark) : undefined,
                                      }}
                                    >
                                      {avg !== null ? avg.toFixed(1) : '-'}
                                    </td>
                                  </tr>
                                );
                              })}
                            <tr className="border-t-2 border-stone-300 dark:border-gray-600 font-medium">
                              <td className="text-slate-700 dark:text-gray-300 py-1">Average</td>
                              {benchmark.criteria.map((c) => {
                                const criterionScores = q.judgments
                                  .filter(
                                    (j) => j.status === 'success' && j.scores?.[g.model_preset_id]
                                  )
                                  .map((j) => getScore(j.scores[g.model_preset_id], c.name))
                                  .filter((s): s is number => typeof s === 'number');
                                const avg =
                                  criterionScores.length > 0
                                    ? criterionScores.reduce((a, b) => a + b, 0) /
                                      criterionScores.length
                                    : null;
                                return (
                                  <td
                                    key={c.name}
                                    className="text-center px-1 rounded"
                                    style={{
                                      color: avg !== null ? getScoreColor(avg, isDark) : undefined,
                                      backgroundColor: avg !== null ? getScoreBgColor(avg, isDark) : undefined,
                                    }}
                                  >
                                    {avg !== null ? avg.toFixed(1) : '-'}
                                  </td>
                                );
                              })}
                              <td></td>
                            </tr>
                          </tbody>
                        </table>
                      </div>
                    )}

                    {/* Judge comments */}
                    <JudgeComments judgments={q.judgments} modelPresetId={g.model_preset_id} />
                  </>
                )}
              </div>
            );
          })}
        </div>

        {/* Judgments */}
        <div>
          <div className="text-sm text-amber-600 dark:text-amber-400 mb-2">Judgments:</div>
          {q.judgments.map((j, i) => {
            const modelAvgScores: {
              model: string;
              avg: number;
              scores: Record<string, number>;
              modelId: number;
            }[] = [];
            const idToLabel: Record<number, string> = {};
            if (j.blind_mapping) {
              Object.entries(j.blind_mapping).forEach(([label, id]) => {
                idToLabel[id] = label;
              });
            }

            if (j.status === 'success' && j.scores) {
              Object.entries(j.scores).forEach(([modelId, criterionScores]) => {
                const gen = q.generations.find((g) => g.model_preset_id === Number(modelId));
                if (!gen) return;
                const validScores = benchmark.criteria
                  .map((c) => getScore(criterionScores as Record<string, number>, c.name))
                  .filter((s): s is number => typeof s === 'number');
                const avg =
                  validScores.length > 0
                    ? validScores.reduce((a, b) => a + b, 0) / validScores.length
                    : 0;
                modelAvgScores.push({
                  model: gen.model_name,
                  avg,
                  scores: criterionScores as Record<string, number>,
                  modelId: Number(modelId),
                });
              });
              modelAvgScores.sort((a, b) => b.avg - a.avg);
            }

            return (
              <div key={i} className="mb-3 p-3 bg-stone-50 dark:bg-gray-800 rounded">
                <div className="flex justify-between items-start mb-2">
                  <div className="font-medium text-amber-600 dark:text-amber-400">{j.judge_name}</div>
                  {j.status === 'failed' && onRetry && (
                    <Button
                      size="sm"
                      variant="outline"
                      onClick={() => onRetry('judgment', j.id)}
                      disabled={retryingItem !== null}
                    >
                      {retryingItem?.type === 'judgment' && retryingItem?.id === j.id ? (
                        <>
                          <Loader2 className="h-4 w-4 animate-spin mr-1" /> Retrying...
                        </>
                      ) : (
                        'Retry'
                      )}
                    </Button>
                  )}
                </div>
                {j.status === 'failed' && j.error && (
                  <div className="text-sm text-red-600 dark:text-red-400 mb-2">
                    {j.status}: {j.error}
                  </div>
                )}
                {/* 33% chart on left, 66% reasoning on right */}
                <div className="flex gap-4">
                  {modelAvgScores.length > 0 && (
                    <div className="w-1/3 space-y-1 flex-shrink-0">
                      {modelAvgScores.map((item, idx) => {
                        const blindLabel = idToLabel[item.modelId];
                        return (
                          <div key={item.model} className="flex items-center gap-2 text-xs">
                            {blindLabel && (
                              <span className="w-5 text-center text-blue-600 dark:text-blue-400 font-mono font-bold">
                                {blindLabel}
                              </span>
                            )}
                            <span
                              className={`w-28 truncate ${
                                idx === 0 ? 'text-yellow-400 font-bold' : 'text-slate-700 dark:text-gray-300'
                              }`}
                            >
                              {idx === 0 && '\uD83C\uDFC6 '}{item.model}
                            </span>
                            <div className="flex-1 h-4 bg-stone-200 dark:bg-gray-700 rounded overflow-hidden relative min-w-[60px]">
                              <div
                                className="h-full rounded transition-all"
                                style={{
                                  width: `${(item.avg / 10) * 100}%`,
                                  backgroundColor: getScoreColor(item.avg, isDark),
                                }}
                              />
                            </div>
                            <span
                              className="w-8 text-right font-mono font-bold"
                              style={{ color: getScoreColor(item.avg, isDark) }}
                            >
                              {item.avg.toFixed(1)}
                            </span>
                          </div>
                        );
                      })}
                    </div>
                  )}
                  {j.reasoning && (
                    <pre className="flex-1 text-sm text-slate-500 dark:text-gray-400 border-l-2 border-stone-300 dark:border-gray-600 pl-3 font-mono whitespace-pre-wrap overflow-x-auto m-0 bg-transparent">
                      {j.reasoning}
                    </pre>
                  )}
                </div>
              </div>
            );
          })}
        </div>

        <Dialog open={isModelChooserOpen} onOpenChange={handleModelChooserOpenChange}>
          <DialogContent className="bg-stone-50 dark:bg-gray-800 border-stone-200 dark:border-gray-700">
            <DialogHeader>
              <DialogTitle>Select Models for Cross-Benchmark Browsing</DialogTitle>
              <DialogDescription>
                Choose 2 to {MAX_QUESTION_BROWSER_MODELS} models from this run before opening the question browser.
              </DialogDescription>
            </DialogHeader>

            <div className="space-y-3">
              <div className="text-xs uppercase tracking-wide text-slate-500 dark:text-gray-400">
                {chooserSelectionCount} selected
              </div>
              <div className="space-y-2">
                {questionBrowserLaunch.kind === 'choose-models' && questionBrowserLaunch.options.map((option) => {
                  const checkboxId = `question-browser-model-${option.id}`;
                  return (
                    <div
                      key={option.id}
                      className="flex items-center gap-3 rounded-md border border-stone-200 bg-white px-3 py-2 dark:border-gray-700 dark:bg-gray-900"
                    >
                      <Checkbox
                        id={checkboxId}
                        checked={selectedModelIds.includes(option.id)}
                        onCheckedChange={(checked) => handleToggleChooserModel(option.id, checked)}
                      />
                      <Label htmlFor={checkboxId} className="cursor-pointer text-sm text-slate-700 dark:text-gray-200">
                        {option.label}
                      </Label>
                    </div>
                  );
                })}
              </div>
              <p className="text-xs text-slate-500 dark:text-gray-400">
                Confirm becomes available when 2 to {MAX_QUESTION_BROWSER_MODELS} models are selected.
              </p>
            </div>

            <DialogFooter>
              <Button variant="outline" onClick={() => handleModelChooserOpenChange(false)}>
                Cancel
              </Button>
              <Button onClick={handleConfirmQuestionBrowserLaunch} disabled={!canConfirmModelSelection}>
                Open Question Browser
              </Button>
            </DialogFooter>
          </DialogContent>
        </Dialog>
      </CardContent>
    </Card>
  );
}
