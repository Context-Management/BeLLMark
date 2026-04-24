import { computeTokenBar } from "@/lib/tokenBar"
import { cn } from "@/lib/utils"

type TokenBarProps = {
  totalTokens: number
  maxTokens: number
  rawChars?: number | null
  answerChars?: number | null
  className?: string
}

export function TokenBar({
  totalTokens,
  maxTokens,
  rawChars,
  answerChars,
  className
}: TokenBarProps) {
  const { fraction } = computeTokenBar({ totalTokens, maxTokens })
  // Cap bar at 65% to leave room for total label + latency columns
  const maxBarPct = 65
  const widthPct = Math.round(fraction * maxBarPct)

  // Calculate thinking vs answer token breakdown
  // Only treat as "thinking" if estimated thinking tokens >= 50 AND >= 5% of total
  const rawHasThinking = rawChars && answerChars && rawChars > answerChars
  const rawAnswerRatio = rawHasThinking ? answerChars / rawChars : 1
  const rawThinkingTokens = rawHasThinking ? totalTokens - Math.round(totalTokens * rawAnswerRatio) : 0
  const hasThinkingData = rawHasThinking && rawThinkingTokens >= 50 && rawThinkingTokens / totalTokens >= 0.05
  const answerRatio = hasThinkingData ? rawAnswerRatio : 1
  const answerTokens = Math.round(totalTokens * answerRatio)
  const thinkingTokens = totalTokens - answerTokens

  // For segmented bar: answer portion relative to total width
  const answerWidthPct = hasThinkingData ? Math.round(answerRatio * widthPct) : widthPct
  const thinkingWidthPct = hasThinkingData ? widthPct - answerWidthPct : 0

  // Only show labels inside segments that are wide enough to fit the text
  const minLabelPct = 12
  const showAnswerLabel = answerWidthPct >= minLabelPct
  const showThinkingLabel = thinkingWidthPct >= minLabelPct
  const showSingleBarLabel = widthPct >= minLabelPct

  return (
    <div className={cn("w-full", className)}>
      {/* Bar container */}
      <div className="relative h-6 w-full overflow-visible rounded bg-stone-100 dark:bg-gray-700/30">
        {hasThinkingData ? (
          <>
            {/* Answer segment (blue) */}
            <div
              className="absolute inset-y-0 left-0 bg-blue-500/70 rounded-l overflow-hidden flex items-center"
              style={{ width: `${answerWidthPct}%` }}
              title={`Answer: ${answerTokens.toLocaleString()} tokens`}
            >
              {showAnswerLabel && (
                <span className="absolute right-1 text-xs font-medium text-white tabular-nums drop-shadow-md">
                  {answerTokens.toLocaleString()}
                </span>
              )}
            </div>

            {/* Thinking segment (purple) */}
            {thinkingWidthPct > 0 && (
              <div
                className="absolute inset-y-0 bg-purple-500/70 overflow-hidden flex items-center"
                style={{
                  left: `${answerWidthPct}%`,
                  width: `${thinkingWidthPct}%`,
                  borderTopRightRadius: '0.25rem',
                  borderBottomRightRadius: '0.25rem'
                }}
                title={`Thinking: ${thinkingTokens.toLocaleString()} tokens`}
              >
                {showThinkingLabel && (
                  <span className="absolute right-1 text-xs font-medium text-white tabular-nums drop-shadow-md">
                    {thinkingTokens.toLocaleString()}
                  </span>
                )}
              </div>
            )}

            {/* Total outside */}
            <span
              className="absolute top-1/2 -translate-y-1/2 text-sm font-semibold text-slate-700 dark:text-gray-300 tabular-nums whitespace-nowrap"
              style={{ left: `calc(${widthPct}% + 8px)` }}
            >
              = {totalTokens.toLocaleString()}
            </span>
          </>
        ) : (
          <>
            {/* Single bar (no thinking data) */}
            <div
              className="absolute inset-y-0 left-0 bg-blue-500/70 rounded overflow-hidden flex items-center justify-end"
              style={{ width: `${widthPct}%` }}
              title={`${totalTokens.toLocaleString()} tokens`}
            >
              {showSingleBarLabel && (
                <span className="pr-2 text-sm font-semibold text-white tabular-nums drop-shadow-md">
                  {totalTokens.toLocaleString()}
                </span>
              )}
            </div>
            {!showSingleBarLabel && (
              <span
                className="absolute top-1/2 -translate-y-1/2 text-sm font-semibold text-slate-700 dark:text-gray-300 tabular-nums whitespace-nowrap"
                style={{ left: `calc(${widthPct}% + 8px)` }}
              >
                {totalTokens.toLocaleString()}
              </span>
            )}
          </>
        )}
      </div>

      {/* Legend below - only show when we have thinking data */}
      {hasThinkingData && (
        <div className="flex gap-4 mt-1 text-[10px] text-slate-400 dark:text-gray-500">
          <div className="flex items-center gap-1">
            <div className="w-2 h-2 rounded-sm bg-blue-500/70" />
            <span>answer</span>
          </div>
          <div className="flex items-center gap-1">
            <div className="w-2 h-2 rounded-sm bg-purple-500/70" />
            <span>thinking</span>
          </div>
        </div>
      )}
    </div>
  )
}
