import { useEffect, useMemo } from 'react';
import { useParams, useSearchParams } from 'react-router-dom';
import { useQuery } from '@tanstack/react-query';
import { Brain } from 'lucide-react';
import { benchmarksApi } from '@/lib/api';
import { useTheme } from '@/lib/theme';
import { computeResultsData } from '@/pages/results/computeResultsData';
import type { BenchmarkDetail } from '@/pages/results/types';
import type { RunStatistics } from '@/types/statistics';

// ──────────────────────────────────────────────────────────────────────────────
// Shared frame — every slide uses this. 1920×1080 canvas, thin rules, logo,
// source line. Intentionally minimal so data fills the page, McKinsey-style.
// ──────────────────────────────────────────────────────────────────────────────

function SlideFrame({
  slideNumber,
  totalSlides,
  sectionLabel,
  runName,
  runId,
  dateStr,
  children,
}: {
  slideNumber: number;
  totalSlides: number;
  sectionLabel: string;
  runName: string;
  runId: number;
  dateStr: string;
  children: React.ReactNode;
}) {
  return (
    <div
      className="bg-background text-foreground font-sans antialiased"
      style={{ width: 1920, height: 1080, overflow: 'hidden' }}
    >
      <div className="flex flex-col h-full px-20 py-12">
        {/* Header */}
        <header className="flex items-center justify-between pb-4 border-b border-border">
          <div className="flex items-center gap-3">
            <img src="/bellmark-logo.svg" alt="" className="h-6 w-6" />
            <span className="font-semibold text-[15px] tracking-tight">BeLLMark</span>
            <span className="text-muted-foreground text-[13px]">·</span>
            <span className="text-muted-foreground text-[13px] uppercase tracking-wider">
              {sectionLabel}
            </span>
          </div>
          <div className="text-muted-foreground text-[12px] tabular-nums">
            {runName} · {dateStr}
          </div>
        </header>

        {/* Content — flex-1 so it fills */}
        <main className="flex-1 pt-8 pb-6 overflow-hidden">{children}</main>

        {/* Footer */}
        <footer className="flex items-center justify-between pt-4 border-t border-border text-[11px] text-muted-foreground">
          <span>bellmark.ai · Run #{runId.toString().padStart(4, '0')}</span>
          <span className="tabular-nums">
            {slideNumber} / {totalSlides}
          </span>
        </footer>
      </div>
    </div>
  );
}

// ──────────────────────────────────────────────────────────────────────────────
// Helpers
// ──────────────────────────────────────────────────────────────────────────────

const formatDate = (iso?: string | null) => {
  if (!iso) return '';
  const d = new Date(iso);
  return d.toLocaleDateString('en-US', { year: 'numeric', month: 'short', day: '2-digit' });
};

const formatCost = (n?: number | null) => {
  if (n == null) return '—';
  if (n === 0) return '$0';
  if (n < 0.01) return `$${n.toFixed(4)}`;
  if (n < 1) return `$${n.toFixed(3)}`;
  return `$${n.toFixed(2)}`;
};

// Strip the "[Reasoning (high)]" / "[Reasoning]" marker; callers render <Brain/> alongside.
// Also strip any trailing (format/quant @ host) meta.
const REASONING_RE = /\s*\[Reasoning[^\]]*\]/i;
const isReasoningModel = (s: string) => REASONING_RE.test(s);
const shortModel = (s: string) => s.replace(REASONING_RE, '').replace(/\s*\(.+\)$/, '').trim();

function ModelLabel({
  label,
  bold = false,
  iconClass = 'h-3.5 w-3.5',
}: {
  label: string;
  bold?: boolean;
  iconClass?: string;
}) {
  const reasoning = isReasoningModel(label);
  const clean = shortModel(label);
  return (
    <span className={`inline-flex items-center gap-1.5 ${bold ? 'font-semibold' : ''}`}>
      {reasoning && (
        <Brain
          className={`${iconClass} text-muted-foreground shrink-0`}
          strokeWidth={1.75}
        />
      )}
      <span>{clean}</span>
    </span>
  );
}

// ──────────────────────────────────────────────────────────────────────────────
// Slide 1 — COVER
// ──────────────────────────────────────────────────────────────────────────────

