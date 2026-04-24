import { useState } from 'react';
import { useParams, useNavigate } from 'react-router-dom';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { toast } from 'sonner';
import { Loader2, Download, AlertTriangle, Search } from 'lucide-react';
import { benchmarksApi, suitesApi } from '@/lib/api';
import { formatISODateTime } from '@/lib/utils';
import { assessSampleSize } from '@/lib/constants';
import { Button } from '@/components/ui/button';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Label } from '@/components/ui/label';
import { Input } from '@/components/ui/input';
import { ContextUsageBadge } from '@/components/ui/context-usage-bar';
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuTrigger,
} from '@/components/ui/dropdown-menu';
import type { BenchmarkDetail } from './results/types';
import { slugify } from './results/types';
import {
  buildQuestionBrowserLaunchHref,
  getQuestionBrowserLaunchMatchMode,
} from '@/pages/questionBrowser/launch';
import { computeResultsData } from './results/computeResultsData';
import { useResultsNav } from './results/useResultsNav';
import { ResultsSidebar, ResultsDropdownNav } from './results/ResultsSidebar';
import { OverviewSection } from './results/OverviewSection';
import { ChartsSection } from './results/ChartsSection';
import { ScoresSection } from './results/ScoresSection';
import { StatsSection } from './results/StatsSection';
import { JudgesSection } from './results/JudgesSection';
import { ModelDetail } from './results/ModelDetail';
import { QuestionDetail } from './results/QuestionDetail';
import { BestWorstSection } from './results/BestWorstSection';
import { JudgeDisagreementSection } from './results/JudgeDisagreementSection';
import { CompareParentSection } from './results/CompareParentSection';

const DEMO_MODE = import.meta.env.VITE_DEMO_MODE === 'true';

