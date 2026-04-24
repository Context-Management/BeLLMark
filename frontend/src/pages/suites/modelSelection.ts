import type { ModelPreset } from '../../types/api.js';

function getHostLabel(baseUrl: string): string | null {
  try {
    const host = new URL(baseUrl).hostname;
    if (host === 'localhost' || host === '127.0.0.1') return null;
    return host;
  } catch {
    return null;
  }
}

export function sortSuiteModels(models: readonly ModelPreset[]): ModelPreset[] {
  return [...models].sort((a, b) => {
    const providerCmp = a.provider.localeCompare(b.provider, undefined, { sensitivity: 'base' });
    if (providerCmp !== 0) return providerCmp;

    const nameCmp = a.name.localeCompare(b.name, undefined, { sensitivity: 'base' });
    if (nameCmp !== 0) return nameCmp;

    return a.model_id.localeCompare(b.model_id, undefined, { sensitivity: 'base' });
  });
}

export function filterSuiteModels(models: readonly ModelPreset[], query: string): ModelPreset[] {
  const tokens = query
    .trim()
    .toLowerCase()
    .split(/\s+/)
    .filter(Boolean);

  const sorted = sortSuiteModels(models);
  if (tokens.length === 0) return sorted;

  return sorted.filter((model) => {
    const haystack = [
      model.name,
      model.model_id,
      model.provider,
      model.base_url,
      getHostLabel(model.base_url) ?? '',
    ].join(' ').toLowerCase();
    return tokens.every((token) => haystack.includes(token));
  });
}

export function allocatePromptCounts(total: number, generatorIds: number[]): number[] {
  if (generatorIds.length === 0) return [];
  const base = Math.floor(total / generatorIds.length);
  const remainder = total % generatorIds.length;
  return generatorIds.map((_, index) => base + (index < remainder ? 1 : 0));
}

export function formatSuiteModelLabel(model: Pick<ModelPreset, 'name' | 'provider' | 'model_id' | 'base_url'>): string {
  const host = getHostLabel(model.base_url);
  return host ? `${model.name} (${host})` : model.name;
}

export function formatSuiteModelMeta(model: Pick<ModelPreset, 'provider' | 'model_id' | 'base_url'>): string {
  const host = getHostLabel(model.base_url);
  return [model.provider, model.model_id, host].filter(Boolean).join(' • ');
}
