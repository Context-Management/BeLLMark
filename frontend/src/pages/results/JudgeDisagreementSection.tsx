import { useState } from 'react';
import ReactMarkdown from 'react-markdown';
import remarkGfm from 'remark-gfm';
import { ChevronDown, ChevronRight, Swords } from 'lucide-react';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import { getScoreColor, getScoreBgColor } from '@/lib/scoreColors';
import { useTheme } from '@/lib/theme';
import { getScore } from './types';
import type { BenchmarkDetail } from './types';
import type { DisagreementEntry } from './computeResultsData';
import type { SectionId } from './useResultsNav';

interface JudgeDisagreementSectionProps {
  disagreements: DisagreementEntry[];
  judgePair: [string, string] | null;
  pairAvgDelta: number;
  benchmark: BenchmarkDetail;
  navigate: (section: SectionId) => void;
}

export function JudgeDisagreementSection({
  disagreements,
  judgePair,
  pairAvgDelta,
  benchmark,
  navigate,
}: JudgeDisagreementSectionProps) {
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

  if (!judgePair || disagreements.length === 0) {
    const uniqueJudgeNames = new Set(
      benchmark.questions.flatMap(q =>
        q.judgments.filter(j => j.status === 'success').map(j => j.judge_name)
      )
    );
    const emptyMsg = uniqueJudgeNames.size < 2
      ? 'Need at least 2 judges with successful judgments to detect disagreement.'
      : 'No significant disagreements found between judges.';
    return (
      <Card className="bg-stone-50 dark:bg-gray-800 border-stone-200 dark:border-gray-700">
        <CardContent className="p-6 text-center">
          <p className="text-slate-500 dark:text-gray-400">{emptyMsg}</p>
        </CardContent>
      </Card>
    );
  }

  const [judgeA, judgeB] = judgePair;

  return (
    <Card className="bg-stone-50 dark:bg-gray-800 border-stone-200 dark:border-gray-700">
      <CardHeader>
        <CardTitle className="flex items-center gap-2">
          <Swords className="w-5 h-5" />
          Judge Disagreement
        </CardTitle>
        <div className="flex items-center gap-2 flex-wrap mt-1">
          <span className="text-sm text-slate-500 dark:text-gray-400">Most disagreeing pair:</span>
          <span className="text-sm font-medium text-amber-600 dark:text-amber-400">{judgeA}</span>
          <span className="text-sm text-slate-400 dark:text-gray-500">vs</span>
          <span className="text-sm font-medium text-amber-600 dark:text-amber-400">{judgeB}</span>
          <span className="text-xs px-2 py-0.5 rounded bg-red-100 dark:bg-red-900/30 text-red-600 dark:text-red-400 font-mono">
            avg delta: {pairAvgDelta.toFixed(2)} pts
          </span>
        </div>
      </CardHeader>
      <CardContent className="space-y-4">
        {disagreements.map((entry, idx) => {
          const isExpanded = expandedCards.has(idx);
          const q = benchmark.questions.find(qq => qq.order === entry.questionOrder);
          const generation = q?.generations.find(g => g.model_preset_id === entry.modelPresetId);
          const judgmentA = q?.judgments.find(j => j.judge_name === entry.judgeA && j.status === 'success');
          const judgmentB = q?.judgments.find(j => j.judge_name === entry.judgeB && j.status === 'success');

          return (
            <div
              key={`${entry.questionOrder}-${entry.modelPresetId}-${idx}`}
              className="border border-stone-200 dark:border-gray-700 rounded-lg overflow-hidden"
            >
              {/* Card header */}
              <div className="p-3 bg-white dark:bg-gray-900 flex items-center justify-between flex-wrap gap-2">
                <div className="flex items-center gap-2 flex-wrap">
                  <span className="text-xs font-bold px-2 py-0.5 rounded bg-red-100 dark:bg-red-900/30 text-red-600 dark:text-red-400">
                    #{idx + 1}
                  </span>
                  <span className="text-green-600 dark:text-green-400 font-medium text-sm">
                    {entry.modelName}
                  </span>
                  <span className="text-slate-400 dark:text-gray-500 text-xs">on</span>
                  <Button
                    variant="link"
                    size="sm"
                    className="text-xs p-0 h-auto text-blue-600 dark:text-blue-400"
                    onClick={() => navigate(`question-${entry.questionOrder}` as SectionId)}
                  >
                    Q{entry.questionOrder + 1}
                  </Button>
                  <span className="text-xs px-2 py-0.5 rounded bg-red-100 dark:bg-red-900/30 text-red-600 dark:text-red-400 font-mono">
                    &Delta; {entry.scoreDelta.toFixed(2)}
                  </span>
                </div>
              </div>

              {/* Score comparison bar */}
              <div className="px-3 py-2 bg-stone-50 dark:bg-gray-800 border-t border-stone-200 dark:border-gray-700">
                <div className="flex items-center gap-2 text-sm">
                  <span className="text-amber-600 dark:text-amber-400 font-medium truncate max-w-[120px]">{entry.judgeA}</span>
                  <span
                    className="px-2 py-0.5 rounded font-mono font-bold text-sm"
                    style={{
                      color: getScoreColor(entry.judgeAScore, isDark),
                      backgroundColor: getScoreBgColor(entry.judgeAScore, isDark),
                    }}
                  >
                    {entry.judgeAScore.toFixed(2)}
                  </span>
                  <span className="text-slate-400 dark:text-gray-500 text-xs px-1">vs</span>
                  <span
                    className="px-2 py-0.5 rounded font-mono font-bold text-sm"
                    style={{
                      color: getScoreColor(entry.judgeBScore, isDark),
                      backgroundColor: getScoreBgColor(entry.judgeBScore, isDark),
                    }}
                  >
                    {entry.judgeBScore.toFixed(2)}
                  </span>
                  <span className="text-amber-600 dark:text-amber-400 font-medium truncate max-w-[120px]">{entry.judgeB}</span>
                </div>
              </div>

              {/* Question prompt */}
              <div className="px-3 py-2 bg-stone-50 dark:bg-gray-800 border-t border-stone-200 dark:border-gray-700">
                <div className="text-xs text-slate-400 dark:text-gray-500 mb-1">Question:</div>
                <p className="text-sm text-slate-700 dark:text-gray-300 line-clamp-2">
                  {entry.userPrompt}
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

              {/* Side-by-side judge comparison */}
              {(judgmentA || judgmentB) && (
                <div className="border-t border-stone-200 dark:border-gray-700">
                  <div className="grid grid-cols-2 divide-x divide-stone-200 dark:divide-gray-700">
                    {/* Judge A */}
                    <div className="p-3">
                      <div className="text-xs font-medium text-amber-600 dark:text-amber-400 mb-2 truncate">
                        {entry.judgeA}
                      </div>
                      {judgmentA && judgmentA.scores?.[entry.modelPresetId] ? (
                        <div className="space-y-1 mb-2">
                          {benchmark.criteria.map(c => {
                            const score = getScore(judgmentA.scores[entry.modelPresetId] as Record<string, number>, c.name);
                            return (
                              <div key={c.name} className="flex items-center gap-1 text-xs">
                                <span className="text-slate-500 dark:text-gray-400 truncate flex-1">{c.name}</span>
                                {score !== undefined ? (
                                  <span
                                    className="px-1.5 py-0.5 rounded font-mono shrink-0"
                                    style={{
                                      color: getScoreColor(score, isDark),
                                      backgroundColor: getScoreBgColor(score, isDark),
                                    }}
                                  >
                                    {score.toFixed(1)}
                                  </span>
                                ) : (
                                  <span className="text-slate-400 dark:text-gray-500">-</span>
                                )}
                              </div>
                            );
                          })}
                        </div>
                      ) : (
                        <p className="text-xs text-slate-400 dark:text-gray-500 mb-2">No scores</p>
                      )}
                      {judgmentA?.comments?.[entry.modelPresetId] && judgmentA.comments[entry.modelPresetId].length > 0 && (
                        <div className="space-y-1 mb-2">
                          {judgmentA.comments[entry.modelPresetId].map((c, i) => (
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
                      {judgmentA?.reasoning && (
                        <pre className="text-xs text-slate-500 dark:text-gray-400 whitespace-pre-wrap max-h-40 overflow-y-auto bg-stone-100 dark:bg-gray-900 p-2 rounded">
                          {judgmentA.reasoning}
                        </pre>
                      )}
                    </div>

                    {/* Judge B */}
                    <div className="p-3">
                      <div className="text-xs font-medium text-amber-600 dark:text-amber-400 mb-2 truncate">
                        {entry.judgeB}
                      </div>
                      {judgmentB && judgmentB.scores?.[entry.modelPresetId] ? (
                        <div className="space-y-1 mb-2">
                          {benchmark.criteria.map(c => {
                            const score = getScore(judgmentB.scores[entry.modelPresetId] as Record<string, number>, c.name);
                            return (
                              <div key={c.name} className="flex items-center gap-1 text-xs">
                                <span className="text-slate-500 dark:text-gray-400 truncate flex-1">{c.name}</span>
                                {score !== undefined ? (
                                  <span
                                    className="px-1.5 py-0.5 rounded font-mono shrink-0"
                                    style={{
                                      color: getScoreColor(score, isDark),
                                      backgroundColor: getScoreBgColor(score, isDark),
                                    }}
                                  >
                                    {score.toFixed(1)}
                                  </span>
                                ) : (
                                  <span className="text-slate-400 dark:text-gray-500">-</span>
                                )}
                              </div>
                            );
                          })}
                        </div>
                      ) : (
                        <p className="text-xs text-slate-400 dark:text-gray-500 mb-2">No scores</p>
                      )}
                      {judgmentB?.comments?.[entry.modelPresetId] && judgmentB.comments[entry.modelPresetId].length > 0 && (
                        <div className="space-y-1 mb-2">
                          {judgmentB.comments[entry.modelPresetId].map((c, i) => (
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
                      {judgmentB?.reasoning && (
                        <pre className="text-xs text-slate-500 dark:text-gray-400 whitespace-pre-wrap max-h-40 overflow-y-auto bg-stone-100 dark:bg-gray-900 p-2 rounded">
                          {judgmentB.reasoning}
                        </pre>
                      )}
                    </div>
                  </div>
                </div>
              )}

              {/* Link to full question */}
              <div className="px-3 py-2 border-t border-stone-200 dark:border-gray-700 bg-stone-50 dark:bg-gray-800">
                <Button
                  variant="link"
                  size="sm"
                  className="text-xs p-0 h-auto"
                  onClick={() => navigate(`question-${entry.questionOrder}` as SectionId)}
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
