/**
 * Statistical utilities for benchmark result analysis.
 */

/**
 * Wilson score confidence interval for a binomial proportion.
 * @param successes Number of wins
 * @param total Total comparisons
 * @param z Z-score (1.96 = 95% CI, 1.645 = 90% CI)
 * @returns [lower, upper] bounds as floats in [0, 1]
 */
export function wilsonCI(successes: number, total: number, z = 1.96): [number, number] {
  if (total === 0) {
    return [0.0, 0.0];
  }

  const p = Math.min(Math.max(successes / total, 0), 1);
  const denominator = 1 + (z * z) / total;
  const centre = p + (z * z) / (2 * total);
  const spread = z * Math.sqrt((p * (1 - p) + (z * z) / (4 * total)) / total);

  const lower = Math.max(0.0, (centre - spread) / denominator);
  const upper = Math.min(1.0, (centre + spread) / denominator);
  return [Math.round(lower * 10000) / 10000, Math.round(upper * 10000) / 10000];
}

/**
 * Format margin of error as '±X.X%' string for UI display.
 * @param successes Number of wins
 * @param total Total comparisons
 * @returns Formatted string like '±12.3%'
 */
export function marginOfErrorDisplay(successes: number, total: number): string {
  if (total === 0) {
    return '±0.0%';
  }
  const [lower, upper] = wilsonCI(successes, total);
  const p = successes / total;
  const margin = Math.max(upper - p, p - lower);
  return `±${(margin * 100).toFixed(1)}%`;
}
