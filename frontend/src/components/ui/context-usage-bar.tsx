import { cn } from '@/lib/utils';

interface ContextUsageBarProps {
  used: number;  // Tokens used
  limit?: number;  // Max context limit (if known)
  className?: string;
}

function formatTokens(count: number): string {
  if (count < 1000) return count.toString();
  if (count < 1000000) return `${(count / 1000).toFixed(1)}K`;
  return `${(count / 1000000).toFixed(2)}M`;
}

export function ContextUsageBar({
  used,
  limit,
  className
}: ContextUsageBarProps) {
  const percentage = limit ? Math.min((used / limit) * 100, 100) : 0;
  const isWarning = percentage > 75;
  const isDanger = percentage > 90;

  return (
    <div className={cn("space-y-1", className)}>
      <div className="flex justify-between text-xs text-muted-foreground">
        <span>Context tokens</span>
        <span>
          {formatTokens(used)}
          {limit && ` / ${formatTokens(limit)}`}
        </span>
      </div>
      {limit && (
        <div className="h-2 bg-secondary rounded-full overflow-hidden">
          <div
            className={cn(
              "h-full transition-all duration-300",
              isDanger ? "bg-red-500" :
              isWarning ? "bg-yellow-500" :
              "bg-green-500"
            )}
            style={{ width: `${percentage}%` }}
          />
        </div>
      )}
    </div>
  );
}

// Compact version for inline use
export function ContextUsageBadge({
  used,
  limit,
  className
}: ContextUsageBarProps) {
  const percentage = limit ? (used / limit) * 100 : 0;
  const isWarning = percentage > 75;
  const isDanger = percentage > 90;

  return (
    <span
      className={cn(
        "inline-flex items-center px-2 py-0.5 rounded text-xs font-medium",
        isDanger ? "bg-red-100 text-red-800 dark:bg-red-900 dark:text-red-200" :
        isWarning ? "bg-yellow-100 text-yellow-800 dark:bg-yellow-900 dark:text-yellow-200" :
        "bg-green-100 text-green-800 dark:bg-green-900 dark:text-green-200",
        className
      )}
    >
      {formatTokens(used)}
      {limit && ` / ${formatTokens(limit)}`} tokens
    </span>
  );
}
