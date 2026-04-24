/**
 * Shared color utilities for 0-10 score scale visualization
 *
 * Color distribution:
 * 10 = green, 8 = lime, 6 = yellow, 5 = orange, 4 = red-orange, 3 = red, 1 = magenta, 0 = purple
 */

/**
 * Get HSL hue value for a score (0-10 scale)
 * Uses piecewise linear interpolation for better visual distinction
 */
export function getScoreHue(score: number): number {
  const s = Math.max(0, Math.min(10, score));

  if (s >= 8) {
    // 8-10: Lime (90) → Green (120)
    return 90 + ((s - 8) / 2) * 30;
  } else if (s >= 6) {
    // 6-8: Yellow (60) → Lime (90)
    return 60 + ((s - 6) / 2) * 30;
  } else if (s >= 5) {
    // 5-6: Orange (35) → Yellow (60)
    return 35 + ((s - 5) / 1) * 25;
  } else if (s >= 4) {
    // 4-5: Red-Orange (15) → Orange (35)
    return 15 + ((s - 4) / 1) * 20;
  } else if (s >= 3) {
    // 3-4: Red (0) → Red-Orange (15)
    return 0 + ((s - 3) / 1) * 15;
  } else if (s >= 1) {
    // 1-3: Magenta (320) → Red (360/0)
    return 320 + ((s - 1) / 2) * 40;
  } else {
    // 0-1: Purple (280) → Magenta (320)
    return 280 + (s / 1) * 40;
  }
}

/**
 * Get HSL color string for text/foreground elements
 * @param dark - true for dark backgrounds (lighter text), false for light backgrounds (darker text)
 */
export function getScoreColor(score: number, dark = true): string {
  const hue = getScoreHue(score);
  const s = Math.max(0, Math.min(10, score));
  if (dark) {
    const saturation = 75 + (s / 10) * 10; // 75-85%
    const lightness = 45 + (s / 10) * 10;  // 45-55%
    return `hsl(${hue}, ${saturation}%, ${lightness}%)`;
  } else {
    const saturation = 80 + (s / 10) * 10; // 80-90%
    const lightness = 30 + (s / 10) * 10;  // 30-40%
    return `hsl(${hue}, ${saturation}%, ${lightness}%)`;
  }
}

/**
 * Get HSLA color string for background elements (semi-transparent)
 * @param dark - true for dark backgrounds, false for light backgrounds
 */
export function getScoreBgColor(score: number, dark = true): string {
  const hue = getScoreHue(score);
  if (dark) {
    return `hsla(${hue}, 70%, 30%, 0.5)`;
  } else {
    return `hsla(${hue}, 60%, 55%, 0.15)`;
  }
}
