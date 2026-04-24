import * as React from "react"

export interface ProgressProps extends React.HTMLAttributes<HTMLDivElement> {
  value?: number
}

const Progress = React.forwardRef<HTMLDivElement, ProgressProps>(
  ({ className = "", value = 0, ...props }, ref) => {
    return (
      <div
        ref={ref}
        className={`relative h-2 w-full overflow-hidden rounded-full bg-stone-200 dark:bg-gray-700 ${className}`}
        {...props}
      >
        <div
          className="h-full bg-blue-500 transition-all"
          style={{ width: `${Math.min(100, Math.max(0, value))}%` }}
        />
      </div>
    )
  }
)
Progress.displayName = "Progress"

export { Progress }
