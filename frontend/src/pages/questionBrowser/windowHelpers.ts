export const WINDOW_SIZE = 4;

export function getVisibleModelIds(modelOrder: number[], windowStart: number): number[] {
  return modelOrder.slice(windowStart, windowStart + WINDOW_SIZE);
}

export function moveModel(
  modelOrder: number[],
  modelId: number,
  direction: -1 | 1,
  windowStart: number,
): { newOrder: number[]; newWindowStart: number } {
  const currentIndex = modelOrder.indexOf(modelId);
  if (currentIndex < 0) return { newOrder: modelOrder, newWindowStart: windowStart };
  const targetIndex = currentIndex + direction;
  if (targetIndex < 0 || targetIndex >= modelOrder.length) {
    return { newOrder: modelOrder, newWindowStart: windowStart };
  }

  const newOrder = [...modelOrder];
  [newOrder[currentIndex], newOrder[targetIndex]] = [newOrder[targetIndex], newOrder[currentIndex]];

  const visualSlot = currentIndex - windowStart;
  const rawWindowStart = targetIndex - visualSlot;
  const maxWindowStart = Math.max(0, newOrder.length - WINDOW_SIZE);
  const newWindowStart = Math.min(maxWindowStart, Math.max(0, rawWindowStart));

  return { newOrder, newWindowStart };
}

export function buildWindowPersistenceKey(sourceRunId: number | null, modelIds: number[]): string {
  return `${sourceRunId ?? ''}|${[...modelIds].sort((a, b) => a - b).join(',')}`;
}

export function shouldShowWindowControls(totalModels: number): boolean {
  return totalModels > WINDOW_SIZE;
}