function CoverSlide({
  benchmark,
  computed,
  statistics,
  dateStr,
}: {
  benchmark: BenchmarkDetail;
  computed: ReturnType<typeof computeResultsData>;
  statistics?: RunStatistics;
  dateStr: string;
}) {
  const nModels = benchmark.model_ids.length;
  const nJudges = benchmark.judge_ids.length;
  const nQ = benchmark.questions.length;
  const nCrit = benchmark.criteria.length;
  const ranked = computed.rankedModelData;
  const winner = ranked[0];
  const winnerStats = statistics?.model_statistics.find(
    (m) => m.model_name === winner?.model
  );
  const winnerCI = winnerStats?.weighted_score_ci;
  const totalSpend =
    Object.values(benchmark.performance_metrics || {}).reduce(
      (s, m) => s + (m.estimated_cost || 0),
      0
    ) +
    Object.values(benchmark.judge_metrics || {}).reduce(
      (s, m) => s + (m.estimated_cost || 0),
      0
    );

  // Count models statistically tied with winner (CI upper overlaps winner CI lower)
  const nTied = statistics?.model_statistics
    ? statistics.model_statistics.filter(
        (m) =>
          m.weighted_score_ci &&
          winnerCI &&
          m.weighted_score_ci.upper >= winnerCI.lower
      ).length
    : 1;

  return (
    <div
      className="bg-background text-foreground font-sans antialiased relative"
      style={{ width: 1920, height: 1080, overflow: 'hidden' }}
    >
      <div className="flex flex-col h-full px-20 py-12">
        {/* Top bar — brand + classification */}
        <header className="flex items-center justify-between pb-5 border-b border-border">
          <div className="flex items-center gap-3">
            <img src="/bellmark-logo.svg" alt="" className="h-9 w-9" />
            <span className="font-semibold text-[20px] tracking-tight">BeLLMark</span>
          </div>
          <div className="flex items-center gap-2 text-[11px] uppercase tracking-[0.22em] text-muted-foreground">
            <span className="w-1.5 h-1.5 rounded-full bg-muted-foreground/50" />
            Internal · Not for distribution
          </div>
        </header>

        {/* Main grid */}
        <div className="flex-1 grid grid-cols-12 gap-14 pt-16">
          {/* Left column — title + subtitle + key finding */}
          <div className="col-span-8 flex flex-col">
            <div className="text-[13px] uppercase tracking-[0.25em] text-muted-foreground mb-7">
              Model Evaluation Report
            </div>
            <h1 className="text-[84px] font-semibold leading-[1.02] tracking-tight mb-8">
              {benchmark.name}
            </h1>
            <p className="text-[20px] text-muted-foreground leading-normal max-w-[900px] mb-auto">
              Blind shuffled-label comparison of {nModels} large language models across {nQ}{' '}
              prompts, evaluated by {nJudges} independent judges against {nCrit} rubric
              criteria.
            </p>

            {/* Key finding block — the cover's hero sentence */}
            {winner && (
              <div className="border-t border-border pt-8 mt-8">
                <div className="text-[11px] uppercase tracking-[0.22em] text-muted-foreground mb-3">
                  Key finding
                </div>
                <div className="text-[22px] leading-snug max-w-[1100px]">
                  <span className="inline-flex items-baseline gap-2 font-semibold">
                    <ModelLabel label={winner.model} iconClass="h-5 w-5 translate-y-0.5" />
                  </span>{' '}
                  leads at{' '}
                  <span className="font-semibold tabular-nums">
                    {winner.score.toFixed(2)} / 10
                  </span>
                  {winnerCI && (
                    <span className="text-muted-foreground">
                      {' '}
                      (95% CI {winnerCI.lower.toFixed(2)}–{winnerCI.upper.toFixed(2)})
                    </span>
                  )}
                  .{' '}
                  {nTied > 1 ? (
                    <>
                      Top {nTied} models are statistically indistinguishable within 95% CI —
                      decision pivots on cost and latency.
                    </>
                  ) : (
                    <>Decisive lead; no overlap with the rest of the field at 95% CI.</>
                  )}
                </div>
              </div>
            )}
          </div>

          {/* Right column — scope tiles + top-3 teaser */}
          <div className="col-span-4 flex flex-col gap-6">
            <div className="grid grid-cols-2 gap-4">
              {[
                { label: 'Candidates', value: nModels },
                { label: 'Prompts', value: nQ },
                { label: 'Judges', value: nJudges },
                { label: 'Rubric criteria', value: nCrit },
                { label: 'Total spend', value: formatCost(totalSpend) },
                { label: 'Mode', value: benchmark.judge_mode },
              ].map((s) => (
                <div
                  key={s.label}
                  className="border border-border rounded-lg px-4 py-3"
                >
                  <div className="text-[10px] uppercase tracking-[0.15em] text-muted-foreground mb-1.5">
                    {s.label}
                  </div>
                  <div className="text-[22px] font-semibold tabular-nums leading-none capitalize">
                    {s.value}
                  </div>
                </div>
              ))}
            </div>

            {/* Top-3 teaser bar chart */}
            <div className="border border-border rounded-lg p-5 flex-1">
              <div className="text-[10px] uppercase tracking-[0.15em] text-muted-foreground mb-4">
                Podium · Weighted score
              </div>
              <div className="space-y-4">
                {ranked.slice(0, 3).map((r, i) => {
                  const pct = (r.score / 10) * 100;
                  return (
                    <div key={r.model}>
                      <div className="flex items-baseline justify-between mb-1.5">
                        <div className="flex items-center gap-2 text-[13px] truncate max-w-[240px]">
                          <span className="text-muted-foreground tabular-nums text-[11px]">
                            {i + 1}.
                          </span>
                          <ModelLabel label={r.model} iconClass="h-3 w-3" />
                        </div>
                        <div className="tabular-nums font-semibold text-[13px]">
                          {r.score.toFixed(2)}
                        </div>
                      </div>
                      <div className="h-1.5 rounded-full bg-muted overflow-hidden">
                        <div
                          className="h-full bg-foreground/70"
                          style={{ width: `${pct}%` }}
                        />
                      </div>
                    </div>
                  );
                })}
              </div>
              <div className="text-[11px] text-muted-foreground mt-4 pt-4 border-t border-border/60">
                Mean weighted score across {nCrit} criteria × {nJudges} judges.
              </div>
            </div>
          </div>
        </div>

        {/* Footer */}
        <footer className="flex items-end justify-between border-t border-border pt-5 mt-8">
          <div className="text-[12px] text-muted-foreground">
            BeLLMark Run #{benchmark.id.toString().padStart(4, '0')} · bellmark.ai · Blind
            shuffled-label comparison
          </div>
          <div className="text-[12px] tabular-nums text-muted-foreground">{dateStr}</div>
        </footer>
      </div>
    </div>
  );
}

// ──────────────────────────────────────────────────────────────────────────────
// Slide 2 — EXECUTIVE SUMMARY
// ──────────────────────────────────────────────────────────────────────────────

