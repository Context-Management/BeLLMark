import { useEffect, useRef, useState } from 'react';
import { useParams, useNavigate } from 'react-router-dom';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import { useBenchmarkStore } from '@/stores/benchmarkStore';
import { benchmarksApi, modelsApi } from '@/lib/api';
import type { BenchmarkDetail } from '@/types/api';
import { getProgressMatrixTemplate, parseModelLabel } from '@/pages/liveProgress/progressMatrix';

interface LogEntry {
  id: number;
  time: string;
  type: 'info' | 'success' | 'error' | 'warning';
  message: string;
}

type Status = 'pending' | 'running' | 'success' | 'failed';

interface BenchmarkData {
  name: string;
  status: string;
  modelIds: number[];
  judgeIds: number[];
  questions: { id: number; order: number }[];
  generations: Map<string, Status>; // "questionId-modelId" -> status
  judgments: Map<string, Status>;   // "questionId-judgeId" -> status
  generationIds: Map<string, number>; // "questionId-modelId" -> generation DB id
}

const StatusDot = ({ status, label, compact }: { status: Status; label?: string; compact?: boolean }) => {
  const size = compact ? "w-3.5 h-3.5" : "w-4 h-4";
  const baseClasses = `${size} rounded-full transition-all duration-300 cursor-default`;
  const title = label ? `${label} — ${status}` : status;

  switch (status) {
    case 'pending':
      return <div className={`${baseClasses} bg-gray-300 dark:bg-gray-600`} title={title} />;
    case 'running':
      return (
        <div className={`${baseClasses} bg-yellow-500 animate-pulse hover:shadow-[0_0_8px_2px_rgba(234,179,8,0.5)]`} title={title} />
      );
    case 'success':
      return <div className={`${baseClasses} bg-green-500 hover:shadow-[0_0_8px_2px_rgba(34,197,94,0.5)]`} title={title} />;
    case 'failed':
      return <div className={`${baseClasses} bg-red-500 hover:shadow-[0_0_8px_2px_rgba(239,68,68,0.5)]`} title={title} />;
  }
};

function MatrixBadge({ value, color }: { value?: string; color: string }) {
  if (!value) return null;

  return (
    <span
      className="inline-flex min-h-5 items-center rounded px-1.5 py-0.5 text-[10px] font-semibold leading-none text-white"
      style={{ backgroundColor: color }}
      title={value}
    >
      {value}
    </span>
  );
}