export function Results() {
  // 1. Route params, navigation
  const { id } = useParams<{ id: string }>();
  const runId = Number(id);
  const routerNavigate = useNavigate();
  const { section: activeSection, navigate } = useResultsNav();

  // 2. Data fetching
  const { data: benchmark, isLoading, error } = useQuery<BenchmarkDetail>({
    queryKey: ['benchmark', runId],
    queryFn: async () => {
      const res = await benchmarksApi.get(runId);
      return res.data;
    },
  });

  // 3. Mutations & shared state
  const queryClient = useQueryClient();

  const [retryingItem, setRetryingItem] = useState<{ type: string; id: number } | null>(null);
  const retryMutation = useMutation({
    mutationFn: ({ itemType, itemId }: { itemType: 'generation' | 'judgment'; itemId: number }) =>
      benchmarksApi.retry(runId, itemType, itemId),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['benchmark', runId] });
    },
  });

  const resumeMutation = useMutation({
    mutationFn: () => benchmarksApi.resume(runId),
    onSuccess: () => {
      toast.success('Resuming run — picking up where it left off');
      queryClient.invalidateQueries({ queryKey: ['benchmark', runId] });
      routerNavigate(`/runs/${runId}/live`);
    },
    onError: (err: unknown) => {
      const detail = (err as { response?: { data?: { detail?: string } } })?.response?.data?.detail;
      toast.error(`Resume failed: ${detail || 'unknown error'}`);
    },
  });

  const [suiteNameInput, setSuiteNameInput] = useState('');
  const [showSuiteDialog, setShowSuiteDialog] = useState(false);
  const [exportLoading, setExportLoading] = useState<string | null>(null);

  const saveSuiteMutation = useMutation({
    mutationFn: ({ runId, name }: { runId: number; name: string }) =>
      suitesApi.fromRun(runId, { name }),
    onSuccess: () => {
      setShowSuiteDialog(false);
      setSuiteNameInput('');
      toast.success('Suite saved successfully!');
    },
  });

  const handleSaveSuite = () => {
    if (!suiteNameInput.trim()) {
      toast.error('Please enter a suite name');
      return;
    }
    saveSuiteMutation.mutate({ runId, name: suiteNameInput });
  };

  const handleRetry = (itemType: 'generation' | 'judgment', itemId: number) => {
    setRetryingItem({ type: itemType, id: itemId });
    retryMutation.mutate({ itemType, itemId }, {
      onSettled: () => setRetryingItem(null),
    });
  };

  const handleExport = async (format: 'pptx' | 'pdf' | 'html' | 'json' | 'csv', theme?: 'light' | 'dark') => {
    setExportLoading(format);
    try {
      const response = await benchmarksApi.export(runId, format, theme);
      const mimeTypes: Record<string, string> = {
        pptx: 'application/vnd.openxmlformats-officedocument.presentationml.presentation',
        pdf: 'application/pdf',
        html: 'text/html',
        json: 'application/json',
        csv: 'text/csv',
      };
      const blob = new Blob([response.data], { type: mimeTypes[format] });
      const safeName = (benchmark?.name || 'run').replace(/[^a-z0-9-_]/gi, '-').slice(0, 50);
      const themeLabel = theme ? `-${theme}` : '';
      const url = URL.createObjectURL(blob);
      const a = document.createElement('a');
      a.href = url;
      a.download = `bellmark-${safeName}${themeLabel}-${runId}.${format}`;
      document.body.appendChild(a);
      a.click();
      setTimeout(() => {
        document.body.removeChild(a);
        URL.revokeObjectURL(url);
      }, 100);
    } catch (err) {
      toast.error(`Failed to export ${format.toUpperCase()}${err instanceof Error ? ': ' + err.message : ''}`);
    } finally {
      setExportLoading(null);
    }
  };

  // 4. Loading/error states
  if (isLoading) return <div className="text-slate-500 dark:text-gray-400">Loading results...</div>;
  if (error || !benchmark) return <div className="text-red-600 dark:text-red-400">Failed to load results</div>;

  // 4a. Defensive normalization — if the API ever returns a benchmark without
  // questions (malformed payload, partial backfill), give the rest of the page
  // an empty array so the small-sample advisory can render at 'critical' rather
  // than the page crashing in computeResultsData. The TypeScript type expects
  // questions to be present; this is a runtime safety net only.
  const safeBenchmark = Array.isArray(benchmark.questions)
    ? benchmark
    : { ...benchmark, questions: [] as typeof benchmark.questions };

  // 5. Compute derived data
  const computed = computeResultsData(safeBenchmark);

  // 6. Section router
  const renderSection = () => {
    if (activeSection === 'overview') {
      return <div data-testid="results-section-overview"><OverviewSection benchmark={safeBenchmark} computed={computed} navigate={navigate} /></div>;
    }
    if (activeSection === 'charts') {
      return <div data-testid="results-section-charts"><ChartsSection benchmark={safeBenchmark} computed={computed} /></div>;
    }
    if (activeSection === 'scores') {
      return <div data-testid="results-section-scores"><ScoresSection benchmark={safeBenchmark} computed={computed} navigate={navigate} /></div>;
    }
    if (activeSection === 'statistics') {
      return <div data-testid="results-section-stats"><StatsSection runId={runId} /></div>;
    }
    if (activeSection === 'judges') {
      return <div data-testid="results-section-judges"><JudgesSection runId={runId} /></div>;
    }
    if (activeSection === 'best-answers') {
      return <div data-testid="results-section-best-worst"><BestWorstSection mode="best" generations={computed.bestGenerations} benchmark={safeBenchmark} navigate={navigate} /></div>;
    }
    if (activeSection === 'worst-answers') {
      return <div data-testid="results-section-best-worst"><BestWorstSection mode="worst" generations={computed.worstGenerations} benchmark={safeBenchmark} navigate={navigate} /></div>;
    }
    if (activeSection === 'judge-disagreement') {
      return <div data-testid="results-section-judge-disagreement"><JudgeDisagreementSection disagreements={computed.topDisagreements} judgePair={computed.mostDisagreeingPair} pairAvgDelta={computed.pairAvgDelta} benchmark={safeBenchmark} navigate={navigate} /></div>;
    }
    if (activeSection.startsWith('model-')) {
      const modelSlug = activeSection.replace('model-', '');
      return (
        <ModelDetail
          benchmark={safeBenchmark}
          computed={computed}
          modelSlug={modelSlug}
          navigate={navigate}
        />
      );
    }
    if (activeSection.startsWith('question-')) {
      const order = parseInt(activeSection.replace('question-', ''), 10);
      return (
        <QuestionDetail
          benchmark={safeBenchmark}
          computed={computed}
          questionOrder={order}
          navigate={navigate}
          onRetry={handleRetry}
          retryingItem={retryingItem}
        />
      );
    }
    if (activeSection === 'compare-parent') {
      return <CompareParentSection runId={runId} />;
    }
    return <OverviewSection benchmark={safeBenchmark} computed={computed} navigate={navigate} />;
  };

  const modelNames = computed.rankedModelData.map(d => d.model);

  // 7. Render
  return (
    <div className={DEMO_MODE ? "space-y-0" : "space-y-4"}>
      {/* Header — sticky below app header */}
      <div className={`sticky z-20 bg-stone-100 dark:bg-gray-900 pb-3 border-b border-stone-200 dark:border-gray-800 ${DEMO_MODE ? 'top-0 px-4 pt-0' : 'top-[73px] -mx-4 md:-mx-6 px-4 md:px-6 pt-2'}`}>
      <div className="flex flex-col sm:flex-row justify-between items-start gap-3">
        <div>
          <h1 className="text-xl md:text-2xl font-bold">{benchmark.name}</h1>
          <div className="flex flex-wrap items-center gap-x-4 gap-y-1 mt-1 text-sm text-slate-500 dark:text-gray-400">
            <span>
              Status: <span className={benchmark.status === 'completed' ? 'text-green-600 dark:text-green-400' : 'text-yellow-600 dark:text-yellow-400'}>
                {benchmark.status}
              </span>
            </span>
            <span>Mode: {benchmark.judge_mode}</span>
            <span>Questions: {safeBenchmark.questions.length}</span>
            {benchmark.created_at && (
              <span>
                📅 {formatISODateTime(benchmark.created_at)}
              </span>
            )}
            {benchmark.created_at && benchmark.completed_at && (
              <span className="text-blue-600 dark:text-blue-400" title={`${formatISODateTime(benchmark.created_at)} → ${formatISODateTime(benchmark.completed_at!)}`}>
                ⏱️ {(() => {
                  const durationMs = new Date(benchmark.completed_at!).getTime() - new Date(benchmark.created_at).getTime();
                  const mins = Math.floor(durationMs / 60000);
                  const secs = Math.floor((durationMs % 60000) / 1000);
                  return mins > 0 ? `${mins}m ${secs}s` : `${secs}s`;
                })()}
              </span>
            )}
            {(benchmark.performance_metrics || benchmark.judge_metrics) && (
              <span className="text-green-600 dark:text-green-400">
                💰 ${(() => {
                  const modelCost = benchmark.performance_metrics
                    ? Object.values(benchmark.performance_metrics).reduce((sum, m) => sum + (m.estimated_cost || 0), 0)
                    : 0;
                  const judgeCost = benchmark.judge_metrics
                    ? Object.values(benchmark.judge_metrics).reduce((sum, m) => sum + (m.estimated_cost || 0), 0)
                    : 0;
                  const total = modelCost + judgeCost;
                  return total < 0.01 ? total.toFixed(3) : total.toFixed(2);
                })()}
              </span>
            )}
            {benchmark.total_context_tokens && (
              <div className="flex items-center gap-2">
                <span className="text-sm text-slate-500 dark:text-gray-400">Context:</span>
                <ContextUsageBadge used={benchmark.total_context_tokens} />
              </div>
            )}
          </div>
        </div>
        {!DEMO_MODE && (
        <div className="flex flex-wrap gap-2 w-full sm:w-auto">
          <Button variant="outline" size="sm" onClick={() => routerNavigate(`/runs/${benchmark.id}/live`)}>
            Progress Grid
          </Button>
          {benchmark.model_ids.length >= 2 && safeBenchmark.questions.length > 0 && (
            <Button
              variant="outline"
              size="sm"
              onClick={() => {
                const firstQ = safeBenchmark.questions.reduce((min, q) => q.order < min.order ? q : min, safeBenchmark.questions[0]);
                const matchMode = getQuestionBrowserLaunchMatchMode(
                  benchmark.model_ids,
                  benchmark.run_config_snapshot,
                );
                routerNavigate(
                  buildQuestionBrowserLaunchHref(
                    benchmark.model_ids,
                    benchmark.id,
                    firstQ.id,
                    matchMode,
                  ),
                );
              }}
            >
              <Search className="h-4 w-4 mr-1" /> Question Browser
            </Button>
          )}
          <DropdownMenu>
            <DropdownMenuTrigger asChild>
              <Button variant="outline" size="sm" disabled={!!exportLoading} data-testid="results-export-trigger">
                {exportLoading ? (
                  <><Loader2 className="h-4 w-4 mr-1 animate-spin" /> Exporting...</>
                ) : (
                  <><Download className="h-4 w-4 mr-1" /> Export</>
                )}
              </Button>
            </DropdownMenuTrigger>
            <DropdownMenuContent>
              <DropdownMenuItem data-testid="results-export-item-pptx-light" onClick={() => handleExport('pptx', 'light')}>
                PowerPoint (Light)
              </DropdownMenuItem>
              <DropdownMenuItem data-testid="results-export-item-pptx-dark" onClick={() => handleExport('pptx', 'dark')}>
                PowerPoint (Dark)
              </DropdownMenuItem>
              <DropdownMenuItem data-testid="results-export-item-pdf-light" onClick={() => handleExport('pdf', 'light')}>
                PDF Report (Light)
              </DropdownMenuItem>
              <DropdownMenuItem data-testid="results-export-item-pdf-dark" onClick={() => handleExport('pdf', 'dark')}>
                PDF Report (Dark)
              </DropdownMenuItem>
              <DropdownMenuItem data-testid="results-export-item-html-light" onClick={() => handleExport('html', 'light')}>
                HTML Report (Light)
              </DropdownMenuItem>
              <DropdownMenuItem data-testid="results-export-item-html-dark" onClick={() => handleExport('html', 'dark')}>
                HTML Report (Dark)
              </DropdownMenuItem>
              <DropdownMenuItem data-testid="results-export-item-json" onClick={() => handleExport('json')}>
                JSON Data
              </DropdownMenuItem>
              <DropdownMenuItem data-testid="results-export-item-csv" onClick={() => handleExport('csv')}>
                CSV Spreadsheet
              </DropdownMenuItem>
            </DropdownMenuContent>
          </DropdownMenu>
          {(benchmark.status === 'failed' || benchmark.status === 'cancelled') && (
            <Button
              variant="default"
              size="sm"
              onClick={() => resumeMutation.mutate()}
              disabled={resumeMutation.isPending}
              title="Re-run only the missing or failed items — keeps existing successful generations"
            >
              {resumeMutation.isPending ? (
                <><Loader2 className="h-4 w-4 mr-1 animate-spin" /> Resuming...</>
              ) : (
                <>▶️ Resume</>
              )}
            </Button>
          )}
          <Button
            variant="outline"
            size="sm"
            onClick={() => routerNavigate('/runs/new', {
              state: {
                cloneFrom: {
                  name: `${benchmark.name.replace(/ \(rerun[^)]*\)$/i, '')} (rerun ${formatISODateTime(new Date().toISOString())})`,
                  questions: safeBenchmark.questions.map(q => ({
                    system_prompt: q.system_prompt,
                    user_prompt: q.user_prompt,
                    expected_answer: q.expected_answer || null
                  })),
                  criteria: benchmark.criteria,
                  judgeMode: benchmark.judge_mode,
                  modelIds: benchmark.model_ids,
                  judgeIds: benchmark.judge_ids
                }
              }
            })}
          >
            🔄 Clone
          </Button>
          {benchmark.status === 'completed' && (
            <Button
              variant="outline"
              size="sm"
              onClick={() => routerNavigate('/runs/new', {
                state: {
                  rejudgeFrom: {
                    parentRunId: benchmark.id,
                    name: `${benchmark.name.replace(/ \(rejudge[^)]*\)$/i, '')} (rejudge ${formatISODateTime(new Date().toISOString())})`,
                    criteria: benchmark.criteria,
                    judgeMode: benchmark.judge_mode,
                    modelIds: benchmark.model_ids,
                    judgeIds: benchmark.judge_ids,
                  }
                }
              })}
            >
              ⚖️ Re-judge
            </Button>
          )}
          <Button
            variant="outline"
            size="sm"
            onClick={() => {
              setSuiteNameInput(`${benchmark.name} Suite`);
              setShowSuiteDialog(true);
            }}
          >
            💾 Save as Suite
          </Button>
        </div>
        )}
      </div>
      <ResultsDropdownNav
        activeSection={activeSection}
        onNavigate={navigate}
        modelNames={modelNames}
        questionCount={safeBenchmark.questions.length}
        slugify={slugify}
        parentRunId={benchmark.parent_run_id}
      />
      </div>

      {/* Sample-size advisory (Tier 0.2.3 — three-tier severity).
          Persistent banner — credibility signal must remain visible across all sections.
          Severity tiers and copy live in @/lib/constants → assessSampleSize.
          Null-safe: a missing/malformed questions field assesses as 0 → critical,
          so the user sees an explanatory banner instead of a silent crash. */}
      {(() => {
        const questionCount = safeBenchmark.questions?.length ?? 0;
        const assessment = assessSampleSize(questionCount);
        if (assessment.severity === 'ok') return null;

        // Severity-driven palette. Each variant picks values from Tailwind tokens
        // that already appear elsewhere in this file so dark/light themes stay consistent.
        const palette = {
          critical: {
            container: 'bg-red-50 dark:bg-red-900/30 border-red-400 dark:border-red-600',
            icon: 'text-red-600 dark:text-red-500',
            title: 'text-red-700 dark:text-red-300',
            body: 'text-red-600 dark:text-red-400/80',
            heading: 'Insufficient sample size',
          },
          warning: {
            container: 'bg-yellow-50 dark:bg-yellow-900/30 border-yellow-400 dark:border-yellow-600',
            icon: 'text-yellow-600 dark:text-yellow-500',
            title: 'text-yellow-700 dark:text-yellow-300',
            body: 'text-yellow-600 dark:text-yellow-400/80',
            heading: 'Small sample size',
          },
          info: {
            container: 'bg-blue-50 dark:bg-blue-900/20 border-blue-300 dark:border-blue-700',
            icon: 'text-blue-600 dark:text-blue-400',
            title: 'text-blue-700 dark:text-blue-300',
            body: 'text-blue-600 dark:text-blue-400/80',
            heading: 'Limited sample size',
          },
        }[assessment.severity];

        // role='alert' is implicitly assertive (interrupts screen readers). Only
        // critical/warning earn that. info is non-urgent — render as a status
        // region so it gets read in queue, not interrupting current speech.
        const isAssertive = assessment.severity === 'critical' || assessment.severity === 'warning';

        return (
          <div
            role={isAssertive ? 'alert' : 'status'}
            aria-live={isAssertive ? undefined : 'polite'}
            data-testid="sample-size-banner"
            data-severity={assessment.severity}
            className={`border rounded-lg p-4 flex items-start gap-3 ${palette.container}`}
          >
            <AlertTriangle aria-hidden="true" className={`w-5 h-5 mt-0.5 shrink-0 ${palette.icon}`} />
            <div>
              <p className={`font-medium ${palette.title}`}>{palette.heading}</p>
              <p className={`text-sm mt-1 ${palette.body}`}>{assessment.message}</p>
            </div>
          </div>
        );
      })()}

      {/* Suite dialog */}
      {showSuiteDialog && (
        <div className="fixed inset-0 bg-black/50 flex items-center justify-center z-50">
          <Card className="bg-white dark:bg-gray-800 border-stone-200 dark:border-gray-700 w-96">
            <CardHeader>
              <CardTitle>Save Questions as Suite</CardTitle>
            </CardHeader>
            <CardContent className="space-y-4">
              <div>
                <Label>Suite Name</Label>
                <Input
                  value={suiteNameInput}
                  onChange={(e) => setSuiteNameInput(e.target.value)}
                  className="bg-stone-50 dark:bg-gray-900 border-stone-200 dark:border-gray-700"
                  placeholder="Enter suite name"
                />
              </div>
              <p className="text-sm text-slate-500 dark:text-gray-400">
                This will save {safeBenchmark.questions.length} question(s) as a reusable prompt suite.
              </p>
              <div className="flex gap-2 justify-end">
                <Button variant="outline" onClick={() => setShowSuiteDialog(false)}>
                  Cancel
                </Button>
                <Button onClick={handleSaveSuite} disabled={saveSuiteMutation.isPending}>
                  {saveSuiteMutation.isPending ? 'Saving...' : 'Save Suite'}
                </Button>
              </div>
            </CardContent>
          </Card>
        </div>
      )}

      {/* Main layout: sidebar + content */}
      <div className="flex gap-6">
        <ResultsSidebar
          activeSection={activeSection}
          onNavigate={navigate}
          modelNames={modelNames}
          questionCount={safeBenchmark.questions.length}
          slugify={slugify}
          parentRunId={benchmark.parent_run_id}
        />
        <div className="flex-1 min-w-0 space-y-6">
          {renderSection()}
        </div>
      </div>
    </div>
  );
}