function ExecutiveSlide({
  benchmark,
  computed,
  statistics,
  dateStr,
}: {
  benchmark: BenchmarkDetail;
  computed: ReturnType<typeof computeResultsData>;
  statistics?: RunStatistics;
  dateStr: string;
}) {
  const ranked = computed.rankedModelData;
  const winner = ranked[0];
  const secondBest = ranked[1];
  const winnerStats = statistics?.model_statistics.find(
    (m) => m.model_name === winner?.model
  );
  const winnerCI = winnerStats?.weighted_score_ci;

  const totalCost = Object.values(benchmark.performance_metrics || {}).reduce(
    (s, m) => s + (m.estimated_cost || 0),
    0
  );
  const judgeCost = Object.values(benchmark.judge_metrics || {}).reduce(
    (s, m) => s + (m.estimated_cost || 0),
    0
  );

  // Cost per prompt for each top-3 to surface the price-quality story
  const costOf = (model: string) =>
    (benchmark.performance_metrics?.[model]?.estimated_cost ?? 0) / Math.max(1, benchmark.questions.length);

  // Find statistically indistinguishable top cluster
  const ciOverlapCount = statistics?.model_statistics
    ? statistics.model_statistics.filter((m) => {
        if (!m.weighted_score_ci || !winnerCI) return false;
        return m.weighted_score_ci.upper >= winnerCI.lower;
      }).length
    : 1;

  const takeawayLine =
    ranked.length >= 2 && secondBest && winner
      ? `Top ${ciOverlapCount} models are statistically indistinguishable within 95% CI; decision therefore pivots on cost and latency.`
      : 'Single-candidate run — see appendix for absolute-score methodology.';

  return (
    <SlideFrame
      slideNumber={2}
      totalSlides={7}
      sectionLabel="Executive Summary"
      runName={benchmark.name}
      runId={benchmark.id}
      dateStr={dateStr}
    >
      {/* Title with the takeaway — action-oriented, not decorative */}
      <h2 className="text-[34px] font-semibold leading-tight tracking-tight max-w-[1500px] mb-8">
        {winner ? shortModel(winner.model) : 'No winner'} leads the leaderboard, but the top
        cluster is a statistical tie — cost is the tiebreaker.
      </h2>

      <div className="grid grid-cols-12 gap-6 h-[calc(100%-140px)]">
        {/* Left: winner callout */}
        <div className="col-span-5 border border-border rounded-lg p-8 flex flex-col">
          <div className="text-[11px] uppercase tracking-wider text-muted-foreground mb-3">
            Ranked #1 · Weighted score
          </div>
          {winner && (
            <>
              <div className="text-[28px] font-semibold leading-tight mb-1">
                <ModelLabel label={winner.model} iconClass="h-6 w-6" />
              </div>
              <div className="flex items-baseline gap-3 mb-4">
                <div className="text-[72px] font-semibold tabular-nums leading-none">
                  {winner.score.toFixed(2)}
                </div>
                {winnerCI && (
                  <div className="text-[15px] text-muted-foreground tabular-nums">
                    95% CI [{winnerCI.lower.toFixed(2)} – {winnerCI.upper.toFixed(2)}]
                  </div>
                )}
              </div>
              <div className="text-[13px] text-muted-foreground mt-auto">
                Bootstrap CI · n=10,000 resamples · weighted across {benchmark.criteria.length}{' '}
                criteria × {benchmark.judge_ids.length} judges.
              </div>
            </>
          )}
        </div>

        {/* Right: three stat blocks + narrative */}
        <div className="col-span-7 flex flex-col gap-6">
          <div className="grid grid-cols-3 gap-4">
            <div className="border border-border rounded-lg p-5">
              <div className="text-[11px] uppercase tracking-wider text-muted-foreground mb-2">
                Total spend
              </div>
              <div className="text-[32px] font-semibold tabular-nums leading-none">
                {formatCost(totalCost + judgeCost)}
              </div>
              <div className="text-[12px] text-muted-foreground mt-2">
                {formatCost(totalCost)} gen · {formatCost(judgeCost)} judge
              </div>
            </div>
            <div className="border border-border rounded-lg p-5">
              <div className="text-[11px] uppercase tracking-wider text-muted-foreground mb-2">
                Top cluster
              </div>
              <div className="text-[32px] font-semibold tabular-nums leading-none">
                {ciOverlapCount} tied
              </div>
              <div className="text-[12px] text-muted-foreground mt-2">
                CIs overlap at 95% — no single dominant winner
              </div>
            </div>
            <div className="border border-border rounded-lg p-5">
              <div className="text-[11px] uppercase tracking-wider text-muted-foreground mb-2">
                Sample size
              </div>
              <div className="text-[32px] font-semibold tabular-nums leading-none">
                {benchmark.questions.length}
              </div>
              <div className="text-[12px] text-muted-foreground mt-2">
                Prompts × {benchmark.judge_ids.length} judges = {benchmark.questions.length *
                  benchmark.judge_ids.length}{' '}
                judgments
              </div>
            </div>
          </div>

          {/* Top-3 price-quality comparison */}
          <div className="border border-border rounded-lg p-6 flex-1">
            <div className="text-[11px] uppercase tracking-wider text-muted-foreground mb-3">
              Top 3 · Quality vs cost per prompt
            </div>
            <div className="space-y-3">
              {ranked.slice(0, 3).map((r) => {
                const cpp = costOf(r.model);
                const barPct = (r.score / 10) * 100;
                return (
                  <div key={r.model} className="grid grid-cols-12 items-center gap-4">
                    <div className="col-span-5 text-[14px] font-medium truncate">
                      <ModelLabel label={r.model} />
                    </div>
                    <div className="col-span-5 h-2 rounded-full bg-muted overflow-hidden">
                      <div
                        className="h-full bg-foreground/70"
                        style={{ width: `${barPct}%` }}
                      />
                    </div>
                    <div className="col-span-2 text-right tabular-nums text-[13px]">
                      <div className="font-semibold">{r.score.toFixed(2)}</div>
                      <div className="text-muted-foreground text-[11px]">{formatCost(cpp)}/prompt</div>
                    </div>
                  </div>
                );
              })}
            </div>
          </div>

          {/* Takeaway */}
          <div className="text-[14px] leading-relaxed text-foreground">{takeawayLine}</div>
        </div>
      </div>
    </SlideFrame>
  );
}

// ──────────────────────────────────────────────────────────────────────────────
// Slide 3 — LEADERBOARD (full ranked table + bars)
// ──────────────────────────────────────────────────────────────────────────────

