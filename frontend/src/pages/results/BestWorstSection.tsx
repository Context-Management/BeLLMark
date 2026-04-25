import { useState } from 'react';
import ReactMarkdown from 'react-markdown';
import remarkGfm from 'remark-gfm';
import { ChevronDown, ChevronRight, Trophy, ThumbsDown } from 'lucide-react';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import { getScoreColor, getScoreBgColor } from '@/lib/scoreColors';
import { useTheme } from '@/lib/theme';
import { getScore } from './types';
import type { BenchmarkDetail } from './types';
import type { RankedGeneration } from './computeResultsData';
import type { SectionId } from './useResultsNav';

interface BestWorstSectionProps {
  mode: 'best' | 'worst';
  generations: RankedGeneration[];
  benchmark: BenchmarkDetail;
  navigate: (section: SectionId) => void;
}

export function BestWorstSection({ mode, generations, benchmark, navigate }: BestWorstSectionProps) {
  const { theme } = useTheme();
  const isDark = theme === 'dark';
  const [expandedCards, setExpandedCards] = useState<Set<number>>(new Set());

  const toggleCard = (idx: number) => {
    setExpandedCards(prev => {
      const next = new Set(prev);
      if (next.has(idx)) next.delete(idx); else next.add(idx);
      return next;
    });
  };

  const isBest = mode === 'best';
  const title = isBest ? 'Best Answers' : 'Worst Answers';
  const Icon = isBest ? Trophy : ThumbsDown;
  const emptyMsg = 'No scored generations found.';

  if (generations.length === 0) {
    return (
      <Card className="bg-stone-50 dark:bg-gray-800 border-stone-200 dark:border-gray-700">
        <CardContent className="p-6 text-center">
          <p className="text-slate-500 dark:text-gray-400">{emptyMsg}</p>
        </CardContent>
      </Card>
    );
  }

  return (
    <Card className="bg-stone-50 dark:bg-gray-800 border-stone-200 dark:border-gray-700">
      <CardHeader>
        <CardTitle className="flex items-center gap-2">
          <Icon className="w-5 h-5" />
          {title}
        </CardTitle>
      </CardHeader>
      <CardContent className="space-y-4">
        {generations.map((gen, idx) => {
          const isExpanded = expandedCards.has(idx);
          const q = benchmark.questions.find(qq => qq.order === gen.questionOrder);
          const generation = q?.generations.find(g => g.model_preset_id === gen.modelPresetId);

          return (
            <div
              key={`${gen.questionOrder}-${gen.modelPresetId}`}
              className="border border-stone-200 dark:border-gray-700 rounded-lg overflow-hidden"
            >
              {/* Card header */}
              <div className="p-3 bg-white dark:bg-gray-900 flex items-center justify-between flex-wrap gap-2">
                <div className="flex items-center gap-2 flex-wrap">
                  <span className={`text-xs font-bold px-2 py-0.5 rounded ${
                    isBest
                      ? 'bg-yellow-100 dark:bg-yellow-900/30 text-yellow-700 dark:text-yellow-400'
                      : 'bg-red-100 dark:bg-red-900/30 text-red-600 dark:text-red-400'
                  }`}>
                    #{idx + 1}
                  </span>
                  <span className="text-green-600 dark:text-green-400 font-medium text-sm">
                    {gen.modelName}
                  </span>
                  <span className="text-slate-400 dark:text-gray-500 text-xs">on</span>
                  <Button
                    variant="link"
                    size="sm"
                    className="text-xs p-0 h-auto text-blue-600 dark:text-blue-400"
                    onClick={() => navigate(`question-${gen.questionOrder}` as SectionId)}
                  >
                    Q{gen.questionOrder + 1}
                  </Button>
                </div>
                <span
                  className="text-sm font-mono font-bold px-2 py-0.5 rounded"
                  style={{
                    color: getScoreColor(gen.weightedAvgScore, isDark),
                    backgroundColor: getScoreBgColor(gen.weightedAvgScore, isDark),
                  }}
                >
                  {gen.weightedAvgScore.toFixed(2)}
                </span>
              </div>

              {/* Question prompt */}
              <div className="px-3 py-2 bg-stone-50 dark:bg-gray-800 border-t border-stone-200 dark:border-gray-700">
                <div className="text-xs text-slate-400 dark:text-gray-500 mb-1">Question:</div>
                <p className="text-sm text-slate-700 dark:text-gray-300 line-clamp-2">
                  {gen.userPrompt}
                </p>
              </div>

              {/* Expandable response */}
              {generation && (
                <div className="border-t border-stone-200 dark:border-gray-700">
                  <button
                    onClick={() => toggleCard(idx)}
                    className="w-full flex items-center gap-2 px-3 py-2 text-xs text-slate-500 dark:text-gray-400 hover:bg-stone-100 dark:hover:bg-gray-750 transition-colors"
                  >
                    {isExpanded ? <ChevronDown className="w-3.5 h-3.5" /> : <ChevronRight className="w-3.5 h-3.5" />}
                    {isExpanded ? 'Hide' : 'Show'} Response ({generation.tokens.toLocaleString()} tokens)
                  </button>
                  {isExpanded && (
                    <div className="px-3 pb-3">
                      <div
                        className="p-3 bg-stone-200 dark:bg-gray-700 text-sm overflow-x-auto whitespace-pre-wrap text-slate-800 dark:text-gray-200 leading-tight rounded
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
                        <ReactMarkdown remarkPlugins={[remarkGfm]}>
                          {generation.content || 'No content'}
                        </ReactMarkdown>
                      </div>
                    </div>
                  )}
                </div>
              )}

              {/* Judge scores table */}
              <div className="px-3 py-2 border-t border-stone-200 dark:border-gray-700">
                <div className="text-xs text-amber-600 dark:text-amber-400 font-medium mb-2">Judge Scores:</div>
                <table className="w-full text-xs">
                  <thead>
                    <tr className="text-slate-400 dark:text-gray-500">
                      <th className="text-left pb-1">Judge</th>
                      {benchmark.criteria.map(c => (
                        <th key={c.name} className="text-center pb-1 px-1">{c.name}</th>
                      ))}
                      <th className="text-center pb-1">Avg</th>
                    </tr>
                  </thead>
                  <tbody>
                    {gen.perJudgeScores.map(judge => (
                      <tr key={judge.judgeName} className="border-t border-stone-200 dark:border-gray-700">
                        <td className="text-slate-500 dark:text-gray-400 py-1">{judge.judgeName}</td>
                        {benchmark.criteria.map(c => {
                          const score = getScore(judge.criterionScores, c.name);
                          return (
                            <td
                              key={c.name}
                              className="text-center px-1 rounded"
                              style={{
                                color: score !== undefined ? getScoreColor(score, isDark) : undefined,
                                backgroundColor: score !== undefined ? getScoreBgColor(score, isDark) : undefined,
                              }}
                            >
                              {score !== undefined ? (typeof score === 'number' ? score.toFixed(1) : score) : '-'}
                            </td>
                          );
                        })}
                        <td
                          className="text-center font-medium rounded"
                          style={{
                            color: getScoreColor(judge.avgScore, isDark),
                            backgroundColor: getScoreBgColor(judge.avgScore, isDark),
                          }}
                        >
                          {judge.avgScore.toFixed(1)}
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>

              {/* Judge comments */}
              {q && (() => {
                const judgeData = q.judgments
                  .filter(j => j.status === 'success')
                  .map(j => ({
                    judgeName: j.judge_name,
                    comments: j.comments?.[gen.modelPresetId] ?? [],
                    rationale: j.score_rationales?.[gen.modelPresetId] ?? '',
                  }))
                  .filter(d => d.comments.length > 0 || d.rationale);
                if (judgeData.length === 0) return null;
                return (
                  <div className="px-3 py-2 border-t border-stone-200 dark:border-gray-700">
                    <div className="text-xs text-purple-600 dark:text-purple-400 font-medium mb-2">Judge Comments:</div>
                    <div className="space-y-2">
                      {judgeData.map(({ judgeName, comments, rationale }) => (
                        <div key={judgeName}>
                          <div className="text-slate-400 dark:text-gray-500 text-[10px] uppercase tracking-wide mb-1">{judgeName}</div>
                          {comments.length > 0 && (
                            <div className="space-y-1">
                              {comments.map((c, i) => (
                                <div
                                  key={i}
                                  className={`flex items-start gap-1.5 px-2 py-1 rounded text-xs ${
                                    c.sentiment === 'positive'
                                      ? 'bg-green-100 dark:bg-green-900/30 text-green-700 dark:text-green-300 border border-green-700/30'
                                      : 'bg-red-100 dark:bg-red-900/30 text-red-600 dark:text-red-300 border border-red-700/30'
                                  }`}
                                >
                                  <span className="font-bold shrink-0 mt-px">
                                    {c.sentiment === 'positive' ? '+' : '\u2212'}
                                  </span>
                                  <span>{c.text}</span>
                                </div>
                              ))}
                            </div>
                          )}
                          {rationale && (
                            <pre className="mt-1 text-xs text-slate-500 dark:text-gray-400 whitespace-pre-wrap max-h-32 overflow-y-auto bg-stone-100 dark:bg-gray-900 p-2 rounded">
                              {rationale}
                            </pre>
                          )}
                        </div>
                      ))}
                    </div>
                  </div>
                );
              })()}

              {/* Link to full question */}
              <div className="px-3 py-2 border-t border-stone-200 dark:border-gray-700 bg-stone-50 dark:bg-gray-800">
                <Button
                  variant="link"
                  size="sm"
                  className="text-xs p-0 h-auto"
                  onClick={() => navigate(`question-${gen.questionOrder}` as SectionId)}
                >
                  View Full Question Detail &rarr;
                </Button>
              </div>
            </div>
          );
        })}
      </CardContent>
    </Card>
  );
}
