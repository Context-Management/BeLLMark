export type NewRunSelectionFilter = 'all' | 'selected' | 'unselected';
export type NewRunVisionFilter = 'all' | 'vision' | 'non-vision';
export type NewRunReasoningFilter = 'all' | 'reasoning' | 'standard';
export type NewRunSortBy = 'provider' | 'name' | 'reasoning' | 'frequency';

export type NewRunFilterModel = {
  id: number;
  name: string;
  model_id: string;
  provider: string;
  base_url: string;
  is_reasoning?: boolean;
  reasoning_level?: string | null;
  supports_vision?: boolean | null;
  quantization?: string | null;
  model_format?: string | null;
  model_source?: string | null;
};

export function filterAndSortNewRunModels(
  models: NewRunFilterModel[],
  options: {
    searchTerm: string;
    providerFilter: string;
    reasoningFilter: NewRunReasoningFilter;
    selectionFilter: NewRunSelectionFilter;
    visionFilter: NewRunVisionFilter;
    sortBy: NewRunSortBy;
    selectedModelIds: Set<number>;
    usageCounts?: Map<number, number>;
  },
): NewRunFilterModel[] {
  const {
    searchTerm,
    providerFilter,
    reasoningFilter,
    selectionFilter,
    visionFilter,
    sortBy,
    selectedModelIds,
    usageCounts,
  } = options;

  let result = [...models];

  if (searchTerm) {
    const search = searchTerm.toLowerCase();
    result = result.filter((m) =>
      m.name.toLowerCase().includes(search) ||
      m.model_id.toLowerCase().includes(search) ||
      m.provider.toLowerCase().includes(search),
    );
  }

  if (providerFilter !== 'all') {
    result = result.filter((m) => m.provider === providerFilter);
  }

  if (reasoningFilter === 'reasoning') {
    result = result.filter((m) => m.is_reasoning);
  } else if (reasoningFilter === 'standard') {
    result = result.filter((m) => !m.is_reasoning);
  }

  if (selectionFilter === 'selected') {
    result = result.filter((m) => selectedModelIds.has(m.id));
  } else if (selectionFilter === 'unselected') {
    result = result.filter((m) => !selectedModelIds.has(m.id));
  }

  if (visionFilter === 'vision') {
    result = result.filter((m) => m.supports_vision === true);
  } else if (visionFilter === 'non-vision') {
    result = result.filter((m) => m.supports_vision !== true);
  }

  result.sort((a, b) => {
    switch (sortBy) {
      case 'name':
        return a.name.localeCompare(b.name);
      case 'provider':
        if (a.provider !== b.provider) {
          return a.provider.localeCompare(b.provider);
        }
        return a.name.localeCompare(b.name);
      case 'reasoning':
        if (a.is_reasoning !== b.is_reasoning) {
          return a.is_reasoning ? -1 : 1;
        }
        return a.name.localeCompare(b.name);
      case 'frequency': {
        const aCount = usageCounts?.get(a.id) ?? 0;
        const bCount = usageCounts?.get(b.id) ?? 0;
        if (aCount !== bCount) return bCount - aCount;
        const provCmp = a.provider.localeCompare(b.provider);
        if (provCmp !== 0) return provCmp;
        return a.name.localeCompare(b.name);
      }
      default:
        return 0;
    }
  });

  return result;
}