function LeaderboardSlide({
  benchmark,
  computed,
  statistics,
  dateStr,
}: {
  benchmark: BenchmarkDetail;
  computed: ReturnType<typeof computeResultsData>;
  statistics?: RunStatistics;
  dateStr: string;
}) {
  const ranked = computed.rankedModelData;

  const statsMap = new Map(
    (statistics?.model_statistics || []).map((m) => [m.model_name, m])
  );
  const maxCost = Math.max(
    1e-6,
    ...Object.values(benchmark.performance_metrics || {}).map((p) => p.estimated_cost || 0)
  );

  return (
    <SlideFrame
      slideNumber={3}
      totalSlides={7}
      sectionLabel="Ranking"
      runName={benchmark.name}
      runId={benchmark.id}
      dateStr={dateStr}
    >
      <h2 className="text-[30px] font-semibold tracking-tight mb-2">
        Full leaderboard — weighted score, Wilson win rate, cost per prompt
      </h2>
      <p className="text-[13px] text-muted-foreground mb-6">
        Mean weighted score across {benchmark.criteria.length} criteria · Bootstrap 95% CI ·
        Wilson 95% CI for win rates · n={benchmark.questions.length} prompts.
      </p>

      <div className="border border-border rounded-lg overflow-hidden">
        <table className="w-full text-[14px] tabular-nums">
          <thead className="bg-muted/40 border-b border-border text-[11px] uppercase tracking-wider text-muted-foreground">
            <tr>
              <th className="text-left py-3 px-4 w-[40px]">#</th>
              <th className="text-left py-3 px-4">Model</th>
              <th className="text-right py-3 px-4 w-[120px]">Mean</th>
              <th className="text-left py-3 px-4 w-[320px]">95% CI</th>
              <th className="text-right py-3 px-4 w-[120px]">Win rate</th>
              <th className="text-right py-3 px-4 w-[120px]">LC win rate</th>
              <th className="text-right py-3 px-4 w-[140px]">$/prompt</th>
            </tr>
          </thead>
          <tbody>
            {ranked.map((r, idx) => {
              const s = statsMap.get(r.model);
              const ci = s?.weighted_score_ci;
              const lc = s?.lc_win_rate;
              const cpp =
                (benchmark.performance_metrics?.[r.model]?.estimated_cost ?? 0) /
                Math.max(1, benchmark.questions.length);
              const costBarPct = (cpp / (maxCost / benchmark.questions.length)) * 100;

              // CI bar — positioned on a 0..10 axis
              const ciLowerPct = ci ? (ci.lower / 10) * 100 : 0;
              const ciUpperPct = ci ? (ci.upper / 10) * 100 : 0;
              const meanPct = (r.score / 10) * 100;

              return (
                <tr
                  key={r.model}
                  className={`border-b border-border/60 ${
                    idx === 0 ? 'bg-foreground/[0.03]' : ''
                  }`}
                >
                  <td className="py-3 px-4 text-muted-foreground">{idx + 1}</td>
                  <td className={`py-3 px-4 ${idx === 0 ? 'font-semibold' : ''}`}>
                    <ModelLabel label={r.model} bold={idx === 0} />
                  </td>
                  <td className="py-3 px-4 text-right font-semibold">{r.score.toFixed(2)}</td>
                  <td className="py-3 px-4">
                    <div className="relative h-2 bg-muted rounded-full">
                      {ci && (
                        <div
                          className="absolute h-2 bg-foreground/20 rounded-full"
                          style={{
                            left: `${ciLowerPct}%`,
                            width: `${ciUpperPct - ciLowerPct}%`,
                          }}
                        />
                      )}
                      <div
                        className="absolute w-[3px] h-3 bg-foreground -top-[2px] rounded-sm"
                        style={{ left: `calc(${meanPct}% - 1.5px)` }}
                      />
                    </div>
                    {ci && (
                      <div className="text-[11px] text-muted-foreground mt-1">
                        {ci.lower.toFixed(2)} – {ci.upper.toFixed(2)}
                      </div>
                    )}
                  </td>
                  <td className="py-3 px-4 text-right">
                    {s && s.win_rate != null ? (
                      <>
                        <div>{(s.win_rate * 100).toFixed(0)}%</div>
                        {s.win_rate_ci && (
                          <div className="text-[11px] text-muted-foreground">
                            [{(s.win_rate_ci.lower * 100).toFixed(0)} – {(s.win_rate_ci.upper * 100).toFixed(0)}]
                          </div>
                        )}
                      </>
                    ) : (
                      '—'
                    )}
                  </td>
                  <td className="py-3 px-4 text-right">
                    {lc ? (
                      <div className="flex items-center justify-end gap-1">
                        {lc.length_bias_detected && (
                          <span
                            className="text-[11px]"
                            style={{ color: 'oklch(0.646 0.222 41.116)' }}
                            title={`Length bias: ${lc.n_flagged}/${lc.n_total} wins discounted`}
                          >
                            ⚠
                          </span>
                        )}
                        {(lc.lc_win_rate * 100).toFixed(0)}%
                      </div>
                    ) : (
                      '—'
                    )}
                  </td>
                  <td className="py-3 px-4 text-right">
                    <div className="flex items-center justify-end gap-2">
                      <div className="relative h-1.5 w-16 bg-muted rounded-full overflow-hidden">
                        <div
                          className="h-full bg-foreground/50"
                          style={{ width: `${Math.min(100, costBarPct)}%` }}
                        />
                      </div>
                      <span className="w-14 text-right">{formatCost(cpp)}</span>
                    </div>
                  </td>
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>

      <div className="mt-4 text-[11px] text-muted-foreground">
        Sources: <code>statistics.model_statistics</code> · <code>performance_metrics</code>. LC
        win rate discounts wins where the winner was significantly longer than the loser (verbosity
        bias control).
      </div>
    </SlideFrame>
  );
}

// ──────────────────────────────────────────────────────────────────────────────
// Slide 4 — PER-CRITERION BREAKDOWN (heatmap)
// ──────────────────────────────────────────────────────────────────────────────

function CriteriaSlide({
  benchmark,
  computed,
  dateStr,
}: {
  benchmark: BenchmarkDetail;
  computed: ReturnType<typeof computeResultsData>;
  dateStr: string;
}) {
  const ranked = computed.rankedModelData;
  const criteria = benchmark.criteria;
  const { modelScores } = computed;
  const { theme } = useTheme();
  const isDark = theme === 'dark';

  // Compute avg per (model, criterion)
  const matrix: Record<string, Record<string, number | null>> = {};
  ranked.forEach((r) => {
    matrix[r.model] = {};
    criteria.forEach((c) => {
      const arr = modelScores[r.model]?.[c.name] || [];
      matrix[r.model][c.name] =
        arr.length > 0 ? arr.reduce((a, b) => a + b, 0) / arr.length : null;
    });
  });

  const cellBg = (score: number | null) => {
    if (score == null) return 'transparent';
    // Gradient from muted (low) to foreground (high) — no rainbow. Consulting palette.
    const t = Math.max(0, Math.min(1, (score - 5) / 5)); // 5→0, 10→1
    // In light mode: lighter → darker neutral. In dark mode: darker → lighter.
    return isDark
      ? `oklch(${0.25 + t * 0.55} 0 0)`
      : `oklch(${0.97 - t * 0.5} 0 0)`;
  };
  const cellFg = (score: number | null) => {
    if (score == null) return 'var(--muted-foreground)';
    const t = Math.max(0, Math.min(1, (score - 5) / 5));
    // Flip text color for readability
    return isDark
      ? t > 0.5
        ? 'oklch(0.15 0 0)'
        : 'oklch(0.985 0 0)'
      : t > 0.6
        ? 'oklch(0.985 0 0)'
        : 'oklch(0.145 0 0)';
  };

  // Best-in-class per criterion
  const bestPerCriterion: Record<string, string> = {};
  criteria.forEach((c) => {
    let bestModel = '';
    let bestScore = -Infinity;
    ranked.forEach((r) => {
      const v = matrix[r.model][c.name];
      if (v != null && v > bestScore) {
        bestScore = v;
        bestModel = r.model;
      }
    });
    bestPerCriterion[c.name] = bestModel;
  });

  return (
    <SlideFrame
      slideNumber={4}
      totalSlides={7}
      sectionLabel="Per-Criterion"
      runName={benchmark.name}
      runId={benchmark.id}
      dateStr={dateStr}
    >
      <h2 className="text-[30px] font-semibold tracking-tight mb-2">
        Where each model wins — criterion-level heatmap
      </h2>
      <p className="text-[13px] text-muted-foreground mb-6">
        Mean score (0–10) per model × rubric criterion. Darker cells = stronger performance. Best
        model per criterion highlighted with rule below.
      </p>

      <div className="border border-border rounded-lg overflow-hidden">
        <table className="w-full text-[13px] tabular-nums">
          <thead className="bg-muted/40 border-b border-border text-[11px] uppercase tracking-wider text-muted-foreground">
            <tr>
              <th className="text-left py-3 px-4 w-[320px]">Model</th>
              {criteria.map((c) => (
                <th key={c.name} className="text-center py-3 px-2">
                  {c.name}
                  {c.weight !== 1.0 && (
                    <span className="block text-[9px] normal-case opacity-70">×{c.weight}</span>
                  )}
                </th>
              ))}
              <th className="text-right py-3 px-4 w-[100px]">Weighted</th>
            </tr>
          </thead>
          <tbody>
            {ranked.map((r, idx) => (
              <tr key={r.model} className="border-b border-border/60">
                <td className={`py-3 px-4 ${idx === 0 ? 'font-semibold' : ''}`}>
                  <span className="text-muted-foreground mr-2">{idx + 1}</span>
                  <ModelLabel label={r.model} bold={idx === 0} />
                </td>
                {criteria.map((c) => {
                  const v = matrix[r.model][c.name];
                  const isBest = bestPerCriterion[c.name] === r.model;
                  return (
                    <td
                      key={c.name}
                      className="text-center py-2 px-2"
                      style={{ backgroundColor: cellBg(v), color: cellFg(v) }}
                    >
                      <div className={`font-semibold text-[15px] ${isBest ? 'underline decoration-2 underline-offset-4' : ''}`}>
                        {v != null ? v.toFixed(1) : '—'}
                      </div>
                    </td>
                  );
                })}
                <td className="py-3 px-4 text-right font-semibold">{r.score.toFixed(2)}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      {/* Best-in-class row */}
      <div className="mt-6 border border-border rounded-lg p-4">
        <div className="text-[11px] uppercase tracking-wider text-muted-foreground mb-3">
          Best-in-class per criterion
        </div>
        <div className="grid gap-x-8 gap-y-2" style={{ gridTemplateColumns: `repeat(${criteria.length}, minmax(0, 1fr))` }}>
          {criteria.map((c) => (
            <div key={c.name}>
              <div className="text-[11px] text-muted-foreground">{c.name}</div>
              <div className="text-[14px] font-medium truncate">
                {bestPerCriterion[c.name] ? <ModelLabel label={bestPerCriterion[c.name]} /> : '—'}
              </div>
            </div>
          ))}
        </div>
      </div>
    </SlideFrame>
  );
}

// ──────────────────────────────────────────────────────────────────────────────
// Slide 5 — STATISTICAL RIGOR
// (methodology paragraph + pairwise significance matrix with Holm-corrected stars)
// ──────────────────────────────────────────────────────────────────────────────

function StatsRigorSlide({
  benchmark,
  statistics,
  dateStr,
}: {
  benchmark: BenchmarkDetail;
  statistics?: RunStatistics;
  dateStr: string;
}) {
  const pairwise = statistics?.pairwise_comparisons || [];
  const models =
    statistics?.model_statistics?.map((m) => m.model_name).slice(0, 8) || [];

  // Build lookup: { modelA: { modelB: comparison } }
  const lookup: Record<string, Record<string, (typeof pairwise)[number]>> = {};
  pairwise.forEach((p) => {
    if (!lookup[p.model_a]) lookup[p.model_a] = {};
    if (!lookup[p.model_b]) lookup[p.model_b] = {};
    lookup[p.model_a][p.model_b] = p;
    lookup[p.model_b][p.model_a] = p;
  });

  const sigColor = (p: (typeof pairwise)[number] | undefined, rowModel: string) => {
    if (!p || p.adjusted_p == null) return 'transparent';
    const sig = p.adjusted_p < 0.05;
    if (!sig) return 'transparent';
    const rowIsA = p.model_a === rowModel;
    const cohenD = p.cohens_d ?? 0;
    const rowLeads = rowIsA ? cohenD > 0 : cohenD < 0;
    return rowLeads ? 'oklch(0.7 0.12 142 / 0.18)' : 'oklch(0.65 0.18 25 / 0.18)';
  };

  return (
    <SlideFrame
      slideNumber={5}
      totalSlides={7}
      sectionLabel="Statistical Rigor"
      runName={benchmark.name}
      runId={benchmark.id}
      dateStr={dateStr}
    >
      <h2 className="text-[30px] font-semibold tracking-tight mb-2">
        Methodology &amp; pairwise significance
      </h2>
      <p className="text-[13px] text-muted-foreground mb-6 max-w-[1500px]">
        Blind shuffled-label comparison judging (presentation order randomised per prompt,
        uncorrelated with blind labels). <strong className="text-foreground">Wilson 95% CI</strong>{' '}
        for win rates. <strong className="text-foreground">Bootstrap 95% CI</strong> (n=10,000
        resamples) for score differences. <strong className="text-foreground">Wilcoxon signed-rank</strong>{' '}
        test (paired, two-sided) for pairwise comparisons.{' '}
        <strong className="text-foreground">Holm-Bonferroni</strong> correction for multiple
        comparisons. <strong className="text-foreground">Cohen&apos;s d</strong> for effect size
        (|d| &lt; 0.2 negligible, 0.2–0.5 small, 0.5–0.8 medium, &gt; 0.8 large).
      </p>

      <div className="grid grid-cols-12 gap-6 h-[calc(100%-180px)]">
        {/* Matrix */}
        <div className="col-span-8 border border-border rounded-lg overflow-hidden">
          <div className="text-[11px] uppercase tracking-wider text-muted-foreground px-4 py-3 border-b border-border bg-muted/40">
            Pairwise · Cohen's d (row vs col) · Holm-corrected p-value
          </div>
          <table className="w-full text-[12px] tabular-nums">
            <thead>
              <tr className="border-b border-border">
                <th className="text-left py-2 px-3 text-muted-foreground font-normal w-[220px]"></th>
                {models.map((_m, i) => (
                  <th
                    key={i}
                    className="text-center py-2 px-2 text-muted-foreground font-medium text-[12px]"
                  >
                    M{i + 1}
                  </th>
                ))}
              </tr>
            </thead>
            <tbody>
              {models.map((rowM, rowIdx) => (
                <tr key={rowM} className="border-b border-border/40">
                  <td className="py-2 px-3 text-[11px] max-w-[220px]">
                    <div className="flex items-center gap-2">
                      <span className="text-muted-foreground font-medium tabular-nums w-[28px]">
                        M{rowIdx + 1}
                      </span>
                      <span className="truncate">
                        <ModelLabel label={rowM} iconClass="h-3 w-3" />
                      </span>
                    </div>
                  </td>
                  {models.map((colM) => {
                    if (rowM === colM) {
                      return (
                        <td
                          key={colM}
                          className="text-center py-2 px-2 text-muted-foreground text-[10px]"
                          style={{ backgroundColor: 'var(--muted)' }}
                        >
                          —
                        </td>
                      );
                    }
                    const p = lookup[rowM]?.[colM];
                    const rowIsA = p?.model_a === rowM;
                    const d = p ? (rowIsA ? p.cohens_d : -(p.cohens_d ?? 0)) : null;
                    const holm = p?.adjusted_p;
                    const sig = holm != null && holm < 0.05;
                    return (
                      <td
                        key={colM}
                        className="text-center py-1 px-1"
                        style={{ backgroundColor: sigColor(p, rowM) }}
                      >
                        {d != null ? (
                          <>
                            <div className={`font-semibold ${sig ? '' : 'opacity-50'}`}>
                              {d > 0 ? '+' : ''}
                              {d.toFixed(2)}
                              {sig && <span className="ml-0.5 text-[10px]">*</span>}
                            </div>
                            {holm != null && (
                              <div className="text-[9px] text-muted-foreground">
                                p={holm < 0.001 ? '<.001' : holm.toFixed(3)}
                              </div>
                            )}
                          </>
                        ) : (
                          <span className="text-muted-foreground text-[10px]">·</span>
                        )}
                      </td>
                    );
                  })}
                </tr>
              ))}
            </tbody>
          </table>
        </div>

        {/* Legend + interpretation */}
        <div className="col-span-4 flex flex-col gap-4">
          <div className="border border-border rounded-lg p-5">
            <div className="text-[11px] uppercase tracking-wider text-muted-foreground mb-3">
              How to read
            </div>
            <div className="space-y-3 text-[13px]">
              <div className="flex items-center gap-3">
                <div
                  className="w-6 h-6 rounded"
                  style={{ backgroundColor: 'oklch(0.7 0.12 142 / 0.18)' }}
                />
                <span>Row model significantly ahead (Holm p &lt; 0.05)</span>
              </div>
              <div className="flex items-center gap-3">
                <div
                  className="w-6 h-6 rounded"
                  style={{ backgroundColor: 'oklch(0.65 0.18 25 / 0.18)' }}
                />
                <span>Row model significantly behind</span>
              </div>
              <div className="flex items-center gap-3">
                <div className="w-6 h-6 rounded bg-muted border border-border" />
                <span>No significant difference (CIs overlap)</span>
              </div>
            </div>
          </div>

          <div className="border border-border rounded-lg p-5 flex-1">
            <div className="text-[11px] uppercase tracking-wider text-muted-foreground mb-3">
              Effect size (Cohen&apos;s d)
            </div>
            <div className="space-y-2 text-[13px]">
              <div className="flex justify-between">
                <span>Negligible</span>
                <span className="tabular-nums text-muted-foreground">|d| &lt; 0.20</span>
              </div>
              <div className="flex justify-between">
                <span>Small</span>
                <span className="tabular-nums text-muted-foreground">0.20 – 0.50</span>
              </div>
              <div className="flex justify-between">
                <span>Medium</span>
                <span className="tabular-nums text-muted-foreground">0.50 – 0.80</span>
              </div>
              <div className="flex justify-between">
                <span>Large</span>
                <span className="tabular-nums text-muted-foreground">&gt; 0.80</span>
              </div>
            </div>
            <div className="text-[11px] text-muted-foreground mt-4 pt-4 border-t border-border/60">
              Matrix values are row-oriented: positive = row leads, negative = row trails. Stars
              mark Holm-significant pairs.
            </div>
          </div>
        </div>
      </div>
    </SlideFrame>
  );
}

// ──────────────────────────────────────────────────────────────────────────────
// Slide 6 — BIAS & CALIBRATION
// ──────────────────────────────────────────────────────────────────────────────

function BiasSlide({
  benchmark,
  biasData,
  dateStr,
}: {
  benchmark: BenchmarkDetail;
  biasData?: unknown;
  dateStr: string;
}) {
  type BiasInd = { severity?: string; correlation?: number | null; p_value?: number | null };
  const bias = biasData as
    | {
        position_bias?: BiasInd;
        length_bias?: BiasInd;
        self_preference?: BiasInd;
        verbosity_bias?: BiasInd;
      }
    | undefined;
  const isDetected = (b?: BiasInd) => b?.severity != null && b.severity !== 'none';

  const kappa = benchmark.kappa_value;
  const kappaType = benchmark.kappa_type;
  const kappaInterp =
    kappa == null
      ? 'n/a'
      : kappa > 0.8
        ? 'almost perfect'
        : kappa > 0.6
          ? 'substantial'
          : kappa > 0.4
            ? 'moderate'
            : kappa > 0.2
              ? 'fair'
              : 'slight';

  const agreement = benchmark.judge_summary?.agreement_rate;

  const fmtR = (v: number | null | undefined, letter = 'r') =>
    v == null ? '—' : `${letter} = ${v.toFixed(3)}`;
  const diagnostics = [
    {
      label: 'Position bias',
      detected: isDetected(bias?.position_bias),
      stat: fmtR(bias?.position_bias?.correlation ?? null, 'r'),
      p: bias?.position_bias?.p_value ?? undefined,
      hint: 'Presentation order effect on scores',
    },
    {
      label: 'Length bias',
      detected: isDetected(bias?.length_bias),
      stat: fmtR(bias?.length_bias?.correlation ?? null, 'ρ'),
      p: bias?.length_bias?.p_value ?? undefined,
      hint: 'Response length correlation with scores',
    },
    {
      label: 'Self-preference',
      detected: isDetected(bias?.self_preference),
      stat: fmtR(bias?.self_preference?.correlation ?? null, 'r'),
      p: bias?.self_preference?.p_value ?? undefined,
      hint: 'Same-provider judge-model favouritism',
    },
    {
      label: 'Verbosity bias',
      detected: isDetected(bias?.verbosity_bias),
      stat: fmtR(bias?.verbosity_bias?.correlation ?? null, 'r'),
      p: bias?.verbosity_bias?.p_value ?? undefined,
      hint: 'Judge-reasoning length effect on scores',
    },
  ];

  return (
    <SlideFrame
      slideNumber={6}
      totalSlides={7}
      sectionLabel="Bias &amp; Calibration"
      runName={benchmark.name}
      runId={benchmark.id}
      dateStr={dateStr}
    >
      <h2 className="text-[30px] font-semibold tracking-tight mb-2">
        Bias diagnostics &amp; judge calibration
      </h2>
      <p className="text-[13px] text-muted-foreground mb-6 max-w-[1500px]">
        Four bias panels run against every result. Non-detection is not proof of absence — it
        means no effect reached the significance threshold at this sample size. All diagnostics
        are disclosed to avoid silent confounds.
      </p>

      {/* 2×2 bias grid — restrained chip for "detected" state, no full-card accent */}
      <div className="grid grid-cols-2 gap-5 mb-6">
        {diagnostics.map((d) => (
          <div
            key={d.label}
            className="border border-border rounded-lg p-6"
          >
            <div className="flex items-center justify-between mb-3">
              <div className="text-[15px] font-semibold">{d.label}</div>
              <div className="inline-flex items-center gap-1.5 text-[11px] uppercase tracking-wider text-muted-foreground">
                <span
                  className="w-1.5 h-1.5 rounded-full"
                  style={{
                    backgroundColor: d.detected
                      ? 'oklch(0.646 0.222 41.116)'
                      : 'var(--muted-foreground)',
                    opacity: d.detected ? 1 : 0.4,
                  }}
                />
                {d.detected ? 'Detected' : 'Not detected'}
              </div>
            </div>
            <div className="flex items-baseline gap-4 mb-2">
              <div className="text-[22px] tabular-nums font-medium">{d.stat}</div>
              {d.p != null && (
                <div className="text-[13px] text-muted-foreground tabular-nums">
                  p = {d.p < 0.001 ? '<.001' : d.p.toFixed(3)}
                </div>
              )}
            </div>
            <div className="text-[12px] text-muted-foreground">{d.hint}</div>
          </div>
        ))}
      </div>

      {/* Judge calibration strip */}
      <div className="grid grid-cols-3 gap-5">
        <div className="border border-border rounded-lg p-5">
          <div className="text-[11px] uppercase tracking-wider text-muted-foreground mb-2">
            Inter-judge agreement
          </div>
          <div className="text-[32px] tabular-nums font-semibold leading-none">
            {agreement != null ? `${(agreement * 100).toFixed(0)}%` : '—'}
          </div>
          <div className="text-[12px] text-muted-foreground mt-2">
            Same winner chosen across judges
          </div>
        </div>
        <div className="border border-border rounded-lg p-5">
          <div className="text-[11px] uppercase tracking-wider text-muted-foreground mb-2">
            {kappaType === 'cohen' ? "Cohen's κ" : "Fleiss' κ"}
          </div>
          <div className="text-[32px] tabular-nums font-semibold leading-none">
            {kappa != null ? kappa.toFixed(2) : '—'}
          </div>
          <div className="text-[12px] text-muted-foreground mt-2 capitalize">{kappaInterp}</div>
        </div>
        <div className="border border-border rounded-lg p-5">
          <div className="text-[11px] uppercase tracking-wider text-muted-foreground mb-2">
            Disagreement questions
          </div>
          <div className="text-[32px] tabular-nums font-semibold leading-none">
            {benchmark.judge_summary?.disagreement_count ?? '—'}
          </div>
          <div className="text-[12px] text-muted-foreground mt-2">
            of {benchmark.questions.length} prompts
          </div>
        </div>
      </div>
    </SlideFrame>
  );
}

// ──────────────────────────────────────────────────────────────────────────────
// Slide 7 — METHODOLOGY & SIGN-OFF
// ──────────────────────────────────────────────────────────────────────────────

function MethodologySlide({
  benchmark,
  dateStr,
}: {
  benchmark: BenchmarkDetail;
  dateStr: string;
}) {
  const judges = [
    ...new Set(benchmark.questions.flatMap((q) => q.judgments?.map((j) => j.judge_name) || [])),
  ];
  const totalModelCost = Object.values(benchmark.performance_metrics || {}).reduce(
    (s, m) => s + (m.estimated_cost || 0),
    0
  );
  const totalJudgeCost = Object.values(benchmark.judge_metrics || {}).reduce(
    (s, m) => s + (m.estimated_cost || 0),
    0
  );

  return (
    <SlideFrame
      slideNumber={7}
      totalSlides={7}
      sectionLabel="Methodology &amp; Sign-off"
      runName={benchmark.name}
      runId={benchmark.id}
      dateStr={dateStr}
    >
      <h2 className="text-[30px] font-semibold tracking-tight mb-6">
        Methodology, scope &amp; sign-off
      </h2>

      <div className="grid grid-cols-12 gap-6 h-[calc(100%-100px)]">
        {/* Scope */}
        <div className="col-span-6 border border-border rounded-lg p-6">
          <div className="text-[11px] uppercase tracking-wider text-muted-foreground mb-4">
            Scope
          </div>
          <dl className="text-[14px] space-y-2">
            <div className="grid grid-cols-[180px_1fr] gap-3">
              <dt className="text-muted-foreground">Prompts</dt>
              <dd className="tabular-nums">{benchmark.questions.length}</dd>
            </div>
            <div className="grid grid-cols-[180px_1fr] gap-3">
              <dt className="text-muted-foreground">Candidate models</dt>
              <dd className="tabular-nums">{benchmark.model_ids.length}</dd>
            </div>
            <div className="grid grid-cols-[180px_1fr] gap-3">
              <dt className="text-muted-foreground">Judges</dt>
              <dd className="tabular-nums">{benchmark.judge_ids.length}</dd>
            </div>
            <div className="grid grid-cols-[180px_1fr] gap-3">
              <dt className="text-muted-foreground">Rubric criteria</dt>
              <dd className="tabular-nums">{benchmark.criteria.length}</dd>
            </div>
            <div className="grid grid-cols-[180px_1fr] gap-3">
              <dt className="text-muted-foreground">Judging mode</dt>
              <dd className="capitalize">{benchmark.judge_mode}</dd>
            </div>
            <div className="grid grid-cols-[180px_1fr] gap-3">
              <dt className="text-muted-foreground">Judgments total</dt>
              <dd className="tabular-nums">
                {benchmark.questions.length * benchmark.judge_ids.length}
              </dd>
            </div>
            <div className="grid grid-cols-[180px_1fr] gap-3">
              <dt className="text-muted-foreground">Total spend</dt>
              <dd className="tabular-nums">
                {formatCost(totalModelCost + totalJudgeCost)}{' '}
                <span className="text-muted-foreground text-[12px]">
                  ({formatCost(totalModelCost)} gen · {formatCost(totalJudgeCost)} judge)
                </span>
              </dd>
            </div>
          </dl>
        </div>

        {/* Criteria */}
        <div className="col-span-6 border border-border rounded-lg p-6">
          <div className="text-[11px] uppercase tracking-wider text-muted-foreground mb-4">
            Rubric criteria
          </div>
          <ul className="space-y-3 text-[14px]">
            {benchmark.criteria.map((c) => (
              <li key={c.name} className="grid grid-cols-[120px_1fr_60px] gap-3">
                <div className="font-medium">{c.name}</div>
                <div className="text-muted-foreground text-[13px] leading-snug">
                  {c.description || <em className="opacity-60">No description</em>}
                </div>
                <div className="text-right tabular-nums text-muted-foreground">
                  ×{c.weight}
                </div>
              </li>
            ))}
          </ul>
        </div>

        {/* Judges */}
        <div className="col-span-6 border border-border rounded-lg p-6">
          <div className="text-[11px] uppercase tracking-wider text-muted-foreground mb-4">
            Judge panel
          </div>
          <ul className="space-y-2 text-[14px]">
            {judges.map((j) => (
              <li key={j} className="flex items-center gap-3">
                <div className="w-1.5 h-1.5 rounded-full bg-muted-foreground/50" />
                {j}
              </li>
            ))}
          </ul>
        </div>

        {/* Sign-off */}
        <div className="col-span-6 border border-border rounded-lg p-6">
          <div className="text-[11px] uppercase tracking-wider text-muted-foreground mb-4">
            Sign-off
          </div>
          <dl className="text-[14px] space-y-2">
            <div className="grid grid-cols-[160px_1fr] gap-3">
              <dt className="text-muted-foreground">Prepared by</dt>
              <dd className="italic text-muted-foreground">[redacted]</dd>
            </div>
            <div className="grid grid-cols-[160px_1fr] gap-3">
              <dt className="text-muted-foreground">Reviewed by</dt>
              <dd className="italic text-muted-foreground">[redacted]</dd>
            </div>
            <div className="grid grid-cols-[160px_1fr] gap-3">
              <dt className="text-muted-foreground">Export date</dt>
              <dd className="tabular-nums">{dateStr}</dd>
            </div>
            <div className="grid grid-cols-[160px_1fr] gap-3">
              <dt className="text-muted-foreground">Source</dt>
              <dd>
                BeLLMark Run #{benchmark.id.toString().padStart(4, '0')} · bellmark.ai
              </dd>
            </div>
            <div className="grid grid-cols-[160px_1fr] gap-3">
              <dt className="text-muted-foreground">Methodology</dt>
              <dd>Blind shuffled-label comparison · Wilson CI · Bootstrap · Wilcoxon · Holm · Cohen&apos;s d</dd>
            </div>
          </dl>
        </div>
      </div>
    </SlideFrame>
  );
}

// ──────────────────────────────────────────────────────────────────────────────
// Router
// ──────────────────────────────────────────────────────────────────────────────

export function MockupSlide() {
  const { slide, runId } = useParams<{ slide: string; runId: string }>();
  const [search] = useSearchParams();
  const themeParam = search.get('theme');

  // Force-apply theme class directly on <html> so Playwright captures the
  // requested mode deterministically, bypassing user prefs / localStorage.
  useEffect(() => {
    if (themeParam === 'dark') {
      document.documentElement.classList.add('dark');
    } else if (themeParam === 'light') {
      document.documentElement.classList.remove('dark');
    }
  }, [themeParam]);

  const id = Number(runId);
  const { data: benchmark } = useQuery<BenchmarkDetail>({
    queryKey: ['benchmark', id],
    queryFn: async () => {
      const res = await benchmarksApi.get(id);
      return res.data;
    },
    enabled: !Number.isNaN(id),
  });
  const { data: statistics } = useQuery<RunStatistics>({
    queryKey: ['run-statistics', id],
    queryFn: () => benchmarksApi.statistics(id),
    enabled: !Number.isNaN(id),
  });
  const { data: biasData } = useQuery<unknown>({
    queryKey: ['run-bias', id],
    queryFn: () => benchmarksApi.bias(id).then((r) => r.data ?? r),
    enabled: !Number.isNaN(id),
  });

  const computed = useMemo(
    () => (benchmark ? computeResultsData(benchmark) : null),
    [benchmark]
  );

  if (!benchmark || !computed) {
    return (
      <div
        className="bg-background text-muted-foreground flex items-center justify-center"
        style={{ width: 1920, height: 1080 }}
      >
        Loading mockup data…
      </div>
    );
  }

  const dateStr = formatDate(benchmark.completed_at || benchmark.created_at);

  switch (slide) {
    case 'cover':
      return (
        <CoverSlide
          benchmark={benchmark}
          computed={computed}
          statistics={statistics}
          dateStr={dateStr}
        />
      );
    case 'executive':
      return (
        <ExecutiveSlide
          benchmark={benchmark}
          computed={computed}
          statistics={statistics}
          dateStr={dateStr}
        />
      );
    case 'leaderboard':
      return (
        <LeaderboardSlide
          benchmark={benchmark}
          computed={computed}
          statistics={statistics}
          dateStr={dateStr}
        />
      );
    case 'criteria':
      return <CriteriaSlide benchmark={benchmark} computed={computed} dateStr={dateStr} />;
    case 'stats-rigor':
      return (
        <StatsRigorSlide benchmark={benchmark} statistics={statistics} dateStr={dateStr} />
      );
    case 'bias':
      return (
        <BiasSlide benchmark={benchmark} biasData={biasData} dateStr={dateStr} />
      );
    case 'methodology':
      return <MethodologySlide benchmark={benchmark} dateStr={dateStr} />;
    default:
      return (
        <div
          className="bg-background text-foreground flex items-center justify-center"
          style={{ width: 1920, height: 1080 }}
        >
          Unknown slide: {slide}
        </div>
      );
  }
}