export function LiveProgress() {
  const { id } = useParams<{ id: string }>();
  const navigate = useNavigate();
  const runId = Number(id);
  const logEndRef = useRef<HTMLDivElement>(null);
  // ?noredirect=1 suppresses the post-completion auto-redirect to /runs/:id.
  // Used by the demo-capture script so Shot 5 holds the live-grid view
  // through the full narration window instead of flipping to results.
  const noRedirect = new URLSearchParams(window.location.search).get('noredirect') === '1';

  const { phase, setActiveRun, updateStatus, addEvent } = useBenchmarkStore();
  const [logs, setLogs] = useState<LogEntry[]>([]);
  const logIdRef = useRef(0);
  const [ws, setWs] = useState<WebSocket | null>(null);
  const [showLogs, setShowLogs] = useState(false);
  const [isCancelling, setIsCancelling] = useState(false);

  // Dashboard state
  const [benchmarkData, setBenchmarkData] = useState<BenchmarkData | null>(null);
  const [modelNames, setModelNames] = useState<Map<number, string>>(new Map());
  const [reasoningModels, setReasoningModels] = useState<Set<number>>(new Set());
  const [winCounts, setWinCounts] = useState<Record<string, number>>({});
  const [retryingModels, setRetryingModels] = useState<Set<number>>(new Set());
  const modelNamesRef = useRef<Map<number, string>>(new Map());
  const loggedEventsRef = useRef<Set<string>>(new Set());

  const fmtTime = (d: Date) => {
    const pad = (n: number) => String(n).padStart(2, '0');
    return `${d.getFullYear()}-${pad(d.getMonth()+1)}-${pad(d.getDate())} ${pad(d.getHours())}:${pad(d.getMinutes())}:${pad(d.getSeconds())}`;
  };

  const addLog = (type: LogEntry['type'], message: string) => {
    logIdRef.current += 1;
    const newId = logIdRef.current;
    const time = fmtTime(new Date());
    setLogs(prevLogs => [...prevLogs, { id: newId, time, type, message }].slice(-200));
  };

  // Update generation status in grid
  const updateGeneration = (questionId: number, modelName: string, status: Status) => {
    setBenchmarkData(prev => {
      if (!prev) return prev;
      const modelId = [...modelNamesRef.current.entries()].find(([, name]) => name === modelName)?.[0];
      if (!modelId) return prev;

      const newGens = new Map(prev.generations);
      newGens.set(`${questionId}-${modelId}`, status);
      return { ...prev, generations: newGens };
    });
  };

  // Update judgment status in grid
  const updateJudgment = (questionId: number, judgeName: string, status: Status) => {
    setBenchmarkData(prev => {
      if (!prev) return prev;
      const judgeId = [...modelNamesRef.current.entries()].find(([, name]) => name === judgeName)?.[0];
      if (!judgeId) return prev;

      const newJudgments = new Map(prev.judgments);
      newJudgments.set(`${questionId}-${judgeId}`, status);
      return { ...prev, judgments: newJudgments };
    });
  };

  useEffect(() => {
    setActiveRun(runId);

    const loadData = async () => {
      try {
        const [modelsRes, res] = await Promise.all([
          modelsApi.list({ include_archived: true }),
          benchmarksApi.get(runId),
        ]);

        const names = new Map<number, string>();
        const allModels = modelsRes.data;
        const reasoning = new Set<number>();
        for (const m of allModels) {
          names.set(m.id, m.name);
          if (m.is_reasoning) reasoning.add(m.id);
        }

        const data = res.data as BenchmarkDetail;
        for (const [presetId, label] of Object.entries(data.preset_labels || {})) {
          names.set(Number(presetId), label);
        }
        for (const question of data.questions || []) {
          for (const gen of question.generations || []) {
            names.set(gen.model_preset_id, gen.model_name);
          }
          for (const judge of question.judgments || []) {
            names.set(judge.judge_preset_id, judge.judge_name);
          }
        }

        setModelNames(names);
        setReasoningModels(reasoning);
        modelNamesRef.current = names;

        // Build generation and judgment status maps
        const generations = new Map<string, Status>();
        const generationIds = new Map<string, number>();
        const judgments = new Map<string, Status>();
        const historyLogs: { time: Date; type: LogEntry['type']; message: string }[] = [];
        const wins: Record<string, number> = {};

        for (const question of data.questions || []) {
          for (const gen of question.generations || []) {
            const key = `${question.id}-${gen.model_preset_id}`;
            generations.set(key, gen.status as Status);
            if (gen.id) generationIds.set(key, gen.id);

            if (gen.completed_at && gen.status !== 'pending') {
              const time = new Date(gen.completed_at);
              loggedEventsRef.current.add(`gen-${question.id}-${gen.model_preset_id}`);
              if (gen.status === 'success') {
                historyLogs.push({ time, type: 'success', message: `${gen.model_name}: Generated ${gen.tokens || 0} tokens` });
              } else if (gen.status === 'failed') {
                historyLogs.push({ time, type: 'error', message: `${gen.model_name}: ${gen.error || 'Failed'}` });
              }
            }
          }
          for (const judge of question.judgments || []) {
            const key = `${question.id}-${judge.judge_preset_id}`;
            judgments.set(key, judge.status as Status);

            // Track wins from historical judgments
            const rankings = judge.rankings;
            if (judge.status === 'success' && rankings && rankings.length > 0 && judge.blind_mapping) {
              const winnerLabel = rankings[0];
              const winnerId = judge.blind_mapping[winnerLabel];
              const winnerName = winnerId != null ? names.get(Number(winnerId)) : undefined;
              if (winnerName) wins[winnerName] = (wins[winnerName] || 0) + 1;
            }

            if (judge.completed_at && judge.status !== 'pending') {
              const time = new Date(judge.completed_at);
              loggedEventsRef.current.add(`judge-${question.id}-${judge.judge_preset_id}`);
              if (judge.status === 'success') {
                historyLogs.push({ time, type: 'success', message: `${judge.judge_name}: Judged Q${question.order + 1}` });
              } else if (judge.status === 'failed') {
                historyLogs.push({ time, type: 'error', message: `${judge.judge_name}: ${judge.error || 'Failed'}` });
              }
            }
          }
        }
        setWinCounts(wins);

        setBenchmarkData({
          name: data.name || 'Unknown',
          status: data.status || 'unknown',
          modelIds: data.model_ids || [],
          judgeIds: data.judge_ids || [],
          questions: (data.questions || []).map((q: { id: number; order: number }) => ({ id: q.id, order: q.order })),
          generations,
          judgments,
          generationIds,
        });

        // Set history logs
        historyLogs.sort((a, b) => a.time.getTime() - b.time.getTime());
        const formatted = historyLogs.map((log, i) => ({
          id: i + 1,
          time: fmtTime(log.time),
          type: log.type,
          message: log.message
        }));
        setLogs(formatted);
        logIdRef.current = formatted.length;

        // Set initial status (no auto-redirect — user navigated here intentionally)
        if (data.status === 'completed') {
          updateStatus('completed', 100);
          addLog('success', 'Benchmark completed!');
        } else if (data.status === 'failed') {
          updateStatus('failed', 0);
        } else if (data.status === 'cancelled') {
          updateStatus('cancelled', 0);
        } else if (data.status === 'summarizing') {
          updateStatus('summarizing', 96);
        } else if (data.status === 'running') {
          const totalGens = data.questions.length * data.model_ids.length;
          const completedGens = [...generations.values()].filter(s => s === 'success' || s === 'failed').length;
          const completedJudgments = [...judgments.values()].filter(s => s === 'success' || s === 'failed').length;

          if (completedGens >= totalGens && totalGens > 0) {
            // All generations done — we're in judging phase
            const totalJudge = data.questions.length * data.judge_ids.length;
            const judgeProgress = totalJudge > 0 ? 50 + (completedJudgments / totalJudge) * 50 : 50;
            updateStatus('judging', Math.round(judgeProgress));
          } else {
            const genProgress = totalGens > 0 ? (completedGens / totalGens) * 50 : 0;
            updateStatus('generating', Math.round(genProgress));
          }
        }
      } catch (e) {
        console.error('Failed to load benchmark data:', e);
        addLog('warning', `Could not load benchmark data: ${e instanceof Error ? e.message : String(e)}`);
      }
    };

    let socket: WebSocket | null = null;

    loadData().then(() => {
      // Derive WebSocket URL from current location or API base
      const apiBase = import.meta.env.VITE_API_URL || window.location.origin;
      const wsProtocol = apiBase.startsWith('https') ? 'wss' : 'ws';
      const wsHost = apiBase.replace(/^https?:\/\//, '');
      const wsUrl = `${wsProtocol}://${wsHost}/ws/runs/${runId}`;
      socket = new WebSocket(wsUrl);

      socket.onopen = () => {
        // Send auth as first message (F-003: avoid token in URL)
        const storedKey = localStorage.getItem('bellmark_api_key');
        if (storedKey) {
          socket!.send(JSON.stringify({ type: 'auth', token: storedKey }));
        }
        addLog('success', `Connected to live updates`);
        // Re-fetch state to catch events missed between initial HTTP load and WS connect
        benchmarksApi.get(runId).then(res => {
          const data = res.data;
          // Rank-based downgrade protection prevents stale poll responses from
          // regressing dots — EXCEPT when local state is `failed`, which is not
          // actually terminal: the retry checkpoint can revive a failed
          // judgment back into `running` and onward to `success`/`failed`.
          // Without the `failed` exception, retried dots stay red forever.
          const statusRank = (s: string) => s === 'success' || s === 'failed' ? 2 : s === 'running' ? 1 : 0;
          const shouldUpdate = (oldS: string, newS: string) =>
            oldS === 'failed' || statusRank(newS) > statusRank(oldS);
          setBenchmarkData(prev => {
            if (!prev) return prev;
            const newGens = new Map(prev.generations);
            const newGenIds = new Map(prev.generationIds);
            const newJudgments = new Map(prev.judgments);
            for (const question of data.questions || []) {
              for (const gen of question.generations || []) {
                const key = `${question.id}-${gen.model_preset_id}`;
                if (gen.id) newGenIds.set(key, gen.id);
                if (shouldUpdate(newGens.get(key) || 'pending', gen.status)) {
                  newGens.set(key, gen.status as Status);
                }
              }
              for (const judge of question.judgments || []) {
                const key = `${question.id}-${judge.judge_preset_id}`;
                if (shouldUpdate(newJudgments.get(key) || 'pending', judge.status)) {
                  newJudgments.set(key, judge.status as Status);
                }
              }
            }
            return { ...prev, generations: newGens, judgments: newJudgments, generationIds: newGenIds };
          });
        }).catch(() => {});
      };

      socket.onmessage = (event) => {
        // eslint-disable-next-line @typescript-eslint/no-explicit-any
        let data: any;
        try {
          data = JSON.parse(event.data);
        } catch {
          return; // ignore non-JSON frames (e.g. keepalive pings)
        }
        addEvent({ type: data.type, data });

        if (data.type === 'status') {
          updateStatus(data.phase, data.progress);
          if (data.phase === 'completed') {
            addLog('success', 'Benchmark completed!');
            if (!noRedirect) {
              setTimeout(() => navigate(`/runs/${runId}`), 1500);
            }
          } else if (data.phase === 'failed') {
            addLog('error', 'Benchmark failed');
          } else if (data.phase === 'cancelled') {
            setBenchmarkData(prev => prev ? { ...prev, status: 'cancelled' } : prev);
            setIsCancelling(false);
          }
        } else if (data.type === 'generation') {
          const questionId = data.question_id;
          const modelId = [...modelNamesRef.current.entries()].find(([, name]) => name === data.model)?.[0];
          const eventKey = `gen-${questionId}-${modelId}`;
          updateGeneration(questionId, data.model, data.status === 'retry' ? 'running' : data.status as Status);
          if (data.status === 'success') {
            if (!loggedEventsRef.current.has(eventKey)) {
              loggedEventsRef.current.add(eventKey);
              addLog('success', `${data.model}: Generated ${data.tokens} tokens`);
            }
          } else if (data.status === 'failed') {
            if (!loggedEventsRef.current.has(eventKey)) {
              loggedEventsRef.current.add(eventKey);
              addLog('error', `${data.model}: ${data.error}`);
            }
          } else if (data.status === 'retry') {
            addLog('warning', `${data.model}: Retrying (attempt ${data.retry + 1})`);
          }
        } else if (data.type === 'judgment') {
          const questionId = data.question_id;
          const judgeId = [...modelNamesRef.current.entries()].find(([, name]) => name === data.judge)?.[0];
          const eventKey = `judge-${questionId}-${judgeId}`;
          updateJudgment(questionId, data.judge, data.status as Status);
          if (data.status === 'success') {
            if (!loggedEventsRef.current.has(eventKey)) {
              loggedEventsRef.current.add(eventKey);
              if (data.winner) {
                setWinCounts(prev => ({ ...prev, [data.winner]: (prev[data.winner] || 0) + 1 }));
              }
              addLog('success', `${data.judge}: Winner is ${data.winner}`);
            }
          } else if (data.status === 'failed') {
            if (!loggedEventsRef.current.has(eventKey)) {
              loggedEventsRef.current.add(eventKey);
              addLog('error', `${data.judge}: ${data.error}`);
            }
          }
        }
      };

      socket.onerror = (event) => {
        console.error('WebSocket error:', event);
        addLog('error', 'WebSocket connection error');
      };
      socket.onclose = (event) => {
        console.log('WebSocket closed:', event.code, event.reason);
        if (event.code === 4001) {
          window.dispatchEvent(new Event('bellmark-auth-required'));
        }
        addLog('info', event.wasClean ? 'Disconnected from server' : `Connection lost (${event.code})`);
      };

      setWs(socket);
    });

    return () => {
      socket?.close();
      setActiveRun(null);
    };
  }, [runId, setActiveRun, updateStatus, addEvent, navigate, noRedirect]);

  // Polling fallback: check run status periodically in case WebSocket drops
  useEffect(() => {
    if (phase === 'completed' || phase === 'failed' || phase === 'cancelled') return;

    const poll = async () => {
      try {
        const res = await benchmarksApi.get(runId);
        const data = res.data;

        // Sync grid data so dots reflect actual state.
        // Rank-based downgrade protection prevents stale poll responses from
        // regressing dots — EXCEPT when local state is `failed`, which is not
        // actually terminal: the retry checkpoint can revive a failed
        // judgment back into `running` and onward to `success`/`failed`.
        // Without the `failed` exception, retried dots stay red forever.
        const statusRank = (s: string) => s === 'success' || s === 'failed' ? 2 : s === 'running' ? 1 : 0;
        const shouldUpdate = (oldS: string, newS: string) =>
          oldS === 'failed' || statusRank(newS) > statusRank(oldS);
        setBenchmarkData(prev => {
          if (!prev) return prev;
          const newGens = new Map(prev.generations);
          const newGenIds = new Map(prev.generationIds);
          const newJudgments = new Map(prev.judgments);
          for (const question of data.questions || []) {
            for (const gen of question.generations || []) {
              const key = `${question.id}-${gen.model_preset_id}`;
              if (gen.id) newGenIds.set(key, gen.id);
              if (shouldUpdate(newGens.get(key) || 'pending', gen.status)) {
                newGens.set(key, gen.status as Status);
              }
            }
            for (const judge of question.judgments || []) {
              const key = `${question.id}-${judge.judge_preset_id}`;
              if (shouldUpdate(newJudgments.get(key) || 'pending', judge.status)) {
                newJudgments.set(key, judge.status as Status);
              }
            }
          }
          return { ...prev, generations: newGens, judgments: newJudgments, generationIds: newGenIds, status: data.status };
        });

        if (data.status === 'completed') {
          updateStatus('completed', 100);
          addLog('success', 'Benchmark completed!');
          if (!noRedirect) {
            setTimeout(() => navigate(`/runs/${runId}`), 1500);
          }
        } else if (data.status === 'failed') {
          updateStatus('failed', 0);
          addLog('error', 'Benchmark failed');
        } else if (data.status === 'cancelled') {
          updateStatus('cancelled', 0);
        } else if (data.status === 'summarizing') {
          updateStatus('summarizing', 96);
        }
      } catch {
        // Ignore poll errors — WS is the primary channel
      }
    };

    const interval = setInterval(poll, 10_000);
    return () => clearInterval(interval);
  }, [runId, phase, updateStatus, navigate, noRedirect]);

  useEffect(() => {
    if (showLogs) {
      logEndRef.current?.scrollIntoView({ behavior: 'smooth' });
    }
  }, [logs, showLogs]);

  const handleCancel = async () => {
    if (isCancelling) return;

    setIsCancelling(true);
    setShowLogs(true); // Open activity log to show cancellation progress
    addLog('warning', '⏹ Cancellation requested...');

    // Try WebSocket first for immediate response
    if (ws && ws.readyState === WebSocket.OPEN) {
      ws.send(JSON.stringify({ type: 'cancel' }));
    }

    // Also call REST API as backup (WebSocket might not be connected)
    try {
      await benchmarksApi.cancel(runId);

      // Count running tasks that will be killed
      const runningGens = benchmarkData
        ? [...benchmarkData.generations.values()].filter(s => s === 'running').length
        : 0;
      const runningJudgments = benchmarkData
        ? [...benchmarkData.judgments.values()].filter(s => s === 'running').length
        : 0;

      if (runningGens > 0 || runningJudgments > 0) {
        addLog('warning', `🛑 Stopping ${runningGens} generation(s) and ${runningJudgments} judgment(s)...`);
      }

      // Update local state to reflect cancellation
      setBenchmarkData(prev => prev ? { ...prev, status: 'cancelled' } : prev);
      updateStatus('cancelled', 0);
      addLog('info', '✓ Benchmark cancelled');
    } catch (e) {
      addLog('error', `Cancel failed: ${e instanceof Error ? e.message : String(e)}`);
      setIsCancelling(false);
    }
  };

  const handleRetryModel = async (modelId: number) => {
    if (!benchmarkData || retryingModels.has(modelId)) return;

    // Collect failed generation DB IDs for this model
    const failedGenIds: { key: string; dbId: number }[] = [];
    for (const q of benchmarkData.questions) {
      const key = `${q.id}-${modelId}`;
      if (benchmarkData.generations.get(key) === 'failed') {
        const dbId = benchmarkData.generationIds.get(key);
        if (dbId) failedGenIds.push({ key, dbId });
      }
    }
    if (failedGenIds.length === 0) return;

    const modelName = modelNames.get(modelId) || String(modelId);
    setRetryingModels(prev => new Set(prev).add(modelId));
    addLog('warning', `Retrying ${failedGenIds.length} failed generation(s) for ${modelName}...`);

    // Optimistic: flip failed dots to running
    setBenchmarkData(prev => {
      if (!prev) return prev;
      const newGens = new Map(prev.generations);
      for (const { key } of failedGenIds) {
        newGens.set(key, 'running');
      }
      // Clear logged event keys so WS updates get logged
      for (const { key } of failedGenIds) {
        const [qId] = key.split('-');
        loggedEventsRef.current.delete(`gen-${qId}-${modelId}`);
      }
      return { ...prev, generations: newGens };
    });

    // Fire all retry calls in parallel
    const results = await Promise.allSettled(
      failedGenIds.map(({ dbId }) => benchmarksApi.retry(runId, 'generation', dbId))
    );

    // Revert any that failed at the API level
    const apiFailures = failedGenIds.filter((_, i) => results[i].status === 'rejected');
    if (apiFailures.length > 0) {
      setBenchmarkData(prev => {
        if (!prev) return prev;
        const newGens = new Map(prev.generations);
        for (const { key } of apiFailures) newGens.set(key, 'failed');
        return { ...prev, generations: newGens };
      });
      addLog('error', `${apiFailures.length} retry call(s) failed for ${modelName}`);
    }

    setRetryingModels(prev => {
      const next = new Set(prev);
      next.delete(modelId);
      return next;
    });
  };

  const getLogColor = (type: LogEntry['type']) => {
    switch (type) {
      case 'success': return 'text-green-600 dark:text-green-400';
      case 'error': return 'text-red-600 dark:text-red-400';
      case 'warning': return 'text-yellow-600 dark:text-yellow-400';
      default: return 'text-slate-500 dark:text-gray-400';
    }
  };

  // Calculate stats
  const genStats = benchmarkData ? {
    total: benchmarkData.questions.length * benchmarkData.modelIds.length,
    success: [...benchmarkData.generations.values()].filter(s => s === 'success').length,
    failed: [...benchmarkData.generations.values()].filter(s => s === 'failed').length,
    running: [...benchmarkData.generations.values()].filter(s => s === 'running').length,
  } : { total: 0, success: 0, failed: 0, running: 0 };

  const judgeStats = benchmarkData ? {
    total: benchmarkData.questions.length * benchmarkData.judgeIds.length,
    success: [...benchmarkData.judgments.values()].filter(s => s === 'success').length,
    failed: [...benchmarkData.judgments.values()].filter(s => s === 'failed').length,
    running: [...benchmarkData.judgments.values()].filter(s => s === 'running').length,
  } : { total: 0, success: 0, failed: 0, running: 0 };
  const progressMatrixTemplate = benchmarkData ? getProgressMatrixTemplate(benchmarkData.questions.length) : '';

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="flex flex-col sm:flex-row justify-between items-start sm:items-center gap-3">
        <div>
          <h1 className="text-lg md:text-xl font-bold">{benchmarkData?.name || 'Benchmark Progress'}</h1>
          <p className="text-slate-500 dark:text-gray-400 mt-1">
            Run #{runId} • <span className="capitalize">{phase === 'summarizing' ? 'Summarizing results...' : phase}</span>
          </p>
        </div>
        <div className="flex gap-3">
          {(phase === 'completed' || phase === 'failed' || phase === 'cancelled') && (
            <Button variant="outline" onClick={() => navigate(`/runs/${runId}`)}>
              View Results
            </Button>
          )}
          <Button
            variant="destructive"
            onClick={handleCancel}
            disabled={phase === 'completed' || phase === 'failed' || phase === 'cancelled' || isCancelling}
          >
            {phase === 'cancelled' ? 'Cancelled' : isCancelling ? (
              <span className="flex items-center gap-2">
                <span className="w-4 h-4 border-2 border-white border-t-transparent rounded-full animate-spin" />
                Cancelling...
              </span>
            ) : 'Cancel Run'}
          </Button>
        </div>
      </div>

      {/* Status Legend */}
      <div className="flex flex-wrap gap-3 md:gap-6 text-sm">
        <div className="flex items-center gap-2">
          <StatusDot status="pending" />
          <span className="text-slate-500 dark:text-gray-400">Pending</span>
        </div>
        <div className="flex items-center gap-2">
          <StatusDot status="running" />
          <span className="text-slate-500 dark:text-gray-400">Running</span>
        </div>
        <div className="flex items-center gap-2">
          <StatusDot status="success" />
          <span className="text-slate-500 dark:text-gray-400">Success</span>
        </div>
        <div className="flex items-center gap-2">
          <StatusDot status="failed" />
          <span className="text-slate-500 dark:text-gray-400">Failed</span>
        </div>
      </div>

      {/* Generations Grid */}
      {benchmarkData && (
        <Card className="bg-stone-50 dark:bg-gray-800 border-stone-200 dark:border-gray-700">
          <CardHeader className="pb-2">
            <CardTitle className="flex items-center justify-between">
              <span>Generations</span>
              <span className="text-sm font-normal text-slate-500 dark:text-gray-400">
                {genStats.success}/{genStats.total} complete
                {genStats.failed > 0 && <span className="text-red-600 dark:text-red-400 ml-2">({genStats.failed} failed)</span>}
              </span>
            </CardTitle>
          </CardHeader>
          <CardContent className="overflow-x-auto">
            <div
              className="grid w-max min-w-full items-center gap-x-3 gap-y-2.5"
              style={{ gridTemplateColumns: progressMatrixTemplate }}
            >
              <div
                data-testid="generations-matrix-header"
                className="contents"
              >
                <div aria-hidden="true" />
                <div className="min-w-0 text-[11px] font-medium uppercase tracking-[0.08em] text-slate-500 dark:text-gray-500">Model</div>
                <div className="text-center text-[11px] font-medium uppercase tracking-[0.08em] text-slate-500 dark:text-gray-500">Retry</div>
                {benchmarkData.questions.map(q => (
                  <div key={q.id} className="w-3.5 text-center text-[12px] leading-none text-slate-500 dark:text-gray-500 tabular-nums">
                    {q.order + 1}
                  </div>
                ))}
              </div>
              {benchmarkData.modelIds.map(modelId => {
                const fullName = modelNames.get(modelId) || String(modelId);
                const { name, format, quant, host } = parseModelLabel(fullName);
                const isReasoning = reasoningModels.has(modelId);
                const failedCount = benchmarkData.questions.filter(q => {
                  const s = benchmarkData.generations.get(`${q.id}-${modelId}`);
                  return s === 'failed' || (benchmarkData.status === 'cancelled' && s === 'running');
                }).length;
                const isRetrying = retryingModels.has(modelId);
                return (
                  <div
                    key={modelId}
                    data-testid={`generations-row-${modelId}`}
                    className="contents"
                  >
                    <div className="flex h-4 w-4 items-center justify-center text-xs text-slate-700 dark:text-gray-400 sm:text-sm">
                      {isReasoning && <span className="text-violet-500 dark:text-violet-400 leading-none" title="Reasoning model">⚡</span>}
                    </div>
                    <div
                      className="flex min-w-0 items-center gap-2 text-xs leading-none text-slate-700 dark:text-gray-400 sm:text-sm"
                      title={fullName}
                    >
                      <span className="shrink-0 whitespace-nowrap">{name}</span>
                      <div className="flex shrink-0 items-center gap-1">
                        <MatrixBadge value={format} color="#3b82f6" />
                        <MatrixBadge value={quant} color="#f59e0b" />
                        <MatrixBadge value={host} color="#64748b" />
                      </div>
                    </div>
                    <div className="flex min-h-5 items-center justify-center">
                      {failedCount > 0 ? (
                        <button
                          onClick={() => handleRetryModel(modelId)}
                          disabled={isRetrying}
                          className="inline-flex items-center gap-0.5 rounded px-1.5 py-0.5 text-[10px] font-medium text-red-500 transition-colors hover:bg-red-500/20 disabled:cursor-not-allowed disabled:opacity-50"
                          style={{ backgroundColor: 'rgba(239, 68, 68, 0.1)' }}
                          title={`Retry ${failedCount} failed generation(s)`}
                        >
                          {isRetrying ? (
                            <span className="h-2.5 w-2.5 rounded-full border border-red-500 border-t-transparent animate-spin" />
                          ) : (
                            <svg className="h-2.5 w-2.5" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round">
                              <path d="M1 4v6h6" /><path d="M3.51 15a9 9 0 1 0 2.13-9.36L1 10" />
                            </svg>
                          )}
                          {failedCount}
                        </button>
                      ) : (
                        <span aria-hidden="true" className="block h-5 w-px" />
                      )}
                    </div>
                    {benchmarkData.questions.map(q => {
                      let status = benchmarkData.generations.get(`${q.id}-${modelId}`) || 'pending';
                      if (benchmarkData.status === 'cancelled' && status === 'running') {
                        status = 'failed';
                      }
                      return (
                        <div
                          key={q.id}
                          data-testid={`gen-cell-${modelId}-${q.id}`}
                          data-status={status}
                          className="flex w-3.5 justify-center"
                        >
                          <StatusDot status={status} label={`Q${q.order + 1}`} compact />
                        </div>
                      );
                    })}
                  </div>
                );
              })}
            </div>
          </CardContent>
        </Card>
      )}

      {/* Judgments Grid */}
      {benchmarkData && benchmarkData.judgeIds.length > 0 && (
        <Card className="bg-stone-50 dark:bg-gray-800 border-stone-200 dark:border-gray-700">
          <CardHeader className="pb-2">
            <CardTitle className="flex items-center justify-between">
              <span>Judgments</span>
              <span className="text-sm font-normal text-slate-500 dark:text-gray-400">
                {judgeStats.success}/{judgeStats.total} complete
                {judgeStats.failed > 0 && <span className="text-red-600 dark:text-red-400 ml-2">({judgeStats.failed} failed)</span>}
              </span>
            </CardTitle>
          </CardHeader>
          <CardContent className="overflow-x-auto">
            <div
              className="grid w-max min-w-full items-center gap-x-3 gap-y-2.5"
              style={{ gridTemplateColumns: progressMatrixTemplate }}
            >
              <div
                data-testid="judgments-matrix-header"
                className="contents"
              >
                <div aria-hidden="true" />
                <div className="min-w-0 text-[11px] font-medium uppercase tracking-[0.08em] text-slate-500 dark:text-gray-500">Judge</div>
                <div aria-hidden="true" />
                {benchmarkData.questions.map(q => (
                  <div key={q.id} className="w-3.5 text-center text-[12px] leading-none text-slate-500 dark:text-gray-500 tabular-nums">
                    {q.order + 1}
                  </div>
                ))}
              </div>
              {benchmarkData.judgeIds.map(judgeId => {
                const fullName = modelNames.get(judgeId) || String(judgeId);
                const { name, format, quant, host } = parseModelLabel(fullName);
                const isReasoning = reasoningModels.has(judgeId);
                return (
                  <div
                    key={judgeId}
                    data-testid={`judgments-row-${judgeId}`}
                    className="contents"
                  >
                    <div className="flex h-4 w-4 items-center justify-center text-xs text-slate-700 dark:text-gray-400 sm:text-sm">
                      {isReasoning && <span className="text-violet-500 dark:text-violet-400 leading-none" title="Reasoning model">⚡</span>}
                    </div>
                    <div
                      className="flex min-w-0 items-center gap-2 text-xs leading-none text-slate-700 dark:text-gray-400 sm:text-sm"
                      title={fullName}
                    >
                      <span className="shrink-0 whitespace-nowrap">{name}</span>
                      <div className="flex shrink-0 items-center gap-1">
                        <MatrixBadge value={format} color="#3b82f6" />
                        <MatrixBadge value={quant} color="#f59e0b" />
                        <MatrixBadge value={host} color="#64748b" />
                      </div>
                    </div>
                    <span aria-hidden="true" className="block h-5 w-px" />
                    {benchmarkData.questions.map(q => {
                      let status = benchmarkData.judgments.get(`${q.id}-${judgeId}`) || 'pending';
                      if (benchmarkData.status === 'cancelled' && status === 'running') {
                        status = 'failed';
                      }
                      return (
                        <div
                          key={q.id}
                          data-testid={`judge-cell-${judgeId}-${q.id}`}
                          data-status={status}
                          className="flex w-3.5 justify-center"
                        >
                          <StatusDot status={status} label={`Q${q.order + 1}`} compact />
                        </div>
                      );
                    })}
                  </div>
                );
              })}
            </div>
          </CardContent>
        </Card>
      )}

      {/* Live Leaderboard */}
      {Object.keys(winCounts).length > 0 && (
        <Card className="bg-stone-50 dark:bg-gray-800 border-stone-200 dark:border-gray-700">
          <CardHeader className="pb-2">
            <CardTitle className="flex items-center justify-between">
              <span>Live Standings</span>
              <span className="text-sm font-normal text-slate-500 dark:text-gray-400">
                {Object.values(winCounts).reduce((a, b) => a + b, 0)} judgments
              </span>
            </CardTitle>
          </CardHeader>
          <CardContent>
            <div className="space-y-2">
              {(() => {
                const sorted = Object.entries(winCounts).sort(([, a], [, b]) => b - a);
                const maxWins = sorted[0]?.[1] || 1;
                const medals = ['🥇', '🥈', '🥉'];
                return sorted.map(([model, count], i) => (
                  <div key={model} className="flex items-center gap-3">
                    <span className="w-6 text-center text-sm">{medals[i] || ''}</span>
                    <span className="text-sm text-slate-700 dark:text-gray-300 whitespace-nowrap shrink-0" title={model}>{model}</span>
                    <div className="flex-1 h-6 bg-stone-200 dark:bg-gray-700/40 rounded overflow-hidden relative">
                      <div
                        className={`h-full rounded transition-all duration-500 ease-out ${
                          i === 0 ? 'bg-yellow-500/70' : i === 1 ? 'bg-gray-400/50' : i === 2 ? 'bg-amber-700/50' : 'bg-blue-500/30'
                        }`}
                        style={{ width: `${Math.max(4, (count / maxWins) * 100)}%` }}
                      />
                      <span className="absolute inset-y-0 right-2 flex items-center text-xs font-semibold text-white tabular-nums">
                        {count}
                      </span>
                    </div>
                  </div>
                ));
              })()}
            </div>
          </CardContent>
        </Card>
      )}

      {/* Collapsible Activity Log */}
      <Card className="bg-stone-50 dark:bg-gray-800 border-stone-200 dark:border-gray-700">
        <CardHeader
          className="cursor-pointer hover:bg-stone-200 dark:hover:bg-gray-700/50 transition-colors"
          onClick={() => setShowLogs(!showLogs)}
        >
          <CardTitle className="flex items-center justify-between">
            <span>Activity Log ({logs.length})</span>
            <span className="text-slate-500 dark:text-gray-400">{showLogs ? '▼' : '▶'}</span>
          </CardTitle>
        </CardHeader>
        {showLogs && (
          <CardContent>
            <div className="bg-white dark:bg-gray-900 rounded-lg p-4 h-64 overflow-y-auto font-mono text-sm">
              {logs.map((log) => (
                <div key={log.id} className="flex gap-3 py-1">
                  <span className="text-slate-400 dark:text-gray-500 shrink-0">{log.time}</span>
                  <span className={getLogColor(log.type)}>{log.message}</span>
                </div>
              ))}
              <div ref={logEndRef} />
            </div>
          </CardContent>
        )}
      </Card>
    </div>
  );
}
