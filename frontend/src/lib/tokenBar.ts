type ComputeTokenBarParams = {
  totalTokens: number;
  maxTokens: number;
};

export function computeTokenBar({ totalTokens, maxTokens }: ComputeTokenBarParams): { fraction: number } {
  if (!Number.isFinite(totalTokens) || !Number.isFinite(maxTokens)) {
    return { fraction: 0 };
  }
  if (maxTokens <= 0) return { fraction: 0 };

  const clamped = Math.min(Math.max(totalTokens, 0), maxTokens);
  return { fraction: clamped / maxTokens };
}

